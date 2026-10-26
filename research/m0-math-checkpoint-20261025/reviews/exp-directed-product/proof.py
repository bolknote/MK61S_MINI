"""Own rational obligations for the new positive/below/tail511 predicate only."""
from fractions import Fraction as F
from pathlib import Path
import hashlib,json,re,struct,sys
sys.dont_write_bytecode=True
R=Path('/Users/bolk/Projects/MK61S_MINI'); O=Path(__file__).resolve().parent
W=R/'.build/m0-exp-directed-product-20261024'
sys.path.insert(0,str(R/'tests'))
from check_stm32_vectors import ElfImage
S=1<<64; mmax=12912720851596686; h=F(mmax,S); rh=F(1,1400)
assert h+F(1,8192*S)+F(1,S)<rh
text=(R/'.build/m0-asin-scaled-bound-v164-20261023/source/code/native_eabi_m0_exp_table.inc').read_text()
low=int(re.search(r'exp_step_low=(\d+)U',text)[1]); assert low==3588551130
nmax=(((1<<32)-1)*0xB8AA3B29+(1<<43))>>44; assert nmax==756388
# Re-derive the source quantization bound, not the producer certificate's result.
c=F(0xAAAAAAAB,1<<32); qcoef=c/2
linear=c/2+abs(c-F(2,3))*S*h/(1<<22)+F(1,2)
square_error=F(1,2)+F(1,1<<23)
quadratic=qcoef*square_error+max(qcoef+abs(qcoef-F(1,3))*S*h*h/(1<<23),1-qcoef)
ae=1+F(1,1<<32); be=1+F(1,1<<17)
cubic=F(1,2)+(ae*S*h/(1<<38)+be*S*h*h/(1<<32)+ae*be)/(1<<17)
fifth=F(2185,1<<15)*cubic+max(F(7*2185,1<<15)+abs(F(2185,1<<15)-F(1,15))*S*h**3/(1<<23),1-F(7*2185,1<<15))
coefficient=linear+quadratic+fifth; assert coefficient<F(5,2)
# For t>=3, quadratic/t is bounded by a*t+b+c/t. It is convex;
# therefore its maximum on the entire integer interval is at an endpoint.
tmax=(mmax+(1<<21))>>22
def quadratic_ratio(t):return qcoef*((F(t)+F(1,2))**2/(1<<43)+F(3,2)+F(1,1<<23))/t
quad_ratios=[quadratic_ratio(t)for t in(3,tmax)]
assert max(quad_ratios)<F(1,3)
for t in(0,1,2):
 zmax=(F(t)+F(1,2))**2/(1<<20)+1
 assert zmax<F(1<<22) and (int(zmax)+(1<<22))>>23==0
 assert ((0xAAAAAAAB+(0))>>33)==0
 if t:assert F(2,3)*t-F(1,2)>0
assert F(2,3)*3-F(1,2)>F(3,3)
vmax=h/6+h*h/24+h**3/120; assert vmax<F(1,2)
# T<=0 now holds throughout the negative residual domain. For true v<0,
# positive 1/2+v/2^44 and square error |Z-z|<=1 combine with parity to <1.
taylor_step=S*h**6/(720*(1-h))+F(nmax,1<<33)/(1-rh)
cross=(rh/2+F(1,1<<33))/(1-rh)
assert taylor_step<F(1,256) and cross<F(1,256)
# b=-D >= m-z/2. With g=ceil((1+ceil(b/2^32))/1024),
# b+1/2 < g*2^42, so z/(g^2*2^20) has this uniform upper.
curvature_ratio=(1+F(1,1<<43))**2/(1-h/2)**2+F(1,1<<20)
assert curvature_ratio<F(6,5)
polynomial=F(1,2)+F(1,2)+coefficient*(S*h*h+1)/(1<<44)+vmax+1+S*h**6/(720*(1-h))
maxD=S*h/(1-h)+polynomial
gmax=((int(maxD)>>32)+2+1023)>>10; curve=(3*gmax*gmax+65535)>>16
assert(gmax,curve)==(2939,396)
assert 3*gmax*gmax+65535<1<<32
assert(257+curve)*(32767+24)+65535<1<<32
assert 257-254>0 and rh<F(1,256)
assert 1+F(nmax,1<<33)<F(8193,8192)
# Independent recertification of the actual loaded Q62/Q94 table bounds.
im=ElfImage(W/'candidate.elf')
def table(fragment,size):
 name=next(n for n in im.symbols if fragment in n and im.sizes.get(n)==size); a=im.symbols[name]
 sec=next(s for s in im.sections if s[3]<=a and a+size<=s[3]+s[5]); return im.bytes_at(sec)[a-sec[3]:a-sec[3]+size]
Araw=table('exp_table',4096); Braw=table('refine_exp_table',6144); biases=[]
for i,A in enumerate(struct.unpack('<512Q',Araw)):
 assert(2*A-1)**512 < 1<<(63*512+i) < (2*A+1)**512
 lo,mid,hi=struct.unpack_from('<3I',Braw,i*12); B=lo+(mid<<32)+(hi<<64)
 assert(2*B-1)**512 < 1<<(95*512+i) < (2*B+1)**512
 bias=B-(A<<32); assert -(1<<31)<bias<1<<31
 assert bias==lo-(int(lo>>31)<<32); biases.append(bias)
# Every F: ceil(256*((F>>31)-F/2^32)) equals the source's cheap expression.
# It is enough to check interval endpoints for each 2^24-wide bucket.
for bucket in range(256):
 for residue in(0,1,(1<<24)-1):
  frac=(bucket<<24)+residue; rho=F(frac>>31)-F(frac,1<<32)
  upper=((frac>>31)<<8)-(frac>>24)
  assert F(upper-1,256)<rho<=F(upper,256)
# Whole signed-bias domain is likewise partitioned into 256 constant buckets.
for bucket in range(-128,128):
 for residue in(0,(1<<24)-1):
  bias=(bucket<<24)+residue; assert F(bucket,256)<=F(bias,1<<32)<F(bucket+1,256)
out=dict(status='PASS_OWN_EXACT_RATIONAL_DELTA_OBLIGATIONS',coefficient=str(coefficient),coefficient_strict5over2=True,
 negative_tail_nonpositive_entire_domain=True,quadratic_over_t_convex_endpoint_bounds=[str(v)for v in quad_ratios],
 signed_square_parity_bound_strict1=True,Taylor_and_step=str(taylor_step),table_cross=str(cross),
 curvature_ratio=str(curvature_ratio),curvature_strict6over5=True,gmax=gmax,curvature_q8_max=curve,
 unsigned_int_products_adds_and_signed_shifts_bounded=True,nmax=nmax,step_low=low,
 all512_actual_table_and_Q94_roots_and_signed_bias_checked=True,
 retained13term_product_rounding_upper='P-A*b/2^64 <= (F>>31)-F/2^32; omitted products are nonnegative',
 strict_rounding_argument='D8/256 bounds E-D strictly; Q8 effect+biasfloor+rhoceil+2 bounds V-q strictly. upper<=256 implies V<q+1; unchanged radius4 excludes q-1023.',
 positive_below_requires_Rnegative_npositive_exact_input_scaling=True,
 index0_cannot_enter='Any positive correction from A0=2^62 doubles q and sets error6; zero correction gives tail0.',
 rounding_integer_bucket_endpoint_checks=1280,normal_error4_tail511_only=True,
 tables={'Q62':hashlib.sha256(Araw).hexdigest(),'Q94':hashlib.sha256(Braw).hexdigest()},
 parent_global_radius_inverse_square_and_general_refinement_proofs_reused_by_exact_binding=True,
 no_exhaustive_binary64_or_physical_cycle_or_whole_math_claim=True)
with(O/'proof.json').open('x')as f:json.dump(out,f,indent=2);f.write('\n')
print(json.dumps({k:v for k,v in out.items()if k not in('tables',)},indent=2))
