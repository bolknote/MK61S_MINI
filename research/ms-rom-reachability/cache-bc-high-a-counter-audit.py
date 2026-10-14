#!/usr/bin/env python3
"""Exact TYPEA demand of the77/C and68/E BB families; pure8 loop limit.

Complete last25 source induction sharpens the C-selector odd-number
theorem to number=type+1. The E-selector result is independently checked.
These are negative/source and CONDITIONAL PRIMARY contracts, not native
key recipes, actual Ms payloads or physical programme writes.

An ORIGINAL counter8/selector9 loop grows type but rotates A by3. Four
continuations force the four control tetras to8, thereafter preventing
the C/E selectors required for these BB writers. Other counters, outside
data updates and alternative callers remain outside that local limit.
"""
from collections import Counter
from pathlib import Path
import runpy

from z3 import And, Extract, Implies, Or, ULE, sat, unsat

root = Path(__file__).resolve().parent
mode = runpy.run_path(str(root / 'cache-bc-lowflag-b-mode-cut.py'))
prior = mode['previous']
source = prior['source']
r, w, q, basis, states, edges, pred, execute, walk = (prior[n] for n in
    ('r', 'w', 'q', 'basis', 'states', 'edges', 'pred', 'execute', 'walk'))
A, B, eq, checked = (prior[n] for n in ('A', 'B', 'eq', 'checked'))
inlet, parity = source['inlet'], source['parity']
even = lambda a: Extract(0, 0, a.r[32]) == 0
lock = lambda a: And(*[a.r[3*j] == 8 for j in (0, 3, 6, 9)])


def exact_c_counter_source():
    checked('complete reset low07/type0/number0 boundary outside selector8',
            inlet['low07_number_cut'])
    checked('complete1070/1340 nonzero25 kind7/even-type source',
            parity['all_nonzero_kind7_cut'])
    targets = {i for i, a in enumerate(states) if a[0] == 0x77
        and (a[5] is None or 12 in a[5]) and (a[7] is None or any(v != 0 for v in a[7]))}
    assert len(targets) == 24
    region = basis['backward'](targets, {0x25})
    counts = Counter(states[i][0] for i in region)
    pairs = basis['internal_pairs'](region)
    assert len(region) == 388 and counts == {0x25: 58, 1: 30, 2: 30, 3: 30, 4: 30,
        0xBA: 30, 0xCB: 30, 0xDD: 30, 0xD4: 24, 0x26: 24, 0x28: 24,
        0x7E: 24, 0x77: 24}
    assert basis['external_pairs'](region) == {(0x1D, 0x25): 4, (0x23, 0x25): 22,
        (0x24, 0x25): 25, (0x36, 0x25): 8}
    assert all(states[i][3] == [4] for i in region if states[i][0] in (1, 2, 3, 4))
    assert not region & set(r['inlet']['g']['graph']['indexes']['roots'])
    checked('same complete388 C-selector/odd-number coverage and real01/02 guards',
            parity['high77_operand_cut'])
    def inv(a, code):
        if code in (0x25, 1): return Implies(a.r[35] == 7, even(a))
        if code == 2: return Implies(a.r[35] == 7, And(even(a), ULE(a.r[29], a.r[32])))
        packet = And(even(a), a.r[29] == a.r[32]+1)
        return packet if code == 0x77 else Implies(a.r[35] == 7, packet)
    for code in sorted(counts):
        destinations = sorted({dst for first, dst in pairs if first == code})
        if not destinations: continue
        label = f'highA_C_exact_last25_{code:02X}'
        a = q['State'](label); p = w['base'](a, code); p.add(inv(a, code))
        if code in (1, 2, 3, 4): p.add(a.s1 == 4)
        b = execute(a, p, code, label)
        w['prove'](p, And(*[Implies(w['ip'](b) == dst, inv(b, dst)) for dst in destinations]),
            f'ORIGINAL{code:02X} preserves COMPLETE388 C-selector exact type+1 source')
    print('PASS GLOBAL eligible C-selector77: even TYPE and EXACT '
          'operand=TYPE+1, not merely odd operand. C/E selector families '
          'are independently justified; no positive graph witness.', flush=True)


def c_family_bb_type():
    a = q['State']('highA_C_family'); p = w['base'](a, 0x77)
    p.add(a.r[38] == 12, a.r[26] != 0, even(a), a.r[29] == a.r[32]+1,
          a.r[25] == a.r[31])
    b = walk(a, p, (0x77, 0x6D, 0x60), 'highA_C_family_48')
    w['prove'](p, And(w['ip'](b) == 0x48,
        b.r[32] == a.r[32], b.r[29] == a.r[32]+1,
        ((b.r[29] == 11) == (a.r[32] == 10)), b.r[29] != 10,
        eq(A(b), [*A(a)[1:], A(a)[0]]), eq(B(b), B(a))),
        'C-family77/60: original operandB iff inputTYPEA; operandA impossible')
    p.add(a.r[32] == 10)
    b = walk(b, p, (0x48, 0xB1, 0xB3), 'highA_C_family_dispatch')
    w['prove'](p, And(w['ip'](b) == 0xBB, w['stack'](b)[0] == 0x49),
        'CONDITIONAL C-family TYPEA/numberB constructs originalBB/head49')


def e_family_bb_type():
    checked('complete206/243 independent68 ready source and all four exits',
            source['native54']['sixtyfive']['complete68_source_induction'])
    a = q['State']('highA_E_family'); p = w['base'](a, 0x68)
    p.add(a.r[38] == 14, a.r[26] != 0, a.r[2] == 15, a.r[5] == 0,
          a.r[23] == 0, a.s1 == 0, a.r[29] == a.r[32]+1,
          Or(*[a.r[32] == v for v in (6, 8, 10, 12)]))
    b = walk(a, p, (0x68, 0x65, 0x7B, 0xB7, 0x45, 0x8B), 'highA_E_family_48')
    w['prove'](p, And(w['ip'](b) == 0x48,
        b.r[32] == a.r[32]+4, b.r[29] == a.r[32]+1,
        ((b.r[29] == 11) == (a.r[32] == 10)), b.r[29] != 10,
        eq(A(b), A(a)), eq(B(b), B(a))),
        'E-family68/65: TYPEA -> first48/TYPEE/numberB; operandA impossible')
    p.add(a.r[32] == 10)
    b = walk(b, p, (0x48, 0xB1, 0xB3), 'highA_E_family_dispatch')
    w['prove'](p, And(w['ip'](b) == 0xBB, w['stack'](b)[0] == 0x49),
        'CONDITIONAL E-family TYPEA/numberB constructs originalBB/head49')


def counter8_cache_lemmas():
    for code in (0x25, 1, 2, 3, 4, 0xBA, 0xCB):
        label = f'highA_clean8_cache_{code:02X}'
        a = q['State'](label); p = w['base'](a, code)
        p.add(a.r[26] == 8, a.r[35] == 7, even(a))
        if code != 0x25: p.add(a.s1 == 4)
        b = execute(a, p, code, label)
        w['prove'](p, And(eq(A(b), A(a)), eq(B(b), B(a)), eq(b.st[:36], a.st[:36]),
            *[b.r[j] == a.r[j] for j in (2, 26, 32, 35)]),
            f'ORIGINAL{code:02X} clean8 counter holds payload/control for ANY evenTYPE/oldMODE')
    print('PASS cache-neutral01/02 wait/counter lemmas for ANY finite '
          'wait and evenTYPE; only DD/26/60 rotateA in this clean loop. '
          'No scalar-type-only model is substituted for the payload.', flush=True)


def original_cycle(a, p, typ, label, *, complete=True):
    sequence = (0x1D, 0x25, 1, *([2]*(typ+1)), 3, 4, 0xBA, 0xCB,
                0xDD, 0xD4, 0x26, 0x28, 0x7E)
    b = a
    for index, code in enumerate(sequence):
        if code == 1: p.add(b.m[22] == 15)
        w['prove'](p, w['ip'](b) == code, label+f' actual ORIGINAL{code:02X}', False)
        before = b; out = []
        b = w['ex'](b, code, *q['arbitrary_keys'](label+f'_keys{index}'),
            serial_inputs=q['State'](label+f'_serial{index}').m, emitted_outputs=out)
        if code == 0xD4:
            w['prove'](p, And(eq(out[0:36:3], A(a)),
                *[out[j] == before.m[j] for j in range(42) if j % 3 != 0 or j >= 36]),
                label+' originalD4 writes numericalM1; no safe physical-slot claim', False)
        else: w['prove'](p, eq(out, before.m), label+' no other ring write', False)
    w['prove'](p, And(w['ip'](b) == 0x77, b.r[32] == typ, b.r[29] == typ+1,
        b.r[38] == a.r[0]+1, b.r[26] == 8, b.r[35] == 7,
        eq(A(b), [*A(a)[2:], *A(a)[:2]]), eq(B(b), B(a))),
        label+' actual counter/DD/26: type+1 number, selector=ENTRY A0+1, rotation2')
    if not complete: return b
    p.add(b.r[38] == 9); assert p.check() == sat
    b = walk(b, p, (0x77, 0x6D, 0x60, 0x18, 0x1B), label+'_selector9_return')
    w['prove'](p, And(w['ip'](b) == 0x1D, b.r[32] == (typ+2) % 16,
        b.r[26] == 8, b.r[35] == 7, b.r[2] == 15,
        eq(A(b), [*A(a)[3:], *A(a)[:3]]), eq(B(b), B(a))),
        label+' original selector9 continuation growsTYPE2 and rotatesA3')
    return b


def clean8_loop_cannot_finish_a():
    label = 'highA_clean8_four_rounds'
    a = q['State'](label); p = w['base'](a, 0x1D)
    p.add(a.r[32] == 2, a.r[35] == 7, a.r[26] == 8,
          a.r[25] == a.r[31])
    b = a
    for index, typ in enumerate((2, 4, 6, 8)):
        b = original_cycle(b, p, typ, label+f'_{index}')
    w['prove'](p, And(w['ip'](b) == 0x1D, b.r[32] == 10,
        eq(A(b), A(a)), lock(a), lock(b)),
        'FOUR original clean8/selector9 continuations reach TYPEA, '
        'but force A0/A3/A6/A9=8 and return A12 to its ORIGINAL orientation')
    b = original_cycle(b, p, 10, label+'_TYPEA_final', complete=False)
    w['prove'](p, And(b.r[38] == 9, b.r[38] != 12, b.r[38] != 14),
        'TYPEA fifth DD necessarily chooses selector9, NEVER C/E: '
        'growing TYPE alone does NOT produce either BB inlet')
    # A rotation by3 permutes the four locked control positions. Together
    # with the ANY-type counter cache lemmas this holds for ALL later
    # pure continuations, not just one chosen fifth-round data sample.
    a = q['State']('highA_clean8_rotation_lock'); p = w['base'](a, 0xDD)
    p.add(lock(a)); b = execute(a, p, 0xDD, 'highA_clean8_rotation_lock_DD')
    w['prove'](p, b.r[38] == 9, 'ANY locked DD payload chooses selector9, notC/E')
    w['prove'](p, And(*[A(a)[(j+3) % 12] == 8 for j in (0, 3, 6, 9)]),
        'rotation3 algebra preserves the four control8 values', False)
    print('PASS LOCAL pure counter8/selector9 loop limit: TYPE2 grows '
          'through4/6/8/A, but its four payload selectors lock at8. '
          'Fifth and ALL later clean continuations cannot select C/E. '
          'Other counter values, outside reads/data updates, independent '
          'TYPEA producers, A3/CC and partialK2 generally are NOT excluded.', flush=True)


def complete_counter8_payload_lock():
    # Join the local rotation result to ALL native counter8 callers,
    # rather than assuming that every high TYPE began at a chosen2.
    targets = {i for i, a in enumerate(states) if a[0] == 0x1D
               and (a[7] is None or 8 in a[7])}
    assert len(targets) == 4
    region = basis['backward'](targets, {0x25, 7})
    counts = Counter(states[i][0] for i in region)
    pairs = basis['internal_pairs'](region)
    assert len(region) == 62 and sum(pairs.values()) == 70
    assert basis['external_pairs'](region) == {(6, 7): 6}
    checked('COMPLETE62/70 counter8 feedback coverage, all four1D targets',
            parity['closed_feedback_region'])
    all25_eight = {i for i, a in enumerate(states) if a[0] == 0x25
                   and (a[7] is None or 8 in a[7])}
    assert len(all25_eight) == 3
    assert all25_eight == {i for i in region if states[i][0] == 0x25}
    ce77_eight = {i for i, a in enumerate(states) if a[0] == 0x77
        and (a[7] is None or 8 in a[7])
        and (a[5] is None or set(a[5]) & {12, 14})}
    assert ce77_eight == {18215, 42131} and ce77_eight <= region
    assert Counter(states[j][0] for i in ce77_eight for j in pred[i]) == {0x7E: 2}
    assert all(states[i][3] == [4] for i in region if states[i][0] in (1, 2, 3, 4))

    guard = lambda a: And(a.r[26] == 8, a.r[35] == 7)
    def rule(a, typ, shift=0):
        positions = {4: (9,), 6: (6, 9), 8: (3, 6, 9),
                     0: (0, 3, 6, 9), 10: (0, 3, 6, 9),
                     12: (0, 3, 6, 9), 14: (0, 3, 6, 9)}
        return And(Extract(0, 0, typ) == 0,
            *[Implies(typ == value,
                And(*[A(a)[(j-shift) % 12] == 8 for j in indices]))
              for value, indices in positions.items()])

    def inv(a, code):
        if code == 7: return Or(a.r[32] == 0, a.r[38] == 8)
        if code in (0x6D, 0x60):
            return Implies(And(guard(a), a.r[38] == 9), rule(a, a.r[32]+2, -1))
        if code == 0x18:
            return Implies(guard(a), And(a.r[38] == 9, rule(a, a.r[32]+2)))
        if code == 0x1B:
            return Implies(guard(a), And(a.r[38] == 9, rule(a, a.r[32]+1)))
        if code in (0xD4, 0x26):
            return Implies(guard(a), And(rule(a, a.r[32], 1), a.r[38] == A(a)[11]+1))
        if code in (0x28, 0x7E, 0x77):
            return Implies(guard(a), And(rule(a, a.r[32], 2), a.r[38] == A(a)[10]+1))
        return Implies(guard(a), And(a.r[38] == 9, rule(a, a.r[32])))

    for code in sorted(counts):
        label = f'highA_complete62_payload_{code:02X}'
        a = q['State'](label); p = w['base'](a, code); p.add(inv(a, code))
        if code in (1, 2, 3, 4): p.add(a.s1 == 4)
        b = execute(a, p, code, label)
        destinations = sorted({dst for first, dst in pairs if first == code})
        w['prove'](p, And(*[Implies(w['ip'](b) == dst, inv(b, dst))
                           for dst in destinations]),
            f'ALL ORIGINAL{code:02X} preserves COMPLETE62/70 TYPE/payload rotation invariant')
    a = q['State']('highA_complete62_CE8_excluded'); p = w['base'](a, 0x77)
    p.add(inv(a, 0x77), guard(a), a.r[32] == 10, Or(a.r[38] == 12, a.r[38] == 14))
    assert p.check() == unsat
    print('PASS GLOBAL eligible77/TYPEA/kind7/counter8 cannot have '
          'selectorC/E. ALL62 classes/70 edges, ALL3 counter8/25 '
          'contexts and BOTH counter8 C/E77 contexts are covered; '
          'unbounded loops/type wrap included. This is not only the '
          'five-round sample. Other nonzero counters/TYPEA sources '
          'and A3/CC remain outside this exclusion.', flush=True)


if __name__ == '__main__':
    r['inlet']['immutable_reference']()
    exact_c_counter_source()
    c_family_bb_type()
    e_family_bb_type()
    counter8_cache_lemmas()
    clean8_loop_cannot_finish_a()
    complete_counter8_payload_lock()
    r['inlet']['immutable_reference']()
    print('PASS exact high-A source/loop audit. No native/live/ALL5/key '
          'search, state/IP/return/ROM repair, physical Ms write or '
          'general partialK2 impossibility claim.', flush=True)
