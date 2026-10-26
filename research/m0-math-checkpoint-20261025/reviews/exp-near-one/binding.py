"""Read frozen provenance and rebuild only private CPU objects in this directory."""
import ast
import difflib
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
sys.dont_write_bytecode=True
R=Path('/Users/bolk/Projects/MK61S_MINI');O=Path(__file__).resolve().parent
W=R/'.build/m0-exp-near-one-20261024';P=R/'.build/m0-exp-directed-product-20261024'
sys.path.insert(0,str(R/'tests'))
from check_stm32_vectors import ElfImage
def ref(p):
 p=Path(p);data=p.read_bytes();return dict(path=str(p),bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
def check(p,h):
 v=ref(p);assert v['sha256']==h,v;return v
def save(n,v):
 with (O/n).open('x') as f:json.dump(v,f,indent=2);f.write('\n')
 return ref(O/n)
def allocated(e):return {n:e.bytes_at(s)for n,s in e.named_sections.items()if s[2]&2 and s[1]!=8 and s[5]}
def bss(e):return {n:(s[5],s[8])for n,s in e.named_sections.items()if s[2]&2 and s[1]==8 and s[5]}
def code(im,name):
 a=im.symbols[name]&~1
 s=next(s for s in im.sections if s[1]!=8 and s[3]<=a and a+im.sizes[name]<=s[3]+s[5])
 return im.bytes_at(s)[a-s[3]:a-s[3]+im.sizes[name]]
refs={
 'FROZEN':check(W/'FROZEN.json','1e5a757a3116d4803330b0e554ad1dffbe0aea838c7a75126460f79dcf4d5de0'),
 'result':check(W/'result.json','fe222980e2687df8ff95d21b73123c5c03b6b2b83624080f0eb44d89f4b9b701'),
 'HANDOFF':check(W/'HANDOFF.md','a2c8a2753933c885e194e2884caa511e05c14978d5ccca50ee4fc5b84aeb6089'),
 'ELF':check(W/'candidate.elf','e6f2f7e0c55b7d7f2547badb00eacef444a1575eb59bdae7d530eec0ea340fcc'),
 'parent_review':check(R/'.build/m0-exp-directed-product-independent-20261024/FINAL-REVIEW.json','0d6073f3534d2abb71ad3348096bca930d2513e3813b06dbcfb8911ca485839b'),
 'parent_ROOT':check(R/'.build/m0-exp-directed-product-root-acceptance-20261024-001/RECEIPT.json','7ec53f3c616b08413d0e88dae6ce65a7d7b4b8d5adb41737ae802e10475bc573')}
pins=[]
for name,row in json.loads((W/'FROZEN.json').read_text())['files'].items():
 v=ref(W/name);assert v['bytes']==row['bytes']and v['sha256']==row['sha256'];pins.append(v)
assert len(pins)==167
lineage=[]
for name,row in json.loads((W/'source-lineage-pins.json').read_text())['files'].items():
 p=R/name
 assert '/dev/' not in str(p) and '/.git/' not in str(p)
 v=ref(p);assert v['bytes']==row['bytes']and v['sha256']==row['sha256'];lineage.append(v)
assert len(lineage)==1389
before=(P/'candidate/native_eabi_m0.cpp').read_text();after=(W/'candidate/native_eabi_m0.cpp').read_text()
assert before==(W/'control/native_eabi_m0.cpp').read_text()
patch=''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile='a/code/native_eabi_m0.cpp',tofile='b/code/native_eabi_m0.cpp'))
assert patch==(W/'directed-to-near-one-exp.patch').read_text()
fragment=(W/'small-fragment.cpp').read_text();anchor='\n#endif\n// On ARMv6-M, -O3 expands wide products'
assert after.count('\n'+fragment+anchor)==1
removed=after.replace('\n'+fragment+anchor,anchor)
dispatch=' else if(e<-11) {\n    return real(exp_small_rne(a));\n  }'
assert removed.count(dispatch)==1 and removed.replace(dispatch,'')==before
unchanged=[]
for p in (P/'candidate').iterdir():
 if p.suffix in ('.S','.inc'):
  assert p.read_bytes()==(W/'candidate'/p.name).read_bytes()==(W/'control'/p.name).read_bytes();unchanged.append(ref(W/'candidate'/p.name))
source=(R/'.build/m0-exp-cached-product-independent-20261024/bind_rebuild.py').read_text()
fn=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef)and n.name=='relocs')
exec(compile(ast.Module(body=[fn],type_ignores=[]),'<accepted-semantic-relocations>','exec'),globals())
def sem(e):return {n:v for n,v in relocs(e).items()if n in allocated(e)}
control,candidate,parent=[ElfImage(p)for p in [W/'RP-control.o',W/'RP-candidate.o',P/'RP-candidate.o']]
assert allocated(control)==allocated(parent)and sem(control)==sem(parent)and bss(control)==bss(parent)
a,z=allocated(control),allocated(candidate)
changed={n:[len(a.get(n,b'')),len(z.get(n,b''))]for n in a.keys()|z.keys()if a.get(n,b'')!=z.get(n,b'')}
assert changed=={'.m0_exp_core':[5208,5188],'.m0_exp_small_products':[0,312],'.m0_exp_small':[0,844]},changed
assert bss(control)==bss(candidate)
for n,v in sem(control).items():
 if n!='.m0_exp_core':assert v==sem(candidate)[n]
contexts=[]
for context in ['generic_M0','M4_soft','M4_hard']:
 c,n=[ElfImage(W/(context+'-'+label+'.o'))for label in ['control','candidate']]
 assert allocated(c)==allocated(n)and sem(c)==sem(n)and bss(c)==bss(n)
 contexts.append(context)
im=ElfImage(W/'candidate.elf');oldim=ElfImage(P/'candidate.elf')
assert code(im,'mk61_m0_pow_exp_product')==code(oldim,'mk61_m0_pow_exp_product')and len(code(im,'mk61_m0_pow_exp_product'))==154
assert allocated(ElfImage(W/'control.elf'))==allocated(oldim)
unit=ElfImage(W/'small-products-unit.elf')
unit_bindings={}
for name in ['mk61_m0_exp_small_product64','mk61_m0_exp_small_product48','mk61_m0_exp_small_square48']:
 assert code(im,name)==code(unit,name)
 unit_bindings[name]=dict(bytes=len(code(im,name)),sha256=hashlib.sha256(code(im,name)).hexdigest())
build=json.loads((W/'build.json').read_text());rebuild=O/'rebuild';rebuild.mkdir()
commands=[];rebuilt=[]
for index in [1,8,10]:
 cmd=list(build['commands'][index]);original=Path(cmd[cmd.index('-o')+1]);new=rebuild/original.name
 assert not any(x in cmd for x in ['-MD','-MMD','-MF','-save-temps','-fprofile-generate'])
 cmd[cmd.index('-o')+1]=str(new)
 if index==10:
  cmd=[str(rebuild/Path(x).name)if x in [str(W/'RP-candidate.o'),str(W/'product.o')]else x for x in cmd]
 p=subprocess.run(cmd,cwd=W,capture_output=True)
 (rebuild/(original.name+'.stdout')).write_bytes(p.stdout);(rebuild/(original.name+'.stderr')).write_bytes(p.stderr)
 assert p.returncode==0,(index,p.stderr.decode())
 assert new.read_bytes()==original.read_bytes(),original
 commands.append(cmd);rebuilt.append(ref(new))
tool=Path(build['commands'][0][0]).parent/'arm-none-eabi-objdump'
dis=subprocess.check_output([str(tool),'-dr',str(rebuild/'candidate.elf')])
assert dis==(W/'candidate.dis').read_bytes().replace(str(W/'candidate.elf').encode(),str(rebuild/'candidate.elf').encode(),1)
(O/'candidate.actual.dis').write_bytes(dis)
# Production validator is explicitly sealed/read-only: it generates fresh
# objdump output and compares the existing immutable proofs without rewriting.
guard=subprocess.run([sys.executable,str(W/'verify-private-return.py')],cwd=R,capture_output=True)
(O/'private-guard.stdout').write_bytes(guard.stdout);(O/'private-guard.stderr').write_bytes(guard.stderr)
assert guard.returncode==0,guard.stderr.decode()
out=dict(status='PASS_FROZEN_ONE_CPP_DELTA_SOURCE_OBJECT_ELF_AND_PRIVATE_GUARD_BINDING',accepted_refs=refs,
 local_pins=pins,external_lineage_pins=lineage,local_count=len(pins),external_count=len(lineage),
 exact_one_CPP_patch=ref(W/'directed-to-near-one-exp.patch'),unchanged_ASM_sources=unchanged,
 changed_CPP_sections=changed,all_other_allocated_bytes_semantic_relocations_and_BSS_unchanged=True,
 generic_M0_M4_selected_contexts_unchanged=contexts,shared_product_bytes154_slot168_unchanged=True,
 literal_integer_unit_public_function_bindings=unit_bindings,own_exact_rebuild_count=3,rebuild_commands=commands,rebuilt=rebuilt,
 author_eleven_rebuilds_evidence_only_not_own_runs=ref(W/'rebuild-proof.json'),
 fresh_disassembly=ref(O/'candidate.actual.dis'),production_fresh_guard_exit=0,production_fresh_guard_stdout=ref(O/'private-guard.stdout'),
 hardware_IO=0,Git_operations=0,canonical_access=0,network_operations=0,integration_GO=False)
print(json.dumps(dict(result=save('binding.json',out),rebuilt=3,local=len(pins),external=len(lineage)),indent=2))
