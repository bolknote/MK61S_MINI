#!/usr/bin/env python3
"""Remaining isolated A7 constructors after the proved reset57/L0 barrier.

Rechecks all256 exact paired source transfers, the complete35 first-use cut,
unreachable arithmetic words and C3's local hex addition. This does not supply
a native C3 entry, a signF register, a finite C3 writer or partialK2.
"""
from collections import Counter
from pathlib import Path
import runpy

from z3 import And

root = Path(__file__).resolve().parent
frontier = runpy.run_path(str(root / 'cache-input-sign-frontier.py'))
w, q = frontier['w'], frontier['q']
g = runpy.run_path(str(root / 'cache-numeric-export-gates.py'))


def complete_constructor_cut():
    inventory = frontier['inventory']()
    report = frontier['first_frontier'](inventory)
    counts = Counter(state[0] for state in g['states'])
    dead = (0x0B, 0x0C, 0x0D, 0x0E, 0x3B, 0x3C, 0x3D, 0x3E)
    assert all(counts[code] == 0 for code in dead)
    assert (counts[0x57], counts[0xC3]) == (104, 61)
    assert set(inventory['isolatedTransformsWithF']) == {
        f'{code:02X}' for code in dead + (0x57, 0xC3)}
    assert report['isolatedTransformsBeforeStop'] == {'57': 18}
    print('PASS complete constructor classification: eight isolated arithmetic '
          'words absent from ALL reset contexts;57 reachable but its L0 '
          'invariant is proved separately. C3 has61 conservative contexts '
          'but NONE before first A7 observer/loss in the complete806→15737 cut.',
          flush=True)
    print('BOUNDARY: turning native idle7 into F requires crossing a first '
          'observer/copy, a different source or earlier preparation. C3 '
          'and its positive graph paths are NOT native witnesses.', flush=True)


def c3_local_and_return():
    a = q['State']('next_constructor_c3')
    p = w['base'](a, 0xC3)
    outputs = []
    b = w['ex'](a, 0xC3, *q['arbitrary_keys']('next_constructor_c3_keys'),
                emitted_outputs=outputs)
    w['prove'](p, And(b.r[21] == a.r[21] + a.r[22],
                     b.r[34] == a.r[34], w['ip'](b) == 0xC2,
                     w['eq'](outputs, a.m)),
               'C3 adds A7+B7 modulo16, holds header R34, exitsC2 and '
               'writes nothing; no carry/key/serial prerequisite')
    p.push(); p.add(a.r[21] == 7)
    w['prove'](p, (b.r[21] == 15) == (a.r[22] == 8),
               'CONDITIONAL C3 makesF from7 IFF B7=8; NOT native B7/C3 entry')
    p.pop()
    a = q['State']('next_constructor_c2')
    p = w['base'](a, 0xC2)
    outputs = []
    b = w['ex'](a, 0xC2, *q['arbitrary_keys']('next_constructor_c2_keys'),
                emitted_outputs=outputs)
    w['prove'](p, And(b.r[21] == a.r[21], b.r[34] == a.r[34],
                     w['ip'](b) == 0xDC, w['stack'](b)[0] == 0xC3,
                     w['eq'](outputs, a.m)),
               'C2 holds A7/header and pushes own returnC3, callsDC, no write')
    # This inherited independent proof is universal in ALL other fields,
    # including freshly constructed F; it must not be rebranded an escape.
    returns = runpy.run_path(str(root / 'cache-d4-return-contract.py'))
    returns['c3_loop_and_cf_inlet']()
    print('C3 LIMIT: even a prepared7+8 makes only a working F. Header4 '
          'forces the proved endless C3/C2/writer loop; other headers, '
          'a preserving first copy and a native joint inlet need separate work.',
          flush=True)


if __name__ == '__main__':
    complete_constructor_cut()
    c3_local_and_return()
