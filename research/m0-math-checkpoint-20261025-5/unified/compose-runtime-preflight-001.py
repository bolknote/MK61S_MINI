"""Compose complete runtime sources and compile them with real symbol edges."""
from pathlib import Path
import hashlib,importlib.util,json,shlex,shutil,subprocess,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1];S=W/'source';CODE=S/'code'
BASE=ROOT/'.build/m0-asin-scaled-bound-v164-20261023';B=ROOT/'.build/m0-pow-reciprocal-bound3-20261025';BOUND=ROOT/'.build/m0-pow-boundary128-20261025'
assert not(W/'runtime-composition.json').exists()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
provenance=json.loads((W/'composition.json').read_bytes())['source_files'].copy()
for p in sorted((BASE/'source/code').iterdir()):
 if p.is_file()and(p.name.startswith('native_eabi_m0')or p.suffix in ['.h','.hpp']or p.name=='compact_math.cpp'):
  dest=CODE/p.name
  if not dest.exists():dest.write_bytes(p.read_bytes());provenance[p.name]=dict(source=str(p.relative_to(ROOT)),sha256=sha(p))
third=BASE/'source/third_party/core_math';dest=S/'third_party/core_math'
if not dest.exists():shutil.copytree(third,dest)
third_pins={str(p.relative_to(dest)):sha(p)for p in dest.rglob('*')if p.is_file()}
def copy(p,name):
 (CODE/name).write_bytes(p.read_bytes());provenance[name]=dict(source=str(p.relative_to(ROOT)),sha256=sha(p))
for name in ['native_eabi_m0_rp2040.S','native_eabi_m0_pow_root_prefix.inc']:copy(B/'candidate'/name,name)
for source,name in [('candidate-ddiv.S','native_eabi_m0_reciprocal1.S'),('candidate-software.S','native_eabi_m0_reciprocal1_sw.S'),('candidate-inline-seed.inc','candidate-inline-seed.inc'),('candidate-remainder-certificate.inc','candidate-remainder-certificate.inc'),('inline-seed-table.inc','inline-seed-table.inc')]:copy(B/source,name)
copy(BOUND/'boundary.cpp','native_eabi_m0_boundary128.cpp')
alias='''// Exact boundary helper is linked to the real compare function in this TU.
.global mk61_m0_boundary128_compare
.thumb_set mk61_m0_boundary128_compare,_ZL15root128_compareRK13PowInteger128S1_
'''
p=CODE/'native_eabi_m0_rp2040.S';t=p.read_text();needle='#include "native_eabi_m0_pow_root_prefix.inc"';assert t.count(needle)==1
p.write_text(t.replace(needle,needle+'\n'+alias));provenance[p.name]['only_source_change']='Add a real global Thumb alias for the existing local boundary comparator.'
license_dest=S/'third_party/rp2040-softfloat';license_dest.mkdir(parents=True,exist_ok=True);(license_dest/'LICENSE.TXT').write_bytes((B/'LICENSE.TXT').read_bytes())
spec=importlib.util.spec_from_file_location('unified_fingerprint',ROOT/'research/m0-math-checkpoint-20261025-4/verify.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
commands=[];outputs={}
# Recompile the previously composed core units after closing local include edges.
for c0 in json.loads((W/'composition.json').read_bytes())['commands']:
 c=list(c0);subprocess.run(c,cwd=W,check=True);commands.append(c)
 out=Path(c[c.index('-o')+1]);outputs[out.name]=dict(sha256=sha(out))
 assert sha(out)==json.loads((W/'composition.json').read_bytes())['outputs'][out.name]['sha256'],out
entries=json.loads((BASE/'build/compile_commands.json').read_bytes())
for name in ['native_eabi_m0_rp2040.S','native_eabi_m0_cr.cpp','compact_math.cpp']:
 entry=next(e for e in entries if e['file'].endswith('/code/'+name));c=shlex.split(entry['command'])
 c[c.index(entry['file'])]=str(CODE/name);out=W/('RP-unified-'+name+'.o');c[c.index('-o')+1]=str(out)
 subprocess.run(c,cwd=W,check=True);commands.append(c);outputs[out.name]=dict(sha256=sha(out))
for oldname,newname in [('candidate-ddiv.S','native_eabi_m0_reciprocal1.S'),('candidate-software.S','native_eabi_m0_reciprocal1_sw.S')]:
 c0=next(c for c in json.loads((B/'build.json').read_bytes())['commands']if'-c'in c and Path(c[c.index('-c')+1]).name==oldname)
 c=list(c0);c[c.index('-c')+1]=str(CODE/newname);out=W/('RP-unified-'+newname+'.o');c[c.index('-o')+1]=str(out)
 subprocess.run(c,cwd=W,check=True);commands.append(c);outputs[out.name]=dict(sha256=sha(out),qualified_object=str((B/('candidate-ddiv.o'if oldname=='candidate-ddiv.S'else'candidate-software.o')).relative_to(ROOT)))
 assert module.image_fingerprint(out.read_bytes())==module.image_fingerprint((ROOT/outputs[out.name]['qualified_object']).read_bytes())
c0=next(c for c in json.loads((BOUND/'build.json').read_bytes())['commands']if'-c'in c and Path(c[c.index('-c')+1]).name=='boundary.cpp')
c=list(c0);c[c.index('-c')+1]=str(CODE/'native_eabi_m0_boundary128.cpp');out=W/'RP-unified-boundary.o';c[c.index('-o')+1]=str(out)
subprocess.run(c,cwd=W,check=True);commands.append(c);outputs[out.name]=dict(sha256=sha(out),qualified_object=str((BOUND/'boundary.o').relative_to(ROOT)))
assert module.image_fingerprint(out.read_bytes())==module.image_fingerprint((BOUND/'boundary.o').read_bytes())
tc=Path(commands[0][0]).parent
runtime_objects=[W/'RP-merged-cpp.o',W/'RP-merged-asm.o']+[W/n for n in outputs if n.startswith('RP-unified-')]
defined=set();undefined=set();definitions={}
for p in runtime_objects:
 for line in subprocess.check_output([str(tc/'arm-none-eabi-nm'),'-g',str(p)],text=True).splitlines():
  words=line.split()
  if len(words)==2 and words[0]=='U':undefined.add(words[1])
  elif len(words)>=3:
   name,kind=words[-1],words[-2];defined.add(name);definitions.setdefault(name,[]).append([p.name,kind])
duplicates={name:values for name,values in definitions.items()if len([v for v in values if v[1].isupper()and v[1]not in ['W','V']])>1}
remaining=sorted(undefined-defined)
result=dict(status='COMPLETE_MATH_SOURCE_UNITS_COMPILED_NOT_LINKED',source_files=provenance,core_math_files_sha256=third_pins,outputs=outputs,commands=commands,
 runtime_objects=list(map(str,runtime_objects)),undefined_remaining=remaining,strong_duplicate_definitions=duplicates,
 exact_boundary_compare_real_Thumb_alias=True,private_reciprocal_objects_match_qualified_bound3=True,boundary_object_matches_qualified_source=True,
 earlier_core_CPP_ASM_whole_objects_byte_exact_after_local_header_copy=True,
 final_ELF_linked=False,actual_linked_R12_guard_passed=False,loader_layout_guard_passed=False,
 actual_ARM_or_MPFR_calls=0,canonical_M4_Git_device_USB_Flash_changed=False,integration_GO=False,goal_complete=False)
(W/'runtime-composition.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items()if k not in ['source_files','core_math_files_sha256','outputs','commands','runtime_objects']},indent=2))
