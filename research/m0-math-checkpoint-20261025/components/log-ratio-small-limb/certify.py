"""Bind the one-sided low-limb seed bounds to the actual source and table."""
from pathlib import Path
from fractions import Fraction as F
import hashlib
import json

W=Path(__file__).resolve().parent
ROOT=W.parents[1]
BASE=ROOT/'.build/m0-ln-endpoint-predicate-20261024'
s=(W/'native_eabi_m0_log70_center.inc').read_text()
p=(BASE/'native_eabi_m0_log70_center.inc').read_text()
start=s.index('  if(uint32_t(uint32_t(delta)+64U)<=128U) {')
endpoint=s.index('  // At either dyadic half-segment endpoint',start)
family=s.index('  // For a small signed low limb,',endpoint)
tail=s.index('  const U q=mk61_m0_log_product46(delta,reciprocal);',family)
original=(s[:start]+s[endpoint:family]+s[tail:]).replace(
    'return q+(uint32_t(r>=den)+uint32_t(r>=2*den));',
    'return q+uint32_t(r>=den)+uint32_t(r>=2*den);')
original=original.replace('  const int32_t signed_correction=negative?-int32_t(correction):int32_t(correction);\n  return q+U(int64_t(signed_correction));','  return negative?q-correction:q+correction;')
assert original==p
for value in [0,1,64,(1<<32)-64,(1<<32)-1,1<<41,(1<<41)-1]:
    low=value&0xffffffff
    selected=((low+64)&0xffffffff)<=128
    ell=low if low<1<<31 else low-(1<<32)
    assert selected==(-64<=ell<=64)
for delta in ((1<<41)-1,1<<41):
    assert (((delta&0xffffffff)+64)&0xffffffff)<=128
assert F(4)+F(1,256)<5
assert F(1)-F(1,256)>0
assert 5*4095<1<<15
assert (65535*512+512)<1<<26
assert ((1<<18)-1)*64+(1<<6)<1<<25
finite=json.loads((W/'seed-domain-proof.json').read_text())
source=hashlib.sha256(s.encode()).hexdigest()
elf=hashlib.sha256((W/'candidate.elf').read_bytes()).hexdigest()
assert source==finite['source_sha256'] and elf==finite['candidate_ELF_sha256']
assert finite['pairs']==67634176 and finite['max_limb_intermediate']<1<<26
out=dict(status='PASS_SOURCE_BOUND_ONE_SIDED_SMALL_LOW_LIMB_SEED',source_sha256=source,candidate_ELF_sha256=elf,
    existing_reciprocal='R=floor(2^75/den)&~63; all1024 actual rows checked',
    input_domain='delta=F*2^32+ell, F0..512, ell-64..64, 0<=delta<=2^41',
    base='floor(F*R/2^14), four exact16-bit limb multiplies; shifts forF0/512',
    low='floor(abs(ell)*(R>>32)/2^14), two uint32 multiplies',
    seed='ell>=0:base+low; ell<0:base-low-2',
    exact_h='H=delta*2^29/den',
    positive_bound='0<=H-seed<4+1/256<5',negative_bound='0<1-1/256<H-seed<5',
    proof='P=delta*R/2^46;0<=H-P<2. A=base+alpha,L=low+beta,alpha,beta in[0,1); eta=abs(ell)*(Rmod2^32)/2^46 in[0,1/256). Positive:P-seed=alpha+beta+eta; negative:alpha-beta-eta+2.',
    exact_floor_correction_range=[0,4],reconstructed_uint32_remainder_below=5*4095,
    endpoint_branch_implies_family_guard=True,endpoint_32bit_bool_sum_at_most=2,
    entire_parent_reconstructed_by_removing_family_guard_body_grouping_and_signed_return=True,
    generic_signed_return_equivalence='q-c or q+c equals q+U(int64_t(negative?-int32_t(c):int32_t(c))), modulo2^64; c0..7',
    host_exhaustive_pairs=67634176,host_exhaustion_is_not_ARM_execution=True,
    no_new_tables_global_RAM_or_libgcc=True,hardware_accessed=False)
(W/'certificate.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps(out,indent=2))
