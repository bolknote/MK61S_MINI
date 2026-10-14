#!/usr/bin/env python3
"""Bounded primary-operation barrier after Z/Q entry, with no real marker.

This is not a whole-ROM impossibility theorem. It covers accepted ordinary
ENTER, LastX, NOP, ordinary-D6 RCL and STORE prefixes, not anomalous state,
digit editing, other primary instructions, secondary operations or header repair.
"""
import contextlib
import io
import runpy
from pathlib import Path
from z3 import And, If, UGE, ZeroExt, sat, unsat

root = Path(__file__).resolve().parent
q = runpy.run_path(str(root / 'ik1302_symbolic.py'))
State, ex, base, keys = (q[n] for n in ('State', 'execute_command', 'base_solver', 'arbitrary_keys'))
slots = ['marker', 'control', 'X1', 'X', 'Y', 'Z', 'T', 'U', 'V', 'W', 'Q', 'P7', 'P8', 'P9', 'P10']
addr = lambda a: ZeroExt(4, a.r[36]) | (ZeroExt(4, a.r[39]) << 4)


def prove(p, claim, label):
    assert p.check() == sat, ('empty premise', label)
    p.push(); p.add(~claim)
    assert p.check() == unsat, label
    p.pop()


def store(start, operand):
    tag = 'zq_store_' + start + '_' + str(operand)
    pages = {n: State(tag + '_' + n).m for n in slots}
    a = State(tag); a.m = pages[start]
    p = base(a, 0x9C)
    p.add(a.r[30] == operand, a.r[33] == 4,
          If(a.m[31] == 15, UGE(a.m[34], 1), UGE(a.m[34], 7)))
    for n in slots:
        p.add(pages[n][22] == 15 if n in ('Z', 'Q') else pages[n][22] != 15)
    source = 'P9' if start == 'T' else 'V'
    route = []
    reads = []
    for step in range(100):
        p.push(); ips = q['possible_values'](addr(a), p, 257); p.pop()
        assert len(ips) == 1, ('unforced', route, ips)
        ip = ips[0]
        here = slots[(slots.index(start) + step) % 15]
        following = slots[(slots.index(start) + step + 1) % 15]
        route.append('%02X(%s)' % (ip, here))
        if ip == 0xEE:
            reads.append(here)
            assert here == source
        out = []
        a = ex(a, ip, *keys(tag + '_' + str(step)), serial_inputs=pages[following], emitted_outputs=out)
        if ip == 0xD4:
            assert reads == [source]
            prove(p, And(*[out[3*j] == pages[source][1+3*j] for j in range(12)],
                         *[out[j] == pages[here][j] for j in range(42) if j % 3 != 0 or j >= 36]),
                  'STORE writes only twelve ordinary-register tetras')
            prove(p, addr(a) == 0xA5, 'STORE returns to A5')
            return {'start': start, 'operand': operand, 'source': source, 'D4': here}
        prove(p, And(*[out[j] == pages[here][j] for j in range(42)]), 'no earlier write ' + route[-1])
    raise AssertionError('No D4 within structural bound')


if __name__ == '__main__':
    reader = runpy.run_path(str(root / 'k1-ytv-reader-map.py'))['reader']
    for code in (0x0E, 0x0F, 0x54):
        for origin in ('T', 'P7'):
            with contextlib.redirect_stdout(io.StringIO()):
                r = reader(origin, code, ('Z', 'Q'), real=False)
            assert r['reads'][1] == 'V'
            assert r['reads'][0] == ({0x0E: ('P9', 'V'), 0x0F: ('P8', 'U'), 0x54: ('P9', 'V')}[code][origin == 'P7'])
            assert r['push'] == ([] if code == 0x54 else ['V', 'W', 'Q', 'P7'])
            print('PASS reader', r, flush=True)
    for origin in ('T', 'P7'):
        windows = {}
        for operand in range(15):
            with contextlib.redirect_stdout(io.StringIO()):
                r = reader(origin, 0x60 + operand, ('Z', 'Q'), real=False)
            assert r['reads'][0] in ('V', 'P9')
            assert r['push'] in (['V', 'W', 'Q', 'P7'], ['P9', 'P10', 'marker', 'control'])
            windows.setdefault('/'.join(r['push']), []).append('%02X' % (0x60 + operand))
        print('PASS all RCL operands with M1[21]!=F', origin, windows, flush=True)
        for operand in range(15):
            r = store(origin, operand)
            assert r['source'] not in ('T', 'P7', 'marker', 'control')
        print('PASS all STORE operands', origin, 'source=' + ('P9' if origin == 'T' else 'V'), flush=True)
    print('LIMIT: accepted local primary prefixes only, not scanner timing or a whole-ROM impossibility theorem.', flush=True)
