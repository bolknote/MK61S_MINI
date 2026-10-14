#!/usr/bin/env python3
"""Original BE writer callers, exact reserves and independent address inlet.

Positive paths are CONDITIONAL PRIMARY ROM contracts, never keyboard
recipes or Ms transfers. All returns are made by original callers.
The complete reset cover plus an exact induction closes only the direct
B3 D/E shortcuts; it does not exclude longer routes through49/82.
"""
from collections import Counter
from pathlib import Path
import runpy

from z3 import And, If, UGE, sat

root = Path(__file__).resolve().parent
prior = runpy.run_path(str(root / 'cache-writer-flag-repair.py'))
r, w, q, states, edges = (prior[n] for n in ('r', 'w', 'q', 'states', 'edges'))
walk = prior['walk']
double = r['double']
N8 = lambda n: q['BitVecVal'](n, 8)
A = lambda a: a.r[0:36:3]
B = lambda a: a.r[1:36:3]
C = lambda a: a.r[2:36:3]
ST0 = lambda a: a.st[0:36:3]
ST1 = lambda a: a.st[1:36:3]


def original_be_source_cut():
    expected = {
        0xB3: {0xB1: 149, 0xB3: 30},
        0xBD: {0x49: 56, 0xB3: 30, 0x82: 30},
        0xBE: {0xB3: 30, 0x9A: 18},
        0x49: {0x47: 47, 0xBC: 9},
        0x82: {0x8F: 30, 0x81: 30},
    }
    assert len(states) == 52416 and sum(map(len, edges)) == 95731
    for target, parents in expected.items():
        assert Counter(states[i][0] for i, row in enumerate(edges)
            for child in row if states[child][0] == target) == parents
    assert states[0][0] != 0xB3
    for code in (0xB1, 0xB3, 0xBD, 0xBE, 0x49, 0x82, 0x47):
        a = q['State'](f'be_source_{code:02X}'); p = w['base'](a, code); out = []
        b = w['ex'](a, code, *q['arbitrary_keys'](f'be_source_keys_{code:02X}'),
                    emitted_outputs=out)
        if code == 0xB1:
            claim = And(b.r[26] == 0, b.r[29] == a.r[29],
                w['ip'](b) == If(UGE(a.r[29], 8), N8(0xB3), N8(0xB2)))
        elif code == 0xB3:
            claim = And(b.r[26] == a.r[26], b.r[29] == a.r[29],
                b.r[23] == 0, b.s1 == a.r[29],
                b.l == If(UGE(a.r[26], 9), q['N1'](1), q['N1'](0)),
                w['ip'](b) == (N8(0xB0) | q['ZeroExt'](4, a.r[29])))
        elif code == 0xBD:
            claim = And(w['ip'](b) == If(a.l == 1, N8(0x91), N8(0xBF)),
                w['stack'](b)[0] == 0xBE, b.s1 == a.r[2],
                w['eq'](A(b), A(a)), w['eq'](ST0(b), ST0(a)),
                w['eq'](ST1(b), ST1(a)))
        elif code == 0xBE:
            claim = And(w['ip'](b) == If(a.r[23] == 0, N8(0xB0), N8(0x63)),
                *[b.r[j] == a.r[j] for j in (2, 23, 26, 30, 31, 33, 34)])
        elif code == 0x49:
            claim = And(w['ip'](b) == 0xBD, b.l == 1,
                w['eq'](A(b), B(a)), w['eq'](B(b), A(a)),
                w['eq'](C(b), C(a)), w['eq'](ST0(b), ST0(a)),
                w['eq'](ST1(b), ST1(a)))
        elif code == 0x82:
            claim = And(w['ip'](b) == If(a.r[26] == 8, N8(0xBD), N8(0x84)),
                b.l == If(a.r[26] == 8, q['N1'](1), q['N1'](0)),
                w['eq'](A(b), A(a)), w['eq'](B(b), B(a)),
                w['eq'](ST0(b), ST0(a)), w['eq'](ST1(b), ST1(a)))
        else:
            claim = And(w['ip'](b) == 0x49, w['eq'](A(b), ST0(a)))
        w['prove'](p, And(claim, w['eq'](out, a.m)), f'exact original BE gate{code:02X}')
    # B1 is the only nonself B3 source and clears R26. B3 holds it.
    # Since reset is not B3, induction gives R26=0 at every actual B3,
    # hence L=0 AFTER B3, even with arbitrary future keys/serial inputs.
    for selector, sequence, exit_code in (
            (13, (0xB3, 0xBD, 0xBF), 0xC0),
            (14, (0xB3, 0xBE), 0xB0)):
        label = f'be_direct_{selector:X}'
        a = q['State'](label); p = w['base'](a, 0xB3)
        p.add(a.r[26] == 0, a.r[29] == selector)
        b = walk(a, p, sequence, label)
        w['prove'](p, And(w['ip'](b) == exit_code, b.r[23] == 0),
            f'reset-shaped B3/{selector:X} shortcut cannot import91 or enter63')
    print('PASS complete reset source cut + R26zero/Lzero induction: '
          'B3/D→BD→BF→C0, B3/E→BE→B0; no direct writer. '
          'Only original49 or82 can supply BD/Lone for full91/headBE. '
          '49 swaps ALL12 A/B, not just the byte;47 overwrites A fromST0.', flush=True)


def original_call_reserves():
    for caller in (0x49, 0x82):
        label = f'be_reserve_{caller:02X}'
        a = q['State'](label); p = w['base'](a, caller)
        if caller == 0x82: p.add(a.r[26] == 8)
        b = walk(a, p, (caller, 0xBD, *double), label)
        values = (B(a), ST0(a), ST1(a), A(a), C(a)) if caller == 0x49 else (
                  A(a), ST0(a), ST1(a), B(a), C(a))
        targets = (A(b), B(b), C(b), ST0(b), ST1(b))
        w['prove'](p, And(w['ip'](b) == 0xBE,
            *[w['eq'](dst, src) for dst, src in zip(targets, values)]),
            f'original{caller:02X}/BD/full91→BE exact five-buffer ALL12 map')
    print('PASS at originalBE:49 path gives (A,B,C,ST0,ST1)='
          '(oldB,oldST0,oldST1,oldA,oldC);82 gives '
          '(oldA,oldST0,oldST1,oldB,oldC). This is a full12-tetra reserve, '
          'NOT a native supplier or safe physical Ms export.', flush=True)


def independent_writer_interfaces():
    for caller in (0x49, 0x82):
        for offset in range(7):
            label = f'be_writer_{caller:02X}_{offset}'
            a = q['State'](label); p = w['base'](a, caller)
            address = 84+offset
            p.add(a.st[1] == 5, a.st[22] == 1, a.st[25] == 0,
                  a.st[30] == address % 10, a.st[33] == address // 10)
            if caller == 0x82: p.add(a.r[26] == 8)
            b = walk(a, p, (caller, 0xBD, *double, 0xBE, 0x63,
                *([0x64]*13), 0x66), label+'_normalize')
            # Source returns/marker assumption are explicit, not repaired IP.
            p.add(b.m[22] == 15)
            b = walk(b, p, (1, *([2]*13), 3, 4, 0xBA, 0xCC, 0xCD), label+'_wait')
            input_buffer = B(a) if caller == 0x49 else A(a)
            reserve = A(a) if caller == 0x49 else B(a)
            w['prove'](p, And(w['ip'](b) == 0xC9, w['stack'](b)[0] == 0x67,
                b.r[2] == 5, b.r[23] == 1, b.r[26] == 0,
                b.r[31] == address % 10, b.r[34] == address // 10,
                b.s1 == 9, b.r[29] == 0, b.r[38] == 8,
                b.r[35] == offset, b.r[32] == 12,
                w['eq'](A(b), input_buffer),
                w['eq'](ST0(b), [*reserve[:9], *input_buffer[9:12]])),
                f'CONDITIONAL original{caller:02X}/offset{offset}: exact writer-C9/67 '
                'inlet, independent256-byte/address, ALL12 input + lower9 reserve intact')
            # Explicit nonempty independent-byte coverage; no payload restriction.
            p.push()
            byte = q['BitVec'](label+'_all256_source', 8)
            p.add(w['byte'](input_buffer[10], input_buffer[11]) == byte)
            assert p.check() == sat
            w['prove'](p, w['byte'](b.r[30], b.r[33]) == byte,
                       label+' all256 source formula', False)
            assert q['possible_values'](byte, p, 257) == list(range(256))
            p.pop()
    print('PASS fourteen nonempty original-caller writer interfaces:49/82×all7 '
          'positions, independent byte/BCD-address; ALL12 source + lower9 reserve. '
          'The normalizer replaces the reserve upper3 from input A9/A10/A11; '
          'Still missing native joint fields/real Ms-byte provenance, physical '
          'page and safe exit. No Ms copy, partialK2 or exchange is claimed.', flush=True)


if __name__ == '__main__':
    r['inlet']['immutable_reference']()
    original_be_source_cut()
    original_call_reserves()
    independent_writer_interfaces()
    r['inlet']['immutable_reference']()
