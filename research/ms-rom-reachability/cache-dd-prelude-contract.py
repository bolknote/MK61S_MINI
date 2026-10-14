#!/usr/bin/env python3
"""DD rotation/source audit: local gadgets versus the C9/no-EE frontier.

The reference and ROM are read-only. Arbitrary per-tick keys and future ring
inputs deliberately overapproximate hardware. A detached RIGHT1 loop is not
a keyboard recipe. In the complete cached controller, every C9→DD/S1=A
route without EE passes through D6; D6 forgets the prior direct A cache.
Earlier copies, numeric reloads, other readers and partial K2 remain open.
"""
from collections import Counter, deque
from pathlib import Path
import runpy

from z3 import And, If, Or, ZeroExt

root = Path(__file__).resolve().parent
w = runpy.run_path(str(root / 'cache-writer-contract.py'))
q = w['q']
State, ex, base, keys = (q[n] for n in
                        ('State', 'execute_command', 'base_solver', 'arbitrary_keys'))
ip, prove, A = (w[n] for n in ('address', 'prove', 'A'))
eq = lambda xs, ys: And(*[x == y for x, y in zip(xs, ys)])


def rotation_words():
    # A syntax inventory is only a hint. The five positive identities below
    # are separately proved for arbitrary keys and every other chip field.
    quiet = {1: [], -1: []}
    for code in range(256):
        a = State(f'dd_rotation_scan_{code:02X}')
        b = ex(a, code)
        for shift in (1, -1):
            if all(q['simplify'](b.r[3*j]).eq(a.r[3*((j+shift) % 12)])
                   for j in range(12)):
                quiet[shift].append(code)
    assert quiet == {1: [0x26, 0x30, 0x60, 0xD7, 0xDD], -1: []}
    print('HINT only: quiet structural A12 LEFT1 words26/30/60/D7/DD; '
          'no syntactically unconditional RIGHT1 word. Conditional/compound '
          'rotations are NOT excluded by this scan.', flush=True)
    for code in quiet[1]:
        a = State(f'dd_rotation_word_{code:02X}')
        p = base(a, code)
        out = []
        b = ex(a, code, *keys(f'dd_rotation_keys_{code:02X}'),
               emitted_outputs=out)
        prove(p, And(eq(A(b), A(a)[1:] + A(a)[:1]), eq(out, a.m)),
              f'{code:02X} universally rotates ALL12 A LEFT1; no outgoing write')


def counted_rotation():
    for start, count in ((5, 11), (11, 5)):
        a = State(f'dd_rotation_30_start{start}')
        p = base(a, 0x30)
        p.add(a.s1 == start)
        b = a
        for j in range(count):
            prove(p, ip(b) == 0x30, f'30/{start} loop step{j}', False)
            out = []
            before = b
            b = ex(b, 0x30, *keys(f'dd_rotation_30_keys{start}_{j}'),
                   emitted_outputs=out)
            prove(p, eq(out, before.m), '30 loop no outgoing write', False)
        shifted = A(a)[count:] + A(a)[:count]
        prove(p, And(ip(b) == 0x31, b.s1 == 0, eq(A(b), shifted),
                     b.r[26] == a.r[26], b.r[35] == a.r[35]),
              f'CONDITIONAL 30/S1={start:X}: exactly{count} LEFT1 steps, '
              'then31, ALL12 raw A retained; control R26/type held')
    a = State('dd_rotation_D2_source')
    p = base(a, 0xD2)
    out = []
    b = ex(a, 0xD2, *keys('dd_rotation_D2_keys'), emitted_outputs=out)
    prove(p, And(ip(b) == 0x30, b.s1 == 11, b.r[3] == 15,
                 b.r[0] == a.s1 + q['N4'](1), eq(out, a.m)),
          'Actual external30 inlet D2 sets counterB, replaces A1 byF '
          'and A0 by oldS1+1; not a raw-cache-preserving RIGHT1 constructor')
    for code in (0x28, 0x6D):
        a = State(f'dd_rotation_selector_{code:02X}')
        p = base(a, code)
        b = ex(a, code, *keys(f'dd_rotation_selector_keys_{code:02X}'))
        prove(p, b.s1 == 14, f'{code:02X} sets selectorE, not the30 counter5')


def dd_inlet_selectors():
    a = State('dd_rotation_DD_gate')
    p = base(a, 0xDD)
    b = ex(a, 0xDD, *keys('dd_rotation_DD_gate_keys'))
    prove(p, And(b.s1 == a.s1,
                 ip(b) == (q['BitVecVal'](0xD0, 8) | ZeroExt(4, a.s1))),
          'DD dispatch is exactly D0|oldS1, and holdsS1 for arbitrary keys/ring')
    p.add(a.s1 == 13)
    prove(p, ip(b) == 0xDD,
          'DD/S1=D is an invariant self-loop; eleven rotations cannot exit toDA')
    for code in (0xDE, 0xD4, 0xD6, 0xCB):
        a = State(f'dd_rotation_inlet_{code:02X}')
        p = base(a, code)
        out = []
        b = ex(a, code, *keys(f'dd_rotation_inlet_keys_{code:02X}'),
               emitted_outputs=out)
        claim = {
            0xDE: Or(ip(b) != 0xDD, b.s1 == 13),
            0xD4: b.s1 == a.s1,
            0xD6: And(b.s1 == a.r[35], eq(A(b), a.m[0:36:3]), eq(out, a.m)),
            0xCB: b.s1 == a.s1,
        }[code]
        prove(p, claim, f'{code:02X} exact DD inlet selector' +
              ('; D6 loads ALL12 A from M1 and creates no outgoing copy'
               if code == 0xD6 else ''))


def cut(blocked):
    g = runpy.run_path(str(root / 'cache-numeric-export-gates.py'))
    states, edges = g['states'], g['edges']
    reached = {j for j, s in enumerate(states) if s[0] == 0xC9}
    assert len(reached) == 146
    todo = deque(sorted(reached))
    while todo:
        j = todo.popleft()
        if states[j][0] in blocked:
            continue
        for k in edges[j]:
            if k not in reached:
                reached.add(k)
                todo.append(k)
    pairs = [(j, k) for j in reached if states[j][0] not in blocked
             for k in edges[j] if states[k][0] == 0xDD]
    return states, edges, reached, pairs


def reader_source_barrier():
    states, edges, reached, pairs = cut({0xEE})
    assert len(reached) == 10695
    assert Counter(states[j][0] for j, k in pairs) == {
        0xDE: 186, 0xDD: 92, 0xD4: 27, 0xD6: 22, 0xCB: 1}
    dd = {k for j, k in pairs}
    assert len(dd) == 125
    admitted_a = {k for k in dd if 10 in states[k][3]}
    assert len(admitted_a) == 17
    for k in admitted_a:
        parents = [j for j, target in pairs if target == k]
        assert len(parents) == 1 and states[parents[0]][0] == 0xD6
    assert all(states[j][3] == [4] for j, k in pairs if states[j][0] == 0xD4)
    assert all(states[j][3] == [6] for j, k in pairs if states[j][0] == 0xCB)
    assert sum(1 for j in reached if states[j][0] == 0xDD
               for k in edges[j] if states[k][0] == 0xDA) == 17
    print('PASS complete C9/noEE graph: all17 DD contexts admittingS1=A '
          'are created ONLY by D6. They are not spurious reachability merely '
          'because D6 starts withS1=6: exact D6 replacesS1 by oldR35.', flush=True)
    # All other inlets are handled by the exact local identities above.
    # The graph does not propagate the source payload or physical ring.
    states, edges, reached, pairs = cut({0xEE, 0xD6})
    assert len(reached) == 7903
    assert Counter(states[k][3][0] for k in {k for j, k in pairs}) == {
        13: 30, 4: 20, 6: 1}
    assert all(len(states[k][3]) == 1 for j, k in pairs)
    assert not any(states[j][0] == 0xDD and states[k][0] == 0xDA
                   for j in reached for k in edges[j])
    assert not any(states[j][0] == 0x26 for j in reached)
    loop = [j for j in reached if states[j][0] == 0x30]
    assert len(loop) == 50
    assert Counter(states[j][3][0] for j in loop) == {v: 10 for v in range(11, 16)}
    assert all(states[j][0] in (0xD2, 0x30)
               for j in reached if states[j][0] not in (0xEE, 0xD6)
               for k in edges[j] if states[k][0] == 0x30)
    print('PASS complete C9/noEE/noD6 cut:7903 contexts; DD selectors '
          'are ONLY4/6/D, no DD→DA; no26, and30 counters onlyB..F, '
          'never the required5. Blocked commands are boundary nodes, '
          'not executed in this cut.', flush=True)
    print('SCOPE: a direct reader→rotate→DD_A bridge beforeEE/D6 is closed. '
          'This does NOT exclude prior reserves, a D6 reload of previously '
          'saved codes, other CA inlets or partialK2.', flush=True)


def d6_direct_cache_loss():
    a = State('dd_rotation_D6_oldA')
    other = a.copy()
    replacement = State('dd_rotation_D6_otherA')
    for k in range(0, 36, 3):
        other.r[k] = replacement.r[k]
    p = base(a, 0xD6)
    serial = State('dd_rotation_D6_common_serial').m
    signals = keys('dd_rotation_D6_common_keys')
    results, outputs = [], []
    for entry in (a, other):
        out = []
        results.append(ex(entry, 0xD6, *signals, serial_inputs=serial,
                          emitted_outputs=out))
        outputs.append(out)
    left, right = results
    prove(p, And(*[eq(getattr(left, n), getattr(right, n))
                   for n in ('r', 'st', 'm')],
                 *[getattr(left, n) == getattr(right, n)
                   for n in ('s', 's1', 'l', 't', 'carry')],
                 eq(outputs[0], outputs[1]), eq(outputs[0], a.m)),
          'D6 forgets ALL12 previousA tetras in ALL primary fields/output; '
          'no new outgoing copy. Earlier copies outsideA are NOT excluded')


if __name__ == '__main__':
    rotation_words()
    counted_rotation()
    dd_inlet_selectors()
    reader_source_barrier()
    d6_direct_cache_loss()
    print('PASS DD prelude/source audit. No native writer, Ms transfer '
          'or partialK2 is claimed.', flush=True)
