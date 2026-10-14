#!/usr/bin/env python3
"""Conditional STORE map with real and V markers, unchanged IK1302 ROM.

Start at an accepted 9C with pending opcode 40h..4Eh. This establishes
which physical EE/D4 pair follows, not the keyboard/frame which reaches
that accepted scan. No native calculator state is injected.
"""
import runpy
from pathlib import Path
from z3 import And, If, UGE, ZeroExt, sat, unsat

q = runpy.run_path(str(Path(__file__).with_name('ik1302_symbolic.py')))
State, ex, base, keys = (q[n] for n in ('State', 'execute_command', 'base_solver', 'arbitrary_keys'))
slots = ['marker','control','X1','X','Y','Z','T','U','V','W','Q','P7','P8','P9','P10']
ordinary = ['8','9','A','B','C','D','E','0','1','2','3','4','5','6','7']
addr = lambda a: ZeroExt(4, a.r[36]) | (ZeroExt(4, a.r[39]) << 4)


def prove(p, claim, name):
    assert p.check() == sat, ('empty premise', name)
    p.push(); p.add(~claim)
    assert p.check() == unsat, name
    p.pop()


def check(start, operand, verbose=False):
    tag = 'store_map_' + start + '_' + str(operand)
    pages = {n: State(tag + '_' + n).m for n in slots}
    a = State(tag); a.m = pages[start]
    p = base(a, 0x9C)
    p.add(a.r[30] == operand, a.r[33] == 4,
          If(pages[start][31] == 15, UGE(pages[start][34], 1), UGE(pages[start][34], 7)))
    for n in slots:
        p.add(pages[n][22] == 15 if n in ('marker','V') else pages[n][22] != 15)
    visible = 5 <= slots.index(start) <= 11
    source = 'X' if visible else 'P7'
    target_index = ((8 if visible else 0) + 7 + operand) % 15
    target = slots[target_index]
    route, reads = [], []
    for step in range(100):
        p.push(); ips = q['possible_values'](addr(a), p, 257); p.pop()
        assert len(ips) == 1, ('not forced', route, ips)
        ip = ips[0]
        here = slots[(slots.index(start) + step) % 15]
        following = slots[(slots.index(start) + step + 1) % 15]
        route.append('%02X(%s)' % (ip, here))
        if ip == 0xEE:
            reads.append(here); assert here == source
        out = []
        a = ex(a, ip, *keys(tag + '_key_' + str(step)),
               serial_inputs=pages[following], emitted_outputs=out)
        if ip == 0xD4:
            assert here == target and reads == [source]
            prove(p, And(*[out[3*j] == pages[source][1+3*j] for j in range(12)],
                         *[out[j] == pages[here][j] for j in range(42) if j % 3 != 0 or j >= 36]),
                  'only twelve ordinary numeric tetras are written')
            prove(p, addr(a) == 0xA5, 'finite D4 return A5')
            break
        prove(p, And(*[out[j] == pages[here][j] for j in range(42)]),
              'no other writes at ' + route[-1])
    else:
        raise AssertionError('no bounded D4')
    result = {'accepted9C':start,'opcode':'%02X' % (0x40+operand),
              'source':source,'D4':target,'ordinaryRegister':ordinary[target_index],
              'commands':len(route)}
    print('PASS',result,flush=True)
    if verbose: print('PATH',' -> '.join(route),flush=True)
    return result


if __name__ == '__main__':
    # Every physical accepted-control origin; the source split is exact.
    for start in slots:
        check(start, 7 if 5 <= slots.index(start) <= 11 else 0,
              verbose=start in ('control','T','W','P7'))
    # Every ordinary STORE operand in each of the two address families.
    for start in ('control','T'):
        for operand in range(15):
            check(start,operand)
    print('LIMIT: accepted-9C suffix through D4/A5 only. No keyboard phase, '
          'late formatting, other-chip interaction or complete save/cleanup is proved.',flush=True)
