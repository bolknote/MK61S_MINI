#!/usr/bin/env python3
"""Bounded primary-input contracts at accepted Z/Q origins.

This follows original IK1302 microcode and a connected 15-page ring. It
does not inject a calculator state or prove a globally impossible exit.
"""
import runpy
from pathlib import Path
from z3 import And, If, UGE, ZeroExt, sat, unsat

root = Path(__file__).resolve().parent
q = runpy.run_path(str(root / 'ik1302_symbolic.py'))
S, ex, base, keys = (q[n] for n in
                    ('State', 'execute_command', 'base_solver', 'arbitrary_keys'))
slots = ['marker', 'control', 'X1', 'X', 'Y', 'Z', 'T',
         'U', 'V', 'W', 'Q', 'P7', 'P8', 'P9', 'P10']
addr = lambda a: ZeroExt(4, a.r[36]) | (ZeroExt(4, a.r[39]) << 4)


def prove(p, claim, label):
    assert p.check() == sat, ('empty premise', label)
    p.push()
    p.add(~claim)
    answer = p.check()
    p.pop()
    assert answer == unsat, label


def primary(start, code):
    assert start in ('T', 'P7') and code in (*range(10), 0x0D)
    tag = 'zq_primary_' + start + '_%02X' % code
    pages = {n: S(tag + n).m for n in slots}
    original = dict(pages)
    a = S(tag)
    a.m = pages[start]
    p = base(a, 0x9C)
    p.add(a.r[30] == code, a.r[33] == 0, a.s1 == code,
          If(a.m[31] == 15, UGE(a.m[34], 1), UGE(a.m[34], 7)))
    for n in slots:
        p.add(pages[n][22] == 15 if n in ('Z', 'Q') else pages[n][22] != 15)
    # This is the fresh-entry branch seen after Z/Q, not all digit modes.
    # 8C restores flags from ST, so R26=0 at 9C would not suffice.
    if code < 10:
        p.add(a.st[25] == 0, a.r[41] == 15)
    route, writes = [], []
    carried = None
    for step in range(160):
        p.push()
        ips = q['possible_values'](addr(a), p, 257)
        p.pop()
        assert len(ips) == 1, ('unforced', route, ips)
        ip = ips[0]
        here = slots[(slots.index(start) + step) % 15]
        following = slots[(slots.index(start) + step + 1) % 15]
        route.append('%02X(%s)' % (ip, here))
        assert ip not in (0xEE, 0xE9, 0xA3, 0xD4, 0xD6), ('other reader/writer', route)
        if code < 10 and ip == 0xA9:
            assert writes == ['V', 'W', 'Q', 'P7'], writes
            for dst, src in [('W', 'V'), ('Q', 'W'), ('P7', 'Q')]:
                prove(p, And(*[pages[dst][1 + 3*j] == original[src][1 + 3*j]
                               for j in range(12)]), dst + ' exact old ' + src)
            # The displaced q is still A immediately before A9, rather
            # than a full word reserved anywhere in the ring by this prefix.
            prove(p, And(*[a.r[3*j] == original['P7'][1 + 3*j]
                           for j in range(12)]), 'q carried in A before A9')
            break
        old = pages[here]
        out = []
        b = ex(a, ip, *keys(tag + str(step)),
               serial_inputs=pages[following], emitted_outputs=out)
        if ip in (0xE7, 0xA8):
            prove(p, And(*[out[j] == old[j] for j in range(42)
                           if j % 3 != 1 or j >= 37]), 'only numeric M2 writes')
            if ip == 0xA8:
                prove(p, And(*[out[1 + 3*j] == carried[j] for j in range(12)]),
                      'exact carried push ' + here)
            writes.append(here)
            carried = [old[1 + 3*j] for j in range(12)]
            if code == 0x0D:
                assert writes == ['V']
                prove(p, And(*[out[1 + 3*j] == 0 for j in range(12)]), 'Cx writes zero')
                pages[here] = out
                a = b
                break
        else:
            prove(p, And(*[x == y for x, y in zip(old, out)]), 'no other write ' + route[-1])
        pages[here] = out
        a = b
    else:
        raise AssertionError('no bounded primary effect')
    for n in slots:
        if n not in writes:
            prove(p, And(*[x == y for x, y in zip(pages[n], original[n])]), 'held page ' + n)
    result = {'origin': start, 'code': '%02X' % code, 'writes': writes,
              'stop': 'after E7' if code == 0x0D else 'before A9', 'commands': len(route)}
    print('PASS', result, flush=True)
    if code in (0, 0x0D):
        print('PATH', ' -> '.join(route), flush=True)
    return result


def cached_editor(start, code):
    """Comma/sign/exponent prefix uses saved registers, not a new word read.

Only the suffix up to 8D is asserted. In particular this does not pretend
    that all numerical modes of the following editor are equivalent.
    """
    assert start in ('T', 'P7') and code in (0x0A, 0x0B, 0x0C)
    tag = 'zq_cached_' + start + '_%02X' % code
    pages = {n: S(tag + n).m for n in slots}
    initial = S(tag)
    initial.m = pages[start]
    a = initial
    p = base(a, 0x9C)
    p.add(a.r[30] == code, a.r[33] == 0, a.s1 == code,
          If(a.m[31] == 15, UGE(a.m[34], 1), UGE(a.m[34], 7)))
    for n in slots:
        p.add(pages[n][22] == 15 if n in ('Z', 'Q') else pages[n][22] != 15)
    route = []
    for step in range(30):
        p.push()
        ips = q['possible_values'](addr(a), p, 257)
        p.pop()
        assert len(ips) == 1, ('unforced editor prefix', route, ips)
        ip = ips[0]
        here = slots[(slots.index(start) + step) % 15]
        following = slots[(slots.index(start) + step + 1) % 15]
        route.append('%02X(%s)' % (ip, here))
        if ip == 0x8D:
            expected = []
            for j in range(36):
                if j >= 27:
                    value = initial.st[j]
                elif j % 3 == 0:
                    value = initial.r[j]
                else:
                    value = initial.st[j - 1]
                expected.append(a.r[j] == value)
            prove(p, And(*expected), 'exact cached R/ST restoration')
            assert here == start
            print('PASS cached editor prefix', {'origin': start, 'code': '%02X' % code,
                  'commands': len(route), 'freshNumericRead': False, 'writes': []}, flush=True)
            return
        out = []
        a = ex(a, ip, *keys(tag + str(step)),
               serial_inputs=pages[following], emitted_outputs=out)
        prove(p, And(*[x == y for x, y in zip(out, pages[here])]), 'editor prefix ring held')
    raise AssertionError('no bounded 8D')


if __name__ == '__main__':
    for origin in ('T', 'P7'):
        for opcode in (*range(10), 0x0D):
            primary(origin, opcode)
        for opcode in (0x0A, 0x0B, 0x0C):
            cached_editor(origin, opcode)
    print('LIMIT: local accepted origins, fresh-digit branch only, primary chip only. '
          'No complete operation, universal input classification, or no-go claim.', flush=True)
