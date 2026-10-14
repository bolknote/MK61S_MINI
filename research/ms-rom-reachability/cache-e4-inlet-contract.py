#!/usr/bin/env python3
"""All three immediate E4 inlets take A; E3 does not recover it from ST.

Exact arbitrary-primary local contracts. These do not claim an entry keyboard
protocol or exclude longer routes, prior ring exports or different readers.
The graph audit distinguishes a complete control-inlet inventory from data
survival. The old-A pair may also carry different prior reserves in B/ST:
neither C1 nor the double restore reads them into A before E4.
"""
from pathlib import Path
import runpy

from z3 import And

root = Path(__file__).resolve().parent
entry = runpy.run_path(str(root / 'cache-e4-entry-audit.py'))
w = runpy.run_path(str(root / 'cache46-writer-contracts.py'))
State, ex, base, keys, ip, A, eq, prove, stack = (w[name] for name in
    ('State', 'ex', 'base', 'keys', 'ip', 'A', 'eq', 'prove', 'stack'))
restore = (0xE3, 0x91, 0x92, 0x93, 0x94, 0x95, 0x98, 0x9A,
           0x93, 0x94, 0x95, 0x98, 0x9A)


def incoming_a(sequence, source):
    result = list(source)
    if sequence[0] == 0xC1:
        # C1 changes the mantissa sign, not a payload tetra or a backup inlet.
        result[8] = 9-source[8]
    return result


def run(sequence, selector=None):
    code = sequence[0]
    a = State(f'e4_inlet_{code:02X}')
    p = base(a, code)
    if selector is not None:
        p.add(a.s1 == selector)
    b = a
    for j, code in enumerate(sequence):
        prove(p, ip(b) == code, f'inlet command{j} {code:02X} forced', False)
        out, before = [], b
        b = ex(b, code, *keys(f'e4_inlet_{sequence[0]:02X}_keys{j}'),
               emitted_outputs=out)
        prove(p, eq(out, before.m), f'inlet {code:02X} no outgoing write', False)
    prove(p, And(ip(b) == 0xE4, eq(A(b), incoming_a(sequence, A(a)))),
          f'{sequence[0]:02X} inlet reachesE4 from incomingA only; arbitrary B/ST; '
          + ('sign8=9-old8' if sequence[0] == 0xC1 else 'exactA12'))
    return sequence, a, b, p


def main():
    states, edges = entry['states'], entry['edges']
    predecessors = {states[i][0] for i, row in enumerate(edges)
                    if any(states[j][0] == 0xE4 for j in row)}
    assert predecessors == {0x9A, 0xC1, 0xE6}, predecessors
    print('PASS complete reset graph: E4 immediate predecessors9A/C1/E6.', flush=True)
    results = [run((0xC1,)), run((0xE6,), selector=4), run(restore)]
    for seq, inlet, end, local in results:
        if seq[0] == 0xE6:
            continue
        # Begin BEFORE the common EE. Old A, B and numeric ST are fully
        # arbitrary and may include an independent/correlated old-A reserve.
        a = State(f'e4_ee_inlet_{seq[0]:02X}')
        p = base(a, 0xEE)
        p.add(stack(a)[0] == seq[0])
        source = a.m[1:36:3]
        out = []
        b = ex(a, 0xEE, *keys(f'e4_ee_keys_{seq[0]:02X}'), emitted_outputs=out)
        prove(p, And(ip(b) == seq[0], eq(A(b), source), eq(out, a.m)),
              f'EE/top{seq[0]:02X} reads newM2 intoA, no oldA reserve read')
        for j, code in enumerate(seq):
            prove(p, ip(b) == code, f'EE inlet{code:02X} forced', False)
            b = ex(b, code, *keys(f'e4_ee_restore_{seq[0]:02X}_{j}'))
        prove(p, And(ip(b) == 0xE4, eq(A(b), incoming_a(seq, source))),
              f'EE→{seq[0]:02X}→E4 copies NEW M2, irrespective of oldA/B/ST backup values')
    print('LIMIT: local straight inlets only; a longer pre-E4 recovery, '
          'a prior ring export, a different reader and a native protocol '
          'remain unproved, not globally excluded.', flush=True)


if __name__ == '__main__':
    main()
