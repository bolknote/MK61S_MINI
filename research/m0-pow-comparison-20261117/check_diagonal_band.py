#!/usr/bin/env python3
"""Check the domain, exterior signs, and shard coverage of a diagonal band."""

import argparse
from hashlib import sha256
import json
from pathlib import Path

from midpoint_grid import FixedInterval, add

Q = 1 << 52


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def check(path, width, d_first, d_stop, shards):
    require(1 <= width <= 51 and 1 <= shards <= 140, 'invalid requested width or shard count')
    last = Q+(1 << width)-1
    require(0 <= d_first < d_stop <= 2*Q-last, 'requested band crosses a binade')
    data = path.read_bytes()
    lines = data.decode('ascii').splitlines()
    require(len(lines) == shards, 'unexpected number of shard records')
    mode = lines[0].split()[0]
    require(mode in ('VERIFIED_BAND', 'VERIFIED_AFFINE'), 'unexpected shard status')

    first = stop = None
    groups = splits = queries = affine_groups = 0
    for index, line in enumerate(lines):
        prefix, *fields = line.split()
        require(prefix == mode and len(fields) == 10+(mode == 'VERIFIED_AFFINE'),
                'mixed or malformed shard records')
        w, d0, d1, r0, r1, start, end, g, s, calls, *affine = map(int, fields)
        require((w, d0, d1) == (width, d_first, d_stop), 'inconsistent band')
        if first is None:
            first, stop = r0, r1
        require(1 <= first <= stop <= Q and (r0, r1) == (first, stop), 'inconsistent exponent cut')
        n = stop-first
        require((start, end) == (first+n*index//shards, first+n*(index+1)//shards),
                'shard gap, overlap, or reordering')
        require(min(g, s, calls) >= 0 and g == end-start+s and (not affine or 0 <= affine[0] <= g),
                'inconsistent work counters')
        groups += g
        splits += s
        queries += calls
        affine_groups += sum(affine)

    grid = FixedInterval(256)
    ln2 = grid.log(2, 1)
    guard = 1 << 128

    def delta(a, d, r):
        lead = grid.scale(ln2, 1022*r-Q)
        base = grid.scale(grid.log(a, Q), r)
        midpoint = grid.scale(grid.log(2*a+2*d+1, 2*a), -Q)
        return add(add(lead, base), midpoint)

    require(delta(last, d_first, first-1)[1] < -guard and delta(Q, d_stop-1, stop)[0] > guard,
            'the exterior exponent ranges are open')
    return dict(status='VERIFIED_PARTITION', mode=mode, width=width, offsets=[d_first, d_stop],
                shards=shards, r=[first, stop], exponent_candidates=stop-first,
                pairs=(1 << width)*(d_stop-d_first), groups=groups, splits=splits,
                sign_queries=queries, affine_groups=affine_groups, sha256=sha256(data).hexdigest())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('log', type=Path)
    for name in ('width', 'd_first', 'd_stop', 'shards'):
        parser.add_argument(name, type=int)
    args = parser.parse_args()
    try:
        result = check(args.log, args.width, args.d_first, args.d_stop, args.shards)
    except (OSError, ValueError, IndexError) as error:
        parser.error(str(error))
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
