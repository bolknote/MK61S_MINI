"""Near-one exp Q16 input-ulp prototype, RP only."""
from pathlib import Path
import ast,difflib,hashlib,json,re,shlex,shutil,struct,subprocess,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
P=ROOT/'.build/m0-asin-scaled-bound-v164-20261023';C=ROOT/'.build/m0-exp-directed-product-20261024';B=ROOT/'.build/m0-exp-cached-product-20261024'
sys.path.insert(0,str(ROOT/'tests'))
from check_stm32_vectors import ElfImage
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert not (W/'FROZEN.json').exists()
for label in ('control','candidate'):
 folder=W/label;folder.mkdir(exist_ok=True)
 for p in (C/'candidate').glob('native_eabi_m0*'):
  if p.suffix in ('.cpp','.S','.inc'):shutil.copyfile(p,folder/p.name)
source=(W/'control/native_eabi_m0.cpp').read_text()
anchor='\n#endif\n// On ARMv6-M, -O3 expands wide products'
assert source.count(anchor)==1
source=source.replace(anchor,'\n'+(W/'small-fragment.cpp').read_text()+anchor)
old='  else if(e<-32) {\n    return real(exp_tiny_rne(a));\n  }'
new=old+' else if(e<-11) {\n    return real(exp_small_rne(a));\n  }'
assert source.count(old)==1
source=source.replace(old,new)
(W/'candidate/native_eabi_m0.cpp').write_text(source)
product=(W/'control/native_eabi_m0_pow_exp_product.inc').read_text()
(W/'candidate/native_eabi_m0_pow_exp_product.inc').write_text(product)
(W/'product.S').write_text(product.replace('.scratch_y.m0_pow_hot','.scratch_y.m0_exp_product_only'))
entry=next(e for e in json.loads((P/'build/compile_commands.json').read_text()) if e['file'].endswith('/code/native_eabi_m0.cpp'))
flags=shlex.split(entry['command']);cc=Path(flags[0]).parent;commands=[];images={}
for context in ('RP','generic_M0','M4_soft','M4_hard'):
 for label in ('control','candidate'):
  command=list(flags)
  if context!='RP':command=[s for s in command if s!='-DMK61_M0_RP2040_EABI=1']
  if context.startswith('M4'):
   command[command.index('-mcpu=cortex-m0plus')]='-mcpu=cortex-m4'
   command[command.index('-DMK61_USE_M0_EABI=1')]='-DMK61_USE_M0_EABI=0'
   if context=='M4_hard':command+=['-mfloat-abi=hard','-mfpu=fpv4-sp-d16']
  command[command.index(entry['file'])]=str(W/label/'native_eabi_m0.cpp')
  out=W/(context+'-'+label+'.o');command[command.index('-o')+1]=str(out)
  subprocess.run(command,cwd=W,check=True);commands.append(command);images[context,label]=ElfImage(out)
def allocated(e):return {n:e.bytes_at(s) for n,s in e.named_sections.items() if s[2]&2 and s[1]!=8 and s[5]}
tree=ast.parse((ROOT/'.build/m0-exp-cached-product-independent-20261024/bind_rebuild.py').read_text())
fn=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=='relocs')
exec(compile(ast.Module(body=[fn],type_ignores=[]),str(W/'build.py'),'exec'),globals())
def semrelocs(e):return {n:v for n,v in relocs(e).items() if n in allocated(e)}
control,candidate=images['RP','control'],images['RP','candidate'];a,b=allocated(control),allocated(candidate)
assert a.keys()<=b.keys()
changed={n:[len(a.get(n,b'')),len(b.get(n,b''))] for n in a.keys()|b.keys() if a.get(n,b'')!=b.get(n,b'')}
assert set(changed)=={'.m0_exp_core','.m0_exp_small','.m0_exp_small_products'},changed
for n,v in semrelocs(control).items():
 if n!='.m0_exp_core':assert v==semrelocs(candidate)[n],n
assert allocated(control)==allocated(ElfImage(C/'RP-candidate.o')) and semrelocs(control)==semrelocs(ElfImage(C/'RP-candidate.o'))
contexts=[]
for context in ('generic_M0','M4_soft','M4_hard'):
 a,b=[images[context,label] for label in ('control','candidate')]
 assert allocated(a)==allocated(b) and semrelocs(a)==semrelocs(b),context
 contexts.append({'context':context,'all_CPP_allocated_bytes_semantic_relocations_equal':True})
product_cmd=[str(cc/'arm-none-eabi-gcc'),'-mcpu=cortex-m0plus','-mthumb','-DMK61_USE_M0_EABI=1','-DMK61_M0_RP2040_EABI=1','-c',str(W/'product.S'),'-o',str(W/'product.o')]
subprocess.run(product_cmd,cwd=W,check=True);commands.append(product_cmd)
shutil.copyfile(C/'bindings.ld',W/'bindings.ld')
base=ElfImage(P/'firmware/mk61s-picocalc-pico-h.elf')
with (W/'bindings.ld').open('a') as f:f.write('\n__aeabi_lasr = '+hex(base.symbols['__aeabi_lasr'])+';\n')
for label in ('control','candidate'):
 command=[str(cc/'arm-none-eabi-ld'),'--gc-sections','-e','mk61_m0_exp','-T',str(W/'bindings.ld'),str(W/('RP-'+label+'.o')),str((W/'product.o') if label=='candidate' else (C/'product.o')),'-o',str(W/(label+'.elf'))]
 subprocess.run(command,cwd=W,check=True);commands.append(command)
 assert not subprocess.check_output([str(cc/'arm-none-eabi-nm'),'-u',str(W/(label+'.elf'))],text=True)
 with (W/(label+'.dis')).open('w') as f:subprocess.run([str(cc/'arm-none-eabi-objdump'),'-dr',str(W/(label+'.elf'))],stdout=f,check=True)
assert allocated(ElfImage(W/'control.elf'))==allocated(ElfImage(C/'candidate.elf'))
patch=''.join(difflib.unified_diff((W/'control/native_eabi_m0.cpp').read_text().splitlines(True),source.splitlines(True),fromfile='a/code/native_eabi_m0.cpp',tofile='b/code/native_eabi_m0.cpp'))
(W/'directed-to-near-one-exp.patch').write_text(patch)
patch+=''.join(difflib.unified_diff((W/'control/native_eabi_m0_pow_exp_product.inc').read_text().splitlines(True),product.splitlines(True),fromfile='a/code/native_eabi_m0_pow_exp_product.inc',tofile='b/code/native_eabi_m0_pow_exp_product.inc'))
(W/'directed-to-near-one-exp.patch').write_text(patch)
out=dict(status='BUILT_PRIVATE_NEAR_ONE_EXP_PROTOTYPE_SAME77_PRODUCT',source_sha256=sha(W/'candidate/native_eabi_m0.cpp'),product_include_sha256=sha(W/'candidate/native_eabi_m0_pow_exp_product.inc'),candidate_ELF_sha256=sha(W/'candidate.elf'),control_ELF_sha256=sha(W/'control.elf'),changed_CPP_sections=changed,CPP_code_delta_bytes=sum(v[1]-v[0] for v in changed.values()),all_other_CPP_allocated_bytes_semantic_relocations_equal=True,qualified_parent_control_object_ELF_allocated_bytes_exact=True,only_ASM_source_changed=None,product_instructions=[77,77],product_body_bytes=[154,154],product_RAM_slot_bytes=[168,168],product_padding_outside_function_bytes=14,product_stack_bytes=[36,36],contexts=contexts,commands=commands,no_new_tables_RAM_libgcc=True,hardware_accessed=False)
out['required_postbuild_private_return_guard']=True
(W/'build.json').write_text(json.dumps(out,indent=2)+'\n')
subprocess.run([sys.executable,str(W/'verify-private-return.py')],cwd=ROOT,check=True)
print(json.dumps({k:v for k,v in out.items() if k!='commands'},indent=2))
