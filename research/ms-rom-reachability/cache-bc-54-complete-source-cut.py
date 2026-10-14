#!/usr/bin/env python3
"""Complete native source theorem for the TYPE3 entry to ORIGINAL54.

Join ALL48/8B/45 callers, the independent65 family and the60 bypass.
Public physical matrix constraints are used for the8A keyboard family;
all other exact-word proofs allow arbitrary per-tick inputs. No reference,
ROM, calculator state, IP or return repair. Negative reset theorems are
NOT claims that all BC/BB or all partialK2 routes are impossible.
"""
from collections import Counter
from pathlib import Path
import runpy

from z3 import And, If, Implies, Not, Or, UGE, ULE, sat, unsat

root = Path(__file__).resolve().parent
highkind = runpy.run_path(str(root / 'cache-bc-high-kind-flag-cut.py'))
loops, basis = highkind['loops'], highkind['basis']
r, w, q, states, edges, walk, execute = (highkind[n] for n in
    ('r', 'w', 'q', 'states', 'edges', 'walk', 'execute'))
sixtyfive = runpy.run_path(str(root / 'cache-bc-65-source-cut.py'))
entry68 = sixtyfive['entry']
low = lambda a: ULE(a.r[23], 2)
parent_counts = lambda code: Counter(states[i][0] for i, row in enumerate(edges)
                                     for j in row if states[j][0] == code)


def complete_callers():
    expected = {
        0x48: {0x8B: 857, 0x60: 19}, 0x8B: {0x45: 1097},
        0x45: {0x35: 806, 0x83: 309, 0xB7: 801, 0x79: 149},
        0x83: {0xB5: 400}, 0xB5: {0x35: 806, 0xB3: 30},
        0xB7: {0xB5: 400, 0x7B: 551, 0xB3: 30, 0x54: 230, 0x0A: 21},
        0x0A: {0xFA: 42},
        0x7B: {0x65: 374, 0x7A: 170, 0x7C: 266, 0x7E: 98},
        0xB3: {0xB1: 149, 0xB3: 30},
        0x4A: {0x48: 466}, 0x4B: {0x4A: 146}, 0x4D: {0x4B: 126},
        0x54: {0x4D: 126, 0x5F: 156, 0x5C: 220}}
    for code, parents in expected.items(): assert parent_counts(code) == parents
    assert sum(a[0] == 0x48 for a in states) == 466
    assert sum(a[0] == 0x54 for a in states) == 230
    assert all(states[i][0] == 0 for i in r['inlet']['g']['graph']['indexes']['roots'])
    print('PASS COMPLETE callers: ALL466 48 contexts, ONLY8B/60; '
          'ALL1097 45 contexts and every B7/7B source; ALL230 54 contexts. '
          'No caller family is replaced by a selected positive graph path.', flush=True)


def exclude_false_b3_callers():
    # Root is notB3; B1 and B3/self are its ONLY graph parents. Both
    # preserve the operand; B1→B3 requires8..F. This is an induction,
    # not deleting the graph's false B5/B7 edges by hand.
    for code in (0xB1, 0xB3):
        label = f'type3_b3_operand_{code:02X}'
        a = q['State'](label); p = w['base'](a, code)
        if code == 0xB3: p.add(UGE(a.r[29], 8))
        b = execute(a, p, code, label)
        if code == 0xB1:
            claim = Implies(w['ip'](b) == 0xB3, UGE(b.r[29], 8))
        else:
            claim = And(b.r[29] == a.r[29], UGE(w['ip'](b), 0xB8),
                        ULE(w['ip'](b), 0xBF), w['ip'](b) != 0xB5, w['ip'](b) != 0xB7)
        w['prove'](p, claim, f'ALL ORIGINAL{code:02X} establishes/preserves real B3 high-operand source')


def physical8a_to7b():
    # Filter actual path choices and each tick's public matrix signals,
    # without overwriting ANY symbolic IP/state field. SAT means only
    # a nonempty PRIMARY premise; every claim below is universal under it.
    for prefix, typ in (((0x35, 0xC5, 0x8A, 0x65), 2), ((0xFA, 0x8A, 0x65), 1)):
        label = 'type3_public8A_'+f'{prefix[0]:02X}'
        a = q['State'](label); p = w['base'](a, prefix[0]); b = a
        for index, code in enumerate(prefix):
            p.add(w['ip'](b) == code)
            assert p.check() == sat
            kx, ky = q['arbitrary_keys'](label+f'_keys{index}')
            p.add(*[Or(And(xx == 0, yy == 0), And(UGE(xx, 2), ULE(xx, 11),
                                                    Or(yy == 1, yy == 8, yy == 9)))
                    for xx, yy in zip(kx, ky)])
            b = w['ex'](b, code, kx, ky,
                serial_inputs=q['State'](label+f'_serial{index}').m)
        w['prove'](p, And(w['ip'](b) == 0x7B, b.r[32] == typ),
            f'ALL-entry/public-tick {prefix}→7B/type{typ}, never type0')


def all65_to7b_packets():
    sixtyfive['complete65_frontier']()
    physical8a_to7b()
    sixtyfive['actual56_source_induction']()  # also excludes5C/5F→54
    sixtyfive['complete68_source_induction']()
    for code in (0x65,):
        a = q['State']('type3_65_phi_hold'); p = w['base'](a, code)
        b = execute(a, p, code, 'type3_65_phi_hold')
        w['prove'](p, And(w['ip'](b) == 0x7B, b.r[23] == a.r[23]),
            'ORIGINAL65→7B holds flag;54/type0 and eligible68 producers haveflag0')
    print('PASS ALL37465 origins:8A gives7B/type1or2 under public matrix; '
          'actual56 and68 giveflag0. Thus every65-origin7B satisfies '
          'TYPE!=0 OR flag<=2. No native capture or fabricated path IP.', flush=True)


def module_low_flag_packets():
    def inv(a, code):
        if code in (0x7A, 0x7C, 0x79, 0x7B): return Or(a.r[32] == 15, low(a))
        assert code == 0x7E
        return Or(a.r[32] == 15, ULE(a.r[35], 7), low(a))
    for code, destination in ((0xFA, 0x7A), (0x28, 0x7E)):
        label = f'type3_loop_source_{code:02X}'
        a = q['State'](label); p = w['base'](a, code)
        if code == 0x28:
            p.add(highkind['high_kind_origin_invariant'](a, code), a.r[26] != 0)
        b = execute(a, p, code, label)
        w['prove'](p, Implies(w['ip'](b) == destination, inv(b, destination)),
            f'ORIGINAL{code:02X} establishes native loop typeF/low-flag packet')
    for code, destinations in ((0x7A, (0x7B, 0x7C)),
        (0x7C, (0x7A, 0x7B, 0x7C, 0x7E, 0x79)),
        (0x7E, (0x7A, 0x7B, 0x7C, 0x7E, 0x79))):
        label = f'type3_loop_induction_{code:02X}'
        a = q['State'](label); p = w['base'](a, code); p.add(inv(a, code))
        b = execute(a, p, code, label)
        w['prove'](p, And(*[Implies(w['ip'](b) == dst, inv(b, dst))
                           for dst in destinations]),
            f'ORIGINAL{code:02X} preserves native typeF/low-flag exits with ANY loop count')
    print('PASS ALL resolver-origin79/7B: typeF OR R23<=2, including '
          'A/C and all finite7A/7C/7E loops. Not only operand6 candidates.', flush=True)


def all8b_type3_flags():
    def inv(a, code):
        if code in (0x35, 0xFA, 0x54): return And()
        if code in (0xB5, 0x83, 0x0A): return a.r[32] == 15
        if code == 0x7B: return Or(a.r[32] != 0, low(a))
        if code == 0xB7: return Or(a.r[32] != 1, low(a))
        if code in (0x45, 0x79): return Or(a.r[32] != 2, low(a))
        if code in (0x8B, 0x48): return Or(a.r[32] != 3, low(a))
        raise AssertionError(code)
    outgoing = {0x35: (0xB5, 0x45), 0xFA: (0x0A,),
        0xB5: (0x83, 0xB7), 0x83: (0x45,), 0x0A: (0xB7,),
        0x7B: (0xB7,), 0x54: (0xB7,), 0xB7: (0x45,),
        0x79: (0x45,), 0x45: (0x8B,), 0x8B: (0x48,)}
    for code, destinations in outgoing.items():
        label = f'type3_all8B_{code:02X}'
        a = q['State'](label); p = w['base'](a, code); p.add(inv(a, code))
        b = execute(a, p, code, label)
        w['prove'](p, And(*[Implies(w['ip'](b) == dst, inv(b, dst))
                           for dst in destinations]),
            f'ORIGINAL{code:02X} preserves COMPLETE 8B-source type3⇒flag<=2')
    print('PASS ALL857 8B callers: native48/type3 impliesflag<=2. '
          '54 may supply ANY old type, but54 itself clears the flag; '
          'this induction does not assume54/type3 excluded in advance.', flush=True)


def independent60_type3_flags():
    parents = {0xC9: {0xCD: 492}, 6: {0x55: 209, 0x38: 48, 0x3A: 178, 0xC9: 85},
        7: {6: 273}, 0x6D: {7: 273, 0x77: 165}, 0x60: {0x6D: 227, 0x6C: 19}}
    for code, incoming in parents.items(): assert parent_counts(code) == incoming
    def inv(a, code):
        if code == 0xC9: return a.r[38] == 8
        if code in (6, 7): return Or(a.r[32] == 0, a.r[38] == 8)
        if code in (0x6D, 0x60): return Or(a.r[32] == 0, a.r[38] == 8, a.r[23] == 0)
        return And()
    sources = sorted({code for row in parents.values() for code in row})
    for code in sources:
        label = f'type3_independent60_{code:02X}'
        a = q['State'](label); p = w['base'](a, code); p.add(inv(a, code))
        b = execute(a, p, code, label)
        destinations = [dst for dst, row in parents.items() if code in row]
        w['prove'](p, And(*[Implies(w['ip'](b) == dst, inv(b, dst))
                           for dst in destinations]),
            f'ORIGINAL{code:02X} preserves COMPLETE independent60 source invariant')
    a = q['State']('type3_independent60_exit'); p = w['base'](a, 0x60)
    p.add(inv(a, 0x60)); b = execute(a, p, 0x60, 'type3_independent60_exit')
    w['prove'](p, Implies(And(w['ip'](b) == 0x48, b.r[32] == 3), b.r[23] == 0),
        'ALL independent60→48/type3 haveflag0; selector8 cannot select48')


def complete54_gate_induction():
    # ALL48 now has the joined type3⇒flag<=2 boundary. 54's other5C/5F
    # parents were excluded by actual56_source_induction(), independently
    # of this target. The two swaps restore type; low-flag exits do not
    # take54. No manufactured higher type is imported into the proof.
    def inv(a, code):
        if code == 0x48: return Or(a.r[32] != 3, low(a))
        if code == 0x4A: return And(ULE(a.r[32], 3), Or(a.r[32] != 3, low(a)))
        if code == 0x4B: return And(ULE(a.r[35], 3), Implies(a.r[35] == 3, ULE(a.r[23], 1)))
        if code == 0x4D: return And(ULE(a.r[32], 3), Implies(a.r[32] == 3, a.r[23] == 0))
        if code == 0x54: return ULE(a.r[32], 2)
        raise AssertionError(code)
    for code, destination in ((0x48, 0x4A), (0x4A, 0x4B), (0x4B, 0x4D), (0x4D, 0x54)):
        label = f'type3_complete54_gate_{code:02X}'
        a = q['State'](label); p = w['base'](a, code); p.add(inv(a, code))
        b = execute(a, p, code, label)
        w['prove'](p, Implies(w['ip'](b) == destination, inv(b, destination)),
            f'ORIGINAL{code:02X} preserves COMPLETE native54/type0..2 gate')
    for operand in (4, 5, 6):
        a = q['State'](f'type3_complete54_excluded_operand{operand}')
        p = w['base'](a, 0x54); p.add(inv(a, 0x54), a.r[32] == 3, a.r[29] == operand)
        assert p.check() == unsat
    print('PASS GLOBAL ALL46648: TYPE3⇒R23<=2, irrespective of operand. '
          'PASS GLOBAL ALL23054: ONLY types0/1/2, NEVER3. Every54-based '
          'type3→second48/type4 BC-A/B/C writer is excluded from reset. '
          'Low-flag directBB, high77/B and other exits remain outside '
          'this exclusion; no general partialK2 impossibility theorem.', flush=True)


if __name__ == '__main__':
    r['inlet']['immutable_reference']()
    zero_region = highkind['all_high_kind_zero07_sources']()
    highkind['nonzero07_high_kind_sources'](zero_region)
    highkind['initial28_high_kind_flag']()
    highkind['exclude_four_conditional_bb_packets']()
    complete_callers()
    exclude_false_b3_callers()
    loops['complete_loop_coverage']()
    module_low_flag_packets()
    all65_to7b_packets()
    all8b_type3_flags()
    independent60_type3_flags()
    complete54_gate_induction()
    r['inlet']['immutable_reference']()
    print('PASS complete native54 writer-source audit. No keyboard search, '
          'native/ALL5/live experiment, state/IP/return/ROM repair or '
          'general partialK2 impossibility claim.', flush=True)
