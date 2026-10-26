"""Own rational derivation; no author certificate code is executed."""
from pathlib import Path
from fractions import Fraction as F
import hashlib,json,re,struct,sys
sys.dont_write_bytecode=True
R=Path('/Users/bolk/Projects/MK61S_MINI');P=R/'.build/m0-exp-cached-product-20261024';V=R/'.build/m0-asin-scaled-bound-v164-20261023';O=Path(__file__).resolve().parent
sys.path.insert(0,str(R/'tests'))
from check_stm32_vectors import ElfImage
S=1<<64;MASK=S-1;H=F(1,1400)
src=(P/'candidate/native_eabi_m0.cpp').read_text()
table_src=(V/'source/code/native_eabi_m0_exp_table.inc').read_text()
words=[int(v) for v in re.findall(r'UINT64_C\((\d+)\)',table_src)]
step_hi,table62=words[0],words[1:];step_lo=int(re.search(r'exp_step_low=(\d+)U',table_src)[1]);assert len(table62)==512
limit=int(re.search(r'magnitude>UINT64_C\((\d+)\)',src)[1]);h=F(limit,S)
# ln(2)=2*atanh(1/3). Bound the positive remaining geometric tail.
ln_lo=sum((F(2,(2*j+1)*3**(2*j+1)) for j in range(100)),F(0))
ln_hi=ln_lo+F(2,201*3**201)*F(9,8)
split=(step_hi<<32)+step_lo
assert F(2*split-1,2)<ln_lo*(1<<87)<ln_hi*(1<<87)<F(2*split+1,2)
inverse=int(re.search(r'significand>>21\),0x([0-9A-F]+)U',src)[1],16)
assert F(2*inverse-1,2)<F(1<<31)/ln_hi<F(1<<31)/ln_lo<F(2*inverse+1,2)
nmax=(((1<<32)-1)*inverse+(1<<43))>>44;assert nmax<1<<20
# floor(x*S) and floor(n*step*S) have opposite directed errors. The
# Q96 nearest-step error is < n/2^33 after changing to the Q64 grid.
reduction_error=1+F(nmax,1<<33)
assert reduction_error<1+F(1,8192) and h+reduction_error/S<H
# The selected n cannot alias a residual by 2^64: the significand-head
# estimate differs by at most this many segments. The source then checks h.
segment_error=F(1,2)+(F(1<<31)/ln_lo+(1<<31))/(1<<44)
assert segment_error*ln_hi/512<H and F(1,1<<11)<H
for e in range(-11,10):
 d=20-e;assert 11<=d<=31 and (((1<<32)-1)>>d)+1<1<<32
assert ((1<<32)-1)*inverse+(1<<62)<S
# Independently reconstructed operation-level quantization errors. The
# square formula omits low^2 plus one cross-product fraction (<2), then
# adds 1; hence |z-S*r^2|<=1, including r=0.
zerr=F(1);c=F(0xAAAAAAAB,1<<32);q=c/2;f=F(2185,1<<15)
linear=c/2+abs(c-F(2,3))*S*h/(1<<22)+F(1,2)
square=F(1,2)+zerr/(1<<23)
quadratic=q*square+max(q+abs(q-F(1,3))*S*h*h/(1<<23),1-q)
ae=1+zerr/(1<<32);be=1+F(1,1<<17)
cubic=F(1,2)+(ae*S*h/(1<<38)+be*S*h*h/(1<<32)+ae*be)/(1<<17)
fifth=f*cubic+max(7*f+abs(f-F(1,15))*S*h**3/(1<<23),1-7*f)
coefficient=linear+quadratic+fifth;assert coefficient<3
zmax=(S*h*h+zerr).__floor__();tmax=(limit+(1<<21))>>22
assert zmax<1<<44 and tmax<1<<32
cubic_intermediate=(zmax>>32)*(tmax>>16)+(1<<16)
cubic_max=cubic_intermediate>>17
fifth_intermediate=(cubic_max+7)*2185
linear_max=(tmax*0xAAAAAAAB+(1<<31))>>32
square_max=(zmax+(1<<22))>>23
quadratic_max=((square_max+1)*0xAAAAAAAB)>>33
tail_max=linear_max+quadratic_max+(fifth_intermediate>>15)
assert cubic_intermediate<1<<32 and fifth_intermediate<1<<32
assert tail_max<1<<31
assert (zmax>>32)*tail_max+(((zmax&0xffffffff)*tail_max)>>32)<1<<64
vmax=h/6+h*h/24+h**3/120
polynomial=F(1,2)+zerr/2+coefficient*(S*h*h+zerr)/(1<<44)+zerr*vmax+1+S*h**6/(720*(1-h))
delta_error=polynomial+reduction_error/(1-H)
# The Q62 table is <2^63. Its nearest error contributes <=.5*exp(h),
# bounded by .5/(1-H). Multiplication contributes its independently
# proven half-up/omitted-limb bound; the delta error is scaled by <.5.
M=(1<<16)-1
omitted_max=M*M+2*M*M*(1<<16)
assert omitted_max==(1<<49)-3*(1<<32)+1
product_error=F(1,2)+F(omitted_max,S)
assert product_error<F(1,2)+F(1,1<<15)
radius=product_error+F(1,2)/(1-H)+delta_error/2
assert radius<4
# The implementation's 4097 tiny guard is checked below; all arithmetic
# bounds here use the sharper exact nmax/omitted errors, independently of
# the slightly looser author certificate.
column2=3*M*M;column3=M*63+2*M*M+32767*M
early=(column2+(column3<<16)+(1<<31))>>32
first4=early+M*63
assert early<1<<18 and first4<1<<23
c4=first4+M*M+32767*M
high5=(c4+((M*63+32767*M)<<16))>>32
assert high5<1<<16 and high5+32767*63<1<<32
assert (5*4+20)%8==0
# Every column >=4 is a multiple of 2^64 in the original product, so
# round(column2+column3) + upper is exactly round(retained full product).
e=ElfImage(P/'candidate.elf')
def symbytes(name):
 a=e.symbols[name];size=e.sizes[name];s=next(s for s in e.sections if s[2]&2 and s[3]<=a<a+size<=s[3]+s[5]);return e.bytes_at(s)[a-s[3]:a-s[3]+size]
tn=next(n for n in e.symbols if 'exp_table' in n and 'refine_' not in n and e.sizes.get(n)==4096)
rn=next(n for n in e.symbols if 'refine_exp_table' in n and e.sizes.get(n)==6144)
raw62=symbytes(tn);raw94=symbytes(rn)
assert list(struct.unpack('<512Q',raw62))==table62
delta32=[]
for i,t62 in enumerate(table62):
 assert (2*t62-1)**512<1<<(63*512+i)<(2*t62+1)**512
 a,b,c=struct.unpack_from('<3I',raw94,i*12);t94=a|(b<<32)|(c<<64)
 assert (2*t94-1)**512<1<<(95*512+i)<(2*t94+1)**512
 d=t94-(t62<<32);assert -(1<<31)<d<1<<31
 assert d==a-(S>>32 if a>>31 else 0)
 delta32.append(d)
# q - true = -delta32/2^32 + remainder, with the latter bounded below.
remaining=radius-F(1,2)+F(1,1<<33)
assert remaining<F(85,32)
assert remaining+F(11,32)<3
assert table62[0]==1<<62 and table62==sorted(table62)
max_delta=S*h/(1-h)+polynomial
assert max_delta<1<<54
# No nonzero table index can normalize; row0 is exactly 1, so remove
# the table's .5 error before doubling. This is essential: 2*radius>6.
assert F(table62[1])*(1-max_delta/S)-product_error>1<<62
normalized=2*(radius-F(1,2));assert normalized<6
assert (1<<63)+(1<<53)+1<S-512
tiny_bound=F(1<<12)/(1-F(1,1<<40));assert tiny_bound<4097
for exp in range(-54,-40):
 for neg in [False,True]:
  shift=-exp-int(neg);assert 40<=shift<=54 and 8<=shift-32<=22
  assert F(2)**(exp+53)/(1-F(1,1<<40))<4097
assert F(4097,1<<40)<F(1,2)
def model(raw):
 """Exact integer transcription of the source up to normal packing."""
 a=raw;m=a&((1<<63)-1)
 if not 0x3C90000000000000<m<0x4090000000000000:return None
 ex=(m>>52)-1023;sig=(m&((1<<52)-1))|(1<<52)
 n=((((sig>>21)*inverse)>>32)>>(20-ex))+1 if ex>=-11 else 0
 if ex>=-11:n>>=1
 shift=ex+12;scaled=(sig<<shift) if shift>=0 else (sig>>-shift)
 r=(scaled-n*step_hi-((n*step_lo)>>32))&MASK
 if a>>63:r=(-r)&MASK
 negative=bool(r>>63);mag=(-r)&MASK if negative else r
 if mag>limit:return dict(fallback='residual',n=n)
 hi,lo=mag>>32,mag&0xffffffff
 z=(hi*hi+((lo*hi)>>31)+1)&((1<<44)-1)
 t=(mag+(1<<21))>>22
 linear=(t*0xAAAAAAAB+(1<<31))>>32;square=(z+(1<<22))>>23
 quadratic=((square+1)*0xAAAAAAAB)>>33
 cubic=(((z>>32)*(t>>16))+(1<<16))>>17;fifth=((cubic+7)*2185)>>15
 tail=(-linear if negative else linear)+quadratic+(-fifth if negative else fifth)
 p=(z&0xffffffff)*abs(tail);corr=(((z>>32)*abs(tail))+(p>>32))>>12
 d=(r+(z>>1)+(-corr if tail<0 else corr))&MASK
 k=-n if a>>63 else n;idx=k&511;k=(k-idx)//512
 q=table62[idx];below=bool(d>>63);b=(-d)&MASK if below else d
 al,bl=q&65535,b&65535
 omitted=al*bl+((al*((b>>16)&65535)+((q>>16)&65535)*bl)<<16)
 product=(q*b-omitted+(1<<63))>>64
 assert q<1<<63 and b<1<<54
 q=q-product if below else q+product;norm=q<1<<62
 if norm:q<<=1;k-=1
 return dict(n=n,index=idx,k=k,q=q,tail=q&1023,normalized=norm,b=b,delta32=delta32[idx],tiny=ex<-40,product_calls=1)
def round_fraction(x):
 """Own exact nearest-even positive rational to IEEE binary64."""
 assert x>=0
 if not x:return 0
 n,d=x.numerator,x.denominator;e=n.bit_length()-d.bit_length()
 if (n<d<<e if e>=0 else n<<-e<d):e-=1
 shift=52-e if e>=-1022 else 1074
 nn,dd=(n<<shift,d) if shift>=0 else (n,d<<-shift)
 q,r=divmod(nn,dd);q+=int(2*r>dd or 2*r==dd and q&1)
 if e<-1022:return q
 if q==1<<53:q>>=1;e+=1
 if e>1023:return 0x7ff0000000000000
 return ((e+1023)<<52)|(q- (1<<52))
def main():
 d=dict(status='PASS_INDEPENDENT_SOURCE_BOUND_PRODUCT_AND_EXP_INTERVALS',author_certificate_not_executed=True,source_sha256=hashlib.sha256(src.encode()).hexdigest(),ln2_step_and_Q31_inverse_nearest=True,nmax=nmax,reduction_error=str(reduction_error),coefficient_error=str(coefficient),polynomial_error=str(polynomial),product_omitted_max=omitted_max,product_error=str(product_error),general_radius=str(radius),general_radius_float=float(radius),required_normal_integer_radius=4,table_removed_remaining=str(remaining),table_removed_remaining_float=float(remaining),distance3_worst_upper=float(remaining+F(11,32)),normalized_radius=str(normalized),normalized_radius_float=float(normalized),required_normalized_integer_radius=6,normalization_only_exact_row0=True,all512_Q62_Q94_nearest_integer_proofs=True,delta32_range=[min(delta32),max(delta32)],all_upper_columns_commute_with_rounding=True,early_rounded_column3_max=early,first_column4_sum_max=first4,high_after_column5_max=high5,product_PCS_stack_bytes=40,tiny_remainder_significand_units=str(tiny_bound),tiny_guard4097_strict=True,tiny_shift_range=[40,54],all_source_variable_shifts_and_fixed_width_intermediates_safe=True,source_intermediate_maxima=dict(z=zmax,t=tmax,cubic32=cubic_intermediate,fifth32=fifth_intermediate,signed_tail=tail_max),new_table_or_global_RAM=False,hardware=False)
 (O/'bounds-result.json').write_text(json.dumps(d,indent=2)+'\n');print(json.dumps(d,indent=2))
if __name__=='__main__':main()
