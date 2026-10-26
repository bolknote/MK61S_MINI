"""Exhaustive finite-domain integer/Thumb correspondence for selected LUT."""
import hashlib,json,struct,sys
from collections import Counter
from pathlib import Path
sys.dont_write_bytecode=True
R=Path('/Users/bolk/Projects/MK61S_MINI');O=Path(__file__).resolve().parent
sys.path.insert(0,str(R/'tests'));from check_stm32_vectors import ElfImage
def ref(p):
 p=Path(p);b=p.read_bytes();return dict(path=str(p),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def save(n,d):
 with (O/n).open('x')as f:json.dump(d,f,indent=2);f.write('\n')
 return ref(O/n)
e=ElfImage(O/'seed-only.elf');blob=e.bytes_at(e.named_sections['.seed']);assert len(blob)==312 and e.sizes['mk61_m0_ddiv_seed17']==56
base=e.symbols['mk61_m0_ddiv_seed17']&~1;table=struct.unpack('<128H',blob[56:]);expected=tuple((1<<32)//(65536+512*i+256)for i in range(128))
assert table==expected and base%4==0
adr=struct.unpack_from('<H',blob,6)[0];assert adr&0xf800==0xa000 and(adr>>8)&7==2
assert ((base+6+4)&~3)+(adr&255)*4==base+56
assert blob[8:10]==bytes.fromhex('105a') # LDRH R0,[R2,R0]
M=(1<<32)-1
def signed(x):return x-(1<<32)if x&(1<<31)else x
errors=Counter();corr=Counter();ranges={k:[1<<64,-(1<<64)]for k in ['p','e','ue','q0','residual']};adversarial={};maxdown=maxup=0
for D in range(65536,131072):
 i=(D>>9)-128;assert 0<=i<128 and 0<=2*i<=254 and(base+56+2*i)%2==0
 u=table[i];assert 0<u<65536
 x=(D+1)>>1;p=x*u;assert 0<=p<1<<32 and abs(p-(1<<31))<1<<30
 folded=signed((p<<1)&M);assert folded==2*(p-(1<<31))
 high=folded>>17;assert high==(p-(1<<31))//65536
 ue=u*high;assert -(1<<31)<=ue<1<<31 and signed(ue&M)==ue
 q0=u-(ue>>15);exact=M//D;err=q0-exact;errors[err]+=1
 residual=M-q0*D;assert -(1<<31)<=residual<1<<31 and signed((~(q0*D&M))&M)==residual
 for name,value in [('p',p),('e',high),('ue',ue),('q0',q0),('residual',residual)]:
  if value<ranges[name][0]:ranges[name][0]=value;adversarial[name+'_min']=D
  if value>ranges[name][1]:ranges[name][1]=value;adversarial[name+'_max']=D
 adversarial.setdefault('error_'+str(err),D)
 q,r=q0,residual;down=up=0
 if r<0:
  while r<0:
   q-=1;r+=D;down+=1;assert -(1<<31)<=r<1<<31 and q*D+r==M
 else:
  while r>=D:
   q+=1;r-=D;up+=1;assert 0<=r<1<<31 and q*D+r==M
 assert q==exact and 0<=r<D and 32768<=q<=65535
 maxdown=max(maxdown,down);maxup=max(maxup,up);corr[str((down,up))]+=1
assert dict(errors)=={-1:140,0:5167,1:35252,2:23815,3:1162}and(maxdown,maxup)==(3,1)
# Binding preflight controls reject corrupted constants/layout. They do not
# execute an unqualified altered table, nor qualify other seed variants.
def table_ok(data,address):return len(data)==256 and address%4==0 and tuple(struct.unpack('<128H',data))==expected
assert table_ok(blob[56:],base+56)
neg=[]
for i in [0,63,127]:
 b=bytearray(blob[56:]);b[2*i]^=1;assert not table_ok(bytes(b),base+56);neg.append('entry'+str(i)+'_onebit')
assert not table_ok(blob[56:-2],base+56);neg.append('truncated_halfword')
assert not table_ok(blob[56:],base+57);neg.append('unaligned_base')
sw=(R/'.build/m0-pow-reciprocal-lut-20261025/software.S').read_text()
assert 'push {r0-r3,r7}'in sw and'pop {r0-r3,r7}'in sw and'bl mk61_m0_ddiv_seed17'in sw
save('adversarial-D.json',dict(status='BOUNDED_VALIDATION_INPUTS_FROM_EXACT_DOMAIN_EXTREMES',values=adversarial))
out=dict(status='PASS_SELECTED_TABLE_GENERATION_INDEX_ALIGNMENT_EXHAUSTIVE_SIGNED_MODULAR_AND_CORRECTION_PROOF',
 HOST_integer_domain_inputs=65536,ARM_calls=0,MPFR_inputs=0,table_bytes=256,table_values=128,
 exact_formula='floor(2^32/(65536+512*i+256)), i=0..127',code56_table256_blob312=True,
 actual_Thumb_ADR_decoded_base_and_LDRH_verified=True,lookup_index0to127_byte_offsets0to254_halfword_aligned=True,
 signed_fold_theorem='For |p-2^31|<2^30, signed32(2p mod2^32)=2(p-2^31); ASR17 equals floor((p-2^31)/2^16).',
 signed_multiply_and_ASR15_match_exact_floor=True,exact_initial_quotient='q0=u-floor(u*floor((ceil(D/2)*u-2^31)/2^16)/2^15)',
 ranges=ranges,error_histogram=dict(sorted(errors.items())),max_down=3,max_up=1,correction_histogram=dict(corr),
 deliberate_product_wrap='low32(q0*D), MVN gives (N-q0D) mod2^32; exact residual fits signed32, so BPL tests its true sign.',
 correction='Negative residual: q--,r+=D with BMI on exact nonoverflowing signed sum; nonnegative residual: unsigned CMP, q++,r-=D until r<D. qD+r=N preserved; result unique floor.',
 final_quotient_range=[32768,65535],incoming_NZCV_not_consumed=True,deliberate_modular_operations_not_claimed_nonoverflowing=True,
 negative_table_binding_controls=neg,negative_controls_HOST_only_not_altered_ARM_qualification=True,
 new_R3_is_exact_residual_but_only_volatile_clobber_contract=True,
 private_caller_saves_pops_R0_R3_must_be_freshly_checked=True,old_R3_preservation_not_inherited=True,
 no_new_binary64_precision_RNE_policy=True,private_seed_only_no_generic_division_ABI=True,device_IO=0)
print(json.dumps(save('proof.json',out)),flush=True)
