#!/usr/bin/env python3
"""Exclude pow midpoints on a fixed base row using a polynomial in both indices."""

import argparse
from dataclasses import dataclass
from fractions import Fraction
from functools import partial
import gzip
import json
from pathlib import Path
from time import perf_counter

from midpoint_entire_surface import divide_integer, exp_near_zero, exp_upper, reduce
from midpoint_grid import add, ceil_div, use_flint_products
from midpoint_rotated_band import (GAP, CurveBounds, absolute, arb_newton_columns,
                                   exact_newton_columns, log_grid, require, search_curve,
                                   verify_curve)
from midpoint_scale_projection import BASE_UNIT, MIDPOINT_UNIT, CONTROL_X, CONTROL_M
from midpoint_surface_rotated import reduce_lattice


@dataclass(frozen=True)
class Row:
    x_scale: int
    m_scale: int
    y_exponent: int
    base: int
    first: int
    last: int


def read_row(fields):
    require(isinstance(fields, list) and len(fields) == 6 and all(type(n) is int for n in fields),
            'invalid row')
    row = Row(*fields)
    require(-1022 <= row.x_scale <= 1023 and -1022 <= row.m_scale <= 1023
            and -64 <= row.y_exponent <= 52, 'invalid binade')
    require(BASE_UNIT < row.base < 2*BASE_UNIT and MIDPOINT_UNIT < row.first <= row.last < 2*MIDPOINT_UNIT
            and row.first % 2 == row.last % 2 == 1, 'invalid significand range')
    return row


class ExponentialRow(CurveBounds):
    def __init__(self, row, degree, work_bits):
        require(type(degree) is int and 1 <= degree <= 48 and type(work_bits) is int
                and 32 <= work_bits <= 2400, 'invalid search shape')
        self.row = row
        self.degree = degree
        self.work_bits = work_bits
        self.grid, ln2 = log_grid(work_bits+72*degree+128)
        grid = self.grid
        self.q = 1 << (52-row.y_exponent)
        self.reference = row.first+2*((row.last-row.first)//4)
        self.sign = 1 if row.m_scale >= 0 else -1

        x_log = add(grid.scale(ln2,row.x_scale),grid.log(row.base,BASE_UNIT))
        x_mag = absolute(x_log)
        m_first, m_last = [add(grid.scale(ln2,row.m_scale),grid.log(b,MIDPOINT_UNIT))
                           for b in (row.first,row.last)]
        require(x_mag[0] > 0 and min(absolute(m_first)[0],absolute(m_last)[0]) > 1,
                'logarithm sign is not separated')
        m_magnitude = absolute((m_first[0],m_last[1]))
        # If the log gap is < 2**-GAP, one work ulp encloses the displacement.
        require(grid.precision < GAP, 'increase padding for the projected numerator')
        p_span = grid.divide(grid.scale((m_magnitude[0]-1,m_magnitude[1]+1),self.q),x_mag)
        low = max(BASE_UNIT,ceil_div(p_span[0],grid.unit))
        high = min(2*BASE_UNIT-1,p_span[1]//grid.unit)
        require(low < high, 'at most one candidate numerator, use direct interval comparison')
        self.p_span = low, high
        self.origin = (low+high)//2
        self.half = high-self.origin

        # For p = origin+half*t the midpoint index is U*exp(a*t)-reference/2.
        # Recenter the first exponential at the reference midpoint.
        rate = grid.scale(x_mag,self.sign)
        m_ref_log = add(grid.scale(ln2,row.m_scale),grid.log(self.reference,MIDPOINT_UNIT))
        near = add(divide_integer(grid.scale(rate,self.origin),self.q),grid.scale(m_ref_log,-1))
        self.amplitude = divide_integer(grid.scale(exp_near_zero(grid,near),self.reference),2)
        self.gradient = divide_integer(grid.scale(rate,self.half),self.q)
        self.offset = add(self.amplitude,grid.rational(-self.reference,2))
        self.slope = grid.multiply(self.amplitude,self.gradient)
        self.real_curvature = self.curvature(1)
        # At an actual midpoint B, the movement is B/2 * |exp(Delta)-1|.
        self.vertical = Fraction(row.last,1 << GAP)

    def curvature(self, radius):
        magnitude = radius*Fraction(max(map(abs,self.gradient)),self.grid.unit)
        return Fraction(self.amplitude[1],self.grid.unit)*(magnitude*magnitude/2)*exp_upper(magnitude)


def exact_columns(geometry, transform, terms):
    grid = geometry.grid
    coefficients = [geometry.offset]
    term = geometry.amplitude
    for k in range(1,terms):
        term = divide_integer(grid.multiply(term,geometry.gradient),k)
        coefficients.append(term)
    return exact_newton_columns(geometry,transform,coefficients)


def approximate_columns(geometry, transform, terms, free):
    from flint import arb, arb_series, ctx

    ctx.prec, ctx.cap = geometry.grid.precision, terms
    row = geometry.row
    x_log = (arb(row.base)/BASE_UNIT).log()+row.x_scale*arb(2).log()
    var = arb_series([0,1],prec=terms)
    rate = geometry.sign*abs(x_log)/geometry.q
    offset = ((geometry.origin+geometry.half*var)*rate).exp()*(arb(2)**(52-row.m_scale))
    offset -= arb(geometry.reference)/2
    return arb_newton_columns(geometry,transform,terms,free,var,offset)


def flatter_reducer(path, lattice, delta):
    from flint import fmpz_mat

    rows, backend = reduce(lattice,delta,path)
    return fmpz_mat(rows), backend


def verify_row(report):
    proof = report['proof']
    require(isinstance(proof,dict), 'no exact certificate')
    geometry = ExponentialRow(read_row(report['row']),proof['degree'],proof['work_bits'])
    verify_curve(geometry,proof,exact_columns)
    return geometry


def verify_cover(expected, reports):
    row = read_row(expected)
    first = row.first
    segments = 0
    for report in reports:
        fields = report['row']
        segment = read_row(fields)
        require(fields[:4] == expected[:4] and segment.first == first and segment.last <= row.last,
                'certificate coverage gap, overlap or wrong chart')
        verify_row(report)
        first = segment.last+2
        segments += 1
    require(first == row.last+2, 'incomplete row cover')
    return segments


def prove_row(fields, degree, work_bits, free_center, reducer):
    geometry = ExponentialRow(read_row(fields),degree,work_bits)
    result = search_curve(geometry,int(free_center),approximate_columns,exact_columns,reducer)
    return dict(result,status='EXCLUDED' if result['proof'] else 'OPEN',row=fields,
                numerators=list(geometry.p_span))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--row',type=lambda n: int(n,0),nargs=6)
    parser.add_argument('--width',type=int,default=43,help='log2 of the number of midpoints in the default row')
    parser.add_argument('--degree',type=int,default=12)
    parser.add_argument('--work-bits',type=int,default=128)
    parser.add_argument('--free-center',action='store_true')
    parser.add_argument('--flatter',type=Path)
    verify = parser.add_mutually_exclusive_group()
    verify.add_argument('--verify',type=Path)
    verify.add_argument('--verify-cover',type=Path)
    args = parser.parse_args()
    require(__debug__, 'enable interval assertions')
    start = perf_counter()
    if args.verify:
        report = json.loads(args.verify.read_text())
        geometry = verify_row(report)
        result = dict(status='VERIFIED',row=report['row'],numerators=list(geometry.p_span))
    else:
        require(0 <= args.width <= 43, 'invalid control row width')
        fields = args.row or [1023,0,-12,CONTROL_X[0],CONTROL_M[0],CONTROL_M[0]+(2 << args.width)-2]
        if args.verify_cover:
            open_report = gzip.open if args.verify_cover.suffix == '.gz' else open
            with open_report(args.verify_cover,'rt') as stream:
                segments = verify_cover(fields,map(json.loads,stream))
            result = dict(status='VERIFIED_COVER',row=fields,segments=segments)
        else:
            use_flint_products()
            reducer = partial(flatter_reducer,args.flatter) if args.flatter else reduce_lattice
            result = prove_row(fields,args.degree,args.work_bits,args.free_center,reducer)
    result['elapsed_s'] = round(perf_counter()-start,6)
    print(json.dumps(result,sort_keys=True))


if __name__ == '__main__':
    main()
