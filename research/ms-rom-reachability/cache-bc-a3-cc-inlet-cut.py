#!/usr/bin/env python3
"""Original E4 packet provenance and the constantCC/head-DD bootstrap cut.

The frozen COMPLETE reset cover supplies all callers, not positive native
witnesses. A class-level induction separates the first head-93 E4 family
from the later head-DD family. All original words use arbitrary per-tick
keys and fresh serial input. Data-changing words are executed, not replaced
with neutral edges. Neither a graph path nor a SAT packet is loaded into
an emulator. No native/live experiment, ROM/state/IP/return repair.
"""
from collections import deque
from pathlib import Path
import runpy

from z3 import And, BoolVal, If, Implies, Or, UGE, ULE, sat, unsat

root = Path(__file__).resolve().parent
old = runpy.run_path(str(root / 'cache-bc-a3-cc-contract.py'))
r, w, q, basis, states, edges, pred = (old[n] for n in
    ('r', 'w', 'q', 'basis', 'states', 'edges', 'pred'))
A, B, eq = old['A'], old['B'], old['eq']
C = lambda a: a.r[2:36:3]


def match(a, index):
    """All nine frozen control fields, not an IP-only destination test."""
    code, tags, vec, selectors, delta, selectors38, delta38, counters, types = states[index]
    assert types is None
    assertions = [w['ip'](a) == code, eq(w['stack'](a),
        [q['BitVecVal'](n, 8) for n in tags])]
    if vec == 'diagonal': assertions.append(a.r[37] == a.r[40])
    elif vec is not None: assertions.append(w['byte'](a.r[37], a.r[40]) == vec)
    for values, expr in ((selectors, a.s1), (selectors38, a.r[38]), (counters, a.r[26])):
        assert values is not None and values
        if len(values) != 16: assertions.append(Or(*[expr == n for n in values]))
    if delta is not None: assertions.append(a.s1-a.r[35] == delta)
    if delta38 is not None: assertions.append(a.r[38]-a.r[35] == delta38)
    return And(*assertions)


def original(a, code, label, output=None):
    b = w['ex'](a, code, *q['arbitrary_keys'](label+'_keys'),
        serial_inputs=q['State'](label+'_serial').m, emitted_outputs=output)
    # Neither fusion is in the selected bootstrap cut. Keep this helper
    # faithful if it is used for a larger coverage audit in the future.
    if code in (0x93, 0x12):
        second = 0x94 if code == 0x93 else 0xC6
        b = w['ex'](b, second, *q['arbitrary_keys'](label+'_second_keys'),
            serial_inputs=q['State'](label+'_second_serial').m)
    return b


def coverage():
    graph = r['inlet']['g']['graph']
    assert len(states) == 52416 and sum(map(len, edges)) == 95731
    assert graph['metadata']['complete'] and graph['metadata']['pending'] == 0
    assert graph['metadata']['terminal'] is None
    assert graph['metadata']['fusedCommands'] == {'93': ['93', '94'], '12': ['12', 'C6']}
    region = basis['backward']({11376, 17324}, {0xE3})
    assert len(region) == 228 and sum(basis['internal_pairs'](region).values()) == 316
    assert basis['external_pairs'](region) == {(0xEE, 0xE3): 38}
    gateways = [(i, j) for i, row in enumerate(edges) if i not in region
                for j in row if j in region]
    assert len(gateways) == 38
    assert all(states[j][1][0] == 0xAD and states[j][2] == 0xD3
        and states[j][3] == [13] for i, j in gateways)
    assert not region & set(graph['indexes']['roots'])
    print('PASS COMPLETE both constantCC sources: 228 classes/316 edges; '
          'all38 exterior gateways are EE->E3 with headAD/vectorD3/S1D. '
          'The head-DD route is not an independent reset inlet.', flush=True)


restore = (0xE3, 0x91, 0x92, 0x93, 0x94, 0x95, 0x98, 0x9A,
           0x93, 0x94, 0x95, 0x98, 0x9A)


def restore_origin():
    a = q['State']('cc_inlet_restore'); p = w['base'](a, 0xE3); b = a
    # Expand every real word here (including each original94), so the
    # automatic93 and E4 return tags are proved instead of assigned.
    for index, code in enumerate(restore):
        w['prove'](p, w['ip'](b) == code, 'restore actual'+f'{code:02X}', False)
        before, output = b, []
        b = w['ex'](b, code, *q['arbitrary_keys'](f'cc_inlet_restore_keys{index}'),
            serial_inputs=q['State'](f'cc_inlet_restore_serial{index}').m,
            emitted_outputs=output)
        w['prove'](p, eq(output, before.m), 'restore no outgoing ring write', False)
    w['prove'](p, And(w['ip'](b) == 0xE4, eq(A(b), A(a)),
        eq(B(b), a.st[0:36:3]), eq(C(b), a.st[1:36:3]),
        eq(b.st[0:36:3], B(a)), eq(b.st[1:36:3], C(a)),
        eq(b.st[2:36:3], a.st[1:36:3]), b.s1 == a.s1,
        b.r[37] == a.r[35], b.r[40] == a.r[35],
        w['stack'](b)[0] == w['stack'](a)[0],
        w['stack'](b)[1] == 0x93, w['stack'](b)[2] == 0xE4),
        'GLOBAL E3/double restore: A held; B=oldST0, C=oldST1, '
        'oldC saved inST1; true head/93/E4; diagonal vector from OLD C11')
    print('PASS at E3 entry late counter/TYPE/KIND are oldST25/ST31/ST34, '
          'not currentC26/C32/C35 or a user opcode. These are raw saved '
          'working-state fields; no public number-digit mapping or native '
          'setter is asserted.', flush=True)


def ac_origin():
    a = q['State']('cc_inlet_ac_origin'); p = w['base'](a, 0xAC); b = a
    for index, code in enumerate((0xAC, 0xE2, 0xE5, 0xE6, 0xED, 0xEE)):
        if code == 0xE5: p.add(b.m[22] == 15)
        w['prove'](p, w['ip'](b) == code, 'AC original inlet'+f'{code:02X}', False)
        b = original(b, code, 'cc_inlet_ac_'+str(index))
    w['prove'](p, And(w['ip'](b) == 0xE3, b.s1 == 13,
        w['stack'](b)[0] == 0xAD,
        b.st[25] == a.st[25], b.st[31] == a.st[32], b.st[34] == a.st[35]),
        'GLOBAL completed AC reader: E3 saved counter/TYPE/KIND '
        'come from AC oldST25/ST32/ST35, not AC current opcode')
    wait = q['State']('cc_inlet_ac_wait'); pw = w['base'](wait, 0xE5)
    after = original(wait, 0xE5, 'cc_inlet_ac_wait')
    w['prove'](pw, And(eq(wait.st, after.st), wait.s1 == after.s1,
        *[wait.r[j] == after.r[j] for j in range(42) if j not in (36, 39)]),
        'ALL finite E5 waits preserve this saved header; no fixed keyboard timing assumption')


def dispatch_dependencies():
    a = q['State']('cc_inlet_dc_gate'); p = w['base'](a, 0xDC)
    b = original(a, 0xDC, 'cc_inlet_dc_gate')
    w['prove'](p, w['ip'](b) == If(And(UGE(a.r[34], 1), ULE(a.r[34], 8)),
        q['BitVecVal'](0xDE, 8), q['BitVecVal'](0xEA, 8)),
        'GLOBAL DC enters DE exactly for B11=1..8; zero and9..F enter EA')
    a = q['State']('cc_inlet_de_prep'); p = w['base'](a, 0xDE)
    b = original(a, 0xDE, 'cc_inlet_de_prep')
    prep = lambda x: And(x.r[27] == x.r[28], x.r[30] == x.r[31], x.r[33] == 15)
    w['prove'](p, And(prep(b), b.r[34] == a.r[34]),
        'GLOBAL DE always stamps A9=B9, A10=B10, A11=F; holdsB11')
    for code in (0xDA, 0xDB, 0xDC):
        label = 'cc_inlet_original_DE_'+f'{code:02X}'
        x = q['State'](label); local = w['base'](x, 0xDE)
        y = original(x, 0xDE, label+'_DE')
        local.add(w['ip'](y) == code); assert local.check() == sat
        z = original(y, code, label+'_next')
        if code == 0xDA:
            claim = And(w['ip'](z) == 0xDC, Or(z.r[34] == 0, z.r[34] == 1))
        elif code == 0xDB:
            claim = And(w['ip'](z) == 0xDC, z.r[34] == 11)
        else: claim = And(w['ip'](z) == 0xEA, z.r[34] == 12)
        w['prove'](local, claim, f'ALL real DE->{code:02X}: '
            'DA gives only0/1, DB keepsB, directDC goesEA, not a free D4 initializer')


def bootstrap_region():
    stops = {i for i, a in enumerate(states)
             if a[0] == 0xE4 and a[1][:2] == [0xAD, 0x93]}
    region, todo = {17324}, deque([17324])
    while todo:
        i = todo.popleft()
        if i in stops: continue
        for j in pred[i]:
            if j not in region: region.add(j); todo.append(j)
    assert len(region) == 79 and sum(basis['internal_pairs'](region).values()) == 149
    assert region & stops == {6017, 9042, 9049, 15889}
    assert basis['external_pairs'](region) == {(0x9A, 0xE4): 2, (0xE6, 0xE4): 2}
    graph = r['inlet']['g']['graph']
    assert not region & set(graph['indexes']['roots'])
    assert all(i in region or j in stops for j in region for i in pred[j])
    assert {j for j in region if any(i not in region for i in pred[j])} == region & stops
    return region, stops


def bootstrap_cut():
    region, stops = bootstrap_region()
    excluded = {11387, 11390, 14572, 14577, 17324}
    assert excluded <= region
    def invariant(a, index):
        code, tags = states[index][:2]
        if index in stops: return BoolVal(True)  # ALL first head93 E4 data are allowed.
        if code == 0xDE:
            if tags == [0xE5, 0xAD, 0x93]: return BoolVal(True)
            if tags == [0xDD, 0xE5, 0xAD]:
                # First DC can continue only after real DE/DA gives1.
                # All later DC/headDD sources below are explicit bottom.
                return a.r[34] == 1
            assert tags == [0xE5, 0xAD, 0xDD]
            return BoolVal(False)
        if code in (0xDA, 0xDB):
            if tags == [0xE5, 0xAD, 0x93]:
                return And(a.r[27] == a.r[28], a.r[30] == a.r[31],
                           a.r[33] == 15, a.r[34] == (10 if code == 0xDA else 11))
            assert tags == [0xE5, 0xAD, 0xDD]
            return BoolVal(False)
        if code == 0xDC:
            if tags == [0xE5, 0xAD, 0x93]:
                return Or(*[a.r[34] == n for n in (0, 1, 11, 12)])
            assert tags == [0xE5, 0xAD, 0xDD]
            return BoolVal(False)
        assert code in (0xE4, 0xD4, 0xD6, 0xE5, 0xE6, 0xDD, 0xED,
            0xEE, 0xAD, 0xA2, 0xA3, 0xCC, 0xBB, 0xBC), (index, code, tags)
        return BoolVal(False)

    checked, empty = 0, []
    for index in sorted(region):
        code = states[index][0]; label = f'cc_inlet_class_{index}'
        a = q['State'](label); p = w['base'](a, code)
        p.add(match(a, index), invariant(a, index))
        result = p.check(); assert result in (sat, unsat)
        destinations = [j for j in edges[index] if j in region]
        checked += len(destinations)
        if result == unsat:
            # Explicit bottom classes of a dataflow induction, NOT a
            # satisfiable constructor proof with silently empty premises.
            empty.append(index)
            continue
        b = original(a, code, label)
        w['prove'](p, And(*[Implies(match(b, j), invariant(b, j)) for j in destinations]),
            f'ALL original{code:02X} class{index} bootstrap induction', False)
    assert checked == 149
    assert excluded <= set(empty)
    print('PASS GLOBAL headDD constantCC bootstrap exclusion: all79 classes/'
          '149 internal edges, four arbitrary head93 E4 boundary classes, '
          f'{len(empty)} explicit bottom classes. TargetA3 class17324 is bottom. '
          'ALL later headDD E4/E5/E6 and targetA3 are bottom, for ANY '
          'TYPE/KIND. This excludes the ENTIRE selected two-D4 inverse '
          'writer source, not just TYPE2 or one shortest path.', flush=True)
    return region, empty


def head93_gateway_writer(typ, waits):
    """CONDITIONAL earlier EE packet, with every later return constructed."""
    assert (typ == 3 and waits == 0) or (typ == 2 and waits >= 1)
    label = f'cc_inlet_head93_type{typ}_wait{waits}'
    a = q['State'](label); p = w['base'](a, 0xEE)
    p.add(a.s1 == 13, w['byte'](a.r[37], a.r[40]) == 0xD3,
        w['stack'](a)[0] == 0xE3, w['stack'](a)[1] == 0xAD,
        a.st[25] == 0, a.st[31] == typ, a.st[34] == 13,
        a.m[34] == 6)
    source_word = a.m[1:36:3]; second_read = None; b = a
    sequence = (0xEE, *restore, 0xE4, 0xDE, 0xD6, 0xE5,
                0xE6, 0xED, 0xEE, 0xAD, 0xAD)
    for index, code in enumerate(sequence):
        if code == 0xE5: p.add(b.m[22] == 15)
        if code == 0xEE and index:
            second_read = b.m[1:36:3]
        before = b
        b, output = old['step'](b, p, code, label+f'_prefix{index}')
        w['prove'](p, eq(output, before.m), 'earlier EE/head93 prefix no outgoing write', False)
    assert second_read is not None
    for index in range(waits):
        p.add(b.m[22] == 15 if index == waits-1 else b.m[22] != 15)
        before = b
        b, output = old['step'](b, p, 0xA2, label+f'_wait{index}')
        w['prove'](p, eq(output, before.m), 'head93 A2 no outgoing write', False)
    w['prove'](p, And(w['ip'](b) == 0xA3, old['vector'](b),
        b.r[26] == 0, b.r[32] == typ, b.r[35] == 13, b.s1 == 9,
        b.r[34] == 6, eq(B(b), source_word), eq(A(b)[:10], second_read[:10]),
        eq(w['stack'](b), [q['BitVecVal'](n, 8) for n in (0x93, 0xE5, 0xAD)])),
        'CONDITIONAL complete earlier EE/E3 constructs head93 A3/CC, '
        'source first-readM2 and cache lower10 of second-readM2')
    for index, code in enumerate((0xA3, 0xCC, 0xBB, 0xBC)):
        before = b
        b, output = old['step'](b, p, code, label+f'_writer{index}')
        if code == 0xA3:
            w['prove'](p, And(eq(output[28:35:3], A(before)[9:]),
                *[output[j] == before.m[j] for j in range(42) if j not in (28, 31, 34)]),
                'head93 original A3 preliminary upper3 numericM2 write', False)
        elif code == 0xBC:
            w['prove'](p, And(eq(output[1:42:3],
                [*source_word, q['N4'](3), q['N4'](10)]),
                *[output[j] == before.m[j] for j in range(42) if j % 3 != 1],
                w['ip'](b) == 0x93, w['byte'](b.r[31], b.r[34]) == 0x36),
                'CONDITIONAL actual first head93 BC writes firstEE word+3/A, '
                'fixed36 and true93; NO imported DD/DA inverse')
        else: w['prove'](p, eq(output, before.m), 'head93 writer other words ring-neutral', False)
    for index, code in enumerate((0x93, 0x94, 0x95, 0x98, 0x9A, 0xE5, 0xE6, 0xEA)):
        if code == 0xE5: p.add(b.m[22] == 15)
        before = b
        b, output = old['step'](b, p, code, label+f'_exit{index}')
        w['prove'](p, eq(output, before.m), 'head93 true exit no extra ring write yet', False)
    w['prove'](p, w['ip'](b) == 0xD8,
        'CONDITIONAL first head93/TYPE2-or-3/KINDD true exit is D8, NOT DD or a finished idle')
    print(f'PASS CONDITIONAL head93 TYPE{typ}/wait{waits}: full original '
          'EE/E3 restoration and both reads composed through BC and true D8. '
          'SavedST25zero/ST31type/ST34D and firstM34six remain inlet '
          'hypotheses. No native key producer, physical slot match, old-word '
          'inverse, other-chip preservation or safe full D8 exit proved.', flush=True)


if __name__ == '__main__':
    r['inlet']['immutable_reference']()
    coverage()
    restore_origin()
    ac_origin()
    dispatch_dependencies()
    bootstrap_cut()
    head93_gateway_writer(3, 0)
    head93_gateway_writer(2, 9)
    r['inlet']['immutable_reference']()
    print('PASS exact E4 inlet provenance and COMPLETE headDD source cut. '
          'First head93 constantCC and diagonal/B3 writers, later adapters, '
          'all partialK2 possibilities and native saved-header producers '
          'are NOT globally excluded. No native recipe or Ms exchange.', flush=True)
