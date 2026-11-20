#!/usr/bin/env python3
"""Prove q115 blocks by using the integer exponent numerator as a parameter."""

import argparse
from fractions import Fraction
from functools import partial
import json
from pathlib import Path
from time import perf_counter

from midpoint_band_layer import MAX_P, MIN_P, SHIFT
from midpoint_entire_surface import divide_integer, exp_near_zero, exp_upper, taylor_exp
from midpoint_exponential_row import flatter_reducer
from midpoint_grid import add, ceil_div, use_flint_products
from midpoint_rotated_band import (GAP, CurveBounds, absolute, arb_newton_columns, dyadic,
                                   exact_newton_columns, log_grid, log_point, read_block,
                                   require, search_curve, verify_curve)
from midpoint_surface_rotated import reduce_lattice


class Inverse(CurveBounds):
    def __init__(self, block, degree, work_bits, gap=GAP):
        require(block.shift == SHIFT and block.width > 0,'expected a nonsingleton q115 block')
        require(type(degree) is int and 1 <= degree <= 48 and type(work_bits) is int
                and 32 <= work_bits <= 2400,'invalid search shape')
        self.block = block
        self.degree = degree
        self.work_bits = work_bits
        self.grid,ln2 = log_grid(work_bits+72*degree+128)
        grid = self.grid
        unit = grid.unit
        self.sign = 1 if block.binade >= 0 else -1
        first = block.encoding+block.first
        last = first+(1 << block.width)-1
        xl,xh = log_point(first,grid.precision,False),log_point(last,grid.precision,False)
        low,high = absolute((xl[0],xh[1]))
        require(low > 0 and SHIFT < gap,'base log or scaled strip is not separated')
        self.target = grid.scale(absolute(log_point(block.midpoint,grid.precision,True)),1 << SHIFT)
        error = 1 << max(0,grid.precision+SHIFT-gap)
        p_low = max(MIN_P,ceil_div(self.target[0]-error,high))
        p_high = min(MAX_P,(self.target[1]+error)//low)
        require(p_low < p_high,'empty or singleton numerator projection')
        self.numerator_span = p_low,p_high
        self.p = (p_low+p_high)//2
        self.half = p_high-self.p
        self.relative = Fraction(self.half,self.p)

        # A_*(t) is the continuous mantissa solving p*abs(ln x)=target.
        # Center its exponential at a binade mantissa to keep the argument small.
        reference = block.base+block.first+(1 << (block.width-1))
        self.c = divide_integer(grid.scale(self.target,self.sign),self.p)
        ref_log = add(grid.scale(ln2,block.binade),grid.log(reference,block.base))
        argument = add(self.c,grid.scale(ref_log,-1))
        require(max(map(abs,argument)) < unit,'center is outside the base binade')
        exp_half = exp_near_zero(grid,divide_integer(argument,2))
        self.amplitude = grid.scale(grid.multiply(exp_half,exp_half),reference)
        self.origin = (sum(self.amplitude)+unit)//(2*unit)
        self.offset = add(self.amplitude,grid.rational(-self.origin))
        self.slope = grid.multiply(self.amplitude,self.exponent_coefficient(1))
        self.real_curvature = self.curvature(1)
        self.vertical = Fraction(1 << (54+SHIFT-52),1 << gap)

    def exponent_coefficient(self, degree):
        ratio = (-self.relative)**degree
        return divide_integer(self.grid.scale(self.c,ratio.numerator),ratio.denominator)

    def curvature(self, radius):
        r = self.relative*radius
        require(r < 1,'complex disk reaches numerator zero')
        c = Fraction(max(map(abs,self.c)),self.grid.unit)
        change = c*r/(1-r)
        # 1/(1+z) after its linear term and exp after its linear term.
        return Fraction(self.amplitude[1],self.grid.unit)*(change*r+change**2*exp_upper(change)/2)


def exact_columns(geo, transform, terms):
    grid = geo.grid
    exponent = [geo.exponent_coefficient(k) for k in range(1,terms)]
    coefficients = [grid.multiply(geo.amplitude,b) for b in taylor_exp(grid,exponent,terms)]
    coefficients[0] = geo.offset
    return exact_newton_columns(geo,transform,coefficients)


def approx_columns(geo, transform, terms, free):
    from flint import arb, arb_series, ctx

    ctx.prec,ctx.cap = geo.grid.precision,terms
    midpoint,scale = dyadic(geo.block.midpoint,True)
    leading = midpoint.bit_length()-1
    m = (arb(midpoint)/(1 << leading)).log()+(scale+leading)*arb(2).log()
    t = arb_series([0,1],prec=terms)
    exponent = (geo.sign*(1 << SHIFT)*abs(m))/(geo.p+geo.half*t)
    a = exponent.exp()*(arb(2)**(-geo.block.binade)*geo.block.base)-geo.origin
    return arb_newton_columns(geo,transform,terms,free,t,a)


def generate(block, degree, work_bits, reducer, gap=GAP):
    geo = Inverse(block,degree,work_bits,gap)
    result = search_curve(geo,1,approx_columns,exact_columns,reducer)
    if result['proof']:
        result['proof']['chart'] = 'inverse'
    return result


def verify_proof(block, proof, gap=GAP):
    require(isinstance(proof,dict) and proof.get('chart') == 'inverse','wrong inverse certificate chart')
    geo = Inverse(block,proof['degree'],proof['work_bits'],gap)
    verify_curve(geo,proof,exact_columns)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--block',type=lambda s:int(s,0),nargs=5)
    parser.add_argument('--verify',type=Path)
    parser.add_argument('--degree',type=int,default=14)
    parser.add_argument('--work-bits',type=int,default=176)
    parser.add_argument('--flatter',type=Path)
    parser.add_argument('--flint-products',action='store_true')
    args = parser.parse_args()
    require(__debug__,'enable interval assertions')
    start = perf_counter()
    if not args.verify or args.flint_products:
        use_flint_products()
    if args.verify:
        row = json.loads(args.verify.read_text())
        verify_proof(read_block(row['block']),row['proof'])
        result = dict(status='VERIFIED_BLOCK',block=row['block'])
    else:
        require(args.block is not None,'specify a proof block')
        block = read_block(args.block)
        reducer = partial(flatter_reducer,args.flatter) if args.flatter else reduce_lattice
        result = dict(block=args.block,**generate(block,args.degree,args.work_bits,reducer))
        result['status'] = 'EXCLUDED' if result['proof'] else 'OPEN'
    result['elapsed_s'] = round(perf_counter()-start,6)
    print(json.dumps(result,sort_keys=True))


if __name__ == '__main__':
    main()
