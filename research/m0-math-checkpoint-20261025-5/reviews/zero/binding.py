"""Independent frozen pins, complete source delta and own whole rebuilds."""
import ast,difflib,hashlib,json,re,struct,subprocess,sys
from pathlib import Path
sys.dont_write_bytecode=True
R=Path('/Users/bolk/Projects/MK61S_MINI');O=Path(__file__).resolve().parent;W=R/'.build/m0-pow-reciprocal-zero-20261025';P=R/'.build/m0-pow-reciprocal-certificate-20261025';U=R/'.build/m0-ddiv-remainder-certificate-r3-20261025'
sys.path.insert(0,str(R/'tests'));from check_stm32_vectors import ElfImage
def ref(p):
 p=Path(p);b=p.read_bytes();return dict(path=str(p),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def pin(p,h):v=ref(p);assert v['sha256']==h,v;return v
def save(n,j):
 with(O/n).open('x')as f:json.dump(j,f,indent=2);f.write('\n')
 return ref(O/n)
def mem(e,a,n):
 s=next(s for s in e.sections if s[1]!=8 and s[3]<=a and a+n<=s[3]+s[5]);return e.bytes_at(s)[a-s[3]:a-s[3]+n]
def alloc(e):return {n:(s[1],s[2],s[3],s[5],None if s[1]==8 else e.bytes_at(s))for n,s in e.named_sections.items()if s[2]&2 and s[5]}
refs=dict(FROZEN=pin(W/'FROZEN.json','98efecf01b96bf8cd1d690682cd9d5b255cbeee997b213ba23e692b926f82544'),result=pin(W/'result.json','226fb8192229a02856a85826221bf1d23dd24b01187be6efae8cfdf35caa0b03'),HANDOFF=pin(W/'HANDOFF.md','4df3a001d8205f240569d1cedcdb00228bebcb4820ed157c399dbb20655674eb'),ELF=pin(W/'candidate.elf','a2957007576c1803479e122991316559b0a7b0cc63b9355c6874bfd29846404a'),
 parent_FROZEN=pin(P/'FROZEN.json','99110367092d4c7397967d9f3b06fb282843431bd7af5b71ea1038a77b4ac329'),parent_independent=pin(R/'.build/m0-pow-reciprocal-certificate-independent-20261025/FINAL-REVIEW.json','6cfdc8862299f9eb776b15dc0aceab8086fb4c847552df58d3e9cd1be3a6fddd'),
 parent_corrigendum=pin(R/'.build/m0-pow-reciprocal-certificate-report-corrigendum-20261025.json','5cd5994f20429814820d5702b8c84782848733e8ee5f95aa17b6a070719a2127'),unit_FROZEN=pin(U/'FROZEN.json','eec45d9efb43fa65741a7e9273b8aebc7f7b82a4df00014b41c99593c24b935c'))
local=[];external=[];unit=[]
for meta,base,out in [(W/'FROZEN.json',W,local),(W/'source-lineage-pins.json',R,external),(U/'FROZEN.json',U,unit)]:
 for name,d in json.loads(meta.read_text())['files'].items():
  assert not name.startswith('/')and'..'not in Path(name).parts and'.git'not in Path(name).parts
  x=ref(base/name);assert[x['bytes'],x['sha256']]==[d['bytes'],d['sha256']],x;out.append(x)
assert len(local)==79 and len(external)==2567
for label in ['control','candidate']:
 for name in ['native_eabi_m0_rp2040.S','native_eabi_m0_pow_root_prefix.inc']:assert(W/label/name).read_bytes()==(P/'candidate'/name).read_bytes()
 for name,pn in [('inline-seed.inc','inline-seed.inc'),('inline-seed-table.inc','inline-seed-table.inc'),(label+'-seed17.S','candidate-seed17.S')]:assert(W/name).read_bytes()==(P/pn).read_bytes()
 assert(W/(label+'.ld')).read_bytes()==(P/'candidate.ld').read_bytes()
def normalize(text,label):
 for suffix in ['_before_second_product','_after_y_residual','_half_normalization','_pack_begin']:
  text=re.sub(r'\.global (mk61_m0_reciprocal1(?:_sw)?'+suffix+r')\n\1:\n','',text)
 return text.replace('#include "'+label+'-remainder-certificate.inc"','#include "remainder-certificate.inc"')
reverse=[(' mul32_32_64 r2,r5, r2,r3, r1,r0,r7,r2,r3  @ xL*a0; preserve R4=0\n',' mul32_32_64 r2,r5, r2,r3, r1,r4,r7,r2,r3  @ xL*a0\n'),
 (' ldr r1,[r13,#4]               @ xH; R1 is dead temporary\n muls r1,r5                    @ xH*a0\n adds r3,r1                    @ r2:r3 now x*a0 Q82\n',' ldr r4,[r13,#4]               @ xH\n muls r4,r5                    @ xH*a0\n adds r3,r4                    @ r2:r3 now x*a0 Q82\n'),
 (' // R4=0 survives the second product and xH temporary.\n',' lsls r4,r0,#5                 @ y Q57\n'),(' // R4 is already zero; next shifts replace flags.\n',' lsls r4,#1                    @ y now Q58\n'),
 (' adds r0,#1                    @ round up with known-zero R6\n adcs r1,r6\n',' movs r2,#0                    @ round up\n adds r0,#1\n adcs r1,r2\n'),(' bmi .Lcertificate_down\n movs r6,#0                   @ full multiplication clobbered R6\n b .Lcertificate_up\n',' bmi .Lcertificate_down\n b .Lcertificate_up\n')]
patch=''
for kind,parent_name,control_name,new_name in [('hardware','candidate-ddiv.S','control-ddiv.S','candidate-ddiv.S'),('software','candidate-software.S','software.S','candidate-software.S')]:
 p=(P/parent_name).read_text();assert normalize((W/control_name).read_text(),'control')==p
 n=normalize((W/new_name).read_text(),'candidate')
 for new,old in reverse:assert n.count(new)==1;n=n.replace(new,old)
 assert n==p
 patch+=''.join(difflib.unified_diff(p.splitlines(True),(W/new_name).read_text().splitlines(True),fromfile='parent/'+kind+'.S',tofile='candidate/'+kind+'.S'))
assert patch==(W/'known-zero.patch').read_text()
macro=(W/'candidate-remainder-certificate.inc').read_bytes();assert macro==(U/'remainder-certificate.inc').read_bytes()
def instructions(s):return'\n'.join(l for l in s.splitlines()if not l.startswith('//'))
assert instructions(macro.decode()).replace('r3','r6')==instructions((P/'remainder-certificate.inc').read_text())
assert(W/'control-remainder-certificate.inc').read_bytes()==(P/'remainder-certificate.inc').read_bytes()
old=ElfImage(P/'candidate.elf');images={n:ElfImage(W/(n+'.elf'))for n in ['control','candidate']};assert alloc(images['control'])==alloc(old)
assert [n for n in alloc(old)if alloc(old)[n]!=alloc(images['candidate'])[n]]==['.ddiv']
assert images['candidate'].symbols['mk61_m0_reciprocal1']==old.symbols['mk61_m0_reciprocal1']and images['candidate'].named_sections['.ddiv'][5]==1100
assert old.bytes_at(old.named_sections['.ddiv'])[-256:]==images['candidate'].bytes_at(images['candidate'].named_sections['.ddiv'])[-256:]
src=(R/'.build/m0-exp-cached-product-independent-20261024/bind_rebuild.py').read_text();fn=next(n for n in ast.parse(src).body if isinstance(n,ast.FunctionDef)and n.name=='relocs');exec(compile(ast.Module(body=[fn],type_ignores=[]),'<accepted-semantic-relocations>','exec'),globals())
for context in ['RP','generic_M0','M4_soft','M4_hard']:
 e=ElfImage(P/(context+'-candidate.o'))
 for label in ['control','candidate']:
  n=ElfImage(W/(context+'-'+label+'.o'));assert alloc(e)==alloc(n)
  for sec in alloc(e):assert relocs(e).get(sec)==relocs(n).get(sec)
 if context!='RP':
  for n in ['candidate-ddiv','candidate-software']:assert not alloc(ElfImage(W/(context+'-'+n+'-disabled.o')))
d=O/'rebuild';d.mkdir();(d/'unit').mkdir();build=json.loads((W/'build.json').read_text());ub=json.loads((U/'build.json').read_text())
names=['RP-control.o','RP-candidate.o','control-ddiv.o','candidate-ddiv.o','software.o','candidate-software.o','control.elf','candidate.elf'];unames=['control.o','candidate.o','control.elf','candidate.elf']
mapping={str(W/n):str(d/n)for n in names};mapping.update({str(U/n):str(d/'unit'/n)for n in unames});commands=[];outputs=[]
for base,cmds,nlist in [(W,build['commands'],names),(U,ub['commands'],unames)]:
 for name in nlist:
  argv=next(c for c in cmds if Path(c[c.index('-o')+1]).name==name);cmd=[mapping.get(x,x)for x in argv]
  assert not any(x in cmd for x in ['-MD','-MMD','-MF','-save-temps'])
  if '-g'in cmd:cmd+=['-fdebug-prefix-map='+str(O)+'='+str(base)]
  dest=Path(cmd[cmd.index('-o')+1]);p=subprocess.run(cmd,cwd=O,capture_output=True);Path(str(dest)+'.stdout').write_bytes(p.stdout);Path(str(dest)+'.stderr').write_bytes(p.stderr)
  assert p.returncode==0,p.stderr.decode();assert dest.read_bytes()==(base/name).read_bytes(),name
  outputs.append(ref(dest));commands.append(dict(argv=cmd,returncode=p.returncode))
tc=Path(build['commands'][0][0]).parent
for n,path in [('control.elf',d/'control.elf'),('candidate.elf',d/'candidate.elf'),('unit-control.elf',d/'unit/control.elf'),('unit-candidate.elf',d/'unit/candidate.elf')]:(O/(n+'.actual.dis')).write_bytes(subprocess.check_output([str(tc/'arm-none-eabi-objdump'),'-d',str(path)]))
print(json.dumps(save('binding.json',dict(status='PASS_EXACT_FROZEN_SOURCE_REVERSAL_CONTEXTS_AND_TWELVE_BYTEEXACT_REBUILDS',refs=refs,local=local,external=external,unit=unit,
 local79_external2567=True,unit_files=len(unit),actual_parent_certificate_not_nearone=True,source_reverse_complete_both_files_bound_not_standalone_equivalence_proof=True,
 macro_r3_register_rename_only_shared_unit_bytes=True,root_call_bytes_and_all_other_allocated_sections_addresses_relocations_unchanged=True,
 unchanged_seed_table256_inline_source_and_no_RAM_libgcc_external_calls=True,allocation1108to1100_minus8=True,defaultM0_M4_and6disabled_unchanged=True,
 own12_byteexact_rebuilds=outputs,commands=commands,producer_commands_not_executed_inplace=True,missing_at_seal_parent_stamp_not_rewritten=True,
 ARM_calls=0,MPFR_inputs=0,devices=0,Git=0,canonical=0,network=0))),flush=True)
