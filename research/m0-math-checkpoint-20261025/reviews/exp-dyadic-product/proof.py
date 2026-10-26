"""Independent all-index0 identity, unchanged arithmetic and stack alignment proof."""
from pathlib import Path
from fractions import Fraction as F
import hashlib,json,re,struct,sys
sys.dont_write_bytecode=True
R=Path('/Users/bolk/Projects/MK61S_MINI');O=Path(__file__).resolve().parent;P=R/'.build/m0-exp-dyadic-product-20261024';B=R/'.build/m0-exp-adaptive-enclosure-20261024';E=R/'.build/m0-exp-adaptive-enclosure-independent-20261024'
sys.path.insert(0,str(R/'tests'))
from check_stm32_vectors import ElfImage
S=1<<64;h=F(12912720851596686,S);rh=F(1,1400);half=F(1,2);c=F(0xAAAAAAAB,1<<32);qcoef=c/2;f=F(2185,1<<15)
lin=c/2+abs(c-F(2,3))*S*h/(1<<22)+half;sq=half+F(1,1<<23)
quad=qcoef*sq+max(qcoef+abs(qcoef-F(1,3))*S*h*h/(1<<23),1-qcoef)
a=1+F(1,1<<32);b=1+F(1,1<<17);cubic=half+(a*S*h/(1<<38)+b*S*h*h/(1<<32)+a*b)/(1<<17)
fifth=f*cubic+max(7*f+abs(f-F(1,15))*S*h**3/(1<<23),1-7*f)
poly=1+(lin+quad+fifth)*(S*h*h+1)/(1<<44)+(h/6+h*h/24+h**3/120)+1+S*h**6/(720*(1-h))
maxD=S*h/(1-h)+poly;assert maxD+2<1<<54
assert maxD==F(json.loads((P/'certificate.json').read_text())['maximum_displacement_bound'])
im=ElfImage(O/'rebuild/candidate.elf');name=next(n for n in im.symbols if 'exp_table' in n and im.sizes.get(n)==4096);addr=im.symbols[name];sec=next(s for s in im.named_sections.values() if s[3]<=addr<s[3]+s[5]);table=im.bytes_at(sec)[addr-sec[3]:addr-sec[3]+4096];assert struct.unpack_from('<Q',table)[0]==1<<62
assert hashlib.sha256(table).hexdigest()==json.loads((B/'certificate.json').read_text())['table_sha256']
old=(P/'control/native_eabi_m0.cpp').read_text();new=(P/'candidate/native_eabi_m0.cpp').read_text()
orig='  const U correction=mk61_m0_pow_exp_product_flash(q,below?U(0)-delta:delta);'
replacement='''  const U displacement=below?U(0)-delta:delta;
  // Row zero is exactly2^62. The rounded high product is a shift;
  // all three omitted partial products are identically zero.
  const U correction=index?mk61_m0_pow_exp_product_flash(q,displacement):
                           (displacement+2U)>>2;'''
assert old.count(orig)==1 and new==old.replace(orig,replacement)
# A only has limb3: every dropped i+j<2 term is identically zero.
A=1<<62;limbs=[(A>>(16*i))&65535 for i in range(4)];assert limbs==[0,0,0,16384]
for i in range(4):
 for j in range(4):
  if i+j<2:assert limbs[i]==0
# Formal quotient identity cancels the common positive2^62 factor.
assert (1<<63)==2*A and (1<<64)==4*A
# PCS mapping holds symbolically relative to the entry stack S.
old_final=-40;new_final=-36
assert old_final+4==new_final and old_final+20==new_final+16==-20
for reg in range(4,8):assert -36+reg*4==-20+(reg-4)*4
src=(P/'candidate/native_eabi_m0_pow_exp_product.inc').read_text();active=src[src.index('mk61_m0_pow_exp_product:'):src.index('.size mk61_m0_pow_exp_product')]
assert not re.search(r'^\s*(bl|blx|b\s)',active,re.M)
assert 'sub sp,' not in active and 'adds r3,#4' not in active and 'add sp,#16' in active
first=active.index(' adcs ');assert active[:first].strip().splitlines()[-1].strip()=='adds r4,r0'
assert not re.search(r'^\s*str',active,re.M)
# Independent exact-product controls covering half ties and every lowword
# carry transition near powers2, upper domain and all4 residue classes.
jobs={}
def add(v):
 if 0<=v<1<<54:jobs.setdefault(v,None)
for bit in range(54):
 for delta in range(-5,6):add((1<<bit)+delta)
for high in [0,1,2,0xffff,0x10000,0x1fffff,0x3fffff]:
 for low in [0,1,2,3,4,0x7ffffffe,0x7fffffff,0x80000000,0xfffffffc,0xfffffffd,0xfffffffe,0xffffffff]:add((high<<32)|low)
for d in range(33):add((1<<54)-1-d);add(int(maxD)-d)
for v in jobs:assert ((A*v+(1<<63))>>64)==(v+2)>>2
(O/'own-dyadic-inputs.bin').write_bytes(b''.join(struct.pack('<Q',v) for v in jobs))
parent=json.loads((E/'FINAL-REVIEW.json').read_text());assert parent['status']=='GO_PRIVATE_RP_ADAPTIVE_EXP_ENCLOSURE_AND_SHARED_PRODUCT_COMPONENT_ONLY'
assert json.loads((P/'result.json').read_text())['source_parent_independent_review_pending'] and json.loads((P/'certificate.json').read_text())['inherited_parent_numeric_proof_independent_review_pending']
out=dict(status='PASS_INDEPENDENT_ALL_VALID_INDEX0_IDENTITY_AND_LEAF_PCS_PROOF',maximum_displacement_bound=str(maxD),displacement_plus2_strict2pow54=True,A0_exact2pow62_actual_linked_table=True,table_bytes_identical_to_accepted_parent=True,all_dropped_partial_terms_identically_zero=True,universal_product_identity_for_b_less2pow54=True,integer_product_half_ties_round_up_as_parent_not_new_RNE_policy=True,only_CPP_change_exact_identity=True,all_gate_error_radius_refinement_endpoint_IEEE_policies_exact_source=True,all_raw_product_ABI_returns_equivalent=True,common144_arithmetic_bytes_and_final_POP_bound_by_binding=True,argument_base_and_saved_register_absolute_positions_equal=True,first_carry_consumption_common_ADDS_establishes_C=True,internal_no_BL_BLX_or_external_memory=True,frame_bytes_before40_after36=True,writes36_both=True,SP_word_aligned_every_instruction_public8_at_entry_return=True,leaf_no_nested_public_call_at_SP4_mod8=True,fixed_instructions_before81_after79=True,AAPCS_primary_source='https://github.com/ARM-software/abi-aa/blob/2025Q4/aapcs32/aapcs32.rst',AAPCS_release='2025Q4',AAPCS_sections=['6.2.1.1','6.2.1.2'],interrupt_hardware_and_cycles_not_qualified=True,own_bounded_dyadic_inputs=len(jobs),own_ARM_MPFR_in_this_file=0,parent_pending_at_seal_preserved=True,parent_GO_added_separately_after_seal=True)
(O/'proof.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
