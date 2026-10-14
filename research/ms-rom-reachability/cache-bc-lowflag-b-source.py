#!/usr/bin/env python3
"""Complete low-flag28 caller audit and an earlier ORIGINAL07 constructor.

60, direct1D and36 cannot supply the new type2/number3/kindB/mode5
packet. The only remaining selected26 source is25/counter/DD/D4.
All coverage is from the COMPLETE reset overapproximation, not witnesses.
Eight positive PRIMARY compositions start at a CONDITIONAL07 packet,
construct28 and reach the original F9/twoC9 island. No native key/live
experiment, state/IP/return/ROM repair or physical memory claim.
"""
from collections import Counter
from pathlib import Path
import runpy

from z3 import And, Implies, Or, ULE, sat

root = Path(__file__).resolve().parent
component = runpy.run_path(str(root / 'cache-bc-lowflag-b-inlet.py'))
source = component['source']
r, w, q, loops, highkind, basis, states, edges, pred, execute, walk = (source[n] for n in
    ('r', 'w', 'q', 'loops', 'highkind', 'basis', 'states', 'edges', 'pred', 'execute', 'walk'))
A, B, eq, checked = source['A'], source['B'], source['eq'], source['checked_dependency']
guard = lambda a: And(a.r[32] == 2, a.r[35] == 11, a.r[2] == 5, a.r[26] != 0)
core = lambda a: And(guard(a), a.r[29] == 3)


def complete_parent_partition():
    targets = {i for i, a in enumerate(states) if a[0] == 0x28
               and (a[7] is None or any(v != 0 for v in a[7]))}
    assert len(targets) == 53
    incoming = Counter(states[j][0] for i in targets for j in pred[i])
    assert incoming == {0x60: 37, 0x1D: 4, 0x26: 27, 0x36: 3}
    selected = {j for i in targets for j in pred[i] if states[j][0] == 0x36}
    region = basis['backward'](selected, {0x1D})
    counts = Counter(states[i][0] for i in region)
    pairs = basis['internal_pairs'](region)
    assert len(region) == 22 and sum(pairs.values()) == 25
    assert counts == {0x1D: 4, 0x2F: 6, 0x20: 3, 0x21: 3, 0x22: 3, 0x36: 3}
    assert basis['external_pairs'](region) == {(0x1B, 0x1D): 4}
    assert not region & set(r['inlet']['g']['graph']['indexes']['roots'])

    selected26 = {j for i in targets for j in pred[i] if states[j][0] == 0x26}
    last25 = basis['backward'](selected26, {0x25, 0x1D})
    counter_counts = Counter(states[i][0] for i in last25)
    counter_pairs = basis['internal_pairs'](last25)
    assert len(last25) == 323 and sum(counter_pairs.values()) == 358
    assert counter_counts == {0x25: 58, 1: 30, 2: 30, 3: 30, 4: 30,
        0xBA: 30, 0xCB: 30, 0xDD: 30, 0xD4: 24, 0x26: 27, 0x1D: 4}
    assert basis['external_pairs'](last25) == {(0x23, 0x25): 22, (0x24, 0x25): 25,
        (0x36, 0x25): 8, (0x1D, 0x25): 2, (0x1B, 0x1D): 4}
    assert all(states[i][3] == [4] for i in last25 if states[i][0] in (1, 2, 3, 4))
    assert Counter(states[j][0] for i in selected26 for j in pred[i]) == {0x1D: 4, 0xD4: 24}
    print('PASS COMPLETE ALL53 nonzero28 parents:60/1D/26/36; '
          'selected36 has22 classes/25 edges, selected26 has323/358 '
          'last25 classes/edges. ALL24 selectedD4 return contexts covered; '
          'no arbitrary return26 or positive graph witness.', flush=True)
    return counts, pairs, counter_counts, counter_pairs


def excluded_direct_sources(counts, pairs):
    for code, destinations in ((0x60, (0x28,)), (0x1D, (0x28, 0x26))):
        label = f'lowflag_B_exclude_parent_{code:02X}'
        a = q['State'](label); p = w['base'](a, code)
        p.add(loops['inlet']['invariant'](a, code))
        b = execute(a, p, code, label)
        w['prove'](p, And(*[Implies(w['ip'](b) == dst, ~core(b)) for dst in destinations]),
            f'ALL selected ORIGINAL{code:02X} cannot supply new28 core packet')
    def inv(a, code):
        if code == 0x1D: return loops['inlet']['invariant'](a, code)
        return Implies(a.r[35] == 11, a.r[29] == 0)
    for code in sorted(counts):
        label = f'lowflag_B_selected36_{code:02X}'
        a = q['State'](label); p = w['base'](a, code); p.add(inv(a, code))
        b = execute(a, p, code, label)
        destinations = sorted({dst for first, dst in pairs if first == code})
        w['prove'](p, And(*[Implies(w['ip'](b) == dst, inv(b, dst)) for dst in destinations]),
            f'ALL ORIGINAL{code:02X} preserves selected22/25 kindB/numberzero source')
    a = q['State']('lowflag_B_selected36_exit'); p = w['base'](a, 0x36)
    p.add(inv(a, 0x36)); b = execute(a, p, 0x36, 'lowflag_B_selected36_exit')
    w['prove'](p, Implies(w['ip'](b) == 0x28, ~core(b)),
        'ALL selected36->28 keeps kindB operand0, NEVER required3')
    print('PASS GLOBAL new lowflag28 core cannot come from60, direct1D '
          'or36, nor from1D->26. The ONLY remaining selected26 supplier '
          'is originalD4 after last25, not four interchangeable free entries.', flush=True)


def last25_constructs_three(counts, pairs):
    def inv(a, code):
        if code in (0x25, 0x1D): return And()
        if code == 1: return Implies(guard(a), a.s1 == 4)
        if code == 2: return Implies(guard(a), And(a.s1 == 4, ULE(a.r[29], 2)))
        if code == 0x26: return Implies(guard(a), Or(a.r[29] == 0, a.r[29] == 3))
        return Implies(guard(a), a.r[29] == 3)
    for code in sorted(counts):
        label = f'lowflag_B_last25_{code:02X}'
        a = q['State'](label); p = w['base'](a, code)
        p.add(inv(a, code))
        if code == 0x1D: p.add(loops['inlet']['invariant'](a, code))
        if code in (1, 2, 3, 4): p.add(a.s1 == 4)
        b = execute(a, p, code, label)
        destinations = sorted({dst for first, dst in pairs if first == code})
        w['prove'](p, And(*[Implies(w['ip'](b) == dst, inv(b, dst)) for dst in destinations]),
            f'ALL ORIGINAL{code:02X} preserves complete323/358 lowflag type2 counter source')
    print('PASS COMPLETE last25 source:01 initializes0 on every wait; '
          'TYPE2 counter exits02 with3. All real25/marker/CB/DD/D4 '
          'feedback retains mode/type/kind/counter. Thus number3 is '
          'constructed by ROM, but boundary25 fields are not yet native witnesses.', flush=True)


def next07_source_frontier():
    metadata = r['inlet']['g']['graph']['metadata']
    assert metadata['stateFields'][5:8] == ['r38Set', 'r38MinusR35', 'r26Set']
    selected = {i for i, a in enumerate(states) if a[0] == 7
        and (a[5] is None or 9 in a[5]) and (a[7] is None or 8 in a[7])}
    assert len(selected) == 6
    # At selector9/kindB the difference is E, not8. This uses the
    # frozen relational field's documented meaning, not the mistaken
    # interpretation of it as a numeric mode.
    compatible = {i for i in selected if states[i][6] is None or states[i][6] == 14}
    assert compatible == {16331, 21371, 21417, 24089}
    sixes = {j for i in compatible for j in pred[i]}
    assert len(sixes) == 4 and {states[i][0] for i in sixes} == {6}
    three_a = {j for i in sixes for j in pred[i]}
    assert len(three_a) == 8 and {states[i][0] for i in three_a} == {0x3A}
    sixtyone = {j for i in three_a for j in pred[i]}
    assert len(sixtyone) == 8 and {states[i][0] for i in sixtyone} == {0x61}
    print('PASS COMPLETE new07 selector9/counter8/kindB frontier: '
          'six control candidates, two rejected by r38-kind=8, four '
          'remaining. ALL four have ONLY06 parents, those06 ONLY3A, '
          'those3A ONLY61. This is exhaustive source coverage, NOT '
          'native data/flag/ST1 compatibility or a positive key witness.', flush=True)


def original3a_payload_limit():
    a = q['State']('lowflag_B_actual3A_payload'); p = w['base'](a, 0x3A)
    b = walk(a, p, (0x3A, 6), 'lowflag_B_actual3A_payload')
    w['prove'](p, And(w['ip'](b) == 7,
        eq(A(b), [*A(a)[1:10], *([q['N4'](15)]*3)])),
        'ALL ORIGINAL last3A/06 source A12 is [oldA1..A9,F,F,F], '
        'NOT a freely chosen original reader cache')

    other = q['State']('lowflag_B_3A_discard_other'); c = a.copy()
    # Upper A10/A11 can affect arithmetic carry and are NOT declared
    # erased from the whole chip merely because A9..A11 becomeF.
    # The payload tetra A0, however, has a stronger exact loss theorem.
    c.r[0] = other.r[0]
    b = a
    for index, code in enumerate((0x3A, 6)):
        pins = q['arbitrary_keys'](f'lowflag_B_3A_discard_keys{index}')
        serial = q['State'](f'lowflag_B_3A_discard_serial{index}').m
        ob, oc = [], []
        b = w['ex'](b, code, *pins, serial_inputs=serial, emitted_outputs=ob)
        c = w['ex'](c, code, *pins, serial_inputs=serial, emitted_outputs=oc)
        w['prove'](p, eq(ob, oc), 'last3A/06 emits no discarded originalA difference', False)
    w['prove'](p, w['same'](b, c),
        'WHOLE-primary pair: arbitrary incoming A0 differences vanish '
        'after ORIGINAL3A/06; earlier independent backups are NOT excluded')
    p.push(); p.add(a.r[0] != other.r[0])
    assert p.check() == sat; p.pop()
    print('LIMIT: earlier07/25 writer preserves its incomingA12, not '
          'the larger pre3A original. At least A0 needs an independent '
          'source (earlier backup or later refetch); all legitimate new07 '
          'sources have upper3 F. '
          'PartialK2 generally and future early backups remain open.', flush=True)


def seed07_packet(a, address):
    return And(a.r[32] == 0, a.r[29] == 0, a.r[35] == 11, a.r[2] == 5,
        a.r[26] == 8, a.r[38] == 9, a.r[25] == a.r[31], ULE(a.r[23], 2),
        a.st[1] == 5, a.st[22] == 1, a.st[25] == 0,
        a.st[30] == address % 10, a.st[33] == address // 10)


def original07_constructor(a, p, address, label):
    sequence = (7, 0x6D, 0x60, 0x18, 0x1B, 0x1D, 0x25,
        1, 2, 2, 2, 3, 4, 0xBA, 0xCB, 0xDD, 0xD4, 0x26)
    b = a
    for index, code in enumerate(sequence):
        if code == 1: p.add(b.m[22] == 15)
        w['prove'](p, w['ip'](b) == code, label+f' actual ORIGINAL{code:02X}', False)
        before = b; output = []
        b = w['ex'](b, code, *q['arbitrary_keys'](label+f'_keys{index}'),
            serial_inputs=q['State'](label+f'_serial{index}').m, emitted_outputs=output)
        if code == 0xD4:
            w['prove'](p, And(eq(output[0:36:3], [*A(a)[1:], A(a)[0]]),
                *[output[j] == before.m[j] for j in range(42) if j % 3 != 0 or j >= 36]),
                label+' originalD4 writes ALL rotated1 A tetras to numericalM1; '
                'physical slot/displaced-word backup UNPROVED')
        else:
            w['prove'](p, eq(output, before.m), label+f' no ring write{code:02X}', False)
    w['prove'](p, And(w['ip'](b) == 0x28, component['inlet_packet'](b, address),
        eq(A(b), [*A(a)[3:], *A(a)[:3]]), eq(B(b), B(a)),
        eq(b.st[:36], a.st[:36]), b.r[23] == a.r[23], b.r[26] == 8),
        label+' original07/counter8 constructs WHOLE new28 packet: '
        'TYPE0->2, operand0->3, mode5/kindB held; A rotates3, B12/ST held')
    return b


def composed07_writer(address):
    initial = {}
    def factory(address, label):
        a = q['State'](label+'_earlier07'); p = w['base'](a, 7)
        p.add(seed07_packet(a, address)); assert p.check() == sat
        initial['a'], initial['p'] = a, p
        b = original07_constructor(a, p, address, label+'_constructor')
        return b, p
    b = component['conditional_writer'](address, entry_factory=factory)
    a, p = initial['a'], initial['p']
    w['prove'](p, And(w['ip'](b) == 6,
        eq(b.st[0:27:3], A(a)[3:12]), eq(b.st[28:36:3], A(a)[:3])),
        f'CONDITIONAL earlier07/address{address}: secondC9 retains ALL12 '
        'PRE-constructor A tetras, rotated3 across ST0lower9/ST1upper3')


if __name__ == '__main__':
    r['inlet']['immutable_reference']()
    checked('complete1213/1525 native28 type/number/mode boundary', loops['inlet']['joint_induction'])
    counts, pairs, counter_counts, counter_pairs = complete_parent_partition()
    excluded_direct_sources(counts, pairs)
    last25_constructs_three(counter_counts, counter_pairs)
    next07_source_frontier()
    original3a_payload_limit()
    for address in (*range(84, 91), 99): composed07_writer(address)
    r['inlet']['immutable_reference']()
    print('PASS complete new28 source audit and eight earlier07-to-F9/'
          'twoC9 CONDITIONAL contracts. Still UNPROVED: native joint '
          '07/counter8/selector9/B8=B10/ST1 producer, PRE3A discarded '
          'payload backup, Ms byte origin, '
          'safe physical M1/M2/M3 visits, both displaced-word backups, '
          'exit/inverse. No actual partialK2 or general impossibility claim.', flush=True)
