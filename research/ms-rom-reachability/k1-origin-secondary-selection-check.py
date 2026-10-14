#!/usr/bin/env python3
"""Conditional ROM geometry with adjacent V/W markers and request in Q.

No native state is injected. These are connected symbolic IK1303 paths,
not keyboard-entry proofs. A separate IK1302 check examines direct AD->A3.
"""
import runpy
from pathlib import Path
from z3 import And, Or, ZeroExt, sat, unsat

root = Path(__file__).resolve().parent
q = runpy.run_path(str(root / 'analyze_ms_pending_opcodes.py'))
State, ex, base, keys, address = (q[n] for n in ('State', 'ex', 'base', 'keys', 'address'))
slots = q['slots']


def prove(p, claim, label):
    assert p.check() == sat, ('empty premise', label)
    p.push(); p.add(~claim)
    assert p.check() == unsat, label
    p.pop()


def secondary(start, opcode, v_marker=True):
    tag = 'origin_select_' + start + '_' + str(opcode) + '_' + str(v_marker)
    pages = {n: State(tag + '_' + n).m for n in slots}
    original = dict(pages)
    a = State(tag); a.m = pages[start]
    p = base(a, 0x6E); p.add(a.r[29] == 0)
    if opcode == 0x25:
        # Native upper-rotation tests supply these retained return tags.
        p.add(a.st[36] == 10, a.st[39] == 3,
              a.st[37] == 10, a.st[40] == 3)
    markers = ('V', 'W') if v_marker else ('W',)
    for n in slots:
        p.add(pages[n][22] == 15 if n in markers else pages[n][22] != 15)
    p.add(pages['W'][34] == 9, pages['W'][31] == 9,
          pages['Q'][34] == opcode // 16, pages['Q'][31] == opcode % 16)
    expected = [] if start == 'V' else (
        [('4E', 'P7', 'P9'), ('2A', 'P8', 'P7')] if opcode == 0x14 else
        [('3A', 'P7', 'P9'), ('3A', 'P8', 'P9'),
         ('3A', 'P9', 'P10'), ('2A', 'P10', 'P8')])
    if not v_marker:
        assert start == 'W'
        expected = ([('4E', 'P8', 'P9'), ('2A', 'P9', 'P8')] if opcode == 0x14 else
                    [('3A', 'P8', 'P9'), ('3A', 'P9', 'P10'),
                     ('3A', 'P10', 'marker'), ('2A', 'marker', 'P8')])
    found, route = [], []
    for step in range(70):
        p.push(); ips = q['q']['possible_values'](address(a), p, 257); p.pop()
        assert len(ips) == 1, ('not forced', route, ips)
        ip = ips[0]
        here = slots[(slots.index(start) + step) % 15]
        following = slots[(slots.index(start) + step + 1) % 15]
        route.append('%02X(%s)' % (ip, here))
        old = pages[here]; out = []
        a = ex(a, ip, *keys(tag + '_key_' + str(step)),
               serial_inputs=pages[following], emitted_outputs=out)
        if ip in (0x4E, 0x2A, 0x3A):
            want_ip, want_slot, source = expected[len(found)]
            assert (ip, here) == (int(want_ip, 16), want_slot)
            prove(p, And(*[out[1 + 3*j] == original[source][1 + 3*j] for j in range(12)],
                         *[out[j] == old[j] for j in range(42) if j % 3 != 1 or j >= 37]),
                  'exact output ' + route[-1])
            found.append((want_ip, want_slot, source))
        elif ip == 0x27:
            assert here == ('W' if v_marker else 'Q')
            prove(p, And(out[31] == 15,
                         *[out[j] == old[j] for j in range(42) if j != 31]),
                  'ACK only its selected request word')
        else:
            prove(p, And(*[out[j] == old[j] for j in range(42)]),
                  'no writes at ' + route[-1])
        pages[here] = out
        if ip == 0x39:
            prove(p, And(address(a) == 0x6E, a.r[29] == 0), 'quiet scanner return')
            break
    else:
        raise AssertionError('unclosed bounded path')
    assert found == expected
    if v_marker:
        prove(p, And(*[pages['marker'][j] == original['marker'][j] for j in range(42)],
                     *[pages['Q'][j] == original['Q'][j] for j in range(42)]),
              'neither the displaced d nor the request in Q is consumed')
    print('PASS', start, '%02X' % opcode, 'markers=' + ','.join(markers), ' -> '.join(route), flush=True)
    print('OUTPUT', found, flush=True)


def direct_request():
    primary = runpy.run_path(str(root / 'ik1302_symbolic.py'))
    addr = lambda a: ZeroExt(4, a.r[36]) | (ZeroExt(4, a.r[39]) << 4)
    for opcode in (0x14, 0x25):
        a = primary['State']('direct_ad_request_' + str(opcode))
        request = primary['State']('direct_ad_page_' + str(opcode)).m
        p = primary['base_solver'](a, 0xAD)
        p.add(a.r[35] == 3, a.r[30] == opcode % 16, a.r[33] == opcode // 16)
        first = []
        b = primary['execute_command'](a, 0xAD, *primary['arbitrary_keys']('direct_ad_keys'),
                                       serial_inputs=request, emitted_outputs=first)
        prove(p, And(addr(b) == 0xA3, *[x == y for x, y in zip(first, a.m)]),
              'AD jumps directly to A3 without writing the ring')
        out = []
        b = primary['execute_command'](b, 0xA3, *primary['arbitrary_keys']('direct_a3_keys'),
                                       emitted_outputs=out)
        prove(p, And(out[28] == a.r[27], out[31] == opcode % 16, out[34] == opcode // 16,
                     *[out[j] == request[j] for j in range(42) if j not in (28, 31, 34)]),
              'AD->A3 writes exactly three header tetras, without E9')
        print('PASS conditional AD->A3 request %02X: R35=3, R30=%X, R33=%X; '
              'R27 supplies third written tetra.' % (opcode, opcode % 16, opcode // 16), flush=True)


if __name__ == '__main__':
    for start in ('V', 'W'):
        for opcode in (0x14, 0x25):
            secondary(start, opcode)
    for opcode in (0x14, 0x25):
        secondary('W', opcode, v_marker=False)
    direct_request()
    print('LIMIT: symbolic local paths; no keyboard reachability, unchanged-Q request producer, '
          'or normal exit is claimed.', flush=True)
