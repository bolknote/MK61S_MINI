"""Frozen Bound3 source identity, controls and own complete rebuilds."""
import ast,difflib,hashlib,json,struct,subprocess,sys
from pathlib import Path
sys.dont_write_bytecode=True
R=Path('/Users/bolk/Projects/MK61S_MINI');O=Path(__file__).resolve().parent;W=R/'.build/m0-pow-reciprocal-bound3-20261025';P=R/'.build/m0-pow-reciprocal-zero-20261025';U=R/'.build/m0-ddiv-seed-bound3-20261025'
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
refs=dict(FROZEN=pin(W/'FROZEN.json','0a5480ab5d386448b05bc3ffe0993ccda2c417025cd31779cb732929e30c56a0'),result=pin(W/'result.json','b141d6569b6f3b861b5a9be70c934bd04118f00453dee06ad7bcaeaa65e53a6f'),HANDOFF=pin(W/'HANDOFF.md','a8129acd4bde1fcc6269143224771207ba2604277d276aad68619b770d01924b'),ELF=pin(W/'candidate.elf','53e624741136a615814141b4f4d69eb563e32909562dd9068fe63bba3d0b0e67'),
 parent_FROZEN=pin(P/'FROZEN.json','98efecf01b96bf8cd1d690682cd9d5b255cbeee997b213ba23e692b926f82544'),parent_independent=pin(R/'.build/m0-pow-reciprocal-zero-independent-20261025/FINAL-REVIEW.json','8c97aa51a42f432aed76da04a4ca44756b0327f812269946f98b9e1f18a0471b'),
 unit_FROZEN=pin(U/'FROZEN.json','58764a6b8b12a221d8cc7061ba60a50541068bf366181aad277c3253757b078e'))
lists=[[],[],[]]
for (meta,base),out in zip([(W/'FROZEN.json',W),(W/'source-lineage-pins.json',R),(U/'FROZEN.json',U)],lists):
 for name,d in json.loads(meta.read_text())['files'].items():
  assert not name.startswith('/')and'..'not in Path(name).parts and'.git'not in Path(name).parts
  x=ref(base/name);assert[x['bytes'],x['sha256']]==[d['bytes'],d['sha256']],x;out.append(x)
assert len(lists[0])==84 and len(lists[1])==2742
for label in ['control','candidate']:
 for name in ['native_eabi_m0_rp2040.S','native_eabi_m0_pow_root_prefix.inc']:assert(W/label/name).read_bytes()==(P/'candidate'/name).read_bytes()
 assert(W/(label+'-ddiv.S')).read_bytes()==(P/'candidate-ddiv.S').read_bytes()
 sn='software.S'if label=='control'else'candidate-software.S'
 assert(W/sn).read_text().replace('#include "'+label+'-inline-seed.inc"','#include "inline-seed.inc"')==(P/'candidate-software.S').read_text()
 assert(W/(label+'-seed17.S')).read_bytes()==(P/'candidate-seed17.S').read_bytes()
 assert(W/(label+'.ld')).read_bytes()==(P/'candidate.ld').read_bytes()
for name in ['candidate-remainder-certificate.inc','inline-seed-table.inc']:assert(W/name).read_bytes()==(P/name).read_bytes()
assert(W/'control-inline-seed.inc').read_bytes()==(P/'inline-seed.inc').read_bytes()==(U/'control-seed.inc').read_bytes()
assert(W/'candidate-inline-seed.inc').read_bytes()==(U/'candidate-seed.inc').read_bytes()
patch=''.join(difflib.unified_diff((P/'inline-seed.inc').read_text().splitlines(True),(W/'candidate-inline-seed.inc').read_text().splitlines(True),fromfile='parent/inline-seed.inc',tofile='candidate/inline-seed.inc'))
assert patch==(W/'bounded-seed.patch').read_text()
old=ElfImage(P/'candidate.elf');images={n:ElfImage(W/(n+'.elf'))for n in ['control','candidate']};assert alloc(images['control'])==alloc(old)
assert[n for n in alloc(old)if alloc(old)[n]!=alloc(images['candidate'])[n]]==['.ddiv']and images['candidate'].named_sections['.ddiv'][5]==1108
assert old.bytes_at(old.named_sections['.ddiv'])[-256:]==images['candidate'].bytes_at(images['candidate'].named_sections['.ddiv'])[-256:]
s=(R/'.build/m0-exp-cached-product-independent-20261024/bind_rebuild.py').read_text();fn=next(n for n in ast.parse(s).body if isinstance(n,ast.FunctionDef)and n.name=='relocs');exec(compile(ast.Module(body=[fn],type_ignores=[]),'<accepted-semantic-relocations>','exec'),globals())
for context in ['RP','generic_M0','M4_soft','M4_hard']:
 p=ElfImage(P/(context+'-candidate.o'))
 for label in ['control','candidate']:
  n=ElfImage(W/(context+'-'+label+'.o'));assert alloc(p)==alloc(n)
  for sec in alloc(p):assert relocs(p).get(sec)==relocs(n).get(sec)
 if context!='RP':
  for name in ['candidate-ddiv','candidate-software']:assert not alloc(ElfImage(W/(context+'-'+name+'-disabled.o')))
d=O/'rebuild';d.mkdir();(d/'unit').mkdir();build=json.loads((W/'build.json').read_text());ub=json.loads((U/'build.json').read_text());names=['RP-control.o','RP-candidate.o','control-ddiv.o','candidate-ddiv.o','software.o','candidate-software.o','control.elf','candidate.elf'];unames=['control.o','candidate.o','control.elf','candidate.elf']
mapping={str(W/n):str(d/n)for n in names};mapping.update({str(U/n):str(d/'unit'/n)for n in unames});commands=[];outputs=[]
for base,cmds,nlist in [(W,build['commands'],names),(U,ub['commands'],unames)]:
 for name in nlist:
  argv=next(c for c in cmds if Path(c[c.index('-o')+1]).name==name);cmd=[mapping.get(x,x)for x in argv];assert not any(x in cmd for x in ['-MD','-MMD','-MF','-save-temps'])
  if '-g'in cmd:cmd+=['-fdebug-prefix-map='+str(O)+'='+str(base)]
  dest=Path(cmd[cmd.index('-o')+1]);p=subprocess.run(cmd,cwd=O,capture_output=True);Path(str(dest)+'.stdout').write_bytes(p.stdout);Path(str(dest)+'.stderr').write_bytes(p.stderr)
  assert p.returncode==0,p.stderr.decode();assert dest.read_bytes()==(base/name).read_bytes(),name;outputs.append(ref(dest));commands.append(dict(argv=cmd,returncode=0))
tc=Path(build['commands'][0][0]).parent
for n,path in [('control.elf',d/'control.elf'),('candidate.elf',d/'candidate.elf'),('unit-control.elf',d/'unit/control.elf'),('unit-candidate.elf',d/'unit/candidate.elf')]:(O/(n+'.actual.dis')).write_bytes(subprocess.check_output([str(tc/'arm-none-eabi-objdump'),'-d',str(path)]))
print(json.dumps(save('binding.json',dict(status='PASS_FROZEN_SOFTWARE_MACRO_ONLY_DELTA_AND_TWELVE_OWN_BYTEEXACT_REBUILDS',refs=refs,local=lists[0],external=lists[1],unit=lists[2],local84_external2742=True,unit_files=len(lists[2]),
 actual_parent_Zero_source_not_nearone=True,entire_hardware_source_and_resident_calls_unchanged=True,only_software_inline_macro_changed=True,
 same256B_table_and_R3certificate_Zero_source=True,all_other_allocated_sections_addresses_semanticrelocs_unchanged=True,defaultM0_M4_and6disabled_unchanged=True,
 own12_byteexact_rebuilds=outputs,commands=commands,own_outputs_only_no_producer_execution_inplace=True,allocation1100to1108_plus8=True,
 new_RAM_libgcc_external_calls=False,ARM_calls=0,MPFR_inputs=0,devices=0,Git=0,network=0,canonical=0))),flush=True)
