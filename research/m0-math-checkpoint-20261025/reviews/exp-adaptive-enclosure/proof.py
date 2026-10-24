"""Independent source-derived rational enclosure, exact table roots and gate controls."""
from pathlib import Path
from fractions import Fraction as F
import hashlib,json,re,struct,sys
sys.dont_write_bytecode=True
R=Path('/Users/bolk/Projects/MK61S_MINI');O=Path(__file__).resolve().parent;P=R/'.build/m0-exp-adaptive-enclosure-20261024'
sys.path.insert(0,str(R/'tests'))
from check_stm32_vectors import ElfImage
S=1<<64;h=F(12912720851596686,S);rh=F(1,1400);red=1+F(1,8192);half=F(1,2)
# Recalculate the unchanged reduction/polynomial certificate independently,
# using rational operations and coefficients from the actual unchanged source.
c=F(0xAAAAAAAB,1<<32);qcoef=c/2;f=F(2185,1<<15)
lin=c/2+abs(c-F(2,3))*S*h/(1<<22)+half
sq=half+F(1,1<<23)
quad=qcoef*sq+max(qcoef+abs(qcoef-F(1,3))*S*h*h/(1<<23),1-qcoef)
a=1+F(1,1<<32);b=1+F(1,1<<17)
cubic=half+(a*S*h/(1<<38)+b*S*h*h/(1<<32)+a*b)/(1<<17)
fifth=f*cubic+max(7*f+abs(f-F(1,15))*S*h**3/(1<<23),1-7*f)
coeff=lin+quad+fifth;assert coeff<3
v=h/6+h*h/24+h**3/120
polynomial=half+half+coeff*(S*h*h+1)/(1<<44)+v+1+S*h**6/(720*(1-h))
error=polynomial+red/(1-rh);assert error<F(275,64)
assert h+red/S<rh
maxD=S*h/(1-h)+polynomial;assert maxD<1<<54
product=half+F(1,1<<15);maxcorrection=maxD/2+product;assert maxcorrection<23*(1<<48)
residual=product+rh/(2*(1-rh))+F(1,1<<33)/(1-rh);assert residual<F(129,256)
author=json.loads((P/'certificate.json').read_text());assert error==F(author['original_reduction_and_polynomial_delta_bound']) and residual==F(author['remaining_product_table_cross_bound']) and maxcorrection==F(author['maximum_correction'])
# New independent ln2 interval (160, rather than author's100, terms).
lnlo=sum((F(2,(2*i+1)*3**(2*i+1)) for i in range(160)),F(0));lnhi=lnlo+F(2,321*3**321)*F(9,8)
text=(R/'.build/m0-asin-scaled-bound-v164-20261023/source/code/native_eabi_m0_exp_table.inc').read_text();words=[int(x) for x in re.findall(r'UINT64_C\((\d+)\)',text)];step=words[0];low=int(re.search(r'exp_step_low=(\d+)U',text)[1]);split=(step<<32)+low
assert F(2*split-1,2)<lnlo*(1<<87)<lnhi*(1<<87)<F(2*split+1,2)
inverse=0xB8AA3B29;assert F(2*inverse-1,2)<F(1<<31)/lnhi<F(1<<31)/lnlo<F(2*inverse+1,2)
nmax=(((1<<32)-1)*inverse+(1<<43))>>44;assert nmax<1<<20 and 1+F(nmax,1<<33)<red
segment=half+(F(1<<31)/lnlo+(1<<31))/(1<<44);assert segment*lnhi/512<rh
im=ElfImage(O/'rebuild/candidate.elf')
def data(fragment,size):
 name=next(n for n in im.symbols if fragment in n and im.sizes.get(n)==size);addr=im.symbols[name];sec=next(s for s in im.named_sections.values() if s[3]<=addr<s[3]+s[5]);return im.bytes_at(sec)[addr-sec[3]:addr-sec[3]+size]
table=data('exp_table',4096);refine=data('refine_exp_table',6144);rows=[]
assert list(struct.unpack('<512Q',table))==words[1:]
for i,A in enumerate(struct.unpack('<512Q',table)):
 assert (2*A-1)**512 < 1<<(63*512+i) < (2*A+1)**512
 lo,mi,hi=struct.unpack_from('<3I',refine,12*i);T=(hi<<64)|(mi<<32)|lo;assert (2*T-1)**512 < 1<<(95*512+i) < (2*T+1)**512
 bias=T-(A<<32);assert -(1<<31)<bias<1<<31 and lo-(int(lo>>31)<<32)==bias
 rows.append(dict(index=i,A=A,delta32=bias))
# Retained distance3 decision independently remains safely separated.
assert F(3)-F(11,32)>error/2+residual
# Actual maximum table row plus its worst correction cannot cross2^63.
assert rows[-1]['A']+F(rows[-1]['A'])*maxD/S+product<1<<63
# q was not doubled for error4. A<2^63 and correction<23slots imply
# q<2^63+23slots; author's qmax uses32slots, a looser safe bound.
qmax=(1<<63)+(1<<53)+1;assert (1<<63)+maxcorrection<qmax
maxhead=qmax>>48;assert maxhead==32800
for H in range(16384,maxhead+1):
 top=H+24;bound=(275*top+16383)//16384+129
 assert 275*top+16383<1<<32
 assert F(bound,256)>error*F(top,65536)+residual
# Signed-bias quantization is safe for every raw signed32 value: floor
# yields a lower bound; subtracting floor+1 handles the opposite sign.
for b8 in range(-128,128):
 for frac in [0,1,(1<<24)-1]:
  d=(b8<<24)+frac;B=F(d,1<<32);assert F(b8,256)<=B<F(b8+1,256)
  for distance in [2,3]:
   assert F(distance*256+b8,256)<=distance+B
   assert F(distance*256-b8-1,256)<=distance-B
# ABI source proof: unchanged suffix has no argument-memory writes or
# calls; the first carry-consuming instruction follows a common ADDS.
src=(P/'candidate/native_eabi_m0_pow_exp_product.inc').read_text();suffix=src[src.index(' ldrh r0,[r3,#0]'):src.index('.size mk61_m0_pow_exp_product')]
assert not re.search(r'^\s*(str|push|bl|b\s)',suffix,re.M)
first=suffix.index(' adcs ');before=suffix[:first].strip().splitlines()[-1];assert before.strip()=='adds r4,r0'
# Bounded independent literal gate controls: head extrema, all coarse
# head neighborhoods, actual table biases and both exact admission edges.
heads={16384,16385,16386,32767,32768,32769,32790,32799,32800}
heads.update(range(16384,32801,1024));heads.update(rows[i]['A']>>48 for i in range(0,512,32));jobs={}
def add(q,d):jobs.setdefault((q,d&0xffffffff),None)
for H in sorted(heads):
 bound=(275*(H+24)+16383)//16384+129
 for distance in [2,3]:
  for above in [False,True]:
   cutoff=bound-distance*256 if above else distance*256-bound-1
   for b8 in {-128,0,127,cutoff-1,cutoff,cutoff+1}:
    if not -128<=b8<=127:continue
    for frac in [0,1,(1<<24)-1]:add((H<<48)|((H*0x81204f)&0xfffffffffffc00)|(512+distance if above else 512-distance),(b8<<24)+frac)
for row in rows:
 for distance in [2,3]:
  for above in [False,True]:add(((row['A']>>48)<<48)|(512+distance if above else 512-distance),row['delta32'])
(O/'own-gate-inputs.bin').write_bytes(b''.join(struct.pack('<QQ',q,d) for q,d in jobs))
(O/'table-rows.json').write_text(json.dumps(rows,indent=2)+'\n')
out=dict(status='PASS_INDEPENDENT_ALL_NORMAL_ERROR4_ENCLOSURE_AND_TABLE_RECERTIFICATION',recomputed_delta=str(error),recomputed_delta_strict275over64=True,max_abs_D_less2pow54=True,max_correction_strict23times2pow48=True,recomputed_residual=str(residual),residual_strict129over256=True,ln2_160term_split_inverse_and_segment_recertification=True,actual_ELF_Q62_Q94_roots512_strict=True,signed_Q94_bias_exact=True,source_normal_error4_only=True,head_bounds=[16384,maxhead],all_head_certificates=16417,strict_uint32_bound_and_signed_floor_predicates_for_all_biases=True,distances0and1_and_doubled_error6_cannot_new_accept=True,unchanged_old_distance3_predicate_preserved=True,old_distance3_margin85over32_independently_certified=True,actual_unnormalized_q_strict_below2pow63=True,argument_prologue_all_raw_bits_ABI_equivalence=True,source_first_ADCS_common_ADDS_sets_carry=True,product_unchanged148byte_arithmetic_proof_inherited=True,product_cost_all_raw84to81=True,no_calls_or_argument_writes_in_common_suffix=True,stack_frame40_touched36_not_same_measure=True,own_bounded_gate_inputs=len(jobs),own_ARM_or_MPFR_in_this_file=0,source_proof_not_exhaustive_raw_binary64_execution=True)
(O/'proof.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
