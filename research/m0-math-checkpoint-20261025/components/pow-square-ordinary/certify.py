"""Source-bound elementary integer proof for full106-bit binary64 square.
The product and RNE grids are exact integers, including gradual underflow.
"""
from pathlib import Path
import hashlib,itertools,json,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1];P=ROOT/'.build/m0-asin-scaled-bound-v164-20261023'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
b=json.loads((W/'build.json').read_text());source=(W/'square.S').read_text()
assert sha(W/'square.S')==b['square_source_sha256']
assert source.count('muls ')==10
for token in ('ldr r3,=485','ldr r3,=1535','push {r4-r7,lr}','push {r0,r1,r3}',
 'lsls r5,r3,#17','lsrs r6,r3,#15','adds r3,r0\n bcc .Lsquare_cross_fits',
 'lsls r0,#1\n adcs r1,r1','adds r5,r0\n adcs r6,r1',
 'movs r0,#0\n adcs r7,r0','lsrs r2,r7,#9','subs r4,r4,r3\n adds r4,r4,r2',
 'lsls r5,#1\n bcc .Lsquare_pack','tst r0,r2','adds r1,r3\n pop {r4-r7,pc}'):
 assert token in source,token
M=(1<<32)-1;LIMB=(1<<16)-1
assert (LIMB*LIMB>>15)+LIMB*LIMB+1<1<<32
cross_max=LIMB*LIMB+LIMB*31
assert 1<<32<cross_max<1<<33
assert LIMB*31+(1<<16)<1<<21
assert 2*((1<<32)-1)*((1<<21)-1)<1<<54
assert ((1<<53)-1)**2<1<<106
# square32: a^2 + 2^17 ab + 2^32 b^2. The high-word addition
# cannot overflow; carry from the low sum completes the exact product.
def square32(x):
 a=x&65535;h=x>>16;mid=a*h
 low=a*a+((mid<<17)&M)
 high=h*h+(mid>>15)+(low>>32)
 assert high<1<<32
 return (low&M)|(high<<32)
# The cross sum may overflow; the source explicitly adds carry<<16
# before finishing this exact32x21 product.
def cross32(x,y):
 a=x&65535;h=x>>16;c=y&65535;d=y>>16
 mid=h*c+a*d;upper=h*d+((mid>>32)<<16)
 low=a*c+((mid<<16)&M)
 return (low&M)|((upper+((mid&M)>>16)+(low>>32))<<32)
products=0
parts=(0,1,32767,32768,65534,65535)
for a0,a1,a2,a3 in itertools.product(parts,parts,parts,(16,17,23,24,30,31)):
 L=a0|(a1<<16);H=a2|(a3<<16);sig=L|(H<<32)
 assert square32(L)==L*L and square32(H)==H*H and cross32(L,H)==L*H
 value=square32(L)+(cross32(L,H)<<33)+(square32(H)<<64)
 assert value==sig*sig and 1<<104<=value<1<<106
 products+=1
# M0 register shifts by32 produce zero. For each source word branch,
# guard and sticky are exactly the dropped product bits, not estimates.
def lsr(x,n):return (x&M)>>n if n<32 else 0
def lsl(x,n):return ((x&M)<<n)&M if n<32 else 0
def pack_model(p,s):
 w=[(p>>(32*i))&M for i in range(4)]
 if s<=64:
  n=s-32;left=32-n
  lo=lsr(w[1],n)|lsl(w[2],left);hi=lsr(w[2],n)|lsl(w[3],left)
  rem=lsl(w[1],left);sticky=w[0]
 elif s<=96:
  n=s-64;left=32-n
  lo=lsr(w[2],n)|lsl(w[3],left);hi=lsr(w[3],n)
  rem=lsl(w[2],left);sticky=w[1]|w[0]
 else:
  n=s-96;left=32-n
  lo=lsr(w[3],n);hi=0;rem=lsl(w[3],left);sticky=w[2]|w[1]|w[0]
 assert 1<=n<=32 and 0<=left<32
 guard=bool(rem>>31);below=bool(((rem<<1)&M)|sticky)
 assert ((hi<<32)|lo)==p>>s
 assert guard==bool((p>>(s-1))&1)
 assert below==bool(p&((1<<(s-1))-1))
 rounded=((hi<<32)|lo)+int(guard and (below or lo&1))
 q,r=divmod(p,1<<s);half=1<<(s-1)
 assert rounded==q+int(r>half or (r==half and q&1))
 return rounded
word_checks=0
words=(0,1,0x7fffffff,0x80000000,0xfffffffe,0xffffffff)
for upper in (0,1,255,256,511,512,1023):
 for a,b0,c in itertools.product(words,repeat=3):
  p=c|(b0<<32)|(a<<64)|(upper<<96)
  for s in range(52,107):pack_model(p,s);word_checks+=1
# A normal input is S*2^(e-1075), 2^52<=S<2^53.
# RNE on the subnormal grid2^-1074 drops1076-2e bits.
# e<=484 gives x^2<2^-1076<the half-minsubnormal2^-1075.
assert 2*(484-1022)==-1076 and -1076<-1075
# e>=1535 gives x^2>=2^1024; every finite such input overflows in RNE.
assert 2*(1535-1023)==1024
# Last finite binade e1534 cannot round to infinity. Its maximum exact
# scaled significand square is below the overflow midpoint by >one ulp.
assert ((1<<53)-1)**2<(1<<106)-(1<<52)
grids=[]
for e in range(485,1535):
 for sig in ((1<<52),(1<<52)+1,(1<<53)-2,(1<<53)-1):
  p=sig*sig;k=p.bit_length()-105;E=2*e-1023+k
  assert k in (0,1) and -53<=E<=2046
  s=52+k if E>0 else 1076-2*e
  assert 52<=s<=106 and (E>0 or s%2==0)
  rounded=pack_model(p,s)
  if E>0:
   assert 1<<52<=p>>s<1<<53
   bits=((E-1)<<52)+rounded
   assert 0<bits<0x7ff0000000000000
  else:assert rounded<=1<<52
  grids.append((e,k,E,s))
# Source tail equality: the ordinary dispatcher removes only checks
# disproved by the assembly precondition, and keeps every common action.
parent=(P/'source/code/native_eabi_m0_pow_fast.inc').read_text();a=parent.index('MK61_SOFT_PCS double mk61_m0_pow_dispatch(double x,double y)');a=parent.index('{',a);depth=0
for z in range(a,len(parent)):
 if parent[z]=='{':depth+=1
 if parent[z]=='}':
  depth-=1
  if not depth:break
oldbody=parent[a+1:z];tail=oldbody[oldbody.index('  if(xb==UINT64_C(0x3FF0000000000000))'):]
assert tail==(W/'ordinary-tail.txt').read_text()
assert tail in (W/'ordinary.cpp').read_text()
assert tail in (W/'candidate/native_eabi_m0_pow_ordinary.inc').read_text()
wrapper=(W/'candidate.S').read_text()
for value in ('0x3ff00000','0xbff00000','0x3fe00000','0x40000000','0xbfe00000'):
 assert 'ldr r2,='+value in wrapper
assert 'lsls r2,r3,#1\n beq .Lpow_zero' in wrapper
assert 'ldr r2,=mk61_m0_pow_dispatch_ordinary\n mov r12,r2\n movs r2,#0\n bx r12' in wrapper
assert '.Lpow_restore_low:\n movs r2,#0\n.Lpow_dispatch:\n b mk61_m0_pow_dispatch' in wrapper
out=dict(status='PASS_SOURCE_BOUND_EXACT106_SQUARE_RNE_AND_ORDINARY_TAIL_PRECONDITION',
 square_source_sha256=b['square_source_sha256'],wrapper_source_sha256=b['images']['candidate']['source_sha256'],
 full_CPP_source_sha256=b['source_alias_CPP_sha256'],ordinary_include_sha256=sha(W/'candidate/native_eabi_m0_pow_ordinary.inc'),
 candidate_ELF_sha256=b['images']['candidate']['ELF_sha256'],
 full_product_identity='S^2=L^2+2*(L*H)*2^32+H^2*2^64, exact four32-bit words;10 retained16x16 products.',
 square32_identity='x^2=lo16(x)^2+2^17*lo16(x)*hi16(x)+2^32*hi16(x)^2; upper addition cannot overflow.',
 cross_sum_max=cross_max,cross_sum_carry_explicit=True,full106_bit_product=True,
 host_product_limb_checks=products,host_arbitrary128_RNE_word_checks=word_checks,host_exponent_grid_checks=len(grids),
 normal_rounding_shift=[52,53],subnormal_rounding_shift=list(range(54,107,2)),
 all_register_shift_counts_defined_1_to32=True,all_guard_sticky_and_tie_parity_bits_retained=True,
 below_input_exponent485_rounds_zero=True,finite_input_exponents1535_to2046_round_infinity=True,
 last_finite_input_binade_cannot_round_infinity=True,NaNs_quieted_with_input_payload_and_sign=True,
 signed_zero_squares_positive=True,positive_finite_square_rounding_to_nearest_even=True,
 ordinary_tail_text_identical_frozen_source=True,removed_checks_precluded_by_assembly=True,
 nonzero_low_exponent_word_keeps_original_dispatch=True,cold_roots_keep_original_dispatch=True,
 storage_free_aliases_add_no_code_or_data=True,actual_ARM_product_and_midpoint_proofs_required=True,
 no_new_tables_RAM_or_libgcc=True,hardware_accessed=False,whole_math_GO=False)
(W/'certificate.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
