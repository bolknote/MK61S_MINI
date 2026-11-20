#!/usr/bin/env python3
"""Prove a width obstruction to sign recovery from aligned pow residues."""

from fractions import Fraction
import json


GAP = 16300
ODD_BITS = 53
MAX_P = (1 << 53)-1


def minimum_width(k, maximum_y_shift):
    """Lower bound for the comparator's width formula after common factors."""
    q = 1 << k
    p = min(q >> maximum_y_shift,MAX_P)
    return ODD_BITS*(q-p)+k+2-GAP


def certify():
    ln2_lower = sum(Fraction(2,(2*j+1)*3**(2*j+1)) for j in range(8))
    ln2_upper = ln2_lower+Fraction(9,4*17*3**17)
    assert Fraction(1,2) < ln2_lower < ln2_upper and 1074*ln2_upper < 745

    # For |y| <= 2**-11 both sides of any candidate are positive and m
    # is strictly inside (1/2,2). The nearest unnormalised midpoint to
    # either end is separated by much more than the guard, so its odd
    # part has at least 54 bits (all midpoints in both binades do).
    y_shift = 11
    assert 2*745+1 < 1 << y_shift  # |ln m| < 1/2 < ln 2.
    assert 1 < GAP-y_shift and 116+1 < GAP

    # Powers aligned to the same scale satisfy p*ex = q*em, or
    # p*ex = -q*em after moving the reciprocal to the other side.
    # Since p is odd and |ex| <= 1074, q >= 2048 forces ex=em=0.
    # The midpoint in (1/2,2) has negative em, so this cannot occur.
    k0 = 11
    assert 1074 < 1 << k0

    # Both aligned integers gcd-free after cancellation are >2**L,
    # apart from a potential width discrepancy of one bit. For positive
    # y this follows from B >= 2**(53*q) and gcd(A,B) <= a**p < 2**(53*p).
    # For negative y the odd product itself is >=2**(53*q).
    # When the two operands are within a factor of two, the smaller is
    # >2**(53*(q-p)-1). The least integral N bounding it by 2**N is
    # therefore >=53*(q-p). The ordinary width formula is N+k+2-GAP.
    bounds = {k:minimum_width(k,y_shift) for k in range(k0,117)}
    assert bounds[11] == 92204 and bounds[12] == 200696
    assert all(bounds[k] > bounds[k-1] for k in range(k0+1,117))
    capacities = (49152,88415,147455)
    first_excluded = {width:next(k for k in bounds if bounds[k] > width) for width in capacities}
    assert first_excluded == {49152:11,88415:11,147455:12}
    return dict(gap_bits=GAP, maximum_y_power=-y_shift, first_k_exceeding_capacity=first_excluded,
                minimum_residue_width={k:bounds[k] for k in (11,12,64,115,116)},
                exact_operand_reductions=['align powers of two','cancel every common integer factor'])


if __name__ == '__main__':
    print(json.dumps(certify(),indent=2,sort_keys=True))
