"""Full tiny-exp exact log-midpoint integer threshold, private RP only."""
from pathlib import Path
import ast,difflib,hashlib,json,shlex,shutil,struct,subprocess,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
P=ROOT/'.build/m0-asin-scaled-bound-v164-20261023'
E=ROOT/'.build/m0-exp-tiny-radius-20261024'
B=ROOT/'.build/m0-exp-cached-product-20261024'
sys.path.insert(0,str(ROOT/'tests'))
from check_stm32_vectors import ElfImage
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert not (W/'FROZEN.json').exists()
for label in ('control','candidate'):
 folder=W/label;folder.mkdir(exist_ok=True)
 for p in (E/'candidate').glob('native_eabi_m0*'):
  if p.suffix in ('.cpp','.S','.inc'):shutil.copyfile(p,folder/p.name)
source=(W/'control/native_eabi_m0.cpp').read_text()
start=source.index('// Called only for 2^-54 < |x| < 2^-38.')
stop=source.index('\n#endif',start)
new='''// Integer floor of the distance from a linear midpoint to its exact
// logarithmic input threshold, in input ulps. The full odd-square and
// odd-cube are exact. The source-bound certificate checks that the fourth
// and higher log terms cannot alter floor(cube/(3*2^(52+negative))).
__attribute__((always_inline)) inline uint32_t exp_tiny_log_floor(uint32_t odd,int e,bool negative) {
  const unsigned q=unsigned(e+55)+2U*unsigned(negative);
  // Here odd^3/(3*2^(52+negative))<1, so its certified floor is0.
  if(odd<65536U) return (odd*odd)>>q;
  const U square=wide32(odd,odd);
  const uint32_t low=uint32_t(square),high=uint32_t(square>>32);
  uint32_t result=(low>>q)|(high<<(32U-q));
  const uint32_t tail=low&((1U<<q)-1U);
  const U cube_low=wide32(low,odd);
  const U cube_high=wide32(high,odd)+(cube_low>>32);
  const uint32_t scaled20=uint32_t(cube_high>>20);
  const uint32_t scaled=scaled20>>unsigned(negative);
  const uint32_t cubic=(scaled*43691U)>>17; // exact /3, scaled<65536
  if(negative) result+=unsigned(tail+cubic>=(1U<<q));
  else result-=unsigned(tail<=cubic);
  return result;
}
// Called only for 2^-54 < |x| < 2^-32, hence s=-e-negative is32..54.
// The exact logarithmic correction is strictly between0 and1048577
// input ulps. Only the affected side of a linear midpoint needs products.
__attribute__((noinline,noipa,section(".m0_exp_tiny"))) static U exp_tiny_rne(U a) {
  const bool negative=bool(a>>63);
  const int e=int((a>>52)&0x7FFU)-1023;
  const unsigned s=unsigned(-e)-unsigned(negative);
  const uint32_t hi=(uint32_t(a>>32)&0xFFFFFU)|0x100000U,lo=uint32_t(a);
  uint32_t retained,distance=0;
  bool up,near=false;
  if(s==32) {
    retained=hi;
    const uint32_t half=0x80000000U;
    up=negative?lo>half:lo>=half;
    distance=negative?lo-half:half-lo;
    near=distance && distance<=1048576U;
  } else {
    const unsigned shift=s-32U;
    const uint32_t tail=hi&((1U<<shift)-1U),half=1U<<(shift-1U);
    retained=hi>>shift;
    if(negative) {
      up=tail>half || (tail==half && lo);
      distance=lo;
      near=tail==half && lo && lo<=1048576U;
    } else {
      up=tail>=half;
      distance=0U-lo;
      near=tail+1U==half && lo>0U-1048577U;
    }
  }
  if(near) {
    const uint32_t threshold=exp_tiny_log_floor((retained<<1)|1U,e,negative);
    up=negative?distance>threshold:distance<=threshold;
  }
  const uint32_t displacement=retained+unsigned(up);
  return negative?UINT64_C(0x3FF0000000000000)-displacement:
                  UINT64_C(0x3FF0000000000000)+displacement;
}'''
source=source[:start]+new+source[stop:]
assert source.count('else if(e<-38)')==1
source=source.replace('else if(e<-38)','else if(e<-32)')
(W/'candidate/native_eabi_m0.cpp').write_text(source)
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
assert a.keys()==b.keys()
changed={n:[len(a[n]),len(b[n])] for n in a if a[n]!=b[n]}
assert set(changed)=={'.m0_exp_core','.m0_exp_tiny'},changed
for n,v in semrelocs(control).items():
 if n not in changed:assert v==semrelocs(candidate)[n],n
assert allocated(control)==allocated(ElfImage(E/'RP-candidate.o'))
assert semrelocs(control)==semrelocs(ElfImage(E/'RP-candidate.o'))
contexts=[]
for context in ('generic_M0','M4_soft','M4_hard'):
 a,b=[images[context,label] for label in ('control','candidate')]
 assert allocated(a)==allocated(b) and semrelocs(a)==semrelocs(b),context
 contexts.append({'context':context,'all_CPP_allocated_bytes_semantic_relocations_equal':True})
shutil.copyfile(E/'bindings.ld',W/'bindings.ld')
for label in ('control','candidate'):
 command=[str(cc/'arm-none-eabi-ld'),'--gc-sections','-e','mk61_m0_exp','-T',str(W/'bindings.ld'),str(W/('RP-'+label+'.o')),str(B/'cached-product.o'),'-o',str(W/(label+'.elf'))]
 subprocess.run(command,cwd=W,check=True);commands.append(command)
 assert not subprocess.check_output([str(cc/'arm-none-eabi-nm'),'-u',str(W/(label+'.elf'))],text=True)
 with (W/(label+'.dis')).open('w') as f:subprocess.run([str(cc/'arm-none-eabi-objdump'),'-dr',str(W/(label+'.elf'))],stdout=f,check=True)
assert allocated(ElfImage(W/'control.elf'))==allocated(ElfImage(E/'candidate.elf'))
patch=''.join(difflib.unified_diff((W/'control/native_eabi_m0.cpp').read_text().splitlines(True),source.splitlines(True),fromfile='a/code/native_eabi_m0.cpp',tofile='b/code/native_eabi_m0.cpp'))
(W/'qualified-tiny-to-log-midpoint.patch').write_text(patch)
out=dict(status='BUILT_PRIVATE_EXACT_LOG_MIDPOINT_TINY_EXP',source_sha256=sha(W/'candidate/native_eabi_m0.cpp'),candidate_ELF_sha256=sha(W/'candidate.elf'),control_ELF_sha256=sha(W/'control.elf'),changed_CPP_sections=changed,CPP_code_delta_bytes=sum(v[1]-v[0] for v in changed.values()),all_other_CPP_allocated_bytes_semantic_relocations_equal=True,qualified_parent_control_object_ELF_allocated_bytes_exact=True,ASM_sources_unchanged=True,contexts=contexts,commands=commands,no_new_tables_RAM_libgcc=True,hardware_accessed=False)
(W/'build.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({k:v for k,v in out.items() if k!='commands'},indent=2))
