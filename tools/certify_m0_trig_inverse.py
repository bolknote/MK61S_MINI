#!/usr/bin/env python3
"""Bound the narrow integer Newton reciprocal used by RP2040 tangent."""
import argparse
from fractions import Fraction as F
import json
from pathlib import Path


def certificate():
    # d = h*2^32+l, 2^63<=d<2^64.  s=floor(2^63/h),
    # y=s*2^31 and Y=2^126/d.  Writing h*s=2^63-r gives
    # y/Y-1 = -r/2^63+s*l/2^95.  Since 0<=r<h and l<2^32,
    # this lies strictly between -2^-31 and 2^-31.
    relative = F(1, 1 << 31)
    exact_max = 1 << 63
    ideal_error = exact_max * relative**2
    assert ideal_error == 2
    # p=floor(d*y/2^64).  A Newton step using exact p has error
    # -Y*(y/Y-1)^2 + (y/2^62)*frac(d*y/2^64).
    # The first term is in (-2,0], the second in [0,2).
    # Symmetric nearest-even rounding of the correction adds <=1/2.
    floor_error = F(1 << 63, 1 << 62)
    bound = max(ideal_error, floor_error) + F(1, 2)
    assert bound == F(5, 2) and bound < 5

    # For h>2^31, s fits32 bits and r<h<=2^32-1.  c=floor(l*s/2^32)
    # is <=s-1.  Thus floor((c-r)/2) has magnitude <=2^31-1.
    max_remainder = (1 << 32) - 2
    max_cross = (1 << 32) - 2
    max_magnitude = max((max_remainder + 1) // 2, max_cross // 2)
    assert max_magnitude == (1 << 31) - 1
    assert max_remainder + 1 < 1 << 32
    max_product = ((1 << 32) - 1) * max_magnitude
    assert max_product < 1 << 63
    # Rounded s*m/2^31 cannot exceed the integer s, so its final
    # increment and the returned y+-correction cannot overflow.
    assert F(max_product, 1 << 31) < (1 << 32) - 1
    assert (1 << 62) > (1 << 32) - 1
    return dict(
        status='PASS', domain='2^62 <= denominator <2^63; d=2*denominator',
        seed='s=floor(2^63/high32(d)); y=s*2^31',
        seed_relative_error_strictly_below=str(relative),
        ideal_newton_error_strictly_below=str(ideal_error),
        floor_residual_error_strictly_below=str(floor_error),
        correction_rounding_error_at_most='1/2',
        result_absolute_Q62_error_strictly_below=str(bound),
        unchanged_caller_bound=5, maximum_residual_magnitude=max_magnitude,
        maximum_32x32_correction_product=max_product,
        exact_identity='floor(d*y/2^64)-2^62 = floor((floor(low32(d)*s/2^32)-r)/2)',
        endpoint='high32(d)=2^31 uses s=2^32 and returns2^63-(low32(d)&~1).',
        scope='Analytic all-domain bounds and width inequalities. ARM implementation, exact quotient seed and caller RNE intervals require separate execution checks.')


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--json',type=Path,required=True)
    a=p.parse_args();result=certificate()
    a.json.parent.mkdir(parents=True,exist_ok=True)
    a.json.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
