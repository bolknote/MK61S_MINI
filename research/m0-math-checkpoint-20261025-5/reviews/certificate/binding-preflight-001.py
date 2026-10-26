"""Independent frozen-input/source/rebuild binding; no producer execution."""
import ast,difflib,hashlib,json,struct,subprocess,sys
from pathlib import Path
sys.dont_write_bytecode=True
R=Path('/Users/bolk/Projects/MK61S_MINI');O=Path(__file__).resolve().parent
W=R/'.build/m0-pow-reciprocal-certificate-20261025';P=R/'.build/m0-pow-reciprocal-inline-20261025';U=R/'.build/m0-ddiv-remainder-certificate-r2-20261025'
sys.path.insert(0,str(R/'tests'));from check_stm32_vectors import ElfImage
def ref(p):
 p=Path(p);b=p.read_bytes();return dict(path=str(p),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def pin(p,h):v=ref(p);assert v['sha256']==h,v;return v
def save(n,d):
 with (O/n).open('x')as f:json.dump(d,f,indent=2);f.write('\n')
 return ref(O/n)
def mem(e,a,n):
 s=next(s for s in e.sections if s[1]!=8 and s[3]<=a and a+n<=s[3]+s[5]);return e.bytes_at(s)[a-s[3]:a-s[3]+n]
def alloc(e):return {n:(s[1],s[2],s[3],s[5],None if s[1]==8 else e.bytes_at(s))for n,s in e.named_sections.items()if s[2]&2 and s[5]}
refs=dict(FROZEN=pin(W/'FROZEN.json','99110367092d4c7397967d9f3b06fb282843431bd7af5b71ea1038a77b4ac329'),
 result=pin(W/'result.json','50b9e0c53b15ebe2a2851a50ac1bcd533558880c02314ce620de5eb55c756a4f'),
 HANDOFF=pin(W/'HANDOFF.md','5729146db8d8cedd47aa540b11728bc532d5ba706696c01211a4beaa29068607'),
 ELF=pin(W/'candidate.elf','aac32d20ff3c7c0f28d77b091e012fb997ce8dce1ec009f259803a8690e36be8'),
 parent_FROZEN=pin(P/'FROZEN.json','0be351d573878a48f13f5d41edd2812a23ab269556b929db9aa8324e6a0bf219'),
 parent_independent=pin(R/'.build/m0-pow-reciprocal-inline-independent-20261025/FINAL-REVIEW.json','4d457dfb509ddbdd7cd4b067bc9f6e413d058c7fd58db3810fbad8a5acc534a0'),
 unit_FROZEN=pin(U/'FROZEN.json','904e63f0ecb510f8db9953ce686510167d598e1a4905a04ce31f2fb3d3ec3cf3'),
 corrigendum=pin(R/'.build/m0-pow-reciprocal-certificate-report-corrigendum-20261025.json','5cd5994f20429814820d5702b8c84782848733e8ee5f95aa17b6a070719a2127'))
local=[];external=[];unit=[]
for meta,base,items in [(W/'FROZEN.json',W,local),(W/'source-lineage-pins.json',R,external),(U/'FROZEN.json',U,unit)]:
 for n,d in json.loads(meta.read_text())['files'].items():
  assert not n.startswith('/')and'..'not in Path(n).parts and'.git'not in Path(n).parts
  v=ref(base/n);assert [v['bytes'],v['sha256']]==[d['bytes'],d['sha256']],v;items.append(v)
assert len(local)==80 and len(external)==2402
for label in ['control','candidate']:
 for n in ['native_eabi_m0_rp2040.S','native_eabi_m0_pow_root_prefix.inc']:assert(W/label/n).read_bytes()==(P/'candidate'/n).read_bytes()
 assert (W/(label+'-seed17.S')).read_bytes()==(P/'candidate-seed17.S').read_bytes()
assert (W/'inline-seed.inc').read_bytes()==(P/'inline-seed.inc').read_bytes()
assert (W/'inline-seed-table.inc').read_bytes()==(P/'inline-seed-table.inc').read_bytes()
assert (W/'control.ld').read_bytes()==(P/'candidate.ld').read_bytes()==(W/'candidate.ld').read_bytes()
def strip_markers(s):
 return '\n'.join(l for l in s.splitlines()if not any(t in l for t in ['_y_low_shift','_certificate_begin','_certificate_up','_certificate_down']))+'\n'
assert strip_markers((W/'control-ddiv.S').read_text())==(P/'candidate-ddiv.S').read_text()
assert strip_markers((W/'software.S').read_text())==(P/'candidate-software.S').read_text()
patch=''
for n,cn,kind in [('candidate-ddiv.S','control-ddiv.S','hardware'),('candidate-software.S','software.S','software')]:
 # The published patch deliberately compares the pre-marker parent text.
 patch+=''.join(difflib.unified_diff((P/('candidate-ddiv.S'if kind=='hardware'else'candidate-software.S')).read_text().splitlines(True),(W/n).read_text().splitlines(True),fromfile='parent/'+kind+'.S',tofile='candidate/'+kind+'.S'))
assert patch==(W/'remainder-certificate.patch').read_text()
assert (W/'remainder-certificate.inc').read_bytes()==(U/'remainder-certificate.inc').read_bytes()
for file in [W/'candidate-ddiv.S',W/'candidate-software.S',U/'candidate.S']:
 s=file.read_text();assert s.count(' remainder_certificate ')==1 and '#include "remainder-certificate.inc"'in s
old=ElfImage(P/'candidate.elf');images={n:ElfImage(W/(n+'.elf'))for n in ['control','candidate']}
assert alloc(images['control'])==alloc(old)
assert [n for n in alloc(old)if alloc(old)[n]!=alloc(images['candidate'])[n]]==['.ddiv']
assert images['candidate'].symbols['mk61_m0_reciprocal1']==old.symbols['mk61_m0_reciprocal1']
assert images['candidate'].named_sections['.ddiv'][5]==1108 and old.named_sections['.ddiv'][5]==1072
table=old.bytes_at(old.named_sections['.ddiv'])[-256:]
assert images['candidate'].bytes_at(images['candidate'].named_sections['.ddiv'])[-256:]==table
assert all(x==(1<<32)//(65536+512*i+256)for i,x in enumerate(struct.unpack('<128H',table)))
s=(R/'.build/m0-exp-cached-product-independent-20261024/bind_rebuild.py').read_text();fn=next(n for n in ast.parse(s).body if isinstance(n,ast.FunctionDef)and n.name=='relocs');exec(compile(ast.Module(body=[fn],type_ignores=[]),'<accepted-relocs>','exec'),globals())
for context in ['RP','generic_M0','M4_soft','M4_hard']:
 p=ElfImage(P/(context+'-candidate.o'))
 for label in ['control','candidate']:
  n=ElfImage(W/(context+'-'+label+'.o'));assert alloc(p)==alloc(n)
  for sec in alloc(p):assert relocs(p).get(sec)==relocs(n).get(sec)
 if context!='RP':
  for name in ['candidate-ddiv','candidate-software']:assert not alloc(ElfImage(W/(context+'-'+name+'-disabled.o')))
build=json.loads((W/'build.json').read_text());ub=json.loads((U/'build.json').read_text());d=O/'rebuild';d.mkdir()
names=['RP-control.o','RP-candidate.o','control-ddiv.o','candidate-ddiv.o','software.o','candidate-software.o','control.elf','candidate.elf']
mapping={str(W/n):str(d/n)for n in names};mapping.update({str(U/n):str(d/('unit-'+n))for n in ['control.o','candidate.o','control.elf','candidate.elf']});commands=[];outputs=[]
for base,commands_in,nlist,prefix in [(W,build['commands'],names,''),(U,ub['commands'],['control.o','candidate.o','control.elf','candidate.elf'],'unit-')]:
 for name in nlist:
  argv=next(c for c in commands_in if Path(c[c.index('-o')+1]).name==name);cmd=[mapping.get(x,x)for x in argv]
  assert not any(x in cmd for x in ['-MD','-MMD','-MF','-save-temps'])
  if '-g'in cmd:cmd+=['-fdebug-prefix-map='+str(O)+'='+str(base)]
  p=subprocess.run(cmd,cwd=O,capture_output=True);(d/(prefix+name+'.stdout')).write_bytes(p.stdout);(d/(prefix+name+'.stderr')).write_bytes(p.stderr)
  assert p.returncode==0,p.stderr.decode();assert (d/(prefix+name)).read_bytes()==(base/name).read_bytes(),name
  commands.append(dict(argv=cmd,returncode=p.returncode));outputs.append(ref(d/(prefix+name)))
tc=Path(build['commands'][0][0]).parent
for name in ['control.elf','candidate.elf','unit-control.elf','unit-candidate.elf']:(O/(name+'.actual.dis')).write_bytes(subprocess.check_output([str(tc/'arm-none-eabi-objdump'),'-d',str(d/name)]))
out=dict(status='PASS_FROZEN_SOURCE_AND_TWELVE_BYTEEXACT_WHOLE_REBUILDS',refs=refs,local=local,external=external,shared_unit=unit,
 local80_external2402=True,unit_file_count=len(unit),actual_parent_inline=True,missing_at_seal_parent_review_or_ROOT_not_rewritten=True,
 exact_patch_and_control_marker_only_delta=True,identical_macro_source_in_unit_and_both_real_paths=True,
 root_source_call_and_linked_call_bytes_addresses_unchanged=True,only_private_ddiv_allocation_changed=True,old1072_new1108_delta36=True,
 same_inline_seed_and256B_table=True,no_new_tablevalues_RAM_libgcc=True,default_M0_M4_selected_and6_disabled_unchanged=True,
 own12_rebuilds_byte_exact=outputs,commands=commands,original_producer_commands_not_executed_inplace=True,
 author_zero_call_preflights=[ref(W/n)for n in ['HOST-PREFLIGHT-001.json','build-preflight-001.log','tally-preflight-001.log']],
 ARM_calls=0,MPFR_inputs=0,device_IO=0,Git=0,canonical=0,network=0,integration_GO=False)
print(json.dumps(save('binding.json',out)),flush=True)
