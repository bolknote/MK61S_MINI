#!/usr/bin/env python3
"""Original7A/7C resolver loops, not post-restore return gadgets.

The complete graph gives exhaustive caller coverage, NOT positive runs.
S, type, number and mode remain jointly correlated through every loop.
Only the direct BC-C and the previously found type3/6/flag>=3→54 bridge
are targets. Other exits, later numeric protocols, BB and partialK2 are
NOT ruled out. No reference/ROM/state or return-address repair is used.
"""
from collections import Counter
from pathlib import Path
import runpy

from z3 import And, If, Implies, Not, Or, UGE, ULE, unsat

root = Path(__file__).resolve().parent
basis = runpy.run_path(str(root / 'cache-bc-zero07-native-cut.py'))
r, w, q, states, edges, walk, execute = (basis[n] for n in
    ('r', 'w', 'q', 'states', 'edges', 'walk', 'execute'))
inlet = basis['old']['inlet']
ac = lambda a: Or(a.r[35] == 10, a.r[35] == 12)
delta = lambda a: a.r[29]-a.r[2]-1
ac_packet = lambda a: Or(a.r[32] == 7,
    And(UGE(a.r[2], 5), Or(And(a.r[32] == 0, a.r[29] == 0),
                          And(a.r[32] == 2, Or(a.r[29] == 0, a.r[29] == 3)))))
controls = (2, 5, 23, 26, 29, 32, 35)


def complete_loop_coverage():
    graph = r['inlet']['g']['graph']
    assert len(states) == 52416 and sum(map(len, edges)) == 95731
    assert graph['metadata']['complete'] and graph['metadata']['pending'] == 0
    assert graph['metadata']['terminal'] is None
    assert graph['metadata']['fusedCommands'] == {'93': ['93', '94'], '12': ['12', 'C6']}
    assert all(states[i][0] == 0 for i in graph['indexes']['roots'])
    region = {i for i, a in enumerate(states) if a[0] in (0x7A, 0x7C, 0x7E)}
    assert len(region) == 538
    assert Counter(states[i][0] for i in region) == {0x7A: 170, 0x7C: 266, 0x7E: 102}
    assert not region & set(graph['indexes']['roots'])
    external = basis['external_pairs'](region)
    assert external == {(0xFA, 0x7A): 42, (0x28, 0x7E): 53}
    internal = basis['internal_pairs'](region)
    assert internal == {(0x7A, 0x7C): 170,
        (0x7C, 0x7A): 266, (0x7C, 0x7C): 266, (0x7C, 0x7E): 266,
        (0x7E, 0x7A): 98, (0x7E, 0x7C): 98, (0x7E, 0x7E): 98}
    assert sum(internal.values()) == 1262
    parents = lambda code: Counter(states[i][0] for i, row in enumerate(edges)
                                   for j in row if states[j][0] == code)
    assert parents(0x79) == {0x7C: 266, 0x7E: 98}
    assert parents(0x7B) == {0x65: 374, 0x7A: 170, 0x7C: 266, 0x7E: 98}
    # The65 family is SEPARATE: it is not silently covered by this loop
    # theorem just because its7B states may merge with a graph candidate.
    print('PASS COMPLETE resolver region:538 classes/1262 internal edges; '
          'ONLY FA/28 external entries. No91/98/9A restore return to7A/7C. '
          'The separate65→7B family is not inferred from the loop proof.', flush=True)


def actual_return_lifetime():
    for prefix, tag in (((0x79, 0x45, 0x8B, 0x48), '79'),
                        ((0x7B, 0xB7, 0x45, 0x8B, 0x48), '7B')):
        label = 'resolver_real_return_'+tag
        a = q['State'](label); p = w['base'](a, prefix[0])
        b = walk(a, p, prefix, label)
        w['prove'](p, And(*[w['stack'](b)[j] == value
                            for j, value in enumerate((0x49, 0x8C, 0x46))]),
            f'ORIGINAL{tag} through first48 leaves49/8C/46; earlier7A/7C tag discarded')


def exact_loop_gates():
    for code in (0x7A, 0x7C, 0x7E):
        label = f'resolver_exact_{code:02X}'
        a = q['State'](label); p = w['base'](a, code)
        b = execute(a, p, code, label)
        held = [b.r[j] == a.r[j] for j in controls]
        if code == 0x7A:
            claim = And(b.s == delta(a), b.s1 == 0,
                w['ip'](b) == If(ULE(delta(a), 5), q['BitVecVal'](0x7B, 8),
                                                    q['BitVecVal'](0x7C, 8)),
                b.r[38] == a.r[38])
        elif code == 0x7C:
            claim = And(b.s == 7, b.s1 == a.s, b.r[38] == 8,
                w['ip'](b) == (q['BitVecVal'](0x70, 8) | q['ZeroExt'](4, a.s)))
        else:
            claim = And(b.s == If(a.r[33] == 0, q['N4'](0), q['N4'](10)),
                b.s1 == a.s1, b.r[38] == a.r[38],
                w['ip'](b) == (q['BitVecVal'](0x70, 8) | q['ZeroExt'](4, a.r[35])))
        w['prove'](p, And(claim, *held, delta(b) == delta(a),
                           w['eq'](w['stack'](b), w['stack'](a))),
            f'ORIGINAL{code:02X} exact correlated dispatch; type/flag/number/mode/delta held')

    # All7C entry S values come from7A,7C or7E. This inductive packet is
    # stronger than treating S as free at every iteration of the graph.
    for code in (0x7A, 0x7C, 0x7E):
        label = f'resolver_S_provenance_{code:02X}'
        a = q['State'](label); p = w['base'](a, code)
        if code == 0x7C: p.add(Or(a.s == delta(a), a.s == 0, a.s == 10, a.s == 7))
        b = execute(a, p, code, label)
        w['prove'](p, Or(b.s == delta(b), b.s == 0, b.s == 10, b.s == 7),
            f'ORIGINAL{code:02X} preserves ALL finite7C-loop S provenance')
    print('PASS7C incoming S ONLY(delta,0,A,7): exits79/7B require '
          'delta9/B respectively. Delta and the control flag cannot be '
          'changed by repeating the resolver loop.', flush=True)


def ac_source_invariant(a, code):
    """High type at1D/2C belongs to kind7, not an arbitrary register kind.

    Swapping such a type into kindA/C therefore produces TYPE7, not0.
    The remaining low-typeA/C arrivals originate from low07 and retain
    its number/mode relation. No high-flag assumption is needed here.
    """
    typ, num, f = a.r[32], a.r[29], a.r[26] == 15
    if code in (0x1F, 0x1C): return And()
    if code == 7: return Or(a.r[38] == 8, And(typ == 0, num == 0))
    if code in (0x6D, 0x60):
        return And(Or(typ == 0, a.r[35] == 7, a.r[38] == 8),
            Implies(ac(a), Or(a.r[38] == 8, And(typ == 0, num == 0, UGE(a.r[2], 5)))))
    if code == 0x77: return a.r[35] == 7
    if code == 0x1A: return typ == 0
    if code in (0x18, 0x1B, 0x1D):
        limit = {0x18: 1, 0x1B: 2, 0x1D: 3}[code]
        ordinary = {0x18: And(typ == 0, num == 0, UGE(a.r[2], 5), a.s1 == 0),
                    0x1B: And(typ == 1, num == 0, UGE(a.r[2], 5), a.s1 == 0),
                    0x1D: And(typ == 2, num == 0, UGE(a.r[2], 5))}[code]
        return And(Or(ULE(typ, limit), a.r[35] == 7), Implies(ac(a), Or(f, ordinary)))
    if code == 0x2D: return typ == 2
    if code == 0x2C: return Or(ULE(typ, 3), a.r[35] == 7)
    regular = And(typ == 2, UGE(a.r[2], 5), Or(num == 0, num == 3))
    if code in (0x28, 0x7E):
        regular = And(UGE(a.r[2], 5), Or(And(typ == 0, num == 0),
                                       And(typ == 2, Or(num == 0, num == 3))))
    if code == 1: regular = And(typ == 2, UGE(a.r[2], 5))
    if code == 2: regular = And(typ == 2, UGE(a.r[2], 5), ULE(num, typ))
    if code in (3, 4, 0xBA, 0xCB, 0xDD, 0xD4, 0xD6):
        regular = And(typ == 2, UGE(a.r[2], 5), num == 3)
    return Implies(ac(a), Or(typ == 7, regular))


def all_ac_source_packets():
    counts, pairs = inlet['source_cut']()
    assert len(counts) == 33
    for code in sorted(counts):
        label = f'resolver_AC_source_{code:02X}'
        a = q['State'](label); p = w['base'](a, code)
        p.add(inlet['invariant'](a, code), ac_source_invariant(a, code))
        if code in (0x1F, 0x1A): p.add(a.r[26] == 15)
        b = execute(a, p, code, label)
        destinations = sorted({dst for first, dst in pairs if first == code})
        w['prove'](p, And(*[Implies(w['ip'](b) == dst,
            And(inlet['invariant'](b, dst), ac_source_invariant(b, dst)))
            for dst in destinations]),
            f'ALL ORIGINAL{code:02X} preserves COMPLETE1213/1525 A/C source packet')
    print('PASS GLOBAL initial28/kindsA/C: ONLY type0/num0/mode5..F, '
          'type2/num0or3/mode5..F, or type7. Type0/num0/mode4 is '
          'excluded by source structure, not by an arbitrary byte filter.', flush=True)


def module_packet(a, code):
    if code in (0x7A, 0x7C):
        packet = Or(a.r[32] == 15, And(ac(a), ac_packet(a)))
        if code == 0x7C:
            packet = And(packet, Or(a.s == delta(a), a.s == 0, a.s == 10, a.s == 7))
        return packet
    assert code == 0x7E
    odd = Or(a.r[35] == 9, a.r[35] == 11)
    return And(Implies(And(a.r[32] != 15, ac(a)), ac_packet(a)),
        Implies(And(a.r[32] != 15, odd),
            And(inlet['invariant'](a, 0x7E), ULE(a.r[23], 2), a.s1 == 14)))


def inductive_module_packets():
    """Close actual FA/28 sources and ALL internal loop transitions."""
    for code, destination in ((0xFA, 0x7A), (0x28, 0x7E)):
        label = f'resolver_module_source_{code:02X}'
        a = q['State'](label); p = w['base'](a, code)
        if code == 0x28:
            p.add(inlet['invariant'](a, code), ac_source_invariant(a, code),
                  basis['old']['origin_invariant'](a, code), a.r[26] != 0)
        b = execute(a, p, code, label)
        w['prove'](p, Implies(w['ip'](b) == destination, module_packet(b, destination)),
            f'ORIGINAL{code:02X} establishes actual resolver module packet')
        if code == 0xFA:
            w['prove'](p, b.r[32] == 15, 'ORIGINAL FA universally initializes typeF')
    for code, destinations in ((0x7A, (0x7C,)),
                               (0x7C, (0x7A, 0x7C, 0x7E)),
                               (0x7E, (0x7A, 0x7C, 0x7E))):
        label = f'resolver_module_induction_{code:02X}'
        a = q['State'](label); p = w['base'](a, code); p.add(module_packet(a, code))
        b = execute(a, p, code, label)
        w['prove'](p, And(*[Implies(w['ip'](b) == dst, module_packet(b, dst))
                           for dst in destinations]),
            f'ORIGINAL{code:02X} preserves ALL538/1262 finite-loop packets')
    print('PASS GLOBAL complete module induction: FA always bringsF; '
          'non-F7A/7C comes ONLY with the proven A/C packet. The S '
          'provenance and odd-kind first-entry flag are preserved through '
          'ANY finite internal loop, not selected graph examples.', flush=True)


def correlated_loop_exits():
    # Full finite-loop coverage from the three exact gates:
    # 7A reinitializes S=delta;7C sets S=7;7E sets S=0/A. Delta, kind,
    # type, number and both modes are held. A non-F7A/7C caller from28
    # must have kindA/C (the kindE7E self-loop cannot leave). FA setsF.
    for route in ('direct7B', 'via79', 'via7B'):
        label = 'resolver_original_'+route
        a = q['State'](label); p = w['base'](a, 0x7A)
        p.add(Or(a.r[32] == 15, And(ac(a), ac_packet(a))))
        b = execute(a, p, 0x7A, label+'_7A')
        if route == 'direct7B':
            p.add(w['ip'](b) == 0x7B)
            b = walk(b, p, (0x7B, 0xB7, 0x45, 0x8B), label)
            claim = And(b.r[32] == a.r[32]+3, b.r[29] == delta(a), ULE(b.r[29], 5))
        else:
            p.add(w['ip'](b) == 0x7C)
            b = execute(b, p, 0x7C, label+'_7C')
            target = 0x79 if route == 'via79' else 0x7B
            p.add(w['ip'](b) == target)
            seq = (0x79, 0x45, 0x8B) if route == 'via79' else (0x7B, 0xB7, 0x45, 0x8B)
            b = walk(b, p, seq, label)
            claim = (And(delta(a) == 9, b.r[32] == a.r[32]+1, b.r[29] == 15)
                     if route == 'via79' else
                     And(delta(a) == 11, b.r[32] == a.r[32]+3, b.r[29] == 6,
                         b.r[32] != 3))
        w['prove'](p, And(w['ip'](b) == 0x48, claim,
            b.r[23] == a.r[23], b.r[29] != 12,
            Not(And(b.r[32] == 3, b.r[29] == 6))),
            f'ALL loop-origin {route}: original correlated first48 excludes '
            'DIRECT operandC and TWO-decoder type3/operand6')

    # A7C which came directly from7E cannot be treated as free S9/B.
    a = q['State']('resolver_7E_7C_no_free_S'); p = w['base'](a, 0x7E)
    b = execute(a, p, 0x7E, 'resolver_7E_7C_no_free_S_7E')
    p.add(w['ip'](b) == 0x7C)
    b = walk(b, p, (0x7C,), 'resolver_7E_7C_no_free_S')
    w['prove'](p, Or(w['ip'](b) == 0x70, w['ip'](b) == 0x7A),
        'ORIGINAL7E→7C only exits70/7A, not fabricated79/7B;7A recomputes delta')
    a = q['State']('resolver_7C_repeat'); p = w['base'](a, 0x7C)
    b = execute(a, p, 0x7C, 'resolver_7C_repeat_first')
    p.add(w['ip'](b) == 0x7C)
    b = walk(b, p, (0x7C,), 'resolver_7C_repeat_second')
    w['prove'](p, w['ip'](b) == 0x77, 'ORIGINAL7C self-repeat next exits77, which clears flag')
    print('PASS unbounded resolver-loop classification: direct7B gives '
          'first48 operand0..5; via79 givesF; via7B gives6 but NEVER type3. '
          'No free S/return/type/mode; no DIRECT BC-C or old3/6→54 writer '
          'from these loops. Other70/76/77/B2/BF and later protocols remain open.', flush=True)

    # The7E direct exits are also part of the complete module; do not
    # mistake them for the delta-correlated7C exits. Non-F odd kinds
    # retain the low flag and low-type/number packet from ORIGINAL28.
    for destination in (0x79, 0x7B):
        label = f'resolver_module_direct_{destination:02X}'
        a = q['State'](label); p = w['base'](a, 0x7E); p.add(module_packet(a, 0x7E))
        b = execute(a, p, 0x7E, label+'_7E'); p.add(w['ip'](b) == destination)
        seq = ((0x79, 0x45, 0x8B) if destination == 0x79 else
               (0x7B, 0xB7, 0x45, 0x8B))
        b = walk(b, p, seq, label)
        w['prove'](p, And(w['ip'](b) == 0x48,
            Not(And(UGE(b.r[32], 4), b.r[29] == 12)),
            Not(And(b.r[32] == 3, b.r[29] == 6, UGE(b.r[23], 3)))),
            f'ALL resolver7E direct{destination:02X}: no DIRECT BC-C or high-flag3/6→54')
    print('PASS ALL resolver-origin79/7B arrivals, including direct7E: '
          'DIRECT BC-C and the old type3/6/flag>=3→54 bridge CLOSED. '
          'Separate65 origins, BB, other exits and later48 paths remain '
          'outside this loop-specific theorem.', flush=True)


def other_gate_exits():
    """Classify what the 0..5 route might do, without claiming a native inlet."""
    a = q['State']('resolver_other48_gates'); p = w['base'](a, 0x48)
    p.add(a.r[32] == 3, ULE(a.r[29], 5), UGE(a.r[23], 3))
    b = walk(a, p, (0x48, 0x4A, 0x4B, 0x4D), 'resolver_other48_gates')
    w['prove'](p, And(w['ip'](b) == 0x54, b.r[32] == 3, b.r[29] == a.r[29]),
        'CONDITIONAL first48/type3/operands0..5/flag>=3 DOES enter54')
    b = walk(b, p, (0x54, 0xB7, 0x45, 0x8B, 0x48, 0xB1),
             'resolver_other48_second')
    w['prove'](p, And(b.r[32] == 4, b.r[29] == a.r[29]+6, b.r[23] == 0,
        w['ip'](b) == If(ULE(a.r[29], 1), q['BitVecVal'](0xB2, 8),
                                            q['BitVecVal'](0xB3, 8))),
        'CONDITIONAL second48/type4: operands6..B, NO C; B2 forold0/1')
    p.add(UGE(a.r[29], 2)); b = walk(b, p, (0xB3,), 'resolver_other48_B3')
    w['prove'](p, w['ip'](b) == q['BitVecVal'](0xB8, 8)+q['ZeroExt'](4, a.r[29]-2),
        'CONDITIONAL oldoperands2/3/4/5 give B8/B9/BA/BB')
    print('SCOPE: the old3/6→54→DIRECT BC-C bridge is closed, NOT every '
          '54 call. A high-flag3/4 or3/5 loop entry could use BA/BB. '
          'Its native high-flag A/C source remains UNPROVED.', flush=True)


def conditional_limited_bb_inlets():
    """Four actual ORIGINAL prefixes toBB/BC, still CONDITIONAL at28.

    Do not confuse valid source type/number/mode bounds with a native
    producer of the high flag. Only reaching BC with a limited buffer is
    proved here, not a physical programme write, an exit or an exchange.
    """
    for kind in (10, 12):
        for mode, number in ((11, 4), (10, 5)):
            label = f'resolver_limited_kind{kind:X}_mode{mode:X}'
            a = q['State'](label); p = w['base'](a, 0x28)
            p.add(a.r[35] == kind, a.r[32] == 0, a.r[29] == 0,
                  a.r[2] == mode, a.r[26] != 0, UGE(a.r[23], 3))
            if kind == 12: p.add(a.r[33] != 0)  # explicit data-sign gate, not a repair
            prefix = (0x28, 0x7E, 0x7A) if kind == 10 else (0x28, 0x7E, 0x7C, 0x7A)
            b = walk(a, p, (*prefix, 0x7B, 0xB7, 0x45, 0x8B), label+'_first')
            w['prove'](p, And(w['ip'](b) == 0x48, b.r[32] == 3,
                b.r[29] == number, b.r[23] == a.r[23]),
                f'CONDITIONAL actual28/kind{kind:X}/mode{mode:X} makes first48/3/{number}')
            b = walk(b, p, (0x48, 0x4A, 0x4B, 0x4D, 0x54,
                0xB7, 0x45, 0x8B, 0x48, 0xB1, 0xB3), label+'_second')
            w['prove'](p, And(b.r[32] == 4, b.r[29] == number+6, b.r[23] == 0,
                w['ip'](b) == (0xBA if number == 4 else 0xBB)),
                'ORIGINAL54 creates second48/type4/numberAorB, neverC')
            branch = (0xBA, 0xCC, 0xBB) if number == 4 else (0xBB,)
            b = walk(b, p, branch, label+'_limited_BB')
            expected_b = [*a.r[4:36:3], q['N4'](15)]
            assert len(expected_b) == 12
            w['prove'](p, And(w['ip'](b) == 0xBC, w['stack'](b)[0] == 0x49,
                w['eq'](b.r[1:36:3], expected_b),
                w['eq'](b.r[0:36:3], a.r[0:36:3])),
                'CONDITIONAL actualBB/BC inlet: A12 held; B12=[oldB1..B11,F]')
            p.push()
            assert q['possible_values'](w['byte'](b.r[31], b.r[34]), p, 257) == list(range(0xF0, 0x100))
            p.pop()
    print('PASS FOUR CONDITIONAL limitedBB/BC inlets: kindsA/C × modesB/A '
          'with type0/num0/flag>=3; ALL16 F0..FF byte values. Every return '
          'constructed by ORIGINAL words, no free head. Joint native high '
          'flag/data producer, phase/Ms provenance/physical writer/exit/'
          'displaced-word recovery/inverse remain UNPROVED.', flush=True)


if __name__ == '__main__':
    r['inlet']['immutable_reference']()
    complete_loop_coverage()
    actual_return_lifetime()
    exact_loop_gates()
    # Verify the inherited GLOBAL odd-kind first-entry boundary before
    # using it, not just the two old conditional writer examples.
    zero_region = basis['native_zero07_induction']()
    basis['native_nonzero07_cut'](zero_region)
    basis['native_first28_flag_cut']()
    all_ac_source_packets()
    inductive_module_packets()
    correlated_loop_exits()
    other_gate_exits()
    conditional_limited_bb_inlets()
    r['inlet']['immutable_reference']()
    print('PASS original resolver-loop inlet cut. Not a native keyboard '
          'recipe, no live/ALL5 capture, no reference mutation, no global '
          'partialK2 impossibility claim.', flush=True)
