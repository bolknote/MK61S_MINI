#!/usr/bin/env python3
"""Both connected primary K* paths with real+V markers and no T marker.

Conditional accepted-9C contracts, not a keyboard-phase proof. In this
geometry neither branch can write E9(V): the possible targets are Q/X1.
"""
import runpy
from pathlib import Path
from z3 import And, If, UGE, ZeroExt, sat, unsat

q = runpy.run_path(str(Path(__file__).with_name('ik1302_symbolic.py')))
State, ex, base, keys = (q[n] for n in ('State', 'execute_command', 'base_solver', 'arbitrary_keys'))
slots = ['marker','control','X1','X','Y','Z','T','U','V','W','Q','P7','P8','P9','P10']
addr = lambda a: ZeroExt(4, a.r[36]) | (ZeroExt(4, a.r[39]) << 4)


def prove(p, claim, label):
    assert p.check() == sat, ('empty premise', label)
    p.push(); p.add(~claim)
    assert p.check() == unsat, label
    p.pop()


def check(start, verbose=False):
    tag = 'single_v_neutral_' + start
    pages = {n: State(tag + '_' + n).m for n in slots}
    original = dict(pages)
    a = State(tag); a.m = pages[start]
    p = base(a, 0x9C)
    p.add(a.r[30] == 8, a.r[33] == 2,
          If(pages[start][31] == 15, UGE(pages[start][34], 1), UGE(pages[start][34], 7)))
    for n in slots:
        p.add(pages[n][22] == 15 if n in ('marker','V') else pages[n][22] != 15)
    visible = 5 <= slots.index(start) <= 11
    source, target, request = ('X','Q','control') if visible else ('P7','X1','W')
    route, reads, writes = [], [], []
    for step in range(70):
        p.push(); ips = q['possible_values'](addr(a), p, 257); p.pop()
        assert len(ips) == 1, ('not forced', route, ips)
        ip = ips[0]
        here = slots[(slots.index(start)+step) % 15]
        following = slots[(slots.index(start)+step+1) % 15]
        route.append('%02X(%s)' % (ip, here))
        if ip == 0xEE:
            reads.append(here); assert here == source
        before = pages[here]; out = []
        a = ex(a, ip, *keys(tag + '_key_' + str(step)),
               serial_inputs=pages[following], emitted_outputs=out)
        if ip == 0xE9:
            assert here == target
            prove(p, And(*[out[1+3*j] == original[source][1+3*j] for j in range(12)],
                         *[out[j] == before[j] for j in range(42) if j % 3 != 1 or j >= 37]),
                  'exact single-word E9 at ' + here)
            writes.append(('E9', here))
        elif ip == 0xA3:
            assert here == request
            prove(p, And(out[28] == original[source][28], out[31] == 8, out[34] == 2,
                         *[out[j] == before[j] for j in range(42) if j not in (28,31,34)]),
                  'exact 28 request with source header tetra')
            prove(p, addr(a) == 0xD3, 'return to D3')
            writes.append(('A3', here))
        else:
            prove(p, And(*[x == y for x,y in zip(out,before)]), 'no writes at ' + route[-1])
        pages[here] = out
        if ip == 0xA3:
            break
    else:
        raise AssertionError('no bounded request')
    assert reads == [source] and writes == [('E9',target),('A3',request)]
    prove(p, And(*[pages['V'][j] == original['V'][j] for j in range(42)],
                 *[pages['T'][j] == original['T'][j] for j in range(42)]),
          'V remains a marker and T remains unchanged')
    print('PASS', {'accepted9C':start,'EE':source,'E9':target,'A3':request,'commands':len(route)},flush=True)
    if verbose:
        print('PATH',' -> '.join(route),flush=True)


if __name__ == '__main__':
    for start in slots:
        check(start, verbose=start in ('control','T','W','P8'))
    print('LIMIT: static real+V geometry, accepted 9C, pending opcode28; '
          'no frame selection or later numeric/secondary return is proved.',flush=True)
