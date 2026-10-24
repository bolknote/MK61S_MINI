from pathlib import Path
import ast,hashlib,json,shlex,struct,subprocess,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1];P=ROOT/'.build/m0-asin-scaled-bound-v164-20261023';C=ROOT/'.build/m0-exp-adaptive-enclosure-20261024';B=ROOT/'.build/m0-exp-cached-product-20261024'
sys.path.insert(0,str(ROOT/'tests'))
from check_stm32_vectors import ElfImage
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def allocated(e):return {n:e.bytes_at(s) for n,s in e.named_sections.items() if s[2]&2 and s[1]!=8 and s[5]}
tree=ast.parse((ROOT/'.build/m0-exp-cached-product-independent-20261024/bind_rebuild.py').read_text());fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='relocs')
exec(compile(ast.Module(body=[fn],type_ignores=[]),str(W/'isolate-rebuild.py'),'exec'),globals())
def semrelocs(e):return {n:v for n,v in relocs(e).items() if n in allocated(e)}
entry=next(e for e in json.loads((P/'build/compile_commands.json').read_text()) if e['file'].endswith('/code/native_eabi_m0.S'))
flags=shlex.split(entry['command']);commands=[];images={}
for context in ('RP','generic_M0','M4_soft','M4_hard'):
 for label in ('control','candidate'):
  for p in (C/'candidate').glob('native_eabi_m0*'):
   if p.suffix in ('.S','.inc') and p.name!='native_eabi_m0_pow_exp_product.inc':assert (W/label/p.name).read_bytes()==p.read_bytes()
  c=list(flags)
  if context!='RP':c=[s for s in c if s!='-DMK61_M0_RP2040_EABI=1']
  if context.startswith('M4'):
   c[c.index('-mcpu=cortex-m0plus')]='-mcpu=cortex-m4';c[c.index('-DMK61_USE_M0_EABI=1')]='-DMK61_USE_M0_EABI=0'
   if context=='M4_hard':c+=['-mfloat-abi=hard','-mfpu=fpv4-sp-d16']
  c[c.index(entry['file'])]=str(W/label/'native_eabi_m0.S');out=W/('ASM-'+context+'-'+label+'.o');c[c.index('-o')+1]=str(out)
  subprocess.run(c,cwd=W,check=True);commands.append(c);images[context,label]=ElfImage(out)
control,candidate=images['RP','control'],images['RP','candidate'];a,b=allocated(control),allocated(candidate)
assert a==allocated(ElfImage(C/'ASM-RP-candidate.o')) and semrelocs(control)==semrelocs(ElfImage(C/'ASM-RP-candidate.o'))
assert a.keys()==b.keys() and {n for n in a if a[n]!=b[n]}=={'.scratch_y.m0_pow_hot'}
assert semrelocs(control)==semrelocs(candidate)
name='mk61_m0_pow_exp_product';off=control.symbols[name]&~1
assert candidate.symbols[name]==control.symbols[name]
assert control.sizes[name]==162 and candidate.sizes[name]==158
oldslot=a['.scratch_y.m0_pow_hot'][off:off+168];newslot=b['.scratch_y.m0_pow_hot'][off:off+168]
assert len(a['.scratch_y.m0_pow_hot'])==len(b['.scratch_y.m0_pow_hot'])
assert a['.scratch_y.m0_pow_hot'][:off]==b['.scratch_y.m0_pow_hot'][:off]
assert a['.scratch_y.m0_pow_hot'][off+168:]==b['.scratch_y.m0_pow_hot'][off+168:]
assert oldslot[14:158]==newslot[10:154]
assert oldslot[160:162]==newslot[156:158]
assert newslot[158:]==b'\x00\xbf'*5
assert oldslot==ElfImage(C/'product.o').bytes_at(ElfImage(C/'product.o').named_sections['.scratch_y.m0_exp_product_only'])
assert newslot==ElfImage(W/'product.o').bytes_at(ElfImage(W/'product.o').named_sections['.scratch_y.m0_exp_product_only'])
for n,address in control.symbols.items():
 if not n.startswith('$') and n in candidate.symbols:assert candidate.symbols[n]==address,n
contexts=[]
for context in ('generic_M0','M4_soft','M4_hard'):
 x,y=[images[context,label] for label in ('control','candidate')]
 assert allocated(x)==allocated(y) and semrelocs(x)==semrelocs(y)
 contexts.append(dict(context=context,all_ASM_allocated_bytes_and_semantic_relocations_equal=True))
for label in ('control','candidate'):
 im=ElfImage(W/(label+'.elf'));section=im.named_sections['.product_ram']
 assert section[3]==0x20038ee4 and section[5]==168
 assert im.bytes_at(section)==(oldslot if label=='control' else newslot)
assert not semrelocs(candidate).get('.scratch_y.m0_pow_hot') or semrelocs(candidate)==semrelocs(control)
cpp0,cpp1=[ElfImage(W/('RP-'+label+'.o')) for label in ('control','candidate')]
assert cpp0.bytes_at(cpp0.named_sections['.m0_exp_tiny'])==cpp1.bytes_at(cpp1.named_sections['.m0_exp_tiny'])
# Byte-identical rebuilds include complete translation units, actual
# public overlay ELFs, the product object and both source-bound units.
build=json.loads((W/'build.json').read_text());unit=json.loads((W/'certificate.json').read_text());prod=json.loads((W/'product-unit-build.json').read_text())
rebuild_commands=[c for c in commands if Path(c[c.index('-o')+1]).name.startswith('ASM-RP-')]
rebuild_commands += [c for c in build['commands'] if Path(c[c.index('-o')+1]).name in ('RP-control.o','RP-candidate.o','product.o','control.elf','candidate.elf')]
rebuild_commands += unit['commands']+prod['commands']
assert len(rebuild_commands)==11
outputs={c[c.index('-o')+1] for c in rebuild_commands};folder=W/'rebuild';folder.mkdir(exist_ok=True);records=[]
for c in rebuild_commands:
 original=Path(c[c.index('-o')+1]);rewritten=[str(folder/Path(s).name) if s in outputs else s for s in c]
 subprocess.run(rewritten,cwd=W,check=True)
 assert original.read_bytes()==(folder/original.name).read_bytes(),original.name
 records.append(dict(original=str(original.relative_to(W)),rebuilt=str((folder/original.name).relative_to(W)),sha256=sha(original),bytes=original.stat().st_size,command=rewritten))
out=dict(status='PASS_ONLY_SHARED_PRODUCT_RAM_SLOT_AND_EXP_CPP_CHANGE_ELEVEN_REBUILDS',candidate_ELF_sha256=sha(W/'candidate.elf'),full_ASM_product_slot_exact_actual_unit_and_public_body=True,
 product_arithmetic144bytes_and_final_POP_byte_identical=True,only_prologue_and_SP_epilogue_active_changes=True,
 outside_slot_all_RP_ASM_bytes_semantic_relocations_and_symbol_addresses_identical=True,
 d2f_f2d_sqrt_pow_dispatch_and_other_sections_unchanged=True,
 product_body_bytes=[162,158],product_slot_bytes=[168,168],product_padding_outside_function_bytes=10,
 accepted_RAM_address_and_Flash_wrapper_binding_preserved=True,tiny472byte_helper_unchanged=True,
 contexts=contexts,records=records,hardware_accessed=False,whole_M4_firmware_not_built=True)
(W/'isolation-rebuild.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:v for k,v in out.items() if k!='records'},indent=2))
