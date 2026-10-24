"""Private exact midpoint correction for all tiny-exp rounding cells."""
from pathlib import Path
import ast,difflib,hashlib,json,shlex,shutil,struct,subprocess,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
P=ROOT/'.build/m0-asin-scaled-bound-v164-20261023'
B=ROOT/'.build/m0-exp-cached-product-20261024'
R=ROOT/'.build/m0-pow-rsqrt-asm-20261024'
F=ROOT/'.build/m0-f2d-leaf-20261024'
sys.path.insert(0,str(ROOT/'tests'))
from check_stm32_vectors import ElfImage
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert not (W/'FROZEN.json').exists()
for label in ('control','candidate'):
 folder=W/label;folder.mkdir(exist_ok=True)
 for parent in (R/'candidate',F/'candidate'):
  for p in parent.glob('native_eabi_m0*'):
   if p.suffix in ('.cpp','.S','.inc'):shutil.copyfile(p,folder/p.name)
source=(W/'control/native_eabi_m0.cpp').read_text()
start=source.index('// Called only for2^-54<|x|<2^-40.')
stop=source.index('\n#endif',start)
old=source[start:stop]
new='''// Called only for 2^-54 < |x| < 2^-38. At a nearby linear midpoint
// M0=(2*retained+1)*2^(s-1), its quadratic correction in input-ulp units
// is (2*retained+1)^2 / 2^(e+55+2*negative). The odd numerator is never
// integral on this grid. Input displacement and the cubic remainder
// together are <2^-22 units, while its distance to an integer is >=2^-18.
// Consequently its exact integer floor decides every guarded midpoint.
__attribute__((noinline,noipa,section(".m0_exp_tiny"))) static U exp_tiny_rne(U a) {
  const bool negative=bool(a>>63);
  const int e=int((a>>52)&0x7FFU)-1023;
  const unsigned shift=unsigned(-e)-unsigned(negative)-32U;
  const uint32_t hi=(uint32_t(a>>32)&0xFFFFFU)|0x100000U,lo=uint32_t(a);
  const uint32_t tail=hi&((1U<<shift)-1U),half=1U<<(shift-1U),retained=hi>>shift;
  if(negative) {
    bool up=tail>half || (tail==half && lo);
    if(tail==half && lo && lo<16385U) {
      const uint32_t odd=(retained<<1)|1U;
      const uint32_t quadratic=(odd*odd)>>unsigned(e+57);
      up=lo>quadratic;
    }
    return UINT64_C(0x3FF0000000000000)-U(retained+unsigned(up));
  }
  bool up=tail>=half;
  if(tail+1U==half && lo>0U-16385U) {
    const uint32_t odd=(retained<<1)|1U;
    const uint32_t quadratic=(odd*odd)>>unsigned(e+55);
    up=(0U-lo)<=quadratic;
  }
  return UINT64_C(0x3FF0000000000000)+U(retained+unsigned(up));
}'''
source=source[:start]+new+source[stop:]
source=source.replace('''  else if(e<-40) {
    const U tiny=exp_tiny_rne(a);
    if(tiny!=(D::Infinity|D::Quiet)) return real(tiny);
  }''','''  else if(e<-38) {
    return real(exp_tiny_rne(a));
  }''')
assert 'else if(e<-38)' in source and source.count('static U exp_tiny_rne(')==1
(W/'candidate/native_eabi_m0.cpp').write_text(source)
entry=next(e for e in json.loads((P/'build/compile_commands.json').read_text()) if e['file'].endswith('/code/native_eabi_m0.cpp'))
flags=shlex.split(entry['command']);cc=Path(flags[0]).parent;commands=[];images={}
for context in ('RP','generic_M0','M4_soft','M4_hard'):
 for label in ('control','candidate'):
  command=list(flags)
  if context!='RP':command=[x for x in command if x!='-DMK61_M0_RP2040_EABI=1']
  if context.startswith('M4'):
   command[command.index('-mcpu=cortex-m0plus')]='-mcpu=cortex-m4'
   command[command.index('-DMK61_USE_M0_EABI=1')]='-DMK61_USE_M0_EABI=0'
   if context=='M4_hard':command+=['-mfloat-abi=hard','-mfpu=fpv4-sp-d16']
  command[command.index(entry['file'])]=str(W/label/'native_eabi_m0.cpp')
  command[command.index('-o')+1]=str(W/(context+'-'+label+'.o'))
  subprocess.run(command,cwd=W,check=True);commands.append(command)
  images[context,label]=ElfImage(W/(context+'-'+label+'.o'))
def allocated(e):return {n:e.bytes_at(s) for n,s in e.named_sections.items() if s[2]&2 and s[1]!=8 and s[5]}
tree=ast.parse((ROOT/'.build/m0-exp-cached-product-independent-20261024/bind_rebuild.py').read_text())
fn=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=='relocs')
exec(compile(ast.Module(body=[fn],type_ignores=[]),str(W/'build.py'),'exec'),globals())
def semrelocs(e):return {n:v for n,v in relocs(e).items() if n in allocated(e)}
control,candidate=images['RP','control'],images['RP','candidate']
a,b=allocated(control),allocated(candidate);assert a.keys()<=b.keys()
changed={n:[len(a.get(n,b'')),len(b[n])] for n in b if a.get(n,b'')!=b[n]}
assert set(changed)=={'.m0_exp_core','.m0_exp_tiny'},changed
for n,v in semrelocs(control).items():
 if n!='.m0_exp_core':assert v==semrelocs(candidate)[n],n
assert a['.m0_exp_core']==allocated(ElfImage(B/'candidate-full.o'))['.m0_exp_core']
contexts=[]
for context in ('generic_M0','M4_soft','M4_hard'):
 a,b=[images[context,label] for label in ('control','candidate')]
 assert allocated(a)==allocated(b) and semrelocs(a)==semrelocs(b),context
 contexts.append({'context':context,'all_CPP_allocated_bytes_semantic_relocations_equal':True})
text=(B/'candidate-bindings.ld').read_text().replace('SECTIONS {','PHDRS { flash PT_LOAD FLAGS(5); product PT_LOAD FLAGS(5); }\nSECTIONS {')
text=text.replace('.text : { *(.text*) *(.m0*) }','.text : { *(.text*) *(.m0*) } :flash')
text=text.replace('.rodata : { *(.rodata*) }','.rodata : { *(.rodata*) } :flash')
text=text.replace('KEEP(*(.scratch_y.m0_exp_product_only)) }','KEEP(*(.scratch_y.m0_exp_product_only)) } :product')
(W/'bindings.ld').write_text(text)
for label in ('control','candidate'):
 command=[str(cc/'arm-none-eabi-ld'),'--gc-sections','-e','mk61_m0_exp','-T',str(W/'bindings.ld'),str(W/('RP-'+label+'.o')),str(B/'cached-product.o'),'-o',str(W/(label+'.elf'))]
 subprocess.run(command,cwd=W,check=True);commands.append(command)
 im=ElfImage(W/(label+'.elf'))
 assert not subprocess.check_output([str(cc/'arm-none-eabi-nm'),'-u',str(W/(label+'.elf'))],text=True)
 with (W/(label+'.dis')).open('w') as f:subprocess.run([str(cc/'arm-none-eabi-objdump'),'-dr',str(W/(label+'.elf'))],stdout=f,check=True)
assert allocated(ElfImage(W/'control.elf'))==allocated(ElfImage(B/'candidate.elf'))
patch=''.join(difflib.unified_diff((W/'control/native_eabi_m0.cpp').read_text().splitlines(True),source.splitlines(True),fromfile='a/code/native_eabi_m0.cpp',tofile='b/code/native_eabi_m0.cpp'))
(W/'qualified-f2d-to-exp-tiny.patch').write_text(patch)
out={'status':'BUILT_PRIVATE_FULL_TINY_EXP_MIDPOINT_FLOOR','source_sha256':sha(W/'candidate/native_eabi_m0.cpp'),'candidate_ELF_sha256':sha(W/'candidate.elf'),'control_ELF_sha256':sha(W/'control.elf'),'changed_CPP_sections':changed,'CPP_code_delta_bytes':sum(v[1]-v[0] for v in changed.values()),'all_other_CPP_allocated_bytes_semantic_relocations_equal':True,'control_exp_allocated_bytes_equal_accepted_cached_product':True,'full_ASM_includes_unchanged_qualified_f2d_parent':True,'contexts':contexts,'commands':commands,'no_new_tables_RAM_libgcc':True,'hardware_accessed':False}
(W/'build.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({k:v for k,v in out.items() if k!='commands'},indent=2))
