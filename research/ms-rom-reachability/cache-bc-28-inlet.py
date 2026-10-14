#!/usr/bin/env python3
"""Joint ORIGINAL28 inlet audit, not a native keyboard recipe.

The complete reset graph supplies caller coverage, NOT positive witnesses.
All nonzero28 parents and their unbounded resolver feedback are included.
The node-sensitive induction distinguishes the two odd kinds9/B from the
kind7 feedback which can grow higher even types. Positive component paths
must still obtain every entry field jointly in the unmodified calculator.
"""
from collections import Counter, defaultdict, deque
from pathlib import Path
import runpy

from z3 import And, BitVec, Extract, If, Implies, Or, UGE, ULE, sat

root = Path(__file__).resolve().parent
previous = runpy.run_path(str(root / 'cache-bc-68-inlet.py'))
r, w, q = (previous[n] for n in ('r', 'w', 'q'))
states, edges = previous['states'], previous['edges']
walk = previous['walk']
double = previous['source']['double']
even = lambda a: Extract(0, 0, a.r[32]) == 0
wanted = lambda a: Or(a.r[35] == 9, a.r[35] == 11)


def source_cut():
    graph = r['inlet']['g']['graph']
    assert len(states) == 52416 and sum(map(len, edges)) == 95731
    assert graph['metadata']['complete'] and graph['metadata']['pending'] == 0
    assert graph['metadata']['terminal'] is None
    assert graph['metadata']['fusedCommands'] == {'93': ['93', '94'], '12': ['12', 'C6']}
    assert all(states[i][0] == 0 for i in graph['indexes']['roots'])
    pred = defaultdict(set)
    for i, row in enumerate(edges):
        for j in row: pred[j].add(i)
    targets = {i for i, a in enumerate(states) if a[0] == 0x28
        and (a[7] is None or any(n != 0 for n in a[7]))}
    assert len(targets) == 53
    region, todo = set(targets), deque(targets)
    while todo:
        i = todo.popleft()
        if states[i][0] in (7, 0x1F, 0x1C): continue
        for j in pred[i]:
            if j not in region: region.add(j); todo.append(j)
    counts = Counter(states[i][0] for i in region)
    assert len(region) == 1213 and counts == {
        1: 41, 2: 41, 3: 41, 4: 41, 7: 26, 0x18: 67, 0x1A: 22,
        0x1B: 67, 0x1C: 88, 0x1D: 67, 0x1F: 22, 0x20: 19,
        0x21: 19, 0x22: 11, 0x23: 22, 0x24: 25, 0x25: 58,
        0x26: 27, 0x28: 53, 0x2C: 25, 0x2D: 22, 0x2E: 28,
        0x2F: 29, 0x36: 11, 0x60: 43, 0x6D: 47, 0x77: 47,
        0x7E: 47, 0xBA: 41, 0xCB: 41, 0xD4: 24, 0xD6: 10, 0xDD: 41}
    assert not region & set(graph['indexes']['roots'])
    external = Counter((states[i][0], states[j][0])
        for i, row in enumerate(edges) if i not in region for j in row if j in region)
    assert external == {(6, 7): 26, (0xA5, 0x1F): 30,
                        (0x19, 0x1C): 44, (0x1E, 0x1C): 22}
    internal = Counter((states[i][0], states[j][0])
        for i in region for j in edges[i] if j in region)
    expected = {
        (1, 1): 41, (1, 2): 41, (2, 2): 41, (2, 3): 41,
        (3, 4): 41, (4, 0xBA): 41, (7, 0x6D): 26,
        (0x18, 0x1B): 67, (0x1A, 0x18): 22, (0x1B, 0x1D): 67,
        (0x1C, 0x2D): 88,
        **{(0x1D, dst): 4 for dst in (0x20, 0x21, 0x23, 0x24, 0x25, 0x26, 0x28, 0x2F)},
        (0x1D, 0x2C): 48, (0x1D, 0x2E): 5,
        **{(0x1F, dst): 22 for dst in (0x18, 0x1A, 0x1B, 0x1C, 0x1D)},
        (0x20, 0x2F): 19, (0x21, 0x22): 11, (0x21, 0x23): 19,
        (0x22, 0x36): 11, (0x23, 0x24): 22, (0x23, 0x25): 22,
        (0x24, 0x25): 25, (0x25, 1): 58, (0x26, 0x28): 27,
        (0x28, 0x7E): 49, (0x2C, 0x2E): 25, (0x2D, 0x2C): 22,
        (0x2E, 1): 28, (0x2F, 0x20): 29, (0x2F, 0x21): 29,
        (0x36, 0x25): 8, (0x36, 0x28): 3, (0x60, 0x18): 25,
        (0x60, 0x28): 37, (0x6D, 0x60): 47, (0x77, 0x6D): 47,
        (0x7E, 0x77): 47, (0x7E, 0x7E): 47, (0xBA, 0xCB): 41,
        (0xCB, 0xDD): 41, (0xD4, 0x26): 24, (0xD6, 0x2F): 10,
        (0xDD, 0xD4): 30, (0xDD, 0xD6): 11}
    assert internal == expected and sum(internal.values()) == 1525
    assert all(states[i][7] == [15] for i in region if states[i][0] in (0x1F, 0x1A))
    assert Counter(states[i][0] for i in region for j in edges[i]
                   if j in region and states[j][0] == 0x77) == {0x7E: 47}
    all_parents = Counter(states[i][0] for i, row in enumerate(edges)
        for j in row if states[j][0] == 0x28)
    assert all_parents == {0x60: 37, 0x1D: 4, 0x26: 38, 0x36: 3}
    print('PASS COMPLETE28 cut: ALL53 nonzero28 classes;1213 classes/1525 '
          'internal edges. Only06/07, A5/1F,19/1C,1E/1C external entries; '
          'ALL four28 parent families included, no positive native witness.', flush=True)
    return counts, internal


def exact_gates():
    for code in (7, 0x18, 0x1A, 0x1B, 0x1F, 0x1C, 0x2C, 0x28, 0x7E, 0x79):
        label = f'bc28_exact_{code:02X}'
        a = q['State'](label); p = w['base'](a, code); out = []
        b = w['ex'](a, code, *q['arbitrary_keys'](label+'_keys'), emitted_outputs=out)
        held = (2, 5, 23, 26, 29, 32, 35, 38)
        if code == 7:
            claim = And(w['ip'](b) == If(UGE(a.r[2], 5), q['BitVecVal'](0x6D, 8),
                                        q['BitVecVal'](9, 8)), b.s1 == 0,
                        w['stack'](b)[0] == 8)
        elif code in (0x18, 0x1A, 0x1B):
            held = (2, 5, 23, 26, 35, 38)
            claim = And(b.r[32] == a.r[32]+1, b.r[29] == a.r[29]+a.s1,
                b.s1 == 0, w['ip'](b) == {0x18: 0x1B, 0x1A: 0x18, 0x1B: 0x1D}[code])
        elif code == 0x1F:
            held = (2, 5, 23, 26, 29, 35)
            claim = And(b.r[32] == 0, b.r[38] == a.r[35]+8, b.s1 == a.s1)
        elif code == 0x1C:
            held = (2, 5, 23, 26, 29, 35, 38)
            claim = b.r[32] == 2
        elif code == 0x2C:
            held = (2, 5, 23, 26, 29, 38)
            claim = And(b.r[32] == a.r[35], b.r[35] == a.r[32], w['ip'](b) == 0x2E)
        elif code == 0x28:
            claim = And(b.s1 == 14, w['ip'](b) == If(a.r[26] == 0,
                q['BitVecVal'](0x2A, 8), q['BitVecVal'](0x7E, 8)),
                w['stack'](b)[0] == 0x29)
        elif code == 0x7E:
            claim = And(w['ip'](b) == (q['BitVecVal'](0x70, 8) | q['ZeroExt'](4, a.r[35])),
                        b.s1 == a.s1)
        else:
            claim = And(w['ip'](b) == 0x45, b.s1 == 6, w['stack'](b)[0] == 0x7A)
        w['prove'](p, And(claim, *[b.r[j] == a.r[j] for j in held], w['eq'](out, a.m)),
                   f'original{code:02X} exact joint control contract; no ring write')
    for code, head in ((0x6D, 0x6E), (0x45, 0x46), (0x8B, 0x8C),
                       (0x48, 0x49), (0x4A, 0x4B), (0xBD, 0xBE), (0x66, 0x67)):
        label = f'bc28_return_constructor{code:02X}'
        a = q['State'](label); p = w['base'](a, code)
        b = w['ex'](a, code, *q['arbitrary_keys'](label+'_keys'))
        w['prove'](p, w['stack'](b)[0] == head,
                   f'original{code:02X} constructs return tag{head:02X}, not a free head')


def invariant(a, code):
    typ, num, mode = a.r[32], a.r[29], a.r[2]
    f = a.r[26] == 15
    regular = And(typ == 2, UGE(mode, 5), Or(num == 0, num == 3))
    if code in (0x1F, 0x1C): return And()
    if code == 7: return Or(a.r[38] == 8, And(typ == 0, num == 0))
    if code in (0x6D, 0x60):
        return And(Or(even(a), a.r[38] == 8), Implies(wanted(a),
            Or(a.r[38] == 8, And(typ == 0, num == 0, UGE(mode, 5)))))
    if code == 0x77: return And(even(a), a.r[35] == 7)
    if code == 0x1A: return typ == 0
    if code == 0x18:
        return And(Or(even(a), And(f, typ == 1)), Implies(wanted(a),
            Or(And(f, Or(typ == 0, typ == 1)),
               And(typ == 0, num == 0, UGE(mode, 5), a.s1 == 0))))
    if code == 0x1B:
        return And(Or(Extract(0, 0, typ) == 1, And(f, Or(typ == 0, typ == 2))),
            Implies(wanted(a), Or(And(f, Or(typ == 0, typ == 1, typ == 2)),
                And(typ == 1, num == 0, UGE(mode, 5), a.s1 == 0))))
    if code == 0x1D:
        return And(Or(even(a), And(f, Or(typ == 1, typ == 3))),
            Implies(wanted(a), Or(And(f, Or(typ == 0, typ == 1, typ == 2, typ == 3)),
                And(typ == 2, num == 0, UGE(mode, 5)))))
    if code == 0x2D: return typ == 2
    if code == 0x2C:
        return And(Or(even(a), typ == 1, typ == 3),
                   Implies(wanted(a), Or(typ == 0, typ == 1, typ == 2, typ == 3)))
    if code in (0x28, 0x7E):
        regular = And(UGE(mode, 5), Or(And(typ == 0, num == 0),
                                     And(typ == 2, Or(num == 0, num == 3))))
    if code == 1: regular = And(typ == 2, UGE(mode, 5))
    if code == 2: regular = And(typ == 2, UGE(mode, 5), ULE(num, typ))
    if code in (3, 4, 0xBA, 0xCB, 0xDD, 0xD4, 0xD6):
        regular = And(typ == 2, UGE(mode, 5), num == 3)
    return And(Implies(a.r[35] == 7, even(a)), Implies(wanted(a), regular))


def joint_induction():
    counts, internal = source_cut()
    # ALL actual07 external entries have the zero type/number alternative,
    # unless selector8.1F/1C are unrestricted OLD entries: their real words
    # reset the type. CounterF1F routes may import arbitrary OLD fields, but
    # reach2C, which swaps a low/even type into kind and loses kinds9/B.
    previous['low07_number_cut']()
    for code in sorted(counts):
        label = f'bc28_joint_{code:02X}'
        a = q['State'](label); p = w['base'](a, code); p.add(invariant(a, code))
        if code in (0x1F, 0x1A): p.add(a.r[26] == 15)
        b = w['ex'](a, code, *q['arbitrary_keys'](label+'_keys'))
        targets = sorted({dst for first, dst in internal if first == code})
        w['prove'](p, And(*[Implies(w['ip'](b) == dst, invariant(b, dst)) for dst in targets]),
                   f'ALL original{code:02X} preserves COMPLETE1213 joint invariant')
    print('PASS GLOBAL nonzero28/kinds9/B: mode5..F; ONLY(type0,number0) '
          'or(type2,number0/3). Unlimited marker/resolver loops do not create a '
          'free high type/operand/mode0 inlet. No native joint flag/Ms source claimed.', flush=True)


def direct_and_second_decoder_gates():
    """Separate the CLOSED direct BC-C path from the surviving54 path."""
    for kind in (9, 11):
        label = f'bc28_native_shape_kind{kind:X}'
        a = q['State'](label); p = w['base'](a, 0x28)
        p.add(a.r[26] != 0, a.r[35] == kind, invariant(a, 0x28))
        prefix = (0x28, 0x7E, 0x79, 0x45, 0x8B) if kind == 9 else (
                  0x28, 0x7E, 0x7B, 0xB7, 0x45, 0x8B)
        b = walk(a, p, prefix, label+'_first48')
        w['prove'](p, And(w['ip'](b) == 0x48,
            b.r[32] == a.r[32]+(1 if kind == 9 else 3),
            b.r[29] == a.r[29]-a.r[2]+(5 if kind == 9 else -3),
            b.r[23] == a.r[23], b.r[2] == a.r[5],
            w['eq'](b.r[0:36:3], a.r[0:36:3]),
            w['eq'](b.r[1:36:3], a.r[1:36:3]), w['eq'](b.st[:36], a.st[:36])),
            f'original28/kind{kind:X}: exact first48 type/number, numeric buffers/flag held')
        w['prove'](p, Implies(UGE(b.r[32], 4), b.r[29] != 12),
            f'ALL native-shaped28/kind{kind:X}: NO direct B1/B3/BC-C')
        needed = (And(a.r[32] == 2, a.r[29] == 0, a.r[2] == 15) if kind == 9 else
                  And(a.r[32] == 0, a.r[29] == 0, a.r[2] == 7))
        w['prove'](p, ((b.r[32] == 3) & (b.r[29] == 6)) == needed,
            f'ALL native-shaped28/kind{kind:X}: exact SECOND54/type3/6 control candidate')
    # The first48, not the old numericST1, supplies the gate flag.
    for flag, suffix, destination in (
        (0, (0x4A, 0x4C), 0x4E),
        (1, (0x4A, 0x4B, 0x4C), 0x4E),
        (2, (0x4A, 0x4B, 0x4D), 0x5E),
        (None, (0x4A, 0x4B, 0x4D), 0x54)):
        label = 'bc28_second54_flag_'+str(flag)
        a = q['State'](label); p = w['base'](a, 0x48)
        p.add(a.r[32] == 3, a.r[29] == 6)
        p.add(UGE(a.r[23], 3) if flag is None else a.r[23] == flag)
        b = walk(a, p, (0x48, *suffix), label)
        w['prove'](p, And(w['ip'](b) == destination, b.r[29] == 6,
            b.r[32] == (a.r[35] if flag == 1 else 3)),
            f'original first48/type3/6/flag{flag}: exact gate exit{destination:02X}')
    print('PASS DIRECT28/79 or7B→BC-C CLOSED. The distinct TWO-decoder '
          'candidate is NOT closed:9 needs(type2,number0,modeF); B needs '
          '(type0,number0,mode7); BOTH need actual incomingR23>=3. '
          'These are necessary component fields, not native producers.', flush=True)


def conditional_two_decoder_writers(*, entry_factory=None, byte_values=None,
                                    label_prefix='bc28_two_decoder'):
    """Original07 callers construct both49 returns, no fabricated head.

    ALL initial fields below are explicitly CONDITIONAL. In particular the
    joint kind/selector/counter/flag and numericST1 packet is not established
    by public keys. Arbitrary-byte coverage does not prove physicalMs origin,
    destination safety, displaced-word recovery or the full exchange.
    """
    if byte_values is None: byte_values = list(range(256))
    for kind, mode, pointer in ((9, 15, 9), (11, 7, 10)):
        for address in (*range(84, 91), 99):
            label = f'{label_prefix}_kind{kind:X}_address{address}_C'
            if entry_factory is None:
                a = q['State'](label); p = w['base'](a, 7)
            else:
                a, p = entry_factory(kind, mode, pointer, address, label)
            p.add(a.r[32] == 0, a.r[29] == 0, a.r[2] == mode,
                a.r[35] == kind, a.r[38] == pointer, a.r[25] == a.r[31],
                UGE(a.r[23], 3), a.r[26] == 11 if kind == 9 else a.r[26] != 0,
                a.st[1] == 5, a.st[22] == 1, a.st[25] == 0,
                a.st[30] == address % 10, a.st[33] == address // 10)
            prefix = (7, 0x6D, 0x60, 0x18, 0x1B, 0x1D, 0x28, 0x7E, 0x79,
                      0x45, 0x8B) if kind == 9 else (
                      7, 0x6D, 0x60, 0x28, 0x7E, 0x7B, 0xB7, 0x45, 0x8B)
            b = walk(a, p, prefix, label+'_prefix')
            w['prove'](p, And(w['ip'](b) == 0x48, b.r[32] == 3,
                b.r[29] == 6, b.r[23] == a.r[23], b.r[2] == a.r[5],
                w['stack'](b)[0] == 0x8C,
                w['eq'](b.r[0:36:3], [*a.r[3:36:3], a.r[0]]),
                w['eq'](b.r[1:36:3], a.r[1:36:3]), w['eq'](b.st[:36], a.st[:36])),
                f'CONDITIONAL kind{kind:X}/address{address}: original07 caller→first48/type3/6')
            b = walk(b, p, (0x48,), label+'_first48_call')
            w['prove'](p, w['stack'](b)[0] == 0x49, 'first ORIGINAL48 creates49')
            b = walk(b, p, (0x4A, 0x4B, 0x4D), label+'_first48_gate')
            w['prove'](p, And(w['ip'](b) == 0x54, b.r[32] == 3,
                b.r[29] == 6, w['stack'](b)[0] == 0x4B),
                'ORIGINAL4A creates4B; real flag gate reaches54/type3/6')
            b = walk(b, p, (0x54, 0xB7, 0x45, 0x8B), label+'_second48')
            w['prove'](p, And(w['ip'](b) == 0x48, b.r[32] == 4,
                b.r[29] == 12, b.r[23] == 0, b.r[2] == a.r[5],
                w['stack'](b)[0] == 0x8C),
                'ORIGINAL54/B7/45/8B constructs second48/type4/numberC; no IP repair')
            b = walk(b, p, (0x48, 0xB1, 0xB3, 0xBC, 0x49, 0xBD, *double,
                0xBE, 0x63, *([0x64]*(address//7+1)), 0x66), label, only_ring_writer=0xBC)
            p.add(b.m[22] == 15)  # explicit PRIMARY marker assumption, not a native edit
            b = walk(b, p, (1, *([2]*(address//7+1)), 3, 4, 0xBA, 0xCC, 0xCD),
                     label+'_writer_wait')
            oldA = a.r[0:36:3]; oldB = a.r[1:36:3]
            w['prove'](p, And(w['ip'](b) == 0xC9, w['stack'](b)[0] == 0x67,
                b.r[2] == 5, b.r[23] == 1, b.r[26] == 0,
                b.r[29] == 0, b.r[38] == 8, b.s1 == 9,
                b.r[31] == address % 10, b.r[34] == address // 10,
                b.r[35] == address % 7, b.r[32] == address//7,
                w['eq'](b.r[0:36:3], oldB),
                w['eq'](b.st[0:36:3], [*oldA[1:10], *oldB[9:12]]),
                w['eq'](b.st[28:36:3], [*oldA[10:12], oldA[0]])),
                f'CONDITIONAL original07/kind{kind:X}/address{address}: C9/67 writer; '
                'ALL rotatedA12 split ST0lower9/ST1upper3, inputB12 intact')
            p.push(); byte = BitVec(label+'_input_byte', 8)
            p.add(w['byte'](b.r[30], b.r[33]) == byte)
            assert p.check() == sat
            assert q['possible_values'](byte, p, 257) == byte_values
            p.pop()
            complete_page_patch(a, b, p, address, label)
    print('PASS16 CONDITIONAL TWO-decoder writer contracts: two07-shaped '
          f'kinds × eight addresses84..90/99, each ALL{len(byte_values)} input bytes and '
          'a complete ORIGINAL F9/two-C9 M3-page patch. '
          '07/6D constructs6E, BOTH8B construct8C, BOTH48 construct49, '
          'BD constructsBE,66 constructs67. '
          'NO fabricated return/ROM edit. Native joint entry/Ms source/physical '
          'safety/exit/inverse remain UNPROVED; not a partialK2 witness.', flush=True)


def complete_page_patch(initial, entry, p, address, label):
    """Compose the ORIGINAL C9/67 island with the actual constructed entry.

    M3 here is the primary chip's serial lane, NOT an identified physical
    programme page. Matching the two physical-ring visits remains unproved.
    The two exact swaps and one F9 patch cannot recover the earlierBC word.
    """
    offset = address % 7
    page = list(entry.m[2:42:3]); assert len(page) == 14
    patch = [initial.r[31], initial.r[34]]  # original B10/B11, not invented data
    byte_index = (2*offset+12) % 14
    expected = list(page); expected[byte_index:byte_index+2] = patch
    output = []
    b = w['ex'](entry, 0xC9, *q['arbitrary_keys'](label+'_first_C9_keys'),
        serial_inputs=q['State'](label+'_first_C9_serial').m, emitted_outputs=output)
    w['prove'](p, And(w['ip'](b) == 0x67,
        w['eq'](b.r[1:42:3], page), w['eq'](output[2:42:3], entry.r[1:42:3]),
        *[output[j] == entry.m[j] for j in range(42) if j % 3 != 2]),
        'constructed FIRST C9: exact M3/B14 swap; M1/M2 held')
    first = (0x6A, 0x6B, 0x6C, 0x69)*(offset+1)
    special = (0xFB, 0xFD, 0xF9, 0xFC, 0x68)
    rest = (0x69, 0x6A, 0x6B, 0x6C, 0x68)*(6-offset)
    b = walk(b, p, (0x67, *first, *special, *rest, 5), label+'_byte_patch')
    w['prove'](p, And(w['ip'](b) == 1, w['stack'](b)[0] == 6, b.s1 == 9,
        w['eq'](b.r[1:42:3], expected), b.r[32] == address//7,
        b.r[35] == offset, b.r[26] == 0),
        'constructed ORIGINAL F9 replaces EXACTLY one of seven opaque bytes; '
        '05 itself constructs06')
    p.add(b.m[22] == 15)  # a second explicit PRIMARY marker assumption
    b = walk(b, p, (1, *([2]*(address//7+1)), 3, 4, 0xBA, 0xCC, 0xCD),
             label+'_second_C9_wait')
    w['prove'](p, And(w['ip'](b) == 0xC9, w['stack'](b)[0] == 6,
        w['eq'](b.r[1:42:3], expected)),
        'ORIGINAL05/marker/count/BA/CC/CD requires SECOND C9/head06, not free BC')
    second = b; output = []
    b = w['ex'](second, 0xC9, *q['arbitrary_keys'](label+'_second_C9_keys'),
        serial_inputs=q['State'](label+'_second_C9_serial').m, emitted_outputs=output)
    oldA = initial.r[0:36:3]; oldB = initial.r[1:36:3]
    w['prove'](p, And(w['ip'](b) == 6, w['eq'](output[2:42:3], expected),
        *[output[j] == second.m[j] for j in range(42) if j % 3 != 2],
        w['eq'](b.st[0:36:3], [*oldA[1:10], *oldB[9:12]]),
        w['eq'](b.st[28:36:3], [*oldA[10:12], oldA[0]])),
        f'CONDITIONAL address{address}: SECOND C9 exports patched14-tetra page, '
        'other SIX original bytes/M1/M2/ALL splitA12 held')
    p.push()
    p.add(page[byte_index] != patch[0], page[byte_index+1] != patch[1])
    assert p.check() == sat  # nonempty genuinely changed byte, not a self-copy
    p.pop()


if __name__ == '__main__':
    r['inlet']['immutable_reference']()
    exact_gates()
    joint_induction()
    direct_and_second_decoder_gates()
    conditional_two_decoder_writers()
    r['inlet']['immutable_reference']()
    print('PASS original28 source and conditional component audit. No native '
          'keyboard capture, live hardware experiment, ROM/state repair or '
          'general partialK2 impossibility claim.', flush=True)
