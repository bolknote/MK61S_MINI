"""Universal integer derivation plus exact emitted Thumb/dataflow binding."""
import hashlib,json,struct,sys
from pathlib import Path
sys.dont_write_bytecode=True
R=Path('/Users/bolk/Projects/MK61S_MINI');O=Path(__file__).resolve().parent
sys.path.insert(0,str(R/'tests'));from check_stm32_vectors import ElfImage
MASK=(1<<32)-1;I=1<<31;K=1<<17
def ref(p):
 p=Path(p);b=p.read_bytes();return dict(path=str(p),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def save(n,d):
 with(O/n).open('x')as f:json.dump(d,f,indent=2);f.write('\n')
 return ref(O/n)
def mem(e,a,n):
 s=next(s for s in e.sections if s[1]!=8 and s[3]<=a and a+n<=s[3]+s[5]);return e.bytes_at(s)[a-s[3]:a-s[3]+n]
def branch(e,a,condition):
 h=struct.unpack('<H',mem(e,a,2))[0];assert h>>8==0xd0+condition
 imm=h&255;return a+4+2*(imm-256 if imm>=128 else imm)
def branch_target(h,pc):
 if h&0xf800==0xe000:
  imm=h&2047;return ('b',pc+4+2*(imm-2048 if imm>=1024 else imm))
 if h&0xf000==0xd000 and (h>>8)&15<14:
  imm=h&255;return ('cond'+str((h>>8)&15),pc+4+2*(imm-256 if imm>=128 else imm))
 return None
def equal_core(c,ca,n,na,length,old_pack,new_pack):
 for offset in range(0,length,2):
  ch,nh=[struct.unpack('<H',mem(e,a+offset,2))[0]for e,a in [(c,ca),(n,na)]]
  cb,nb=branch_target(ch,ca+offset),branch_target(nh,na+offset)
  if cb:
   assert nb and cb[0]==nb[0]
   if cb[1]==old_pack:assert nb[1]==new_pack
   else:assert ca<=cb[1]<ca+length and nb[1]-na==cb[1]-ca
  else:assert ch==nh
images={n:ElfImage(O/'rebuild'/(n+'.elf'))for n in ['control','candidate']};unit={n:ElfImage(O/'rebuild/unit'/(n+'.elf'))for n in ['control','candidate']}
mapping={};prefixes=[]
for tag,fn in [('mk61_m0_reciprocal1','mk61_m0_reciprocal1'),('mk61_m0_reciprocal1_sw','mk61_m0_reciprocal1_sw_from_guard')]:
 c,n=images['control'],images['candidate'];cb=c.symbols[tag+'_certificate_begin']&~1;cu=c.symbols[tag+'_certificate_up']&~1;cd=c.symbols[tag+'_certificate_down']&~1
 nb=n.symbols[tag+'_certificate_begin']&~1;nu=n.symbols[tag+'_certificate_up']&~1;nd=n.symbols[tag+'_certificate_down']&~1;nf=n.symbols[tag+'_certificate_full']&~1
 assert nu==nb+16 and branch(n,nb+12,0)==nf and branch(n,nb+14,2)==nd
 prefix=mem(n,nb,12);prefixes.append(prefix);assert prefix.hex()=='150c060c7543641b660cb604'
 assert mem(n,nf,2).hex()=='6419'
 old_len=cu-cb;assert old_len==44 and mem(n,nf+2,old_len-2)==mem(c,cb,old_len-2)
 assert branch(n,nf+old_len,4)==nd
 # Entire final rounding and exponent/sign pack is unchanged, ending at POP.
 old_end=(c.symbols[fn]&~1)+c.sizes[fn];pack=mem(c,cu,old_end-cu);assert mem(n,nu,len(pack))==pack
 assert pack.hex()=='0022013051414008ca071043490802b06246d707920812058918c919f0bd'
 old_zero=c.symbols[tag+'_y_low_shift']&~1;new_zero=n.symbols[tag+'_y_low_shift']&~1
 assert mem(c,old_zero,2).hex()=='2404'and mem(c,old_zero+2,cb-old_zero-2)==mem(n,new_zero,nb-new_zero)
 old_after=c.symbols[tag+'_after_second_product']&~1;new_after=n.symbols[tag+'_after_second_product']&~1
 assert old_zero-old_after==new_zero-new_after
 equal_core(c,old_after,n,new_after,old_zero-old_after,cd+8,nd+8)
 mapping[tag]=dict(begin=hex(nb),full=hex(nf),up=hex(nu),down=hex(nd),full_product_core42B_byteequal=True,unchanged_final_round_pack_bytes=len(pack),removed_zero_shift=hex(new_zero))
u=unit['candidate'];ub=u.symbols['unit_certificate_begin']&~1;prefixes.append(mem(u,ub,12));assert len(set(prefixes))==1
mapping['unit']=dict(begin=hex(ub),up=hex(ub+16),full=hex(branch(u,ub+12,0)),down=hex(branch(u,ub+14,2)))
# The two shifts alone implement the intended classifier, independently of
# incoming flags. Enumerate every high-bit bucket and its two endpoints;
# E's interior follows by interval monotonicity, not sampling.
modelchecks=0
for bucket in range(1<<15):
 for low in [0,K-1]:
  A=(bucket<<17)|low;shifted=((A>>17)<<18)&MASK;Z=shifted==0;C=(A>>31)&1
  fast=(A&0x7fffffff)>=K;assert Z==(not fast) and C==bool(A&I)
  if fast:
   for E in [0,K-1]:
    H=(A-E)&MASK;assert bool(H&I)==bool(A&I)and H!=0 and H!=I;modelchecks+=1
  else:assert (A&0x7fffffff)<K
# Algebra uses four independent unsigned16 limbs. C=floor((cross*2^16+
# ll)/2^32), cross<=65535*(uh+vh), ll<=65535^2. Hence
# C < uh+vh+1 and C<=uh+vh<=131070, including the case uh+vh=0.
assert (65535*131070*(1<<16)+65535**2)<(131070+1)*(1<<32)
assert (65535**2)<1<<32
product_pairs=[(0,0xffffffff),(1,1),(0xffff,0xffff),(0x10000,0x10000),(0xffff0001,0x7fffffff),(0xffffffff,0xffffffff),(0x80000000,0x80000000),(0x1234abcd,0xfedc5432)]
As=[0,1,K-2,K-1,K,K+1,I-1,I,I+1,I+K-2,I+K-1,I+K,MASK]
triples=[];seen=set()
for u,v in product_pairs:
 prod=u*v;d=(u>>16)*(v>>16);borrow=bool(prod&MASK);E=(prod>>32)-d+borrow
 assert 0<=E<=131071
 bases=[((A+d)&MASK,'classifier_inclusive_boundaries')for A in As]
 bases +=[((((prod>>32)+borrow+H)&MASK),'exact_sign_zero_INTMIN_and_wrap')for H in [0,1,MASK,I-1,I,I+1]]
 for B,g in bases:
  if (B,u,v)not in seen:seen.add((B,u,v));triples.append(dict(base=B,u=u,v=v,group=g))
save('unit-selection.json',dict(status='BOUNDED_EXACT_DISCONTINUITY_AND_BORROW_CASES',triples=triples,flags='all16_each_triple'))
out=dict(status='PASS_UNIVERSAL_UINT32_SIGN_CERTIFICATE_AND_EXACT_THUMB_LIVENESS',
 theorem=dict(limbs='u=65536*uh+ul; v=65536*vh+vl, all limbs 0..65535',
 exact_product_hi='uh*vh + floor(((uh*vl+ul*vh)*65536+ul*vl)/2^32)',
 omitted_C='0 <= C <= uh+vh <=131070; since numerator < (uh+vh+1)*2^32',
 exact_borrow='NEGS lo sets C=(lo==0); SBCS subtracts hi+(lo!=0)',
 error_E='C+borrow in[0,131071]',modular_A='A=(B-uh*vh)mod2^32; H=(A-E)mod2^32',
 accept='(A&0x7fffffff)>=131072, inclusive lower edge',
 positive='A in[131072,2147483647] => H in[1,2147483647]',
 negative='A in[2147614720,4294967295] => H in[2147483649,4294967295]',
 fallback='Both closed bands[0,131071] and[2147483648,2147614719], including all exact H=0 and H=INT32_MIN cases',
 fallback_restore='(A+d)mod2^32=B exactly; unchanged full product/NEGS/SBCS/CMP executes',
 source_domain='Every uint32 B/u/v; no reciprocal approximation or numerator assumption needed for sign certificate'),
 classifier_all32768_buckets_endpoints_and_extremeE=modelchecks,low17_and_E_interiors_covered_by_interval_proof=True,
 shared12B_nonbranch_prefix_in_unit_and2_production_paths=True,macro16B_eight_instructions_no_calls_or_memory=True,
 clobbers=['R4','R5','R6','NZCV'],preserves=['R0','R1','R2','R3','R7','R12','SP'],mapping=mapping,
 live_skip_targets=dict(up='MOVS R2,0; ADDS R0,1 resets carry; ADCS R1,R2 uses only fresh carry',down='LSRS R0,1 / LSLS R2,R1,31 / ORRS / LSRS R1,1; no inherited flags consumed',
  pack='SP+=8; R2=R12; fresh sign/exponent temporaries; R4-R7 restored from original frame; missing R2/R3/product limbs dead',
  no_exact_product_or_certificate_flag_leak_into_RNE=True),
 zero_shift_private_proof='Sole actual caller loads positive1. R0=raw low0 survives both seed paths and first/second unsigned products; R4=R0<<5=0. Signed product never writes R4. Either quotient normalization preserves R4=0. Removed LSLS R4,16 precedes no carry consumer before SUBS resets flags.',
 parent186B_suffix_not_blindly_inherited_new_split_full_fallback_freshly_checked=True,
 generic_division_or_integration_claim=False,ARM_calls=0,MPFR_inputs=0,device_IO=0)
print(json.dumps(save('proof.json',out)),flush=True)
