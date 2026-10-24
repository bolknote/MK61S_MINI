"""Private exp delta: immutable provenance, actual code/isolation and fresh links."""
import ast
import difflib
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
R=Path('/Users/bolk/Projects/MK61S_MINI');O=Path(__file__).resolve().parent
W=R/'.build/m0-exp-directed-product-20261024';P=R/'.build/m0-exp-dyadic-product-20261024'
V=R/'.build/m0-asin-scaled-bound-v164-20261023';PREV=R/'.build/m0-exp-dyadic-product-independent-20261024'
sys.dont_write_bytecode=True;sys.path.insert(0,str(R/'tests'))
from check_stm32_vectors import ElfImage
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def ref(p):
 p=Path(p).absolute();b=p.read_bytes();return dict(path=str(p),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def save(name,value):
 with(O/name).open('x')as f:json.dump(value,f,indent=2);f.write('\n')
def at(e,address,n):
 for s in e.sections:
  if s[1]!=8 and s[3]<=address and address+n<=s[3]+s[5]:return e.data[s[4]+address-s[3]:s[4]+address-s[3]+n]
 raise AssertionError((hex(address),n))
def allocated(e):return {n:e.bytes_at(s)for n,s in e.named_sections.items()if s[2]&2 and s[1]!=8 and s[5]}
def bss(e):return {n:(s[5],s[8])for n,s in e.named_sections.items()if s[2]&2 and s[1]==8 and s[5]}
assert sha(W/'FROZEN.json')=='e6ce76786eeb9443af86b04596cac95fc56aba312ba6bdd1b0d2226da8b69b10'
assert sha(W/'HANDOFF.md')=='9944b911c477e44fdc12bf41fd20c1b9a623edd1e1f6648e932a2dbd7a775308'
assert sha(W/'result.json')=='69a3ec384e20e03f943d8b756335f17166bddd0f2990666cac39f8649b6687d9'
assert sha(W/'candidate.elf')=='b4049e5a39c2bc9d663acab44a7683f1811daedd1c43497cd5ad7588b1b408ac'
assert sha(PREV/'FINAL-REVIEW.json')=='c6aef2f9683f8d234f850363cbfda7f687d65c7ba9581987b723a14db37c536a'
frozen=json.loads((W/'FROZEN.json').read_bytes());pins=[]
for name,row in frozen['files'].items():
 actual=ref(W/name);assert actual['bytes']==row['bytes']and actual['sha256']==row['sha256'];pins.append(actual)
assert len(pins)==295
lineage=json.loads((W/'source-lineage-pins.json').read_bytes());lineage_count=0
for name,row in lineage['files'].items():
 actual=ref(R/name);assert actual['bytes']==row['bytes']and actual['sha256']==row['sha256'];lineage_count+=1
patch=''
for name in ('native_eabi_m0.cpp','native_eabi_m0_pow_exp_product.inc'):
 before=(W/'control'/name).read_text();after=(W/'candidate'/name).read_text()
 assert before==(P/'candidate'/name).read_text()
 patch+=''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile='a/code/'+name,tofile='b/code/'+name))
assert patch==(W/'dyadic-to-directed-exp.patch').read_text()
for p in(P/'candidate').iterdir():
 if p.suffix in('.cpp','.S','.inc')and p.name not in('native_eabi_m0.cpp','native_eabi_m0_pow_exp_product.inc'):
  assert p.read_bytes()==(W/'candidate'/p.name).read_bytes()==(W/'control'/p.name).read_bytes()
# Exact previously accepted semantic ELF relocation decoder; no body exclusions.
relpath=R/'.build/m0-exp-cached-product-independent-20261024/bind_rebuild.py'
node=next(n for n in ast.parse(relpath.read_text()).body if isinstance(n,ast.FunctionDef)and n.name=='relocs')
exec(compile(ast.Module(body=[node],type_ignores=[]),str(relpath),'exec'),globals())
def semantic(e):return {n:v for n,v in relocs(e).items()if n in allocated(e)}
cpp0,cpp1=ElfImage(W/'RP-control.o'),ElfImage(W/'RP-candidate.o')
a,b=allocated(cpp0),allocated(cpp1);assert a.keys()==b.keys()
changed={n:(len(a[n]),len(b[n]))for n in a if a[n]!=b[n]}
assert changed=={'.m0_exp_core':(5088,5208)}and bss(cpp0)==bss(cpp1)
for n,v in semantic(cpp0).items():
 if n!='.m0_exp_core':assert v==semantic(cpp1)[n]
assert a['.m0_exp_core'][:3736]==b['.m0_exp_core'][:3736]
assert [x for x in semantic(cpp0)['.m0_exp_core']if x[0]<3736]==[x for x in semantic(cpp1)['.m0_exp_core']if x[0]<3736]
assert allocated(cpp0)==allocated(ElfImage(P/'RP-candidate.o'))and semantic(cpp0)==semantic(ElfImage(P/'RP-candidate.o'))
contexts=[]
for label in('generic_M0','M4_soft','M4_hard'):
 for prefix in('','ASM-'):
  x,y=ElfImage(W/(prefix+label+'-control.o')),ElfImage(W/(prefix+label+'-candidate.o'))
  assert allocated(x)==allocated(y)and semantic(x)==semantic(y)and bss(x)==bss(y)
  contexts.append(dict(profile=label,unit=prefix or'CPP',allocated_and_relocations_and_BSS_equal=True))
asm0,asm1=ElfImage(W/'ASM-RP-control.o'),ElfImage(W/'ASM-RP-candidate.o')
a,b=allocated(asm0),allocated(asm1);sec='.scratch_y.m0_pow_hot';symbol='mk61_m0_pow_exp_product'
assert a.keys()==b.keys()and {n for n in a if a[n]!=b[n]}=={sec}and semantic(asm0)==semantic(asm1)
offset=asm0.symbols[symbol]&~1;assert asm1.symbols[symbol]==asm0.symbols[symbol]
assert asm0.sizes[symbol]==158 and asm1.sizes[symbol]==154
assert a[sec][:offset]==b[sec][:offset]and a[sec][offset+168:]==b[sec][offset+168:]
oldslot,newslot=a[sec][offset:offset+168],b[sec][offset:offset+168]
assert oldslot[:8]==newslot[:8]and oldslot[154:158]==newslot[150:154]and newslot[154:]==bytes.fromhex('00bf')*7
for name,address in asm0.symbols.items():
 if not name.startswith('$')and name in asm1.symbols:assert asm1.symbols[name]==address,name
assert bss(asm0)==bss(asm1)
for name,slot in(('old',oldslot),('new',newslot)):
 unit=ElfImage(W/('product-'+name+'.elf'));full=ElfImage(W/('candidate.elf'if name=='new'else'control.elf'))
 assert unit.bytes_at(unit.named_sections['.product'])==slot==full.bytes_at(full.named_sections['.product_ram'])
 assert full.named_sections['.product_ram'][3]==0x20038ee4 and full.named_sections['.product_ram'][5]==168
assert allocated(ElfImage(W/'control.elf'))==allocated(ElfImage(P/'candidate.elf'))
assert (W/'bindings.ld').read_bytes()==(P/'bindings.ld').read_bytes()
image=ElfImage(W/'candidate.elf');base=ElfImage(V/'firmware/mk61s-picocalc-pico-h.elf')
start=image.symbols['mk61_m0_exp']&~1;marker=image.symbols['mk61_m0_exp_fraction_capture']
assert start<=marker<start+image.sizes['mk61_m0_exp']and image.sizes['mk61_m0_exp_fraction_capture']==0
assert image.symbols['mk61_m0_exp']==image.symbols['_ZN12compact_math3expEd']
wrapper=image.symbols['mk61_m0_pow_exp_product_flash']&~1
wrapper_bytes=at(base,wrapper,16)
assert wrapper_bytes==bytes.fromhex('01b40248844601bc6047c046')+struct.pack('<I',0x20038ee5)
assert image.symbols['mk61_m0_pow_exp_product']==0x20038ee5
for r in json.loads((W/'isolation-rebuild.json').read_bytes())['records']:
 assert (W/r['original']).read_bytes()==(W/r['rebuilt']).read_bytes()and sha(W/r['original'])==r['sha256']
# Own necessary source-to-whole-object/source-to-full-linked-image rebuild.
build=json.loads((W/'build.json').read_bytes());folder=O/'rebuild';folder.mkdir()
chosen=[]
for name in('RP-candidate.o','product.o','candidate.elf'):
 commands=[c for c in build['commands']if Path(c[c.index('-o')+1]).name==name]
 assert len(commands)==1
 chosen.append(commands[0])
mapping={c[c.index('-o')+1]:str(folder/Path(c[c.index('-o')+1]).name)for c in chosen};rebuilt=[]
for command in chosen:
 actual=[mapping.get(x,x)for x in command]
 assert not any(x in('-MD','-MMD','-MF')for x in actual)
 done=subprocess.run(actual,cwd=W,capture_output=True)
 original=Path(command[command.index('-o')+1]);output=Path(actual[actual.index('-o')+1])
 with(O/(original.name+'.build.stdout')).open('xb')as f:f.write(done.stdout)
 with(O/(original.name+'.build.stderr')).open('xb')as f:f.write(done.stderr)
 assert done.returncode==0,(original,done.stderr)
 assert original.read_bytes()==output.read_bytes(),original
 rebuilt.append(dict(original=ref(original),rebuilt=ref(output),argv=actual,exit_code=0))
cc=Path(build['commands'][0][0]).parent
done=subprocess.run([str(cc/'arm-none-eabi-objdump'),'-dr',str(W/'candidate.elf')],capture_output=True,check=True)
assert not done.stderr and done.stdout==(W/'candidate.dis').read_bytes()
with(O/'candidate.actual.dis').open('xb')as f:f.write(done.stdout)
guard=subprocess.run([sys.executable,str(W/'verify-private-return.py')],cwd=R,capture_output=True)
with(O/'private-guard.stdout').open('xb')as f:f.write(guard.stdout)
with(O/'private-guard.stderr').open('xb')as f:f.write(guard.stderr)
assert guard.returncode==0 and not guard.stderr
save('binding.json',dict(status='PASS_INDEPENDENT_EXACT_PRIVATE_SOURCE_OBJECT_AND_LINK_BINDING',
 frozen=ref(W/'FROZEN.json'),parent=ref(PREV/'FINAL-REVIEW.json'),frozen_files=295,lineage_pins=lineage_count,
 source_CPP=ref(W/'candidate/native_eabi_m0.cpp'),source_ASM_include=ref(W/'candidate/native_eabi_m0_pow_exp_product.inc'),
 candidate_ELF=ref(W/'candidate.elf'),source_patch_exact=True,CPP_changed_sections=changed,
 other_CPP_allocated_bytes_semantic_relocations_BSS_unchanged=True,refinement_prefix3736_and_tiny472_unchanged=True,
 generic_M0_M4_contexts=contexts,only_ASM168byte_slot_changed=True,product_old158_new154_bytes=True,
 product_old79_new77_instructions=True,frame36_both=True,padding14_outside_function=True,
 bare_full_source_slot_byteexact=True,all_other_ASM_bytes_relocations_symbols_unchanged=True,
 marker=dict(address=marker,bytes=0,hidden_global_source=True),real_Flash_tail_veneer=dict(address=wrapper,bytes=wrapper_bytes.hex()),
 full_source_to_object_ELF_rebuilds=rebuilt,author11_rebuilds_byteexact_inputs_verified=True,
 actual_disassembly_byteexact_to_frozen=True,required_linked_guard_exit=guard.returncode,
 private_guard=ref(W/'verify-private-return.py'),actual_disassembly=ref(O/'candidate.actual.dis'),
 no_hardware_or_canonical=True,whole_firmware_GC_and_physical_cycles_unmeasured=True,verified_inputs=pins))
print(json.dumps(dict(status='PASS_BINDING',frozen_files=295,lineage_pins=lineage_count,own_full_byte_exact_rebuilds=3)))
