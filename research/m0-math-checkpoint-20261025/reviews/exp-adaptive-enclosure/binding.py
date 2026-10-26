from pathlib import Path
import ast,difflib,hashlib,json,shlex,struct,subprocess,sys
sys.dont_write_bytecode=True
R=Path('/Users/bolk/Projects/MK61S_MINI');P=R/'.build/m0-exp-adaptive-enclosure-20261024';O=Path(__file__).resolve().parent;B=R/'.build/m0-exp-tiny-log-midpoint-20261024';E=R/'.build/m0-exp-tiny-log-midpoint-independent-20261024';V=R/'.build/m0-asin-scaled-bound-v164-20261023'
sys.path.insert(0,str(R/'tests'))
from check_stm32_vectors import ElfImage
def read(p):return json.loads(Path(p).read_text())
def ref(p):
 p=Path(p);b=p.read_bytes();return dict(path=str(p),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
assert ref(P/'FROZEN.json')['sha256']=='de974c59adb91f98123723c014d0e41e44fa4fb966bc76ff87cf11bec994f5f8'
assert ref(P/'result.json')['sha256']=='f1b729a9ed7bbf468643ce41fe9193f1d1ee1ace98c139589ba82482bab7a5a7'
assert ref(P/'candidate.elf')['sha256']=='c1d7a59ffe62a886b3fdfaaf3d215a24e1c52c902c3b1a31b75286960261eb6c'
verified=[]
for n,base,count in [('FROZEN.json',P,143),('source-lineage-pins.json',R,741)]:
 files=read(P/n)['files'];assert len(files)==count
 for name,d in files.items():
  actual=ref(base/name);assert actual['bytes']==d['bytes'] and actual['sha256']==d['sha256'];verified.append(actual)
parent=E/'FINAL-REVIEW.json';assert ref(parent)['sha256']=='bdaba8cf9bbe58c8e36dafe9b8f904eb8428fdd42db0abb070b5f4a42e472554'
pins={}
def walk(x):
 if isinstance(x,dict):
  if {'path','bytes','sha256'}<=x.keys():pins[x['path']]=x
  for v in x.values():walk(v)
 elif isinstance(x,list):
  for v in x:walk(v)
walk(read(parent));assert len(pins)==48
for pin in pins.values():assert ref(pin['path'])==pin
for f,names in [(R/'.build/m0-pow-square-ordinary-independent-20261024/bind.py',['allocated','body']),(R/'.build/m0-exp-cached-product-independent-20261024/bind_rebuild.py',['relocs']),(R/'.build/m0-exp-tiny-radius-independent-20261024/binding.py',['loads'])]:
 nodes=[x for x in ast.parse(f.read_text()).body if isinstance(x,ast.FunctionDef) and x.name in names];assert len(nodes)==len(names);exec(compile(ast.Module(body=nodes,type_ignores=[]),str(O/'binding.py'),'exec'),globals())
def rel(e):return {n:v for n,v in relocs(e).items() if n in allocated(e)}
patch=''
for name in ['native_eabi_m0.cpp','native_eabi_m0_pow_exp_product.inc']:
 a=(P/'control'/name).read_text();b=(P/'candidate'/name).read_text();assert a==(B/'candidate'/name).read_text();patch+=''.join(difflib.unified_diff(a.splitlines(True),b.splitlines(True),fromfile='a/code/'+name,tofile='b/code/'+name))
assert patch==(P/'qualified-log-midpoint-to-adaptive-exp.patch').read_text()
for f in (B/'candidate').iterdir():
 if f.suffix in ('.S','.inc','.cpp') and f.name not in ['native_eabi_m0.cpp','native_eabi_m0_pow_exp_product.inc']:
  for label in ['control','candidate']:assert (P/label/f.name).read_bytes()==f.read_bytes()
x,y=ElfImage(P/'RP-control.o'),ElfImage(P/'RP-candidate.o');a,b=allocated(x),allocated(y)
assert a==allocated(ElfImage(B/'RP-candidate.o')) and rel(x)==rel(ElfImage(B/'RP-candidate.o'))
changed={n:(len(a[n]),len(b[n])) for n in a if a[n]!=b[n]};assert changed=={'.m0_exp_core':(5012,5064)}
assert a['.m0_exp_core'][:3736]==b['.m0_exp_core'][:3736]
for n in a:
 if n!='.m0_exp_core':assert rel(x).get(n)==rel(y).get(n)
assert body(x,'exp_tiny_rne')==body(y,'exp_tiny_rne') and len(body(y,'exp_tiny_rne'))==472
contexts={}
for ctx in ['generic_M0','M4_soft','M4_hard']:
 c,d=ElfImage(P/(ctx+'-control.o')),ElfImage(P/(ctx+'-candidate.o'));assert allocated(c)==allocated(d) and rel(c)==rel(d);contexts[ctx]=sum(map(len,allocated(c).values()))
x,y=ElfImage(P/'ASM-RP-control.o'),ElfImage(P/'ASM-RP-candidate.o');a,b=allocated(x),allocated(y);name='mk61_m0_pow_exp_product';off=x.symbols[name]&~1;sec='.scratch_y.m0_pow_hot'
assert a==allocated(ElfImage(B/'ASM-candidate.o')) and rel(x)==rel(y)==rel(ElfImage(B/'ASM-candidate.o'))
assert {n for n in a if a[n]!=b[n]}=={sec} and len(a[sec])==len(b[sec])
oldslot=a[sec][off:off+168];newslot=b[sec][off:off+168]
assert a[sec][:off]==b[sec][:off] and a[sec][off+168:]==b[sec][off+168:] and oldslot[20:]==newslot[14:162] and newslot[162:]==b'\x00\xbf'*3
assert body(x,name)==oldslot and body(y,name)==newslot[:162]
for n,address in x.symbols.items():
 if not n.startswith('$') and n in y.symbols:assert y.symbols[n]==address,n
assert len(body(y,'__aeabi_d2f'))==256 and len(body(y,'__aeabi_f2d'))==172
for ctx in ['generic_M0','M4_soft','M4_hard']:
 c,d=ElfImage(P/('ASM-'+ctx+'-control.o')),ElfImage(P/('ASM-'+ctx+'-candidate.o'));assert allocated(c)==allocated(d) and rel(c)==rel(d)
for label,slot in [('control',oldslot),('candidate',newslot)]:
 im=ElfImage(P/(label+'.elf'));s=im.named_sections['.product_ram'];assert s[3]==0x20038ee4 and s[5]==168 and im.bytes_at(s)==slot
 assert im.symbols['mk61_m0_exp']==im.symbols['_ZN12compact_math3expEd']
assert allocated(ElfImage(P/'control.elf'))==allocated(ElfImage(B/'candidate.elf'))
assert (P/'bindings.ld').read_bytes()==(B/'bindings.ld').read_bytes()
segments=loads(P/'candidate.elf');prior=loads(B/'candidate.elf');assert segments[0]['bytes']-prior[0]['bytes']==48 and segments[1]['bytes']==168
build=read(P/'build.json');iso=read(P/'isolation-rebuild.json');cert=read(P/'certificate.json');prod=read(P/'product-unit-build.json');commands=list(build['commands'])
db=read(V/'build/compile_commands.json');entry=next(z for z in db if z['file'].endswith('/code/native_eabi_m0.S'));flags=shlex.split(entry['command']);cc=Path(flags[0]).parent
for ctx in ['RP','generic_M0','M4_soft','M4_hard']:
 for label in ['control','candidate']:
  c=list(flags)
  if ctx!='RP':c=[z for z in c if z!='-DMK61_M0_RP2040_EABI=1']
  if ctx.startswith('M4'):
   c[c.index('-mcpu=cortex-m0plus')]='-mcpu=cortex-m4';c[c.index('-DMK61_USE_M0_EABI=1')]='-DMK61_USE_M0_EABI=0'
   if ctx=='M4_hard':c+=['-mfloat-abi=hard','-mfpu=fpv4-sp-d16']
  c[c.index(entry['file'])]=str(P/label/'native_eabi_m0.S');c[c.index('-o')+1]=str(P/('ASM-'+ctx+'-'+label+'.o'));commands.append(c)
commands+=cert['commands']+prod['commands'];assert len(commands)==23
out=O/'rebuild';out.mkdir(exist_ok=True);mapping={c[c.index('-o')+1]:str(out/Path(c[c.index('-o')+1]).name) for c in commands};records=[]
# Commands were discovered in dependency order except product unit links, which run last.
for c in commands:
 cmd=[mapping.get(z,z) for z in c];assert not any(z in ['-MD','-MMD','-MF'] for z in cmd)
 run=subprocess.run(cmd,cwd=P,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT);assert run.returncode==0,run.stdout
 original=Path(c[c.index('-o')+1]);fresh=Path(cmd[cmd.index('-o')+1]);assert ref(original)['sha256']==ref(fresh)['sha256'],original
 records.append(dict(original=ref(original),rebuilt=ref(fresh),command=cmd,returncode=0))
for n in ['candidate.elf','control.elf','unit.elf','product-old.elf','product-new.elf']:assert not subprocess.check_output([str(cc/'arm-none-eabi-nm'),'-u',str(out/n)],text=True).strip()
assert ElfImage(out/'product-new.elf').bytes_at(ElfImage(out/'product-new.elf').named_sections['.product'])==newslot
for n in ['candidate','control','unit','product-old','product-new']:(O/(n+'.dis')).write_text(subprocess.check_output([str(cc/'arm-none-eabi-objdump'),'-dr',str(out/(n+'.elf'))],text=True))
stacks={}
for label in ['control','candidate']:
 lines=(out/('RP-'+label+'.su')).read_text().splitlines();line=next(x for x in lines if 'double mk61_m0_exp(double)' in x);stacks[label]=int(line.split('\t')[1]);assert stacks[label]==96
src=(P/'candidate/native_eabi_m0.cpp').read_text();start=src.index('          const uint32_t top=uint32_t(q>>48)+24U;');end=src.index('          safe=margin>int32_t(bound);',start)+len('          safe=margin>int32_t(bound);');fragment=src[start:end]
assert fragment in (P/'unit.cpp').read_text()
d=dict(status='PASS_INDEPENDENT_ADAPTIVE_SOURCE_REBUILD_AND_PRODUCT_SLOT_CLOSURE',accepted_parent=ref(parent),accepted_parent_referenced_files48_plus_receipt49=True,frozen_artifacts=143,lineage_pins=741,verified=verified,parent_references=list(pins.values()),source_patch_exact=True,CPP_changed_sections=changed,all_other_CPP_bytes_semantic_relocations_exact=True,preexisting_refine3736_and_tiny472_exact=True,only_RP_ASM_product168byte_slot_changed=True,product_active_body_bytes=[168,162],product_suffix148_byte_exact=True,product_slot_padding6_outside_function=True,all_other_RP_ASM_bytes_semantic_relocations_symbol_addresses_exact=True,d2f256_f2d172_preserved=True,generic_M0_M4_CPP_and_ASM_fresh_equal=True,whole_M4_not_built=True,generic_CPP_allocated_sizes=contexts,public_entry_alias_direct=True,bindings_and_wrapper_unchanged=True,product_address='0x20038ee4',selected_CPP_delta52=True,selected_ASM_slot_delta0=True,private_Flash_delta48_including_alignment=True,load_segments=segments,own_complete_byte_exact_rebuilds=23,source_literal_gate_fragment_sha256=hashlib.sha256(fragment.encode()).hexdigest(),static_exp_core_stack_bytes=stacks,records=records,hardware=False,canonical=False)
(O/'binding.json').write_text(json.dumps(d,indent=2)+'\n');print(json.dumps({k:v for k,v in d.items() if k not in ['verified','records','parent_references']},indent=2))
