#!/usr/bin/env python3
"""Reuse the reduced integer polynomial basis over consecutive q115 blocks."""

import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
import gzip
from hashlib import sha256
from itertools import islice
import json
from pathlib import Path
from time import perf_counter

from midpoint_band_layer import GAP, SCHEMA, bounded_map, indexed_spans, shape, spans, tasks
from midpoint_entire_surface import reduce
from midpoint_grid import use_flint_products
from midpoint_rotated_band import (Geometry, adapt, arb_columns, certify_candidates,
                                   exact_columns, powers, require, verify_curve)


def generalized_binomials(value, degree):
    coefficients = [1]
    for k in range(degree):
        coefficients.append(coefficients[-1]*(value-k)//(k+1))
    return coefficients


def translation(degree, dx, dy, free=1):
    """Newton coefficients for P(Lx+dx,Ly+dy), optionally modulo constants."""
    from flint import fmpz_mat

    x,y = generalized_binomials(dx,degree),generalized_binomials(dy,degree)
    basis = powers(degree)[free:]
    return fmpz_mat([[x[i-a]*y[j-b] if i >= a and j >= b else 0 for a,b in basis]
                     for i,j in basis])


def coordinates(geo, transform):
    return [int(a*geo.center+b*geo.origin) for a,b in transform]


def reduce_block(geo, transform, prior, flatter):
    from flint import fmpz_mat

    shift,terms = geo.choose(transform,geo.work_bits)
    dimension = len(powers(geo.degree))-1
    penalty = terms+4
    current = coordinates(geo,transform)
    if prior is None:
        coefficients = [[int(i==j) for j in range(dimension)] for i in range(dimension)]
        leading = arb_columns(geo,transform,terms,1)
    else:
        previous,basis = prior
        dx,dy = [new-old for new,old in zip(current,previous)]
        rotation = basis*translation(geo.degree,dx,dy)
        coefficients = [[int(rotation[i,j]) for j in range(dimension)] for i in range(dimension)]
        extra = max(abs(value).bit_length() for row in coefficients for value in row)+dimension.bit_length()+4
        values = fmpz_mat(arb_columns(geo,transform,terms,1,extra))
        preconditioned = rotation*values
        leading = [[int(preconditioned[i,j]) >> extra for j in range(terms-1)] for i in range(dimension)]
    lattice = [vector+[penalty*x for x in row] for vector,row in zip(leading,coefficients)]
    start = perf_counter()
    reduced,_ = reduce(lattice,.98,flatter)
    elapsed = perf_counter()-start
    basis = [[value//penalty for value in row[terms-1:]] for row in reduced]
    norms = [sum(map(abs,row[:terms-1])) for row in reduced]
    short = [[0]+row for row,norm in zip(basis,norms) if norm < 1 << geo.work_bits]
    proof,_ = certify_candidates(geo,transform,shift,terms,short,exact_columns)
    if proof:
        proof['origin'] = geo.origin
    return proof,(current,fmpz_mat(basis)),elapsed,min(norms).bit_length()-1-geo.work_bits


def transport(geo, previous_geo, proof):
    from flint import fmpz_mat

    transform = proof['transform']
    old,new = coordinates(previous_geo,transform),coordinates(geo,transform)
    dx,dy = [b-a for a,b in zip(old,new)]
    polynomials = fmpz_mat(proof['polynomials'])*translation(geo.degree,dx,dy,0)
    shift,terms = geo.choose(transform,geo.work_bits)
    next_proof = dict(proof,origin=geo.origin,shift=shift,terms=terms,
                      polynomials=[[int(polynomials[i,j]) for j in range(polynomials.ncols())]
                                   for i in range(polynomials.nrows())])
    try:
        verify_curve(geo,next_proof,exact_columns)
    except ValueError:
        return None
    return next_proof


def batch(args):
    blocks,degree,bits,flatter,mode = args
    output = []
    state = previous = transform = previous_geo = previous_proof = None
    for block in blocks:
        geometry = Geometry(block,degree,bits)
        contiguous = (previous is not None and previous.binade == block.binade
                      and previous.midpoint == block.midpoint and previous.width == block.width
                      and previous.first+(1 << block.width) == block.first)
        if mode != 'prereduce' or not contiguous:
            state = None
            transform = adapt(geometry)
        previous = block
        start = perf_counter()
        proof = transport(geometry,previous_geo,previous_proof) if (
            mode == 'transport' and contiguous and previous_proof) else None
        reused = bool(proof)
        basis,reduction,norm = None,0,None
        if not proof:
            proof,basis,reduction,norm = reduce_block(geometry,transform,state,flatter)
            if state is not None and not proof:
                transform = adapt(geometry)
                proof,basis,time,norm = reduce_block(geometry,transform,None,flatter)
                reduction += time
        elapsed = perf_counter()-start
        output.append(dict(block=[block.midpoint,block.binade,block.first,block.width,block.shift],
                           proof=proof,elapsed_s=round(elapsed,6),lll_s=round(reduction,6),
                           best_log2=norm,reused=reused,prereduced=state is not None))
        state = basis
        previous_geo,previous_proof = geometry,proof
    return output


def batches(blocks,size):
    while chunk := tuple(islice(blocks,size)):
        yield chunk


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output',type=Path)
    parser.add_argument('--width',type=int,default=38)
    parser.add_argument('--first',type=int,default=0)
    parser.add_argument('--stop',type=int,required=True)
    parser.add_argument('--group',type=int,default=16)
    parser.add_argument('--workers',type=int,default=8)
    parser.add_argument('--degree',type=int)
    parser.add_argument('--work-bits',type=int)
    parser.add_argument('--flatter',type=Path)
    parser.add_argument('--mode',choices=('cold','transport','prereduce'),default='transport')
    parser.add_argument('--certificate',type=Path)
    args = parser.parse_args()
    require(0 <= args.first < args.stop and min(args.group,args.workers) > 0,'invalid pilot range')
    plan = tuple(spans(args.width))
    count = max(end for _,end,*_ in indexed_spans(plan))
    require(args.stop <= count,'range exceeds the proof plan')
    blocks = tasks(plan,args.first,args.stop)
    d,p = shape(args.width)
    requests = ((group,args.degree or d,args.work_bits or p,args.flatter,args.mode)
                for group in batches(blocks,args.group))
    start = perf_counter()
    report = Counter()
    with ProcessPoolExecutor(max_workers=args.workers,initializer=use_flint_products) as pool, \
            gzip.open(args.output,'xt',compresslevel=3) as out:
        certificate = gzip.open(args.certificate,'xt',compresslevel=3) if args.certificate else None
        try:
            if certificate:
                digest = sha256(json.dumps(plan,separators=(',',':')).encode()).hexdigest()
                print(json.dumps([SCHEMA,GAP,args.width,digest,args.first,args.stop,count]),file=certificate)
            for records in bounded_map(pool,batch,requests,args.workers):
                for record in records:
                    block,proof = record['block'],record['proof']
                    report['verified_candidates' if proof else 'open'] += 1
                    report['reused'] += int(record['reused'])
                    print(json.dumps(record,separators=(',',':')),file=out)
                    if certificate:
                        row = [block,'polynomial',proof] if proof else [block,'open']
                        print(json.dumps([row],separators=(',',':')),file=certificate)
        finally:
            if certificate:
                certificate.close()
    print(json.dumps(dict(elapsed_s=round(perf_counter()-start,6),path=str(args.output),**report)))


if __name__ == '__main__':
    main()
