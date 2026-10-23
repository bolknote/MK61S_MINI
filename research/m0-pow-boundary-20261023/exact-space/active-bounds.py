"""Exact rational bounds for a finite binary64 pow-vs-midpoint circuit."""
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
WORK=Path(__file__).resolve().parent

# ln2=2*sum(1/((2k+1)*3^(2k+1))). The geometric majorant bounds the tail.
n=32
lower=2*sum((F(1,(2*k+1)*3**(2*k+1)) for k in range(n)),F(0))
upper=lower+F(9,4*(2*n+1)*3**(2*n+1))
assert 0<lower<upper<1
assert 1074*upper<745
tiny_t=F(745,1<<65)
assert tiny_t<F(1,2) and 2*tiny_t<F(1,1<<54)
# For positive t<=1/2, exp(t)-1<=t/(1-t)<=2t. For negative t,
# 1-exp(-t)<=t. Thus |y|<2^-65 guarantees RNE1 for every finite x>0.
assert 1024>1075*upper and 1024>1024*upper
assert F(1,1<<52)/(1+F(1,1<<52))>F(1,1<<53)
# |y|>=2^63 and x!=1 gives |y*ln(x)|>=1024 from either neighbour of1:
# ln(1-d)<=-d and ln(1+d)>=d/(1+d). This is beyond zero/overflow RNE.
p_upper=1<<63;q_upper=1<<117
coefficient_bits_upper=53*p_upper+54*q_upper
scale_magnitude_upper=1074*p_upper+1075*q_upper
assert coefficient_bits_upper<55*q_upper
assert scale_magnitude_upper<1076*q_upper
assert coefficient_bits_upper+scale_magnitude_upper<1<<128
limbs_upper=(coefficient_bits_upper+15)//16
assert limbs_upper<1<<119
accumulator_upper=limbs_upper*(1<<32)
assert accumulator_upper<1<<151
assert (2*62)<125 and 117<125
record=dict(status='PASS_EXACT_ACTIVE_DOMAIN_INDEX_AND_CARRY_BOUNDS',
    ln2_interval=[str(lower),str(upper)],
    tiny_y_rule='For positive finite x and |y|<2^-65, |y*ln(x)|<745*2^-65 and |exp(y*ln(x))-1|<2^-54. The positive magnitude rounds to1 in binary64 RNE.',
    huge_y_rule='For x!=1 and |y|>=2^63, nearest binary64 neighbours of1 imply |y*ln(x)|>=1024, beyond both zero and overflow RNE thresholds. Sign of log-result selects0 or infinity.',
    active_domain='2^-65<=|y|<2^63 after special/near-one/magnitude rules.',
    reduced_exponent='y=s*p/q, q power-of-two. If q>1,p<2^53,q<=2^117; if q=1,p<2^63.',
    input_x='x=A*2^e with odd A<2^53 and -1074<=e<=1023.',
    midpoint='midpoint=M*2^g with odd M<2^54 and -1075<=g<=970, including zero/subnormal/overflow boundaries.',
    positive_relation='x^(p/q) ? M*2^g iff A^p*2^(e*p) ? M^q*2^(g*q).',
    inverse_relation='x^(-p/q) ? M*2^g iff A^p*M^q*2^(e*p+g*q) has the reversed relation to1.',
    coefficient_bit_bound=str(coefficient_bits_upper),scale_magnitude_bound=str(scale_magnitude_upper),
    lifted_bit_position_bound='strictly less than2^128',radix16_limb_count_bound='strictly less than2^119',
    carry_column_accumulator_bound='strictly less than2^151;160-bit unsigned arithmetic is enough',
    maximum_product_circuit_depth=125,
    termination='A recursive column evaluator has strictly decreasing exponent/circuit depth and finite index loops, so a correctly implemented unlimited-work version terminates mathematically. This does not establish acceptable wall time or a compiled M0 memory/stack bound.',
    firmware_status='No implementation/promotion. Cost feasibility and exact fixed-width code remain required.',
    producer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),hardware_accessed=False,candidate_changed=False,goal_complete=False)
(WORK/'active-bounds.json').write_text(json.dumps(record,indent=2)+'\n')
print('PASS: tiny/huge-y rules; active exponentsp<2^63,q<=2^117;128-bit indices,160-bit accumulators,125 circuit depth.')
