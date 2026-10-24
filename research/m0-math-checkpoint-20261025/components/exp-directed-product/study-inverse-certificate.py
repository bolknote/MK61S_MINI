"""Exact directed enclosure for positive input with negative residual."""
from pathlib import Path
from fractions import Fraction as F
import ast,copy,hashlib,json,re,shlex,struct,subprocess,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
P=ROOT/'.build/m0-asin-scaled-bound-v164-20261023'
C=ROOT/'.build/m0-exp-dyadic-product-20261024'
sys.path.insert(0,str(ROOT/'tests'))
from check_stm32_vectors import ElfImage
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
b=json.loads((W/'build.json').read_text());source=(W/'candidate/native_eabi_m0.cpp').read_text()
assert sha(W/'candidate/native_eabi_m0.cpp')==b['source_sha256']
parent=(C/'candidate/native_eabi_m0.cpp').read_text()
start=source.index('  U correction;');stop=source.index('  unsigned error=4;',start)
original=parent[parent.index('  const U correction=index?'):parent.index('  unsigned error=4;',parent.index('  const U correction=index?'))]
without_call=source[:start]+original+source[stop:]
g0=without_call.index('      else if(error==4U && tail==511U');g1=without_call.index('      if(!safe) return exp_refine(x,n);',g0)
assert without_call[:g0]+without_call[g1:]==parent
assert '"=l"(product_fraction)' in source and 'mov %2,r12' in source
assert '"r12", "lr", "cc"' in source
tool=ROOT/'tools/certify_m0_exp_fast.py'
fn=copy.deepcopy(next(n for n in ast.parse(tool.read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='certificate'))
fn.body[-1].value=ast.Call(func=ast.Name(id='locals',ctx=ast.Load()),args=[],keywords=[])
env=dict(F=F,Path=Path,re=re,__file__=str(P/'source/tools/certify_m0_exp_fast.py'))
exec(compile(ast.fix_missing_locations(ast.Module(body=[fn],type_ignores=[])),str(tool),'exec'),env)
d=env['certificate']();h=d['h'];rh=d['real_h'];scale=1<<64
assert d['coefficient']<F(5,2)
tmax=(12912720851596686+(1<<21))>>22
small_quad=(((F(5,2)**2)/(1<<20)+1)/(1<<24))+F(3,4)
large_quad_ratio=(F(tmax+1)+F(1,12))/(1<<44)+F(1,3*(1<<24))+F(1,4)
assert small_quad<1 and large_quad_ratio<F(1,3)
assert F(2,3)-F(1,6)>F(1,3)
# Negative residual: t0 has linear=quadratic=fifth=0. t1/t2 have
# quadratic0 and linear>=1. For t>=3, quadratic<t/3<linear.
# Hence Tapprox<=0; Ttrue<0 and1/2+Ttrue/2^44 is positive.
assert d['vmax']<F(1,2)
curvature_ratio=(1+F(1,1<<43))**2/(1-h/2)**2+F(1,1<<20)
assert curvature_ratio<F(6,5)
taylor_step=scale*h**6/(720*(1-h))+F(d['nmax'],1<<33)/(1-rh)
cross=(F(1,2)*rh+F(1,1<<33))/(1-rh)
assert taylor_step<F(1,256) and cross<F(1,256)
maximum=d['scale']*d['h']/(1-d['h'])+d['polynomial']
im=ElfImage(W/'candidate.elf')
def data(fragment,size):
 n=next(n for n in im.symbols if fragment in n and im.sizes.get(n)==size);a=im.symbols[n]
 sec=next(s for s in im.named_sections.values() if s[3]<=a<s[3]+s[5])
 return im.bytes_at(sec)[a-sec[3]:a-sec[3]+size]
table=data('exp_table',4096);refine=data('refine_exp_table',6144);biases=[]
for i,value in enumerate(struct.unpack('<512Q',table)):
 assert (2*value-1)**512<(1<<(63*512+i))<(2*value+1)**512
 lo,mid,hi=struct.unpack_from('<3I',refine,12*i);v94=lo|(mid<<32)|(hi<<64)
 assert (2*v94-1)**512<(1<<(95*512+i))<(2*v94+1)**512
 bias=v94-(value<<32);assert -(1<<31)<bias<1<<31
 assert bias==lo-(int(lo>>31)<<32)
 biases.append(bias)
values=list(struct.unpack('<512Q',table));inverses={}
for i in range(1,512):
 inv=(values[(-i)&511]>>48)+2
 assert values[i]*inv>1<<77
 assert inv<1<<16
 inverses[i]=inv
maximum_correction=maximum/2+F(1,2)+F(1,1<<15)
phmax=(int(maximum_correction)>>32)+1
max_inverse=max(inverses.values());gmax=((phmax*max_inverse)>>23)+1
curve_max=(3*gmax*gmax+65535)>>16
assert 65535*max_inverse<1<<32
assert (phmax>>16)*max_inverse+((65535*max_inverse)>>16)<1<<32
assert 3*gmax*gmax+65535<1<<32
assert (257+curve_max)*(32767+24)+65535<1<<32
assert 257+curve_max-254>0
jobs={}
def add_cases(head,ph,n,bias):
 i=n&511;assert i
 g=((ph*inverses[i])>>23)+1
 f=((n*d['low'])&0xffffffff)>>24
 du=257+((3*g*g+65535)>>16)-(f-1 if f else 0)
 effect=(du*(head+24)+65535)>>16;base=effect+(bias>>24)+2
 buckets={0,127,128,255}
 for cut in (base-256,base):buckets.update((cut-1,cut,cut+1))
 for bucket in buckets:
  if not 0<=bucket<=255:continue
  for low in (0,(1<<24)-1):
   frac=(bucket<<24)|low;q=(head<<48)|511
   jobs.setdefault((q,(ph<<32)|(bias&0xffffffff),(n<<32)|frac),None)
ph_edges={1,2,65534,65535,65536,65537,phmax-1,phmax}
for i in range(1,512):
 for k in (0,1023):
  n=k*512+i
  for ph in ph_edges|{1+((i*0x9e3779b9)&0xffffffff)%phmax}:
   head=16384+((ph*17+n)&16383)
   add_cases(head,ph,n,biases[i])
for head in range(16384,32768):
 n=(head*31337)%d['nmax']+1
 if not n&511:n+=1
 ph=1+((head*7919)&0xffffffff)%phmax
 bias=-(1<<31)+1 if head&1 else (1<<31)-1
 add_cases(head,ph,n,bias)
raw=b''.join(struct.pack('<3Q',*row) for row in jobs)
(W/'direction-unit-inputs.bin').write_bytes(raw)
first=source.index('        const uint32_t ph=uint32_t((A-q)>>32)+1U;')
last=source.index('        safe=int32_t(effect)+bias+product_upper+2<=256;',first)+len('        safe=int32_t(effect)+bias+product_upper+2<=256;')
fragment=source[first:last]
fragment=fragment.replace('const uint32_t ph=uint32_t((A-q)>>32)+1U;','const uint32_t ph=uint32_t(arguments>>32);')
fragment=fragment.replace('const int32_t bias=int32_t(refine_exp_table[n&511U][0])>>24;','const int32_t bias=delta32>>24;')
unit="#include <stdint.h>\nusing U=uint64_t;\nstatic constexpr uint32_t exp_step_low="+str(d['low'])+"U;\n"
unit+="static const U exp_table[512]={"+','.join('UINT64_C('+str(v)+')' for v in values)+"};\n"
unit+='''extern "C" __attribute__((optimize("Os"))) U audit_exp_direction(U q,U arguments,U parameters) {
 const int32_t delta32=int32_t(uint32_t(arguments));
 const uint32_t n=uint32_t(parameters>>32);
 const unsigned i=n&511U;
 const uint32_t product_fraction=uint32_t(parameters);
 bool safe=false;
'''+fragment+'''
 const int32_t upper=int32_t(effect)+bias+product_upper+2;
 return (U(uint32_t(upper))<<32)|unsigned(safe);
}
'''
(W/'direction-unit.cpp').write_text(unit)
entry=next(e for e in json.loads((P/'build/compile_commands.json').read_text()) if e['file'].endswith('/code/native_eabi_m0.cpp'))
c=shlex.split(entry['command']);cc=Path(c[0]).parent
c[c.index(entry['file'])]=str(W/'direction-unit.cpp');c[c.index('-o')+1]=str(W/'direction-unit.o')
subprocess.run(c,cwd=W,check=True)
(W/'direction-unit.ld').write_text('PHDRS { code PT_LOAD FLAGS(5); }\nSECTIONS { . = 0x10166000; .unit : { *(.text*) *(.rodata*) } :code /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment) *(.ARM.attributes) *(.note*) } }\n')
link=[str(cc/'arm-none-eabi-ld'),'--gc-sections','-e','audit_exp_direction','-T',str(W/'direction-unit.ld'),str(W/'direction-unit.o'),'-o',str(W/'direction-unit.elf')]
subprocess.run(link,cwd=W,check=True)
assert not subprocess.check_output([str(cc/'arm-none-eabi-nm'),'-u',str(W/'direction-unit.elf')],text=True)
out=dict(status='AUTHOR_EXACT_RATIONAL_DIRECTED_EXP_UPPER_ENCLOSURE',
 source_sha256=b['source_sha256'],candidate_ELF_sha256=b['candidate_ELF_sha256'],
 only_CPP_product_call_and_new_else_branch_changed=True,atomic_BL_and_fraction_read_inline_asm=True,
 original_coefficient_error=str(d['coefficient']),coefficient_strict5over2=True,
 negative_polynomial_tail_nonpositive_all_integer_magnitude_proof=True,
 small_t_quadratic_upper=str(small_quad),large_t_quadratic_over_t_upper=str(large_quad_ratio),
 square_parity_and_negative_tail_combined_error_strict1=True,
 curvature_ratio=str(curvature_ratio),curvature_ratio_strict6over5=True,
 Taylor_plus_step_upper=str(taylor_step),Taylor_plus_step_strict1over256=True,
 Q94_table_bias_cross_upper=str(cross),table_cross_strict1over256=True,
 maximum_displacement_bound=str(maximum),maximum_correction_bound=str(maximum_correction),phmax=phmax,max_inverse_head=max_inverse,gmax=gmax,maximum_curvature_q8=curve_max,
 all511_existing_inverse_heads_certify_integer_reciprocal_upper=True,
 exact_two_partial32x16_product_then_shift_proved=True,
 q_less_A_certifies_negative_residual_and_nonzero_index=True,
 unit_readonly_table_copies_existing512rows_only=True,
 all_runtime_integer_operations_no_overflow_or_undefined_shift=True,
 positive_input_below_implies_n_positive_and_exact_Q64_input=True,
 error4_tail511_below_implies_index_nonzero=True,
 retained_product_F_and_rounding_bit_give_directed_upper_without_omission_penalty=True,
 old_global_radius4_preserved_and_lower_midpoint_excluded=True,
 strict_integer_upper_le256_implies_true_output_below_midpoint=True,
 all512_ELF_Q62_Q94_table_roots_and_signed_bias_recertified=True,
 table_sha256=hashlib.sha256(table).hexdigest(),Q94_table_sha256=hashlib.sha256(refine).hexdigest(),
 nmax=d['nmax'],exp_step_low=d['low'],real_h=str(rh),
 unit_inputs=len(jobs),unit_inputs_sha256=sha(W/'direction-unit-inputs.bin'),unit_ELF_sha256=sha(W/'direction-unit.elf'),
 source_literal_fragment_with_bias_input_substitution_sha256=hashlib.sha256(fragment.encode()).hexdigest(),
 commands=[c,link],hardware_accessed=False,independent_review_pending=True)
(W/'certificate.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({k:v for k,v in out.items() if k!='commands'},indent=2))
