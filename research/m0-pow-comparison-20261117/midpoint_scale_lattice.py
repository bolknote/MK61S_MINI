#!/usr/bin/env python3
"""Certify a mantissa rectangle without enumerating binary scales or mantissas."""

import argparse
from concurrent.futures import ProcessPoolExecutor
from fractions import Fraction
from functools import cache
import gzip
from itertools import product
import json
from math import ceil
from pathlib import Path
from time import perf_counter

import midpoint_grid
from midpoint_entire_surface import binomial_modulo, chebyshev_weights, reduce
from midpoint_grid import add, interval_series_product, use_flint_products
from midpoint_rotated_band import bound_shape, signed_interval
from midpoint_scale_grid import (BASE_UNIT, GAP, MIDPOINT_UNIT, P_LIMIT, logarithm_grid,
                                 project_scales, require)


@cache
def basis_powers(degree):
    return tuple((a,b,c,total-a-b-c) for total in range(degree+1) for a in range(total+1)
                 for b in range(total-a+1) for c in range(total-a-b+1))


def packed_convolve(first, second, count):
    """Exactly convolve signed coefficients with byte-aligned Kronecker packing."""
    a,b = max(map(abs,first)).bit_length(),max(map(abs,second)).bit_length()
    if not a or not b:
        return [0]*count
    stride = (a+b+min(len(first),len(second)).bit_length()+8)//8

    def pack(values):
        positive = b''.join(max(0,x).to_bytes(stride,'little') for x in values)
        negative = b''.join(max(0,-x).to_bytes(stride,'little') for x in values)
        return int.from_bytes(positive,'little')-int.from_bytes(negative,'little')

    radix = 1 << (stride*8)
    total = pack(first)*pack(second)
    raw = (total & ((1 << (stride*count*8))-1)).to_bytes(stride*count,'little')
    # The true coefficients lie strictly inside (-radix/2,radix/2).
    # A negative coefficient in one digit subtracts one from the next.
    result = []
    carry = 0
    for start in range(0,len(raw),stride):
        digit = int.from_bytes(raw[start:start+stride],'little')+carry
        carry = digit >= radix//2
        result.append(digit-radix*carry)
    return result


def use_packed_products():
    midpoint_grid.convolve = packed_convolve


class Geometry:
    def __init__(self, block, degree, work_bits):
        require(isinstance(block,list) and len(block) == 7 and all(type(n) is int for n in block),
                'invalid block')
        a0,a1,b0,b1,k,p0,p1 = block
        require(BASE_UNIT <= a0 <= a1 < 2*BASE_UNIT and MIDPOINT_UNIT <= b0 <= b1 < 2*MIDPOINT_UNIT
                and (b0-b1)%2 == 0 and 0 <= k <= 116 and -P_LIMIT < p0 <= p1 < P_LIMIT,
                'block is outside the normalized proof grid')
        require(type(degree) is int and 1 <= degree <= 10 and type(work_bits) is int
                and 32 <= work_bits <= 768, 'invalid search shape')
        self.degree = degree
        self.work_bits = work_bits
        self.grid,self.ln2 = logarithm_grid(work_bits+64*degree+128)
        # I=A-A0, J=(B-B0)/2 and N=p-P0 are integer offsets.
        center = (a0+a1+1)//2, b0+2*((b1-b0+2)//4), (p0+p1+1)//2
        self.p = center[2]
        self.q = 1 << k
        self.half = center[0]-a0,(center[1]-b0)//2,center[2]-p0
        self.relative = Fraction(self.half[0],center[0]),Fraction(2*self.half[1],center[1])
        grid = self.grid
        self.log_x = grid.divide(grid.log(center[0],BASE_UNIT),self.ln2)
        self.log_m = grid.divide(grid.log(center[1],MIDPOINT_UNIT),self.ln2)
        z = add(grid.scale(self.log_x,self.p),grid.scale(self.log_m,-self.q))
        origin = (sum(z)+grid.unit)//(2*grid.unit)
        self.offset = add(z,grid.rational(-origin))
        self.linear = (grid.scale(self.log_coefficient(0,1),self.p),
                       grid.scale(self.log_coefficient(1,1),-self.q),
                       grid.scale(self.log_x,self.half[2]))
        self.vertical = Fraction(1 << (k+1),1 << GAP)

    def log_coefficient(self, axis, power):
        a = self.relative[axis]**power
        factor = self.grid.rational((-1)**(power-1)*a.numerator,power*a.denominator)
        return self.grid.divide(factor,self.ln2)

    def nonlinear(self, x_radius, m_radius):
        x,m = self.relative[0]*x_radius,self.relative[1]*m_radius
        require(max(x,m) <= Fraction(1,2), 'logarithm disk is too large')
        # ln(2)>1/2. Bound both pure log tails and N*delta(log2(X)).
        return abs(self.p)*x*x/(1-x)+self.q*m*m/(1-m)+2*self.half[2]*x/(1-x)

    def sizes(self, transform, x_radius, m_radius):
        unit = self.grid.unit
        remainder = self.nonlinear(x_radius,m_radius)+Fraction(max(map(abs,self.offset)),unit)
        radii = x_radius,m_radius,1
        return [abs(row[3])*remainder+sum(r*max(abs(a*h+row[3]*Fraction(v,unit)) for v in slope)
                for a,h,slope,r in zip(row,self.half,self.linear,radii)) for row in transform]

    def choose(self, transform):
        shifts = []
        for span in self.relative:
            shift = 1
            while shift < 52 and span*(1 << (shift+1)) <= Fraction(1,2):
                shift += 1
            shifts.append(shift)
        sizes = self.sizes(transform,*(1 << s for s in shifts))
        cap = max(ceil(size) for size in sizes)+self.degree
        target = (cap**self.degree).bit_length()+self.work_bits+6
        terms = [max(2,-(-target//s)) for s in shifts]
        # A constant coordinate has no analytic tail in that direction.
        for axis,span in enumerate(self.relative):
            if span == 0:
                terms[axis] = 2
        return shifts, terms

    def tail(self, transform, shifts, terms):
        require(isinstance(shifts,list) and isinstance(terms,list) and len(shifts) == len(terms) == 2
                and all(type(s) is int and 1 <= s <= 52 for s in shifts)
                and all(type(n) is int and 2 <= n <= 128 for n in terms),'invalid series shape')
        sizes = self.sizes(transform,*(1 << s for s in shifts))
        radii = sum(Fraction(4,1 << (s*n)) for s,n,relative in zip(shifts,terms,self.relative) if relative)
        movement = [abs(row[3])*self.vertical for row in transform]
        real = bound_shape(self.degree,[a+b for a,b in zip(self.sizes(transform,1,1),movement)])
        disk = bound_shape(self.degree,sizes)
        result = [0]
        for powers in basis_powers(self.degree)[1:]:
            delta = radii
            for shape,power in zip(disk,powers):
                delta *= shape[power]
            for axis,speed in enumerate(movement):
                if speed and powers[axis]:
                    term = speed
                    for i,(shape,power) in enumerate(zip(real,powers)):
                        term *= shape[power-(axis == i)]
                    delta += term
            result.append(ceil(delta*self.grid.unit))
        return result


class Series:
    """Tensor truncation in the two logs and a complete polynomial in p."""
    def __init__(self, geometry, terms):
        self.grid = geometry.grid
        nx,nm = terms
        self.indices = tuple(product(range(nx),range(nm),range(geometry.degree+1)))
        self.locations = {key:i for i,key in enumerate(self.indices)}
        stride_m = 2*nm-1
        stride_p = (2*nx-1)*stride_m
        self.flat = [i*stride_m+j+k*stride_p for i,j,k in self.indices]
        self.length = max(self.flat)+1

    def multiply(self, first, second):
        left,right = [(0,0)]*self.length,[(0,0)]*self.length
        for index,value,other in zip(self.flat,first,second):
            left[index],right[index] = value,other
        result = interval_series_product(left,right,self.grid)
        return [result[index] for index in self.flat]

    def basis(self, geo, transform, terms):
        grid = self.grid
        z = [(0,0)]*len(self.indices)
        z[0] = geo.offset
        z[self.locations[0,0,1]] = geo.linear[2]
        for n in range(1,terms[0]):
            coefficient = geo.log_coefficient(0,n)
            z[self.locations[n,0,0]] = grid.scale(coefficient,geo.p)
            z[self.locations[n,0,1]] = grid.scale(coefficient,geo.half[2])
        for n in range(1,terms[1]):
            z[self.locations[0,n,0]] = grid.scale(geo.log_coefficient(1,n),-geo.q)
        variables = []
        for row in transform:
            values = [grid.scale(c,row[3]) for c in z]
            for direction,index in enumerate(((1,0,0),(0,1,0),(0,0,1))):
                i = self.locations[index]
                values[i] = add(values[i],grid.rational(row[direction]*geo.half[direction]))
            variables.append(values)
        powers = basis_powers(geo.degree)
        polynomials = {powers[0]:[grid.rational(1)]+[(0,0)]*(len(z)-1)}
        for indices in powers[1:]:
            axis = next(i for i,n in enumerate(indices) if n)
            n = indices[axis]
            previous = list(indices)
            previous[axis] -= 1
            factor = variables[axis].copy()
            factor[0] = add(factor[0],grid.rational(1-n))
            values = factor if sum(indices) == 1 else self.multiply(polynomials[tuple(previous)],factor)
            polynomials[indices] = [(lo//n,-(-hi//n)) for lo,hi in values]
        return [polynomials[indices] for indices in powers]


def adapt(geo):
    from flint import fmpz_mat

    scale = 1 << 96
    slopes = [sum(d)*scale//(2*geo.grid.unit) for d in geo.linear]
    matrix = [[max(1,h)*scale*(i == j) for j in range(4)] for i,h in enumerate(geo.half)]
    matrix.append(slopes+[ceil(max(1,geo.nonlinear(1,1))*scale)])
    _,transform = fmpz_mat(matrix).lll(transform=True)
    return [[int(transform[i,j]) for j in range(4)] for i in range(4)]


def enclose_basis(geo,transform,terms):
    columns = Series(geo,terms).basis(geo,transform,terms)
    # Only the p axis is converted. It has finite degree, with no tail.
    size = geo.degree+1
    divisor = 1 << geo.degree
    weights = chebyshev_weights(size)
    converted = []
    for column in columns:
        target = []
        for start in range(0,len(column),size):
            values = [[0,0] for _ in range(size)]
            for (lo,hi),coefficients in zip(column[start:start+size],weights):
                for index,value in coefficients:
                    values[index][0] += lo*value
                    values[index][1] += hi*value
            target.extend((lo//divisor,-(-hi//divisor)) for lo,hi in values)
        converted.append(target)
    return converted


@cache
def parity_masks(degree):
    powers = basis_powers(degree)
    period = 1 << degree.bit_length()
    width = period**4
    # Lucas' theorem covers negative n as well through periodicity of
    # the truncated binomial expansion in characteristic two.
    coordinate_masks = []
    for axis in range(4):
        stride = period**axis
        masks = []
        for degree_part in range(degree+1):
            bits = bytearray((width+7)//8)
            for index in range(width):
                if (index//stride%period)&degree_part == degree_part:
                    bits[index//8] |= 1 << (index%8)
            masks.append(int.from_bytes(bits,'little'))
        coordinate_masks.append(masks)
    a,b,c,d = coordinate_masks
    masks = [a[i]&b[j]&c[k]&d[l] for i,j,k,l in powers]
    return (1 << width)-1,masks


def excludes_parity(degree, poly_list):
    candidates,masks = parity_masks(degree)
    selected = []
    for poly in poly_list:
        odd = 0
        for term,mask in zip(poly,masks):
            if term % 2:
                odd ^= mask
        if odd&candidates:
            selected.append(poly)
            candidates &= ~odd
            if not candidates:
                return selected
    return None


def excludes_bands(degree, bands, prime):
    require(prime in (11,13,17,19,23,29,31),'unsupported residue field')
    table = binomial_modulo(degree,prime)
    powers = basis_powers(degree)
    choices = []
    for index,(poly,lo,hi) in enumerate(bands):
        if hi-lo+1 < prime:
            residues = frozenset(value%prime for value in range(lo,hi+1))
            terms = [(a,b,c,d,w%prime) for (a,b,c,d),w in zip(powers,poly) if w%prime]
            choices.append((hi-lo,index,residues,terms))
    if not choices:
        return None
    choices.sort()
    found = set()
    for x in table:
        first = []
        for _,index,residues,terms in choices:
            partial = {}
            for a,b,c,d,w in terms:
                partial[b,c,d] = partial.get((b,c,d),0)+w*x[a]
            first.append((index,residues,partial))
        for y in table:
            second = []
            for index,residues,partial in first:
                partial_y = [[0]*(degree+1) for _ in range(degree+1)]
                for (b,c,d),w in partial.items():
                    partial_y[d][c] += y[b]*w
                second.append((index,residues,partial_y))
            for p in table:
                remaining = table
                for index,residues,partial in second:
                    coefficients = [sum(a*b for a,b in zip(p,row))%prime for row in partial]
                    active = [(i,w) for i,w in enumerate(coefficients) if w]
                    keep = [z for z in remaining if sum(w*z[i] for i,w in active)%prime in residues]
                    if len(keep) != len(remaining):
                        found.add(index)
                    if not keep:
                        break
                    remaining = keep
                else:
                    return None
    return sorted(found)


def verify(report):
    geo = Geometry(report['block'],report['degree'],report['work_bits'])
    transform = report['transform']
    require(isinstance(transform,list) and len(transform) == 4 and all(isinstance(row,list) and len(row) == 4
            and all(type(v) is int and abs(v).bit_length() <= 512 for v in row) for row in transform),
            'invalid integer coordinate transform')
    terms = report['terms']
    tail = geo.tail(transform,report['shifts'],terms)
    n = len(tail)
    polynomials = report['polynomials']
    require(isinstance(polynomials,list) and 1 <= len(polynomials) <= n
            and all(isinstance(poly,list) and len(poly) == n and any(poly)
                    and all(type(v) is int and abs(v).bit_length() <= 2048 for v in poly)
                    for poly in polynomials),'invalid integer polynomials')
    columns = enclose_basis(geo,transform,terms)
    ys = [signed_interval(poly,columns,tail,geo.grid.unit) for poly in polynomials]
    if len(ys) == 1 and ys[0][0] > ys[0][1]:
        return
    prime = report['prime']
    if prime == 2:
        require(all(y == (0,0) for y in ys) and excludes_parity(geo.degree,polynomials),
                'possible integer point in the parity classes')
    else:
        bands = [(poly,lo,hi) for poly,(lo,hi) in zip(polynomials,ys)]
        require(excludes_bands(geo.degree,bands,prime),'possible integer point in the modular band')


def numerator_span(binade, negative):
    """Inclusive endpoints and spacing of the numerator on the binade grid."""
    step = 1 << max(0,binade-52)
    low,high = BASE_UNIT*step,(2*BASE_UNIT-1)*step
    return (-high,-low,step) if negative else (low,high,step)


def cover_plan(rectangle, precision):
    require(isinstance(rectangle,list) and len(rectangle) == 4 and all(type(v) is int for v in rectangle),
            'invalid rectangle')
    a0,a1,b0,b1 = rectangle
    require((b1-b0)%2 == 0,'midpoint range crosses parities')
    report = project_scales(a0,a1+1,b0,b1+1,precision)
    return {(band,sign) for band,n in enumerate(report['by_y_exponent'],start=-64) if n
            for sign in (False,True)}


def verify_cover(record, workers=1, flint_products=False):
    require(workers >= 1,'the worker count must be positive')
    rectangle = record['rectangle']
    expected = cover_plan(rectangle,record['projection_bits'])
    seen = set()
    proofs = []
    for row in record['bands']:
        band,negative = key = row['binade'],row['negative']
        require(type(band) is int and type(negative) is bool and key in expected and key not in seen,
                'unexpected or duplicate exponent binade')
        seen.add(key)
        cursor,high,step = numerator_span(band,negative)
        shift = max(0,52-band)
        for proof in row['certificates']:
            block = proof['block']
            require(block[:5] == rectangle+[shift] and block[5] <= cursor <= block[6] <= high,
                    'certificate does not cover the next numerator')
            cursor = (block[6]//step+1)*step
            proofs.append(proof)
        require(cursor == high+step,'incomplete numerator cover')
    require(seen == expected,'missing exponent binades in rectangle')
    initializer = use_flint_products if flint_products else use_packed_products
    if workers == 1:
        initializer()
        for proof in proofs:
            verify(proof)
    elif proofs:
        with ProcessPoolExecutor(max_workers=min(workers,len(proofs)),initializer=initializer) as pool:
            list(pool.map(verify,proofs))
    return dict(status='VERIFIED_RECTANGLE',rectangle=rectangle,projected_bands=len(expected)//2,
                certificates=len(proofs))


def generate(block, degree, work_bits, flatter):
    start = perf_counter()
    geo = Geometry(block,degree,work_bits)
    transform = adapt(geo)
    shifts,terms = geo.choose(transform)
    tail = geo.tail(transform,shifts,terms)
    columns = enclose_basis(geo,transform,terms)
    expanded = perf_counter()
    scale = 1 << work_bits
    approximations = [[(lo+hi)*scale//(2*geo.grid.unit) for lo,hi in col[1:]] for col in columns[1:]]
    used = [i for i,values in enumerate(zip(*approximations)) if max(map(abs,values)) > 1]
    rank = len(approximations)
    penalty = len(used)+4
    lattice = [[row[j] for j in used]+[penalty*(i == j) for j in range(rank)]
               for i,row in enumerate(approximations)]
    reduced,backend = reduce(lattice,.98,flatter)
    exhausted = perf_counter()
    candidates = sorted((sum(map(abs,row[:len(used)])),i) for i,row in enumerate(reduced))
    zeros = []
    bands = []
    solution = None
    prime = 0
    for error,i in candidates:
        if error >= 16*scale or len(bands) >= 28:
            break
        poly = [0]+[v//penalty for v in reduced[i][len(used):]]
        lo,hi = signed_interval(poly,columns,tail,geo.grid.unit)
        if lo > hi:
            solution = [poly]
            break
        if lo == hi:
            zeros.append([-lo]+poly[1:])
        if hi-lo < 30:
            bands.append((poly,lo,hi))
    if solution is None and zeros:
        prime = 2
        solution = excludes_parity(degree,zeros)
    if solution is None and len(bands) >= 4:
        for prime in (11,13,17,19,23,29,31):
            hits = excludes_bands(degree,bands,prime)
            if hits:
                solution = [bands[i][0] for i in hits]
                break
    report = dict(block=block,degree=degree,work_bits=work_bits,transform=transform,shifts=shifts,terms=terms)
    if solution:
        report['polynomials'] = solution
        report['prime'] = prime
    return dict(status='EXCLUDED' if solution else 'OPEN',report=report,rank=rank,columns=len(used),
                best_bits=candidates[0][0].bit_length()-1-work_bits,zeros=len(zeros),backend=backend,
                expand_s=round(expanded-start,6),reduce_s=round(exhausted-expanded,6))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--block',type=lambda s: int(s,0),nargs=7)
    parser.add_argument('--degree',type=int,default=5)
    parser.add_argument('--work-bits',type=int,default=112)
    parser.add_argument('--flatter',type=Path)
    checks = parser.add_mutually_exclusive_group()
    checks.add_argument('--verify',type=Path)
    checks.add_argument('--verify-cover',type=Path)
    parser.add_argument('--flint-products',action='store_true')
    parser.add_argument('--workers',type=int,default=1)
    args = parser.parse_args()
    require(__debug__,'enable interval assertions')
    if not args.verify_cover and (args.flint_products or not args.verify):
        use_flint_products()
    elif not args.verify_cover:
        use_packed_products()
    if args.verify or args.verify_cover:
        path = args.verify or args.verify_cover
        open_report = gzip.open if path.suffix == '.gz' else open
        with open_report(path,'rt') as stream:
            record = json.load(stream)
    if args.verify:
        proof = record.get('report',record)
        verify(proof)
        print(json.dumps(dict(status='VERIFIED_BLOCK',block=proof['block']),sort_keys=True))
    elif args.verify_cover:
        print(json.dumps(verify_cover(record,args.workers,args.flint_products),sort_keys=True))
    else:
        require(args.block is not None,'specify a mantissa and numerator block')
        print(json.dumps(generate(args.block,args.degree,args.work_bits,args.flatter),sort_keys=True))


if __name__ == '__main__':
    main()
