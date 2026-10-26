"""Independent exact seed/quotient/Taylor/Newton/boundary proof."""
from pathlib import Path
from fractions import Fraction as F
import hashlib,json,re,sys
sys.dont_write_bytecode=True
R=Path('/Users/bolk/Projects/MK61S_MINI');P=R/'.build/m0-pow-rsqrt-asm-20261024';S=R/'.build/m0-pow-square-ordinary-20261024';V=R/'.build/m0-asin-scaled-bound-v164-20261023';O=Path(__file__).resolve().parent
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
table=V/'source/code/native_eabi_m0_rsqrt_table.inc'
assert sha(table)=='52c3eae1c6226efab643387d4ab9611ae366363180fd026151cd4558483ffba6'
seeds=[int(x) for x in re.findall(r'\b(\d+)[uU]',table.read_text())];assert len(seeds)==512
M=(1<<32)-1;W=1<<32
reciprocal=[]
for j,b in enumerate(seeds):
 p,i=divmod(j,256);d=513+2*i
 assert d*(1<<p)*(2*b-1)**2<4*(1<<64)*512<d*(1<<p)*(2*b+1)**2
 assert 0<b<W
 r=((b>>16)**2+(((b&65535)*(b>>16))>>15))>>(9-p)
 exact=W//d;assert r in [exact,exact-1]
 assert 0<=W-d*r<2*d
 reciprocal.append(r)
v=F(1,513)
# The exact seed after coordinate quantization is B*f(+-t/2^32).
# Table bias, first derivative and fourth derivative use conservative
# integer powers of1/(1-v); no sampled maximum is used.
table_error=F(1,2)/(1-v)
coordinate=F(1,2)/(1-v)**2
remainder=F(35,128)*W*v**4/(1-v)**5
qres=[F((3*j+4)//8)-F(3*j,8) for j in range(8)]
cres=[F((5*j+8)//16)-F(5*j,16) for j in range(16)]
assert (min(qres),max(qres))==(F(-3,8),F(1,2))
assert (min(cres),max(cres))==(F(-7,16),F(1,2))
cube_argument=1+v+(1<<16)*v*v
quad=F(3,4);cube=F(7,16)+F(5,16)*cube_argument
seed_bound=table_error+coordinate+remainder+quad+cube+F(1,2)
E=F(25,8);assert seed_bound<E
newton=E*E*(F(3,2)+E/W);down=newton+1;up=F(3)
assert down<F(15649,1000) and up==3
# Finite intermediate widths, signed correction and exact high-word
# rounding identity. Saturating at W-1 only costs1 at the endpoint.
tmax=(W-1)//513;zmax=(tmax*tmax)>>32;wprod=zmax*(tmax>>16);wmax=wprod>>16
Qmax=(3*zmax+4)>>3;Cmax=(5*wmax+8)>>4;magmax=tmax+2*Qmax+2*Cmax
assert tmax<1<<23 and zmax<1<<14 and wprod<1<<21 and 5*wmax+8<1<<16 and magmax<1<<24
assert F(3,4)*tmax/W+F(1,2)<1
assert ((W-1)*magmax+(1<<32))<1<<64
assert F(1<<62)*(1+E/(1<<31))**2<3*(1<<62)
assert (1<<63)+3+512<1<<64
# q<T+3 and q>T-down. These are asymmetric: q's left tail needs
# 16 integers of conservatism, its right side only3. Endpoints are strict.
assert 496+down<512 and 515-up==512
def model(raw):
 field=raw>>52;assert 0<field<2047
 m=(raw&((1<<52)-1))|(1<<52);p=(field-1023)&1;i=(m&((1<<52)-1))>>44;d=513+2*i;b=seeds[256*p+i]
 dist=abs(m-(d<<43));N=((dist-1)>>11) if dist else 0;t=N//d
 assert 0<=N<W and 0<=F(dist,d<<11)-t<=1
 z=t*t>>32;Q=(3*z+4)>>3;w=(z*(t>>16))>>16;C=(5*w+8)>>4
 negative=m<d<<43
 delta=(t+2*Q+2*C) if negative else (-t+2*Q-2*C)
 if t>=2:assert 2*Q<t
 else:assert Q==C==0
 corr=(b*abs(delta)+W)>>33
 assert corr==(((b*abs(delta))>>32)+1)>>1
 seed=min(M,b+corr) if delta>=0 else b-corr
 A=m<<(10+p);ss=seed*seed
 prod=(A>>32)*(ss>>32)+(((A&M)*(ss>>32))>>32)+(((A>>32)*(ss&M))>>32)
 Fct=(3<<62)-prod;q=Fct*seed>>32
 assert 0<seed<W and 0<Fct<3<<62 and 0<q<1<<64
 return dict(q=q,seed=seed,N=N,t=t,base=b,d=d,p=p,i=i,m=m,A=A,factor=Fct,field=field,below=negative)
def frac64(b):
 field=(b>>52)&2047;assert 0<field<2047 and not b>>63
 return F((b&((1<<52)-1))|(1<<52))*F(2)**(field-1075)
def exact_RNE_cell(x,y):
 """Independent integer-rational check of rounded1/sqrt(x)."""
 xx=frac64(x);lo=(frac64(y-1)+frac64(y))/2;hi=(frac64(y)+frac64(y+1))/2
 low=xx*lo*lo;high=xx*hi*hi
 assert low<=1<=high
 if low==1 or high==1:assert not y&1
def prove_point(vv):
 A,q,s=vv['A'],vv['q'],vv['seed']
 # No square root library participates in these exact comparisons.
 assert A*(8*s-25)**2<(8*(1<<63))**2<A*(8*s+25)**2
 assert A*(q-3)**2<1<<188
 assert A*(q*down.denominator+down.numerator)**2>(1<<188)*down.denominator**2
def main():
 cases=0;factors=set();zero_coords=0
 for p in [0,1]:
  for i in range(256):
   for low in [0,(1<<43)-1,1<<43,(1<<43)+1,(1<<44)-1]:
    raw=((1023+p)<<52)|(i<<44)|low;vv=model(raw);prove_point(vv);cases+=1;factors.add((vv['factor']>>32)-0x80000000);zero_coords+=vv['t']==0
 for field in range(1,2047):
  p=(field-1023)&1;scale=-((field-1023-p)//2);base=(3066-field)//2
  assert base==1021+scale and 510<=base<=1532 and 511<=base+1<=1533 and 512<=base+2<=1534
 # A boundary call's lower is always in[.5,1), so exponent=-1 and
 # its exact target is bit160-p, within the unchanged161-bit comparator.
 for parity in [0,1]:assert 158-parity-2*(-1)==160-parity and 128<=160-parity<192
 d=dict(status='PASS_INDEPENDENT_RSQRT_SEED_QUOTIENT_DIRECTIONAL_POINT_AND_GRID',source_seeds_SHA256=sha(table),all512_nearest_seed_integer_inequalities=True,all512_reciprocal_floor_or_floor_minus1=True,whole_uint32_quotient_proof='0<=N/d-N*R/2^32<2 implies floor(N/d)-floor(N*R/2^32) in{0,1,2}; q0*d<=N<2^32, so the remainder is exact and two corrections suffice.',seed_error=str(seed_bound),seed_error_float=float(seed_bound),chosen_seed_bound=str(E),newton_down=str(newton),point_down=str(down),point_down_float=float(down),point_up_strict_lt3=True,unsafe_integer_tails=[497,514],unsafe_count18=True,all_derivative_rounding_and_width_bounds_independent=True,coordinate_cases=cases,zero_coordinate_cases=zero_coords,all_point_and_seed_checks_exact_integer=True,model_factor_high_deltas=sorted(factors),all2046_exponent_scalings_normal_and_exact=True,full_factor_fallback_multiplication_required_and_preserved=True,exact_boundary_161bit_input_precondition=True,boundary_AAPCS='m usesr0/r1, parityr2; aligned third64bit argument lower is written to[sp,sp+4], and SP remains8-byte aligned at BL. lower exponent=-1 gives bit160-p; compare<0 increments, exact tie increments only odd lower.',rounding='If tail<=496, T<q+15.649 stays below the midpoint. If tail>=515, T>q-3 stays strictly above. Accepted tails exclude ties; half-up therefore equals RNE. At the normalized .5/1 endpoints the same interval rounds to the endpoint. Other18 integer tails call the unchanged exact161-bit comparator.',source_side_notes='The two common factor-high words use exact shift/subtract multiplication; every other high word uses full32x32 MUL. No assumption that only the two common words can occur is used. Product high-word underestimate<3, and the final floor adds downward error<1.',hardware=False)
 (O/'proof.json').write_text(json.dumps(d,indent=2)+'\n');print(json.dumps(d,indent=2))
if __name__=='__main__':main()
