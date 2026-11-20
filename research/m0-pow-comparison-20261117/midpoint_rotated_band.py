#!/usr/bin/env python3
"""Exclude dyadic exponent numerators near a fixed pow rounding midpoint."""

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from fractions import Fraction
from functools import lru_cache
import json
from math import ceil, factorial
from pathlib import Path
import sys
from time import perf_counter, process_time

from midpoint_grid import add, exclude_residues, interval_series_product, use_flint_products
from midpoint_surface_rotated import integer_interval, polynomial_bounds, reduce_lattice, require

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'dev/tools'))
from verify_m0_pow_binary64 import INF, dyadic, log_grid, log_point


GAP = 16300


@dataclass(frozen=True)
class Block:
    midpoint: int
    binade: int
    first: int
    width: int
    shift: int

    @property
    def base(self):
        return 1 << min(52, self.binade + 1074)

    @property
    def encoding(self):
        return (self.binade + 1023) << 52 if self.binade >= -1022 else self.base

def absolute(span):
    lo, hi = span
    if lo >= 0:
        return span
    if hi <= 0:
        return -hi, -lo
    return 0, max(-lo, hi)


def read_block(fields):
    require(isinstance(fields, list) and len(fields) == 5 and all(type(n) is int for n in fields),
            'invalid block')
    block = Block(*fields)
    require(0 <= block.midpoint < INF and -1074 <= block.binade <= 1023
            and 0 <= block.width <= min(52, block.binade+1074) and 0 <= block.shift <= 116,
            'block is out of range')
    count = 1 << block.width
    require(block.first % count == 0 and 0 <= block.first <= block.base-count, 'misaligned block')
    return block


@lru_cache(maxsize=32)
def powers(degree):
    return tuple((i, weight-i) for weight in range(degree+1) for i in range(weight+1))


def bound_shape(degree, real_or_disk):
    # |binom(L,k)| <= (|L|+k)^k/k!. The derivative follows by
    # differentiating the factors, so this works at near-integers too.
    return [tuple(Fraction((ceil(size)+degree)**k, factorial(k)) for k in range(degree+1))
            for size in real_or_disk]


class CurveBounds:
    def sizes(self, transform, radius, curvature):
        unit = self.grid.unit
        constant = Fraction(max(map(abs,self.offset)), unit)
        return tuple(abs(b)*(constant+curvature) + radius*max(abs(a*self.half+b*Fraction(s,unit))
                       for s in self.slope) for a,b in transform)

    def tail(self, transform, shift, terms):
        require(type(shift) is int and 1 <= shift <= 52 and type(terms) is int
                and 2 <= terms <= 1024, 'invalid series cutoff')
        radius = 1 << shift
        curvature = self.curvature(radius)
        disk = bound_shape(self.degree, self.sizes(transform,radius,curvature))
        choices = self.sizes(transform, 1, self.real_curvature)
        movement = tuple(abs(b)*self.vertical for _,b in transform)
        real = bound_shape(self.degree, [size+move for size,move in zip(choices,movement)])
        scale = Fraction(2, 1 << (shift*terms))
        result = []
        for i,j in powers(self.degree):
            if i == j == 0:
                result.append(0)
                continue
            a = disk[0][i]*disk[1][j]*scale
            b = (movement[0]*real[0][i-1]*real[1][j] if i else 0)
            c = (movement[1]*real[0][i]*real[1][j-1] if j else 0)
            result.append(ceil((a+b+c)*self.grid.unit))
        return result

    def choose(self, transform, work_bits):
        options = []
        for shift in range(1, 53):
            try:
                radius = 1 << shift
                curvature = self.curvature(radius)
            except ValueError:
                break
            disk = bound_shape(self.degree, self.sizes(transform, radius, curvature))
            bound = ceil(max(disk[0][i]*disk[1][j] for i,j in powers(self.degree)))
            # Bounding the disk term is enough to pick a candidate shape.
            # The checker also adds the vertical error before accepting it.
            terms = max(2, -(-(bound.bit_length()+work_bits+3)//shift))
            if terms <= 1024:
                options.append((terms,-shift))
        require(options, 'no usable complex disk for this lattice')
        terms, shift = min(options)
        return -shift, terms


class Geometry(CurveBounds):
    def __init__(self, block, degree, work_bits, origin=None, gap=GAP):
        require(block.width >= 1, 'a singleton needs the direct rule')
        require(type(degree) is int and 1 <= degree <= 48
                and type(work_bits) is int and 32 <= work_bits <= 2400, 'invalid search shape')
        self.degree = degree
        self.work_bits = work_bits
        self.block = block
        self.grid, log2 = log_grid(work_bits + 72*degree + 128)
        grid = self.grid
        self.half = half = Fraction(1 << block.width, 2)
        self.center = block.base + block.first + half
        self.relative = half / self.center
        self.sign = 1 if block.binade >= 0 else -1
        center_log = add(grid.scale(log2, block.binade),
                         grid.log(self.center.numerator, block.base*self.center.denominator))
        self.log_x = grid.scale(center_log, self.sign)
        self.target = grid.scale(absolute(log_point(block.midpoint, grid.precision, True)), 1 << block.shift)
        require(self.log_x[0] > 0 and self.target[0] > 0, 'logarithm sign is not separated')
        value = grid.divide(self.target, self.log_x)
        if origin is None:
            origin = (sum(value)+grid.unit)//(2*grid.unit)
        require(type(origin) is int and abs(origin).bit_length() <= 192, 'invalid exponent origin')
        self.origin = origin
        self.offset = add(value, grid.rational(-origin))
        require(max(map(abs,self.offset)) < 2*grid.unit, 'exponent origin is too far from the centre')
        linear_log = grid.rational(self.sign*self.relative.numerator, self.relative.denominator)
        self.slope = grid.scale(grid.divide(grid.multiply(value,linear_log),self.log_x), -1)
        self.real_curvature, self.real_log = self.disk(1)
        self.vertical = Fraction(1 << block.shift, 1 << gap) / self.real_log

    def disk(self, radius):
        a = self.relative*radius
        require(0 < a < 1, 'complex disk crosses the logarithm cut')
        tail = a*a/(2*(1-a))
        delta = a/(1-a)
        log_low = Fraction(self.log_x[0], self.grid.unit)
        low = log_low-delta
        require(low > 0, 'complex log may contain zero')
        c = Fraction(self.target[1], self.grid.unit)
        # C/(L+h) = C/L - C*h/L**2 + C*h**2/(L**2*(L+h)).
        return c*(tail+delta*delta/low)/log_low**2, low

    def curvature(self, radius):
        return self.disk(radius)[0]


def checked_transform(matrix):
    require(isinstance(matrix,list) and len(matrix) == 2
            and all(isinstance(row,list) and len(row) == 2 and all(type(n) is int for n in row)
                    for row in matrix), 'invalid transform')
    (a,b),(c,d) = matrix
    require(abs(a*d-b*c) == 1 and max(map(abs,(a,b,c,d))) <= 1 << 80, 'invalid transform')
    return matrix


def adapt(geometry):
    from flint import fmpz_mat

    scale = 1 << 24
    tangent = sum(geometry.slope)*scale//(2*geometry.grid.unit)
    approx = [[int(geometry.half*scale), 0], [tangent, ceil(max(1,geometry.real_curvature)*scale)]]
    _, transform = fmpz_mat(approx).lll(transform=True)
    return checked_transform([[int(transform[i,j]) for j in range(2)] for i in range(2)])


def exact_columns(geometry, transform, terms):
    grid = geometry.grid
    x = [geometry.log_x]
    z = geometry.relative
    for k in range(1,terms):
        x.append(grid.rational(geometry.sign*(-1)**(k-1)*z.numerator**k, z.denominator**k*k))
    quotient = [grid.divide(geometry.target, x[0])]
    for k in range(1,terms):
        v = (0,0)
        for i in range(1,k+1):
            v = add(v,grid.multiply(x[i],quotient[k-i]))
        quotient.append(grid.divide(grid.scale(v,-1),x[0]))
    quotient[0] = add(quotient[0], grid.rational(-geometry.origin))
    return exact_newton_columns(geometry, transform, quotient)


def exact_newton_columns(geometry, transform, series_offset):
    grid = geometry.grid
    terms = len(series_offset)
    one = [grid.rational(1)]+[(0,0)]*(terms-1)
    basis = []
    for a,b in transform:
        series = [grid.scale(v,b) for v in series_offset]
        series[1] = add(series[1],grid.rational(a*geometry.half.numerator,geometry.half.denominator))
        row = [one, series]
        for k in range(2, geometry.degree+1):
            factor = series.copy()
            factor[0] = add(factor[0],grid.rational(1-k))
            row.append([(lo//k,-(-hi//k)) for lo,hi in interval_series_product(row[-1],factor,grid)])
        basis.append(row)
    return [interval_series_product(basis[0][i],basis[1][j],grid) if i and j else
            basis[0][i] if i else basis[1][j] for i,j in powers(geometry.degree)]


def arb_columns(geometry, transform, terms, free, extra_bits=0):
    from flint import arb, arb_series, ctx

    ctx.prec, ctx.cap = geometry.grid.precision+extra_bits, terms
    block = geometry.block
    c = geometry.center
    x0 = (arb(c.numerator)/(c.denominator*block.base)).log() + block.binade*arb(2).log()
    b,bexp = dyadic(block.midpoint,True)
    l = b.bit_length()-1
    m = (arb(b)/(1 << l)).log()+(bexp+l)*arb(2).log()
    c = abs(m)*(1 << block.shift)*geometry.sign
    var = arb_series([0,1],prec=terms)
    a = geometry.relative
    offset = c/(x0+(1+var*(arb(a.numerator)/a.denominator)).log())-geometry.origin
    return arb_newton_columns(geometry, transform, terms, free, var, offset, extra_bits)


def arb_newton_columns(geometry, transform, terms, free, var, offset, extra_bits=0):
    from flint import arb, arb_series

    half = arb(geometry.half.numerator)/geometry.half.denominator
    basis = []
    for a,b in transform:
        series = a*half*var+b*offset
        row = [arb_series([1],prec=terms)]
        for k in range(geometry.degree):
            row.append(row[-1]*(series-k)/(k+1))
        basis.append(row)
    result = []
    scale = 1 << (geometry.work_bits+extra_bits)
    for i,j in powers(geometry.degree)[free:]:
        column = basis[0][i]*basis[1][j]*scale
        result.append([int(column[k].mid().floor().fmpz()) for k in range(free,terms)])
    return result


def signed_interval(poly, columns, tail, unit, limited=False):
    padding = sum(abs(c)*d for c,d in zip(poly,tail))
    result = polynomial_bounds(poly,columns,0,2*unit if limited else None)
    if result is None:
        return None
    return integer_interval((result[0]-padding,result[1]+padding),unit)


def no_modular_roots(degree, polynomials, prime):
    if prime == 2:
        return exclude_residues(powers(degree),polynomials,2,'newton')
    require(prime in (53,59,61,67), 'unsupported residue field')
    rows = powers(degree)
    table = []
    for x in range(prime):
        row = [1]
        for k in range(1,degree+1):
            row.append(row[-1]*(x-k+1)*pow(k,-1,prime)%prime)
        table.append(row)
    remaining = [(x,y) for x in table for y in table]
    selected = []
    for poly in polynomials:
        terms = [(i,j,c%prime) for (i,j),c in zip(rows,poly) if c%prime]
        next_set = [(x,y) for x,y in remaining if not sum(c*x[i]*y[j] for i,j,c in terms)%prime]
        if len(next_set) < len(remaining):
            selected.append(poly)
            remaining = next_set
        if not remaining:
            return selected
    return None


def verify_proof(block, proof, gap=GAP):
    require(isinstance(proof,dict), 'invalid proof row')
    geo = Geometry(block,proof['degree'],proof['work_bits'],proof['origin'],gap)
    verify_curve(geo, proof, exact_columns)


def verify_curve(geo, proof, columns):
    transform = checked_transform(proof['transform'])
    terms = proof['terms']
    errors = geo.tail(transform,proof['shift'],terms)
    polys = proof['polynomials']
    n = len(powers(geo.degree))
    require(isinstance(polys,list) and 1 <= len(polys) <= n and all(isinstance(p,list) and len(p)==n
            and any(p) and all(type(c) is int and abs(c).bit_length() <= 2400 for c in p)
            for p in polys), 'invalid integer polynomials')
    exact = columns(geo,transform,terms)
    intervals = [signed_interval(poly,exact,errors,geo.grid.unit) for poly in polys]
    if proof['prime'] == 0:
        require(len(polys)==1 and intervals[0][0]>intervals[0][1], 'integer in the range')
    else:
        require(all(pair==(0,0) for pair in intervals), 'nonzero integer in the range')
        require(no_modular_roots(geo.degree,polys,proof['prime']), 'common modular root')


def search_block(job):
    fields,degree,work_bits,free = job
    start = process_time()
    block = read_block(fields)
    geo = Geometry(block,degree,work_bits)
    result = search_curve(geo,free,arb_columns,exact_columns)
    if result['proof']:
        result['proof']['origin'] = geo.origin
    return dict(block=fields,cpu=round(process_time()-start,6),**result)


def search_curve(geo, free, approximate_columns, checked_columns, reducer=reduce_lattice):
    degree, work_bits = geo.degree, geo.work_bits
    matrix = adapt(geo)
    shift,terms = geo.choose(matrix,work_bits)
    scale = 1 << work_bits
    columns = approximate_columns(geo,matrix,terms,free)
    size,rank = terms-free,len(columns)
    penalty = terms+4
    lattice = [row+[penalty*(i==j) for j in range(rank)] for i,row in enumerate(columns)]
    launched = process_time()
    reduced, backend = reducer(lattice,0.98)
    reduction = process_time()-launched
    short = []
    smallest = None
    for i in range(rank):
        error = sum(abs(int(reduced[i,k])) for k in range(size))
        smallest = error if smallest is None else min(error,smallest)
        if error < scale:
            short.append([0]*free+[int(reduced[i,size+k])//penalty for k in range(rank)])
    cert,count = certify_candidates(geo,matrix,shift,terms,short,checked_columns)
    return dict(degree=degree,work_bits=work_bits,free_center=bool(free),terms=terms,
                rank=rank,backend=backend,lll_cpu=round(reduction,6),
                best_log2=(smallest.bit_length()-1-work_bits) if smallest else None,
                integer_polynomials=count,proof=cert)


def certify_candidates(geo, matrix, shift, terms, short, checked_columns):
    proof = None
    polys = []
    prime = 0
    if short:
        exact = checked_columns(geo,matrix,terms)
        errors = geo.tail(matrix,shift,terms)
        for poly in short:
            result = signed_interval(poly,exact,errors,geo.grid.unit,True)
            if result is None:
                continue
            a,b = result
            if a>b:
                proof = [poly]
                break
            if a==b:
                poly[0] -= a
                if any(poly):
                    polys.append(poly)
        if proof is None and polys:
            for prime in (2,53,59,61,67):
                proof = no_modular_roots(geo.degree,polys,prime)
                if proof:
                    break
    cert = dict(degree=geo.degree,work_bits=geo.work_bits,transform=matrix,
                shift=shift,terms=terms,prime=prime,polynomials=proof) if proof else None
    return cert,len(polys)


def run(job):
    try:
        return search_block(job)
    except ValueError as error:
        return dict(block=job[0],degree=job[1],work_bits=job[2],proof=None,error=str(error))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='mode',required=True)
    search = sub.add_parser('sample')
    search.add_argument('jobs',type=Path)
    search.add_argument('output',type=Path)
    search.add_argument('--workers',type=int,default=1)
    verify = sub.add_parser('verify')
    verify.add_argument('input',type=Path)
    verify.add_argument('--flint-products',action='store_true')
    args = parser.parse_args()
    start = perf_counter()
    if args.mode == 'sample':
        jobs = json.loads(args.jobs.read_text())
        with args.output.open('x') as output, ProcessPoolExecutor(max_workers=args.workers,
                    initializer=use_flint_products) as pool:
            for future in as_completed([pool.submit(run,job) for job in jobs]):
                row = future.result()
                print(json.dumps(row,separators=(',',':')),file=output,flush=True)
                print({k:v for k,v in row.items() if k!='proof'},'PASS' if row['proof'] else 'OPEN',flush=True)
    else:
        if args.flint_products:
            use_flint_products()
        total = 0
        with args.input.open() as stream:
            for line in stream:
                row = json.loads(line)
                if row['proof'] is not None:
                    verify_proof(read_block(row['block']),row['proof'])
                    total += 1
        print(json.dumps(dict(status='VERIFIED_ACCEPTED_ROWS',accepted=total,seconds=perf_counter()-start)))


if __name__ == '__main__':
    main()
