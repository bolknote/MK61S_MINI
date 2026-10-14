#!/usr/bin/env python3
"""Bounded symbolic refinement of transport candidates, not keyboard search.

Needs loaded `transport`, `verify`, `patterns`, `triples` from the interactive
analysis. No exhaustion in this old graph proves physical impossibility.
"""

from z3 import sat, unsat


def graph_sequence(sequence):
    out = []
    for ip in sequence:
        if out and (out[-1], ip) in ((0x93, 0x94), (0x12, 0xC6)):
            continue
        out.append(ip)
    return tuple(out)


def refine(limit=12):
    records = []
    for attempt in range(limit):
        print(f'REFINEMENT {attempt+1}/{limit}', flush=True)
        candidate = transport['find_candidate'](
            blocked={(0xB3, i) for i in range(0xBA, 0xC0)},
            blocked_triples=triples, blocked_patterns=patterns)
        if not candidate:
            return records, None
        result = verify['verify'](candidate)
        if result['result'] != unsat:
            return records, (candidate, result)
        bad = result['sequence'][:result['index']+1]
        generic = verify['verify_sequence'](bad)
        universal = generic['result'] == unsat
        if universal:
            # Binary search for a shortest impossible suffix. This is exact
            # multi-command reasoning with arbitrary future ring inputs.
            low, high = 0, len(bad)-1
            while high-low > 1:
                mid = (low+high)//2
                probe = verify['verify_sequence'](bad[mid:])
                if probe['result'] == unsat:
                    low = mid
                elif probe['result'] == sat:
                    high = mid
                else:
                    break
            blocked = graph_sequence(bad[low:])
        else:
            blocked = (0x100,) + graph_sequence(bad)
        patterns.add(blocked)
        records.append({'universal': universal, 'blocked': blocked})
        print('EXCLUDED '+('universal path: ' if universal else 'native prefix only: ')
              +' '.join(f'{v:02X}' for v in blocked), flush=True)
    return records, None
