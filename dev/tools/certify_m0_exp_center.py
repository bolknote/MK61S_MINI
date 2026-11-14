#!/usr/bin/env python3
"""Bound the complete RP2040 dyadic-center exp path with exact rationals."""
import argparse
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import re

from generate_m0_exp_center import render


def certificate(root):
    code = root / 'code'
    s = 1 << 69
    max_h = F(2939, 1 << 22)
    max_c = F(1469, 1 << 21)
    max_t = F(1, 1 << 22)
    # x and n*ln(2)/512 are both truncated to Q69 from below.
    # The step itself is rounded at Q96, and n < 2^20.
    reduction_error = 1 + F(1, 256)
    assert reduction_error == 1 + F(1 << 20, 2 * (1 << 27))
    ln2_lo = sum((F(2, (2*i+1)*3**(2*i+1)) for i in range(44)), F(0))
    ln2_hi = ln2_lo + F(9, 4*89*3**89)
    exp = (code / 'native_eabi_m0_exp_table.inc').read_text()
    step_high = int(re.search(r'UINT64_C\((\d+)\)', exp)[1])
    step_low = int(re.search(r'exp_step_low=(\d+)U', exp)[1])
    full_step = (step_high << 32) + step_low
    assert F(2*full_step-1, 2) < ln2_lo*(1 << 87) < ln2_hi*(1 << 87) < F(2*full_step+1, 2)
    inverse = 0xB8AA3B29
    max_n = (((1 << 32)-1)*inverse+(1 << 43)) >> 44
    assert max_n < 1 << 20
    # The half-up bit of head*inverse stays in the high word for every
    # selected e. Before the modular subtraction, bound the actual
    # residual: head truncation costs at most inverse*2^(9-53), and
    # the error of inverse/2^22 is scaled by |x|<1024.
    assert 65535*(0x3B29+0xB8AA+1) < 1 << 32
    inverse_error = max(abs(F(inverse,1 << 22)-512/lo) for lo in (ln2_lo,ln2_hi))
    reduction_index_error = F(1,2)+F(inverse,1 << 44)+1024*inverse_error
    # If e<-11 then n=0 and |x|<2^-11. Otherwise use the high-word
    # half-up estimate above. In both cases the rounded residual stays
    # strictly inside the first and last supported center intervals.
    assert max(F(1,1 << 11),reduction_index_error*ln2_hi/512)+reduction_error/s < max_h
    assert max_h*s < 1 << 63 # Modular subtraction cannot alias a large residual.
    # The early exact results do not depend on the polynomial.
    tiny = F(1,1 << 54)
    assert tiny/(1-tiny) < F(1,1 << 53) # exp(-tiny)>1-tiny by strict convexity.
    assert 1075*ln2_hi < 1024
    # The extraction and shift logic uses the same segment n as the existing
    # Q64 path. With e<=9 the exact low-Q69 significand shift is <=26.
    assert 9 + 17 == 26 and -(-54 + 17) == 37
    assert (int(max_h*s)-1+(1 << 47)) >> 48 == 1469
    assert max_h*s/(1 << 32)+(1 << 15) < 1 << 32
    # |t| <= 2^-22, a rounded |t| in Q53 has error <=2^-54.
    # The square of that integer is <=2^62, and its rounded Q69
    # half-square is below 2^25. Omitting the signed cubic is safe.
    assert (max_t*(1 << 53))**2 == 1 << 62
    assert (max_t**2*s/2).denominator == 1 and max_t**2*s/2 <= 1 << 24
    square_error = F(1, 2) + s*(max_t+F(1, 1 << 55))/(1 << 54)
    taylor = s*max_t**3/(6*(1-max_t))
    correction_error = square_error + taylor
    assert correction_error < 2
    # The generated even and odd components err by <=1 and <=1/2
    # Q69 units. Subtracting the signed correction from the exact c
    # gives the slope at negative c, adding gives it at positive c.
    center_error = F(3,2)
    assert 1469**2 < 1 << 32
    assert max_c**2*s/(2*(1-max_c))+center_error < 1 << 48
    # Rounding the split slope in Q43 cannot underflow at a nonzero
    # center, even on the negative side. idx=0 packs all zeros.
    assert (max_c**2/(2*(1-max_c))+center_error/s)*(1 << 43)+F(1,2) < 1 << 22
    # Approximate (exp(c)-1)*(exp(t)-1) using the Q43 slope and
    # the Q69(t+adjusted quadratic). Decompose v at bit16: the omitted
    # low*low product is below 2^-11 Q69 units.
    slope = max_c/(1-max_c)
    v = max_t/(1-max_t)
    max_slope = slope*(1 << 43)+F(1,2)+center_error/(1 << 26)
    assert max_slope < 1 << 33
    max_head = v*(1 << 53)+correction_error/(1 << 16)
    assert max_head < 1 << 32
    assert (int(max_slope) >> 32)*max_head < 1 << 32
    assert ((1 << 32)-1)*max_head+65535**2+(65535 << 16)+(1 << 26) < 1 << 64
    slope_error = F(1, 1 << 44)+center_error/s
    v_error = correction_error/s
    linear_error = s*(slope_error*(v+v_error)+slope*v_error)+F(1,2)+F(1,1<<11)
    gc_error = center_error + correction_error + linear_error
    assert gc_error < 13
    # For a nonzero center, h>=2^-22, and the approximation to
    # g(h)=exp(h)-1-h is small enough to keep h-g(h) nonnegative.
    # For center zero the sole term is the rounded half-square.
    assert s*max_t**2*(F(1,2)-max_h/(6*(1-max_h))) > gc_error
    assert max_h/(2*(1-max_h)) + gc_error/(max_t*s) < 1
    assert max_t/2 + square_error/(1 << 15) < 1 # Nonzero rounded Q53 magnitude.
    d_error = gc_error + reduction_error/(1-max_h-F(2,s))
    dmax = int(max_h*s/(1-max_h)+d_error)+1
    assert dmax < 1 << 59
    # The table contributes <1+2^-26 Q69 units: truncate the nearest
    # Q94 value. The product instead uses the integer Q62 base, losing
    # up to 1+2^-33 Q62 units; scale that error by the residual. Also
    # multiply the residual error by the true table factor (<2).
    # Dropping al*dl contributes <4 Q69 units; +2 and nearest rounding
    # of the cross terms leave <2.5 units of multiplication error.
    base_product_error = (1+F(1,1<<33))*dmax/(1 << 62)
    value_error = (1+F(1,1<<26)) + 2*d_error + base_product_error + F(5,2)
    assert value_error < 31
    # |wide32(ah,dl)+wide32(al,dh)| fits 64 bits: ah < 2^31,
    # al < 2^32, dh < 2^27. The final scaled product fits signed64.
    assert (1 << 63) + (1 << 59) + (1 << 29) < 1 << 64
    assert 2*dmax+128+3 < 1 << 63
    # Near the lower binade boundary, a different normalization on the
    # two endpoints cannot affect the nearest rounding (distance >=
    # 2^15 Q69 units even below the boundary). The smallest normal binade
    # has the same nearest spacing below 2^-1022 as just above it.
    assert max_h + reduction_error/s < ln2_lo/512 # Never cross the upper binade.
    assert 2*31 < 1 << 15
    # Reproduce every dyadic-center constant and prove exact enclosing
    # inequalities for the reused table, independently of MPFR.
    assert render() == (code / 'native_eabi_m0_exp_center_table.inc').read_text()
    refine = (code / 'native_eabi_m0_refine_table.inc').read_text()
    block = refine.split('refine_exp_table[512][3]={', 1)[1].split('};', 1)[0]
    rows = [tuple(map(int, m)) for m in re.findall(r'\{(\d+)U,(\d+)U,(\d+)U\}', block)]
    assert len(rows) == 512
    for i, (lo, mid, hi) in enumerate(rows):
        q = lo+(mid << 32)+(hi << 64)
        if i == 0:
            assert q == 1 << 94
        assert (2*q-1)**512 < 1 << (95*512+i) < (2*q+1)**512
    sources = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (
        code / 'native_eabi_m0_exp_center.inc', code / 'native_eabi_m0_exp_center_table.inc',
        code / 'native_eabi_m0_exp_table.inc', code / 'native_eabi_m0_refine_table.inc')}
    return dict(status='PASS_RATIONAL_EXP_CENTER_ENCLOSURE', sources=sources,
                result_error_units_q69=float(value_error), accepted_radius=31,
                normalized_radius=62, coefficient_rows=1470, table_bytes=11760)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--json', type=Path, required=True)
    a = p.parse_args()
    result = certificate(Path(__file__).resolve().parents[2])
    a.json.write_text(json.dumps(result, indent=2) + '\n')
    print(result['status'], result['result_error_units_q69'], '<', result['accepted_radius'])


if __name__ == '__main__':
    main()
