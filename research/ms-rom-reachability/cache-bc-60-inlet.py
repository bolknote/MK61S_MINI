#!/usr/bin/env python3
"""Exact60 dispatch, reset predecessor cut, and conditional high-type BC.

60→48 requires selectorC, not4: the selector high bit is inverted. Native
low type3 arrives here only with R23zero and cannot take the direct54 route.
A high-type77 route avoids54 conditionally and rotatesA12 first. Its writer
overwrites the ST0 upper reserve but keeps it in ST1 upper3: ALL12 survive
split across two buffers, including the first cached low tetra in ST1[34].
No conditional source path or arbitrary-state SAT is a keyboard witness.
"""
from collections import Counter
from pathlib import Path
import runpy

from z3 import And, If, Implies, Or, UGE, ULE, sat

root = Path(__file__).resolve().parent
x = runpy.run_path(str(root / 'cache-bc-writer-contract.py'))
r, w, q = (x[n] for n in ('r', 'w', 'q'))
states, edges = (x['entry'][n] for n in ('states', 'edges'))
walk, double = x['walk'], x['double']
A, B, ST0, ST1 = (x[n] for n in ('A', 'B', 'ST0', 'ST1'))
N8 = lambda n: q['BitVecVal'](n, 8)


def selector_inventory():
    assignments = {
        0x1F: lambda a: a.r[35]+8,
        0x59: lambda a: q['N4'](11),
        **{code: lambda a: q['N4'](8) for code in (0x5C, 0x5F, 0x6C, 0x7C, 0xB3, 0xCD)},
        0x85: lambda a: a.r[35], 0xDD: lambda a: a.r[0]+1,
        0xDE: lambda a: q['N4'](15), 0xE6: lambda a: a.s+1,
    }
    assert len(assignments) == 12
    for code in range(256):
        label = f'bc60_selector_inventory_{code:02X}'
        a = q['State'](label); p = w['base'](a, code)
        b = w['ex'](a, code, *q['arbitrary_keys'](label+'_keys'))
        expected = assignments[code](a) if code in assignments else a.r[38]
        w['prove'](p, b.r[38] == expected, f'exact selector assignment{code:02X}', False)
    print('PASS ALL256 selector assignments:12 setters, every other word holdsR38. '
          'C can be supplied locally by1F[R35=4],85[R35=C],DD[A0=B],E6[S=B]; '
          'these are source formulas, not four reachable keyboard recipes.', flush=True)


def exact_gates():
    a = q['State']('bc60_exact_dispatch'); p = w['base'](a, 0x60); out = []
    b = w['ex'](a, 0x60, *q['arbitrary_keys']('bc60_exact_dispatch_keys'), emitted_outputs=out)
    w['prove'](p, And(
        w['ip'](b) == If(a.r[25] == a.r[31],
            (q['ZeroExt'](4, a.r[38]^8) << 4) | N8(8), N8(0x61)),
        ((w['ip'](b) == 0x48) == And(a.r[38] == 12, a.r[25] == a.r[31])),
        b.s1 == a.r[25]-a.r[31],
        w['eq'](A(b), [*A(a)[1:], A(a)[0]]),
        w['eq'](b.r[1:42:3], a.r[1:42:3]), w['eq'](b.st, a.st),
        *[b.r[j] == a.r[j] for j in (2, 5, 23, 26, 29, 32, 35, 38)],
        w['eq'](out, a.m)),
        '60 exact inverted-selector/equality gate; rotates ALL12 A once, B14/ST/control held')
    a = q['State']('bc60_exact_6D'); p = w['base'](a, 0x6D); out = []
    b = w['ex'](a, 0x6D, *q['arbitrary_keys']('bc60_exact_6D_keys'), emitted_outputs=out)
    w['prove'](p, And(w['ip'](b) == If(a.r[26] == 0, N8(0x6F), N8(0x60)),
        w['stack'](b)[0] == 0x6E, b.s1 == 14, w['eq'](A(b), A(a)),
        w['eq'](B(b), B(a)), w['eq'](out, a.m)),
        'original6D selects60 only with nonzeroR26 and pushes6E; no payload writer')


def low_type_reset_cut():
    predecessors = {
        0xC9: {0xCD: 492},
        0x06: {0x55: 209, 0x38: 48, 0x3A: 178, 0xC9: 85},
        0x07: {0x06: 273},
        0x6D: {0x07: 273, 0x77: 165},
        0x60: {0x6D: 227, 0x6C: 19},
    }
    graph = r['inlet']['g']['graph']
    assert len(states) == 52416 and sum(map(len, edges)) == 95731
    assert graph['metadata']['complete'] and graph['metadata']['pending'] == 0
    assert graph['metadata']['terminal'] is None
    assert graph['metadata']['fusedCommands'] == {'93': ['93', '94'], '12': ['12', 'C6']}
    assert all(states[i][0] == 0 for i in graph['indexes']['roots'])
    for target, parents in predecessors.items():
        assert Counter(states[i][0] for i, row in enumerate(edges)
            for child in row if states[child][0] == target) == parents

    def invariant(a, code):
        if code == 0xC9: return a.r[38] == 8
        if code in (0x06, 0x07): return Or(a.r[32] == 0, a.r[38] == 8)
        if code in (0x6D, 0x60): return Or(a.r[32] == 0, a.r[38] == 8, a.r[23] == 0)
        return And()

    for first, second in ((0x93, 0x94), (0x12, 0xC6)):
        a = q['State'](f'bc60_fused_{first:02X}'); p = w['base'](a, first)
        b = w['ex'](a, first, *q['arbitrary_keys'](f'bc60_fused_keys_{first:02X}'))
        w['prove'](p, w['ip'](b) == second, 'fused internal boundary outside60 region', False)
    sources = sorted({code for row in predecessors.values() for code in row})
    assert sources == [0x06, 0x07, 0x38, 0x3A, 0x55, 0x6C, 0x6D, 0x77, 0xC9, 0xCD]
    for code in sources:
        label = f'bc60_reset_induction_{code:02X}'
        a = q['State'](label); p = w['base'](a, code); p.add(invariant(a, code))
        b = w['ex'](a, code, *q['arbitrary_keys'](label+'_keys'))
        targets = [target for target, parents in predecessors.items() if code in parents]
        w['prove'](p, And(*[Implies(w['ip'](b) == target, invariant(b, target))
            for target in targets]), f'ALL reset{code:02X} outgoing60-region invariants')
    a = q['State']('bc60_reset_type3'); p = w['base'](a, 0x60)
    p.add(invariant(a, 0x60), a.r[32] == 3)
    b = w['ex'](a, 0x60, *q['arbitrary_keys']('bc60_reset_type3_keys'))
    w['prove'](p, Implies(w['ip'](b) == 0x48, b.r[23] == 0),
        'ALL reset60→48/type3 arrive with R23zero; impossible direct4A/4B/4D→54/type3')
    print('PASS GLOBAL RESET CUT: at60, type0 OR selector8 OR R23zero. '
          '60→48/type3 necessarily has R23zero. This closes this DIRECT low-type '
          'bridge for unlimited future key timing/serial data. High-type77/B1 '
          'and later paths through other decoder entries are NOT excluded.', flush=True)


def high_type_writer_families():
    for offset in range(7):
        label = f'bc60_high_writer_{offset}_C'; address = 84+offset
        a = q['State'](label); p = w['base'](a, 0x77)
        p.add(UGE(a.r[32], 4), a.r[29] == 12, a.r[38] == 12,
            a.r[26] != 0, a.r[25] == a.r[31],
            a.st[1] == 5, a.st[22] == 1, a.st[25] == 0,
            a.st[30] == address % 10, a.st[33] == address // 10)
        prefix = (0x77, 0x6D, 0x60, 0x48, 0xB1, 0xB3, 0xBC, 0x49, 0xBD,
                  *double, 0xBE, 0x63, *([0x64]*13), 0x66)
        b = walk(a, p, prefix, label, only_ring_writer=0xBC)
        p.add(b.m[22] == 15)
        b = walk(b, p, (1, *([2]*13), 3, 4, 0xBA, 0xCC, 0xCD), label+'_wait')
        w['prove'](p, And(w['ip'](b) == 0xC9, w['stack'](b)[0] == 0x67,
            b.r[2] == 5, b.r[23] == 1, b.r[26] == 0,
            b.r[31] == address % 10, b.r[34] == address // 10,
            w['eq'](A(b), B(a)), w['eq'](ST0(b), [*A(a)[1:10], *B(a)[9:12]]),
            w['eq'](ST1(b)[9:12], [*A(a)[10:12], A(a)[0]]),
            w['eq']([b.st[j] for j in (34, 0, 6, 9, 15, 18)], [a.r[j] for j in w['raw']])),
            f'CONDITIONAL high-type77/60/C/offset{offset}: original BC writer, '
            'no54 and no pre48 nonzeroR23 needed; ALL12 rotated reserve is split ST0/ST1')
        p.push(); byte = q['BitVec'](label+'_byte', 8)
        p.add(w['byte'](b.r[30], b.r[33]) == byte)
        assert p.check() == sat and q['possible_values'](byte, p, 257) == list(range(256))
        p.pop()
    print('PASS seven CONDITIONAL original77/6D/60/48/B1/B3/BC/49/91 writer '
          'interfaces, all256 bytes/all7 positions. No native high-type/selectorC '
          'joint constructor, opaque Ms byte, physical page/exit or exchange.', flush=True)


def rotated_cache_reserve():
    label = 'bc60_rotated_A0_reserve_C'
    a = q['State'](label); other = a.copy()
    other.r[0] = q['BitVec'](label+'_other_A0', 4)
    p = w['base'](a, 0x77)
    p.add(UGE(a.r[32], 4), a.r[29] == 12, a.r[38] == 12,
        a.r[26] != 0, a.r[25] == a.r[31],
        a.st[1] == 5, a.st[22] == 1, a.st[25] == 0,
        a.st[30] == 9, a.st[33] == 8)
    left, right = a, other
    sequence = (0x77, 0x6D, 0x60, 0x48, 0xB1, 0xB3, 0xBC, 0x49, 0xBD,
                *double, 0xBE, 0x63, *([0x64]*13), 0x66)
    for i, code in enumerate(sequence):
        w['prove'](p, And(w['ip'](left) == code, w['ip'](right) == code),
            f'paired original60 cache-reserve boundary{i}', False)
        pins = q['arbitrary_keys'](label+f'_keys{i}')
        serial = q['State'](label+f'_serial{i}').m
        out_left, out_right = [], []
        left = w['ex'](left, code, *pins, serial_inputs=serial, emitted_outputs=out_left)
        right = w['ex'](right, code, *pins, serial_inputs=serial, emitted_outputs=out_right)
        w['prove'](p, w['eq'](out_left, out_right),
            f'oldA0 is not exported at original word{code:02X}', False)
    w['prove'](p, And(w['eq'](ST0(left)[:9], A(a)[1:10]),
        w['eq'](ST1(left)[9:12], [*A(a)[10:12], A(a)[0]])),
        'CONDITIONAL high-type60 writer keeps ALL12 oldA, split rotated ST0lower9/ST1upper3')
    w['prove'](p, And(w['eq'](left.r, right.r),
        *[left.st[j] == right.st[j] for j in range(42) if j != 34],
        left.st[34] == a.r[0], right.st[34] == other.r[0],
        w['eq'](left.m, right.m), *[getattr(left, n) == getattr(right, n)
            for n in ('s', 's1', 'l', 't', 'carry')]),
        'CONDITIONAL high-type60 writer holds independent oldA0 ONLY in ST1[34]; '
        'not in BC output or anywhere else in final PRIMARY state')
    p.push(); p.add(a.r[0] != other.r[0]); assert p.check() == sat; p.pop()
    print('PASS original60 moves cached A0 to A11, then writer reserves it in '
          'ST1[34] before replacing ST0 upper3. All THREE opaque cached codes '
          'survive across ST0[0/6/9/15/18]+ST1[34]. No BC export of those codes '
          'or native transport from this split reserve is claimed.', flush=True)


if __name__ == '__main__':
    r['inlet']['immutable_reference']()
    selector_inventory()
    exact_gates()
    low_type_reset_cut()
    high_type_writer_families()
    rotated_cache_reserve()
    r['inlet']['immutable_reference']()
    print('PASS original60 source audit. Conditional high-type writer is NOT a '
          'native Ms supplier, safe exchange or partialK2.', flush=True)
