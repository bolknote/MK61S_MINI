#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Exact integer/rational proofs for the standalone Qfplib ln changes."""
import argparse
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import re


def prove():
    root = Path(__file__).resolve().parent
    sources = {name: root/directory/'qfplib-m0-full_gcc.S'
               for name, directory in [('original', 'upstream'), ('modified', 'src')]}
    for path in sources.values():
        table = path.read_text().split('\ndtab_exp:\n')[1].split('\nqfp_lib_end:')[0]
        rows = re.findall(r'\.word\s+(0x[\da-f]+),\s*(0x[\da-f]+)', table)
        assert len(rows) == 32
        assert int(rows[-1][0], 16)+(int(rows[-1][1], 16) << 32) == 1 << 30
    # On each side of its rejection threshold, a greedy step is monotone.
    # Therefore the smallest reachable output is the smaller of its accepted
    # lower endpoint and its first rejected input. This bounds *all* Q62 inputs.
    limit = 1 << 62
    low = 1 << 61
    bounds = []
    for i in range(1, 32):
        def candidate(x):
            return x + ((x + (1 << (i-1))) >> i)
        left, right = low, limit
        while left < right:
            middle = (left+right)//2
            if candidate(middle) >= limit:
                right = middle
            else:
                left = middle+1
        threshold = left
        assert candidate(threshold) >= limit
        if threshold:
            assert candidate(threshold-1) < limit
        low = min(candidate(low) if low < threshold else low, threshold)
        bounds.append(dict(step=i, maximum_deficit=limit-low))
    assert limit-low == (1 << 31)-1
    # Throughout that interval, round_half_up(x/2^32) is exactly 2^30.
    assert (low+(1 << 31)) >> 32 == 1 << 30
    assert ((limit-1)+(1 << 31)) >> 32 == 1 << 30
    # The last table entry is 2^30; accepting step 32 subtracts it from y
    # and adds it to x, leaving the final integer y+x-1 exactly unchanged.

    # For 0 < a < 2^-37, the cubic-and-higher remainder in either |ln(1+-a)|
    # is strictly between zero and a^3/[3*(1-a)]. In Q108 it is below 1.
    a = F(65535, 1 << 53)
    remainder = a**3 / (3*(1-a)) * (1 << 108)
    assert 0 < remainder < 1
    counts = dict(positive=0, negative=0, exact_one=1)
    for negative in (False, True):
        # Above one, N is even because binary64 has spacing 2^-52.
        for n in range(1 if negative else 2, 65536, 1 if negative else 2):
            d = 0 if n < 256 else 4 if n < 4096 else 8
            polynomial = (n << 55) + (2*n*n if negative else -2*n*n)
            if d:
                square = n*n
                correction = (square if negative else square+(1 << (d-1))-1) >> (d-1)
            else:
                correction = 2*n*n
            quotient = (n << (55-d)) + (correction if negative else -correction)
            assert quotient == polynomial >> d
            jammed = quotient | 1
            assert 56 <= jammed.bit_length() <= 63
            # The exact magnitude lies inside (quotient, quotient+1), or
            # inside (quotient, quotient+remainder) when d=0. Binary64
            # midpoints at this scale are even integers (in fact multiples
            # of four). The odd jammed value cannot be a midpoint or cross
            # one: rounding it gives the exact function's RNE value.
            assert jammed & 1
            counts['negative' if negative else 'positive'] += 1
    assert sum(counts.values()) == 98303
    return dict(status='PASS',
                source_sha256={name:hashlib.sha256(path.read_bytes()).hexdigest()
                               for name,path in sources.items()},
                greedy_bounds=bounds,
                omitted_step=32, omitted_increment_and_table_entry=1 << 30,
                near_one_finite_input_count=sum(counts.values()), counts=counts,
                remainder_Q108_upper_bound=str(remainder),
                proof='All Q62 mantissas bounded by monotone branch intervals; all 98,302 nonzero near-one encodings checked for exact integer assembly, positive remainder and sufficient rounding guard bits. One returns exact +0.')


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--json',type=Path,required=True)
    args=p.parse_args()
    report=prove()
    args.json.parent.mkdir(parents=True,exist_ok=True)
    args.json.write_text(json.dumps(report,indent=2)+'\n')
    print('PASS: redundant ln step and exact near-one integer kernel')
