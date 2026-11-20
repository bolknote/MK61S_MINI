#!/usr/bin/env python3
"""Project a pow mantissa block onto distinct binary64 exponents."""

import argparse
from fractions import Fraction
from heapq import merge
import json
from time import monotonic

from midpoint_scale_grid import (BASE_UNIT, MIDPOINT_UNIT, MAX_PRECISION, GAP,
                                 log2_approx, logarithm_grid, require)


CONTROL_X = (0x18000000000000, 0x18080000000000)
CONTROL_M = (0x28000000000001, 0x28100000000000)
Y_EXPONENTS = (-64, 63)
X_SCALES = (-1074, 1024)
M_SCALES = (-1075, 1024)


def y_boundary(exponent):
    return (exponent+1023)*BASE_UNIT


def ratio_encoding(numerator, denominator, upward):
    """Directed binary64 encoding of a positive normal rational."""
    exponent = numerator.bit_length()-denominator.bit_length()
    if (numerator < denominator<<exponent if exponent >= 0
            else numerator<<-exponent < denominator):
        exponent -= 1
    assert -1022 <= exponent <= 1023
    shift = 52-exponent
    quotient, remainder = (divmod(numerator<<shift, denominator) if shift >= 0
                           else divmod(numerator, denominator<<-shift))
    return y_boundary(exponent)-BASE_UNIT+quotient+int(upward and bool(remainder))


def absolute_logs(span, significand_unit, precision, scale_range):
    """Directed endpoints for the range of abs(log2(2**scale * significand))."""
    unit = 1 << precision
    lo = log2_approx(span[0], significand_unit, precision)
    hi = log2_approx(span[1]-1, significand_unit, precision)
    require(1 < lo <= hi < unit-3, 'block must be strictly inside the normalized binade')
    positive = [(e, e*unit+lo, e*unit+hi+2) for e in range(max(0,scale_range[0]),scale_range[1])]
    negative = [(e, -e*unit-hi-2, -e*unit-lo)
                for e in range(min(-1,scale_range[1]-1),scale_range[0]-1,-1)]
    return positive, negative


def interval(xlo, xhi, mlo, mhi, inner):
    # Outer endpoints allow one log2 unit for the gap. Inner endpoints
    # use the opposite ends of the two-ulp bounds of the extrema.
    if inner:
        stop = ratio_encoding(mhi-2,xlo+2,False)+1
        first = ratio_encoding(mlo+2,xhi-2,True)
    else:
        stop = ratio_encoding(mhi+1,xlo,False)+1
        first = ratio_encoding(mlo-1,xhi,True)
    return max(first,y_boundary(Y_EXPONENTS[0])), min(stop,y_boundary(Y_EXPONENTS[1]))


def union(ranges):
    """Merge sorted half-open encoding ranges, skipping empty ranges."""
    result = []
    for lo, hi in ranges:
        if lo >= hi:
            continue
        if result and lo <= result[-1][1]:
            result[-1] = result[-1][0], max(hi,result[-1][1])
        else:
            result.append((lo,hi))
    return result


def signed_projection(x, m, precision, x_scales, m_scales):
    require(128 <= precision <= MAX_PRECISION, 'invalid directed precision')
    xlogs = absolute_logs(x,BASE_UNIT,precision,x_scales)
    mlogs = absolute_logs(m,MIDPOINT_UNIT,precision,m_scales)
    intervals = [[[],[]],[[],[]]]
    for xsign, rows in enumerate(xlogs):
        for _, xlo, xhi in rows:
            for msign, cols in enumerate(mlogs):
                sign = xsign^msign
                for inner in (False,True):
                    # For fixed x bounds, sorting f by abs(log2(m))
                    # also sorts both ends of the projected y intervals.
                    part = union(interval(xlo,xhi,mlo,mhi,inner) for _,mlo,mhi in cols)
                    intervals[inner][sign] = union(merge(intervals[inner][sign],part))
    for outer, inner in zip(*intervals):
        require(union(merge(outer,inner)) == outer, 'inner union escaped the outer union')
    return intervals


def binade_count(ranges, exponent):
    lo, hi = y_boundary(exponent), y_boundary(exponent+1)
    return sum(max(0,min(hi,b)-max(lo,a)) for a,b in ranges)


def full_row_witnesses(x, m, precision, exponents):
    """Find a normal chart per binade with every point on one real row in range."""
    # For fixed X, the y interval has only the variation of log2(M).
    xlogs = {e:(lo,hi) for rows in absolute_logs((x[0],x[0]+1),BASE_UNIT,precision,(-1022,1024))
             for e,lo,hi in rows}
    mlogs = [row for rows in absolute_logs(m,MIDPOINT_UNIT,precision,(-1022,1024)) for row in rows]
    witnesses = {}
    for exponent in exponents:
        lo, hi = y_boundary(exponent), y_boundary(exponent+1)
        for e in (1023,-1022,0,-1):
            xlo, xhi = xlogs[e]
            for f, mlo, mhi in mlogs:
                first, stop = interval(xlo,xhi,mlo,mhi,False)
                if not lo < first < stop < hi:
                    continue
                left, right = interval(xlo,xhi,mlo,mhi,True)
                if right-left > 2:
                    witnesses[exponent] = dict(x_scale=e, midpoint_scale=f,
                                               y_negative=(e<0) != (f<0),
                                               y_magnitude=f'{(left+right)//2:016x}')
                    break
            if exponent in witnesses:
                break
    return witnesses


def integer_polynomial_obstruction(m, min_q_bits, precision):
    """Verify an obstruction to a constant multiplier of p on the full grid row."""
    first, stop = m
    require(first%2 == 1 and stop%2 == 0, 'invalid grid of odd midpoints')
    count = (stop-first+1)//2
    last = stop-1
    dmax = (1 << 38)-1
    grid, ln2 = logarithm_grid(precision)
    # For a constant polynomial the total variation of q*ln(m)/ln(x)
    # already exceeds one, in the smallest q binade under consideration.
    require(1075*ln2[1] < 746*grid.unit
            and (1 << min_q_bits)*2*(count-1) > last*746, 'constant obstruction failed')
    require(count == 1 << 43 and last < 1 << 54 and 2*first > last
            and (count-1)//(dmax+1) >= 16, 'large-degree obstruction failed')
    # For 1 <= d <= 7, check the ratio of the lower and upper bounds
    # on D*q/abs(ln(x)). For d >= 8, h>=16 and d*2*h/last>2**-13
    # give a ratio greater than 4**d / 2**14.
    for d in range(1,8):
        h = (count-1)//(d+1)
        ratio = (1-Fraction(1 << (d-1), h**d))*Fraction(2*d*h,last)*Fraction(h*first,2*last)**d
        require(ratio > 1, 'finite-difference obstruction failed')
    return dmax


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--precision',type=int,default=168)
    args = parser.parse_args()
    require(__debug__, 'enable interval assertions')
    start = monotonic()
    intervals = signed_projection(CONTROL_X,CONTROL_M,args.precision,X_SCALES,M_SCALES)
    by_band = []
    for exponent in range(*Y_EXPONENTS):
        counts = [[binade_count(spans,exponent) for spans in scope] for scope in intervals]
        by_band.append(dict(exponent=exponent,outer=counts[0],inner=counts[1]))
    opened = [row['exponent'] for row in by_band if any(row['outer'])]
    witnesses = full_row_witnesses(CONTROL_X,CONTROL_M,args.precision,opened)
    require(witnesses.keys() == set(opened), 'could not find a whole row for every open binade')
    degree = integer_polynomial_obstruction(CONTROL_M,52-max(opened),args.precision)
    print(json.dumps(dict(status='OPEN_DISCRETE_MANTISSAS', gap_bits=GAP, precision=args.precision,
                          elapsed_s=round(monotonic()-start,3), intervals=[list(map(len,s)) for s in intervals],
                          by_band=by_band, relaxed_projection_exact=intervals[0] == intervals[1],
                          full_row_witnesses=witnesses,
                          obstructed_degrees=[0,degree]),sort_keys=True))


if __name__ == '__main__':
    main()
