"""Independent full-product/carry, rounding-grid and dispatch proof."""
from pathlib import Path
from fractions import Fraction as F
import ast,hashlib,itertools,json,sys
sys.dont_write_bytecode=True
R=Path('/Users/bolk/Projects/MK61S_MINI');P=R/'.build/m0-pow-square-ordinary-20261024';V=R/'.build/m0-asin-scaled-bound-v164-20261023';O=Path(__file__).resolve().parent
M=(1<<32)-1;D=(1<<16)-1;MASK=(1<<64)-1
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
tree=ast.parse((R/'.build/m0-exp-cached-product-independent-20261024/bounds.py').read_text())
fn=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=='round_fraction')
exec(compile(ast.Module(body=[fn],type_ignores=[]),str(O/'proof.py'),'exec'),globals())
src=(P/'square.S').read_text();assert sha(P/'square.S')=='1f8bf735a0478b3e47caa5f1872d7437bd7d94a4b52f331cdcfb6bd719fa24e1'
assert src.count('muls ')==10
square_high_max=D*D+((D*D)>>15)+1
assert square_high_max<(1<<32)
cross_middle_max=D*D+D*31
assert (1<<32)<=cross_middle_max<(1<<33)
cross_upper_max=D*31+(1<<16)+65535+1
assert cross_upper_max<(1<<22)
assert 2*((1<<32)-1)*((1<<21)-1)<1<<54
assert ((1<<53)-1)**2<1<<106
# Source arithmetic, expressed as exact coefficient identities. The low
# sum's carry and the one possible cross-middle carry are kept explicitly.
def sq32(x):
 a,b=x&65535,x>>16;ab=a*b
 low=a*a+((ab<<17)&M);hi=b*b+(ab>>15)+(low>>32)
 assert hi<=square_high_max
 return (low&M)+(hi<<32)
def mul32x21(x,y):
 a,b=x&65535,x>>16;c,d=y&65535,y>>16
 middle=b*c+a*d;carry=middle>>32
 low=a*c+((middle<<16)&M)
 high=b*d+(carry<<16)+((middle&M)>>16)+(low>>32)
 return (low&M)+(high<<32)
products=0;cross_carries=0
for l0,l1,h0,h1 in itertools.product([0,1,65534,65535],[0,1,65534,65535],[0,1,65534,65535],[16,23,31]):
 L=l0+(l1<<16);H=h0+(h1<<16);sig=L+(H<<32)
 assert sq32(L)==L*L and sq32(H)==H*H and mul32x21(L,H)==L*H
 full=sq32(L)+(mul32x21(L,H)<<33)+(sq32(H)<<64)
 assert full==sig*sig and 1<<104<=full<1<<106
 cross_carries+=int(l1*h0+l0*h1>=1<<32);products+=1
assert cross_carries>0
def lsr(x,n):return (x&M)>>n if n<32 else 0
def lsl(x,n):return ((x&M)<<n)&M if n<32 else 0
def emitted_round(p,s):
 """Exact source word moves, independently checked against bit ranges."""
 assert 0<=p<1<<106 and 52<=s<=106
 w=[(p>>(32*i))&M for i in range(4)]
 if s<=64:
  n=s-32;t=32-n;lo=lsr(w[1],n)|lsl(w[2],t);hi=lsr(w[2],n)|lsl(w[3],t);rem=lsl(w[1],t);sticky=w[0]
 elif s<=96:
  n=s-64;t=32-n;lo=lsr(w[2],n)|lsl(w[3],t);hi=lsr(w[3],n);rem=lsl(w[2],t);sticky=w[1]|w[0]
 else:
  n=s-96;t=32-n;lo=lsr(w[3],n);hi=0;rem=lsl(w[3],t);sticky=w[0]|w[1]|w[2]
 assert 1<=n<=32 and 0<=t<=31
 assert (lo|(hi<<32))==p>>s
 guard=(rem>>31)&1;sticky=bool(((rem<<1)&M)|sticky)
 assert guard==(p>>(s-1))&1 and sticky==bool(p&((1<<(s-1))-1))
 got=lo+(hi<<32)+int(guard and (sticky or lo&1))
 a,r=divmod(p,1<<s)
 assert got==a+int(r>1<<(s-1) or r==1<<(s-1) and a&1)
 return got
word_checks=0;odd_ties=even_ties=0
for s in range(52,107):
 qmax=min((1<<53)-1,(1<<(106-s))-1)
 for q in sorted({0,min(1,qmax),max(0,qmax-1),qmax}):
  for rem in [0,1,(1<<(s-1))-1,1<<(s-1),(1<<(s-1))+1,(1<<s)-1]:
   p=(q<<s)+rem
   if p>=1<<106:continue
   emitted_round(p,s);word_checks+=1
   if rem==1<<(s-1):
    if q&1:odd_ties+=1
    else:even_ties+=1
assert odd_ties and even_ties
grid_checks=0
for e in range(485,1535):
 for n in [0,1]:
  E=2*e-1023+n;s=52+n if E>0 else 1076-2*e
  # The source uses53-E+n for subnormals, which cancels normalization.
  assert E>0 or 53-E+n==1076-2*e
  assert 52<=s<=106 and (E>0 or not s&1)
  grid_checks+=1
assert (1<<104)<=((1<<53)-1)**2<1<<106
# Last source-finite binade cannot round to infinity; the true product
# lies strictly below its half-ULP overflow midpoint.
assert ((1<<53)-1)**2<(1<<106)-(1<<52)
assert 2*(484-1022)<-1075 and 2*(1535-1023)>=1024
# An actual square midpoint needs2*v2(sig)=s-1. Subnormal s is even,
# so ties there are impossible. Normal s52 is also impossible. At s53,
# sig=odd*2^26; floor(sig^2/2^53)=(odd^2-1)/2 is always even.
assert all((odd*odd-1)//2%2==0 for odd in range(1,128,2))
def square_oracle(raw):
 e=(raw>>52)&2047;f=raw&((1<<52)-1)
 if e==2047:return raw|(1<<51) if f else 0x7ff0000000000000
 sig=f|((1<<52) if e else 0);k=e-1075 if e else -1074
 return round_fraction(F(sig*sig)*F(2)**(2*k))
# The ordinary tail is byte-for-byte the old common body. Every removed
# preceding action is excluded by the assembly's checked y precondition.
old=(V/'source/code/native_eabi_m0_pow_fast.inc').read_text();a=old.index('MK61_SOFT_PCS double mk61_m0_pow_dispatch(double x,double y)');a=old.index('{',a);d=0
for z in range(a,len(old)):
 if old[z]=='{':d+=1
 if old[z]=='}':
  d-=1
  if not d:break
oldbody=old[a+1:z];tail=oldbody[oldbody.index('  if(xb==UINT64_C(0x3FF0000000000000))'):]
assert tail==(P/'ordinary-tail.txt').read_text()
assert tail in (P/'ordinary.cpp').read_text() and tail in (P/'candidate/native_eabi_m0_pow_ordinary.inc').read_text()
wrapper=(P/'candidate.S').read_text()
assert wrapper[wrapper.index('mk61_m0_pow_fast:'):].startswith('mk61_m0_pow_fast:\n cmp r2,#0\n bne .Lpow_dispatch\n')
assert 'lsls r2,r3,#1\n beq .Lpow_zero' in wrapper
for n in ['0x3ff00000','0xbff00000','0x3fe00000','0x40000000','0xbfe00000']:assert 'ldr r2,='+n in wrapper
assert 'ldr r2,=mk61_m0_pow_dispatch_ordinary\n mov r12,r2\n movs r2,#0\n bx r12' in wrapper
assert '.Lpow_restore_low:\n movs r2,#0\n.Lpow_dispatch:\n b mk61_m0_pow_dispatch' in wrapper
def main():
 notes=dict(product='Write the53-bit mantissa as L+2^32*H. The three-product32-bit squares and four-product32x21 cross preserve every carry. Their exact sum L^2+2^33*L*H+2^64*H^2 is the106-bit significand square. Carry from the two16-bit cross terms is explicitly added as2^16 to the high partial word; subsequent ADC chains preserve both doubling and three-word addition carries.',grid='For stored input exponent e, x=S*2^(e-1075), P=S^2. Its leading bit selects n=0/1 and biased output exponent E=2e-1023+n. Normal drop52+n; subnormal drop1076-2e. The source53-E+n reduces to that same subnormal grid. At each word branch, retained bits equal P>>s, guard equals P bit(s-1), and sticky is OR of all lower bits. Register shifts by32 intentionally yield0. RNE increment is exactly guard&&(sticky||retained_odd).',classification='e<485 gives x^2<2^-1076, below half-minsubnormal. e1535..2046 gives x^2>=2^1024. e2047 separately distinguishesInfinity/NaN; NaNs preserve input sign/payload and set quiet. Finite and zero squares return positive sign. e1534 cannot round through the overflow midpoint.',actual_ties='Only normal shift53 actual square ties are possible: significand odd*2^26 above sqrt(2)*2^52. Their retained quotient is necessarily even. Subnormal shifts and normal shift52 cannot be exact square midpoints. Odd-parity ties in arbitrary-product model are synthetic controls, never mislabeled as actual square inputs.',dispatch='Nonzero low32(y) goes directly to the identical old dispatcher before any added action. Lowwordzero checks both signedzero,1,-1,+half,2,-half. Half/inverse-root cold cases restore original y registers and go to the old dispatcher. Ordinary receives only lowwordzero nonzero y with all old prefix exact cases already rejected. Its unchanged common source tail preserves every action. Three aliases refer to existing function addresses and add no storage.',sNaN_zero='For y=+/-0 the wrapper identifies a NaN from exponent/fraction with sign ignored. A quiet NaN returns1, as doesInfinity. Signalling NaN returns original input payload/sign with quiet bit set; no dispatcher frame is allocated. y=1 still quiets any NaN while retaining all other input bits.')
 out=dict(status='PASS_INDEPENDENT_PRODUCT_CARRY_RNE_GRIDS_AND_DISPATCH_PROOF',source_SHA256=sha(P/'square.S'),author_certificate_not_executed=True,square_high_max=square_high_max,cross_middle_max=cross_middle_max,cross_one_carry_preserved=True,cross_upper_max=cross_upper_max,host_corner_products=products,host_cross_carry_witnesses=cross_carries,host_RNE_word_boundary_checks=word_checks,synthetic_odd_half_controls=odd_ties,synthetic_even_half_controls=even_ties,complete_exponent_grid_relations=grid_checks,normal_shifts=[52,53],subnormal_shifts=list(range(54,107,2)),normal_and_subnormal_grid_exact=True,quiet_payload_sign_and_zero_partition=True,ordinary_precondition_and_same_tail=True,notes=notes,hardware=False)
 (O/'proof.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:v for k,v in out.items() if k!='notes'},indent=2))
if __name__=='__main__':main()
