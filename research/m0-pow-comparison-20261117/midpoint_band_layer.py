#!/usr/bin/env python3
"""Generate and replay complete coverage for the first layer above |y|=2^-63."""

import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from dataclasses import astuple
from fractions import Fraction
from functools import lru_cache
import gzip
from hashlib import sha256
from itertools import islice
import json
from pathlib import Path
import sys
from time import monotonic

from midpoint_rotated_band import Block, GAP, absolute, read_block, require
from midpoint_rotated_band import run as find_polynomial
from midpoint_rotated_band import verify_proof
from midpoint_grid import use_flint_products
from verify_m0_pow_binary64 import INF, ONE, log_grid, log_point


SCHEMA = 'pow-q115-rotated-layer-v1'
SHIFT = 115
PRECISION = 144
MIN_P = 1 << 52
MAX_P = 2*MIN_P-1
MIDPOINTS = (ONE-1, ONE)


def verify_reduction():
    # Positive finite x, excluding x=1, satisfies abs(ln(x)) <= 1074*ln(2).
    grid, (_, log2_hi) = log_grid(PRECISION)
    max_log = Fraction(1074*log2_hi, grid.unit)
    cut = Fraction(1, 1 << GAP)
    limit = Fraction(MAX_P, 1 << SHIFT)*max_log+cut
    require(limit < min(Fraction(3, 1 << 54), Fraction(3, (1 << 53)+3)),
            'more rounding midpoints enter the layer')
    # The two other midpoints nearest 1 are 1-3*2^-54 and 1+3*2^-53.
    # Use -ln(1-a)>=a and ln(1+a)>=a/(1+a).
    require(cut < min(Fraction(1, 1 << 54), Fraction(1, (1 << 53)+1)),
            'opposite logarithmic signs may enter the strip')
    require(Fraction(MIN_P, 1 << SHIFT) == Fraction(1, 1 << 63)
            and Fraction(MAX_P+1, 1 << SHIFT) == Fraction(1, 1 << 62)
            and PRECISION+SHIFT < GAP, 'wrong exponent grid or directed unit')


@lru_cache(maxsize=2)
def scaled_target(midpoint):
    lo, hi = absolute(log_point(midpoint, PRECISION, True))
    # One unit covers Q*2^-GAP after scaling by 2^PRECISION.
    return (lo << SHIFT)-1, (hi << SHIFT)+1


def sides(block, index):
    x = block.encoding+index
    lo, hi = absolute(log_point(x, PRECISION, False))
    target_lo, target_hi = scaled_target(block.midpoint)
    below, above = MAX_P*hi < target_lo, MIN_P*lo > target_hi
    return (below, above) if block.binade >= 0 else (above, below)


def margin(block):
    """Return a half-open interval covering every admissible mantissa."""
    size = 1 << block.width
    offset = block.first
    low = lambda i: sides(block, offset+i)[0]
    high = lambda i: sides(block, offset+i)[1]
    if low(size-1) or high(0):
        return 0, 0
    lo, hi = 0, size
    if low(0):
        a, b = 0, size-1
        while a+1 < b:
            mid = (a+b)//2
            if low(mid):
                a = mid
            else:
                b = mid
        lo = a+1
    if high(size-1):
        a, b = 0, size-1
        while a+1 < b:
            mid = (a+b)//2
            if high(mid):
                b = mid
            else:
                a = mid
        hi = b
    # Only the successful endpoint tests and monotonicity of the exact
    # logarithm are needed. Rounding of the tests need not be monotone.
    return lo, max(lo, hi)


def spans(width):
    verify_reduction()
    require(type(width) is int and 1 <= width <= 52, 'invalid root block width')
    for m in MIDPOINTS:
        overall = 0
        for e in range(-1074, 1024):
            bits = min(52, e+1074)
            whole = Block(m, e, 0, bits, SHIFT)
            overall += whole.base
            lo, hi = margin(whole)
            if lo == hi:
                continue
            bits = min(bits, width)
            size = 1 << bits
            yield m, e, bits, lo//size*size, -(-hi//size)*size
        require(overall == INF-1, 'base-binade enumeration does not cover binary64')


def indexed_spans(plan):
    position = 0
    for m, e, width, start, stop in plan:
        end = position + ((stop-start) >> width)
        yield position, end, m, e, width, start
        position = end


def tasks(plan, first, last):
    for begin, end, m, e, width, start in indexed_spans(plan):
        if begin >= last:
            return
        low, high = max(begin, first), min(end, last)
        for index in range(low, high):
            yield Block(m, e, start + ((index-begin) << width), width, SHIFT)


def shape(width):
    for bound, degree, work_bits in ((18,3,64),(24,5,80),(30,6,96),(34,8,112),
                                     (38,11,144),(42,14,176),(45,17,192),(48,23,224),(52,32,288)):
        if width <= bound:
            return degree, work_bits
    raise ValueError('unsupported proof width')


def direct_excludes(block):
    for index in range(block.first, block.first+(1 << block.width)):
        if any(sides(block,index)):
            continue
        x = block.encoding + index
        for precision in (192, GAP+128):
            lo,hi = absolute(log_point(x,precision,False))
            require(lo > 0, 'the candidate denominator does not exclude zero')
            mlo,mhi = absolute(log_point(block.midpoint,precision,True))
            error = 1 << max(0,precision+SHIFT-GAP)
            first = max(MIN_P,-(-((mlo << SHIFT)-error)//hi))
            last = min(MAX_P,((mhi << SHIFT)+error)//lo)
            if first > last:
                break
        else:
            return False
    return True


def generate_block(block):
    fields = list(astuple(block))
    if block.width <= 8:
        return [[fields, 'direct' if direct_excludes(block) else 'open']]
    degree, work_bits = shape(block.width)
    job = (fields, degree, work_bits, 1)
    result = find_polynomial(job)
    if result['proof'] is not None:
        return [[fields, 'polynomial', result['proof']]]
    half = 1 << (block.width-1)
    left = Block(block.midpoint, block.binade, block.first, block.width-1, block.shift)
    right = Block(block.midpoint, block.binade, block.first+half, block.width-1, block.shift)
    return generate_block(left)+generate_block(right)


def verify_rows(job):
    root, records = job
    position = root.first
    stop = position+(1 << root.width)
    counts = Counter()
    for row in records:
        require(isinstance(row, list) and len(row) in (2,3), 'invalid layer record')
        piece = read_block(row[0])
        require((root.midpoint,root.binade,root.shift) == (piece.midpoint,piece.binade,piece.shift)
                and piece.first == position and position+(1 << piece.width) <= stop,
                'gap, overlap or wrong root in coverage')
        if row[1] == 'polynomial' and len(row) == 3:
            verify_proof(piece, row[2])
        elif row[1:] == ['direct']:
            require(piece.width <= 8 and direct_excludes(piece), 'direct leaf does not exclude its block')
        else:
            require(row[1:] == ['open'], 'invalid layer rule')
        counts[row[1]] += 1
        position += 1 << piece.width
    require(position == stop, 'missing end of root block')
    return counts


def record_batches(stream, roots):
    for root in roots:
        line = stream.readline()
        require(bool(line), 'missing root certificate')
        yield root, json.loads(line)
    require(not stream.read(1), 'unexpected rows at end of certificate')


def bounded_map(pool, fn, items, workers):
    source = iter(items)
    while batch := list(islice(source, 2*workers)):
        yield from pool.map(fn, batch)


def merged_ranges(ranges):
    merged = []
    for first, stop in sorted(ranges):
        require(first < stop and (not merged or first >= merged[-1][1]), 'overlapping proof ranges')
        if merged and first == merged[-1][1]:
            merged[-1] = (merged[-1][0], stop)
        else:
            merged.append((first, stop))
    return merged


def archive_range(path, prefix, count):
    with gzip.open(path, 'rt') as stream:
        header = json.loads(stream.readline())
    require(isinstance(header,list) and len(header) == 7 and header[:4] == prefix and header[-1] == count,
            'certificate does not match the full plan')
    first, stop = header[4:6]
    require(type(first) is int and type(stop) is int and 0 <= first < stop <= count, 'invalid archive range')
    return first, stop


def verify_archive(path, prefix, count, plan, first, stop, pool, workers):
    checked = Counter()
    with gzip.open(path, 'rt') as stream:
        header = prefix + [first, stop, count]
        require(json.loads(stream.readline()) == header, 'certificate does not match the full plan')
        work = record_batches(stream, tasks(plan, first, stop))
        for result in bounded_map(pool, verify_rows, work, workers):
            checked.update(result)
    return checked


def verify_bundle(args, plan, prefix, count, start):
    selected = set(args.binade)
    require(not selected or all(-1074 <= e <= 1023 for e in selected), 'invalid binade selection')
    required = [(lo, hi) for lo, hi, _, e, _, _ in indexed_spans(plan) if not selected or e in selected]
    archives = [(archive_range(path, prefix, count), path) for path in args.files]
    require(merged_ranges(r for r, _ in archives) == merged_ranges(required), 'missing or outside proof ranges')
    checked = Counter()
    with ProcessPoolExecutor(max_workers=args.workers, initializer=use_flint_products
                             if args.flint_products else None) as pool:
        for (first, stop), path in archives:
            checked.update(verify_archive(path, prefix, count, plan, first, stop, pool, args.workers))
    status = 'INCOMPLETE' if checked['open'] else 'VERIFIED_BINADES' if selected else 'VERIFIED_Q115'
    bases = sum(1 << min(52, e+1074) for e in selected) if selected else INF-1
    print(json.dumps(dict(status=status, seconds=round(monotonic()-start,3), binades=sorted(selected),
                          bases=bases, roots=sum(hi-lo for lo,hi in required), leaves=checked, plan_sha256=prefix[-1])))
    return 2 if checked['open'] else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('plan','generate','verify','verify-bundle'))
    parser.add_argument('files', type=Path, nargs='*')
    parser.add_argument('--width', type=int, default=38)
    parser.add_argument('--first', type=int, default=0)
    parser.add_argument('--stop', type=int)
    parser.add_argument('--workers', type=int, default=1)
    parser.add_argument('--flint-products', action='store_true')
    parser.add_argument('--binade', type=int, action='append', default=[])
    args = parser.parse_args()
    start = monotonic()
    plan = list(spans(args.width))
    count = sum((b-a) >> w for _,_,w,a,b in plan)
    plan_hash = sha256(json.dumps(plan,separators=(',',':')).encode()).hexdigest()
    if args.mode == 'plan':
        print(json.dumps(dict(gap_bits=GAP,shift=SHIFT,width=args.width,roots=count,binades=len(plan),
                             pruned=2*(INF-1)-sum(b-a for _,_,_,a,b in plan),plan_sha256=plan_hash)))
        return
    require(args.workers > 0, 'positive worker count required')
    prefix = [SCHEMA, GAP, args.width, plan_hash]
    if args.mode == 'verify-bundle':
        require(args.first == 0 and args.stop is None, 'a bundle derives ranges from the plan')
        return verify_bundle(args, plan, prefix, count, start)
    require(len(args.files) == 1 and not args.binade, 'one certificate file required')
    path, = args.files
    stop = count if args.stop is None else args.stop
    require(0 <= args.first < stop <= count, 'root range is outside plan')
    checked = Counter()
    with ProcessPoolExecutor(max_workers=args.workers, initializer=use_flint_products
                             if args.flint_products or args.mode == 'generate' else None) as pool:
        if args.mode == 'generate':
            with gzip.open(path,'xt',compresslevel=3) as stream:
                print(json.dumps(prefix+[args.first,stop,count]),file=stream)
                roots = tasks(plan, args.first, stop)
                for index,rows in enumerate(bounded_map(pool,generate_block,roots,args.workers),1):
                    print(json.dumps(rows,separators=(',',':')),file=stream)
                    checked.update(row[1] for row in rows)
                    if index % 512 == 0:
                        stream.flush()
                        print(f'{index}/{stop-args.first} roots',dict(checked), file=sys.stderr,flush=True)
        else:
            checked.update(verify_archive(path,prefix,count,plan,args.first,stop,pool,args.workers))
    status = ('INCOMPLETE' if checked['open'] else 'GENERATED' if args.mode == 'generate'
              else 'VERIFIED_Q115' if args.first == 0 and stop == count else 'VERIFIED_RANGE')
    print(json.dumps(dict(status=status,seconds=round(monotonic()-start,3),first=args.first,
                          stop=stop,total_roots=count,leaves=checked,plan_sha256=plan_hash)))
    return 2 if status == 'INCOMPLETE' else 0


if __name__ == '__main__':
    sys.exit(main())
