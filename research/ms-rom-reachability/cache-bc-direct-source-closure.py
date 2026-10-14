#!/usr/bin/env python3
"""Join ALL native B3/CC/BB sources of the original BC writer.

Negative native theorems use COMPLETE reset caller coverage and original
word inductions. No graph path/SAT packet is a positive keyboard witness.
The 3-high/F-high bound concerns the immediate numeric-byte interface,
NOT every payload tetra BC writes or every possible later adapter.
Public keyboard matrix is constrained for the8A family. Elsewhere fresh
serial/key inputs deliberately overapproximate the other chips and ring.
"""
from collections import Counter
from contextlib import redirect_stdout
import io
from pathlib import Path
import runpy

from z3 import And, Extract, If, Implies, Not, Or, UGE, ULE, sat, unsat

root = Path(__file__).resolve().parent
native54 = runpy.run_path(str(root / 'cache-bc-54-complete-source-cut.py'))
highkind, loops, basis, inlet = (native54[n] for n in
    ('highkind', 'loops', 'basis', 'entry68'))
r, w, q, states, edges, execute, walk = (native54[n] for n in
    ('r', 'w', 'q', 'states', 'edges', 'execute', 'walk'))
pred = basis['pred']
parity = inlet['parity']
even = lambda a: Extract(0, 0, a.r[32]) == 0
odd = lambda a: Extract(0, 0, a.r[29]) == 1
A = lambda a: a.r[0:36:3]
B = lambda a: a.r[1:36:3]
N8 = lambda n: q['BitVecVal'](n, 8)


def eq(xs, ys):
    assert len(xs) == len(ys), (len(xs), len(ys))
    return w['eq'](xs, ys)


def checked_dependency(label, verify):
    output = io.StringIO()
    try:
        with redirect_stdout(output): verify()
    except Exception:
        print(output.getvalue()[-2400:], end='', flush=True)
        raise
    print('PASS dependency:', label, f'({len(output.getvalue().splitlines())} checked reports)',
          flush=True)


def complete_writer_callers():
    expected = {0xB1: {0x48: 466, 0xB3: 30},
        0xB3: {0xB1: 149, 0xB3: 30},
        0xBA: {4: 574, 0xB3: 30}, 0xCC: {0xBA: 495, 0xA3: 3},
        0xBB: {0xB3: 30, 0xCC: 5, 0xA3: 1},
        0xBC: {0xB3: 30, 0xBB: 8}}
    for code, parents in expected.items(): assert native54['parent_counts'](code) == parents
    assert sum(a[0] == 0xBB for a in states) == 8
    assert sum(a[0] == 0xBC for a in states) == 11
    cc = {i for i, a in enumerate(states) if a[0] == 0xCC
          and any(states[j][0] == 0xBB for j in edges[i])}
    assert len(cc) == 5
    cc_parents = {j for i in cc for j in pred[i]}
    assert Counter(states[j][0] for i in cc for j in pred[i]) == {0xBA: 3, 0xA3: 3}
    ba = {i for i in cc_parents if states[i][0] == 0xBA}
    assert len(ba) == 3
    assert Counter(states[j][0] for i in ba for j in pred[i]) == {0xB3: 30}
    assert all(states[i][1][0] == 0x49 for i in ba)
    a3 = {i for i in cc_parents if states[i][0] == 0xA3}
    assert len(a3) == 3
    assert Counter(states[i][2] for i in a3) == {0xCC: 2, 'diagonal': 1}
    assert Counter(states[i][1][0] for i in a3) == {0x93: 2, 0xDD: 1}
    assert all(states[i][3] == [9] for i in a3)
    print('PASS COMPLETE writer sources: ALL8 BB/11 BC classes; CC has '
          'three B3/BA sources AND three A3 source edges. Two constantCC '
          'A3 classes are NOT the earlier diagonal A3/BB packet. '
          'No4/counter entry supplies the three BA->CC->BB classes.', flush=True)


def safe_dispatch(a, code):
    # Exact short-suffix predicate at a decoder boundary. No IP is
    # repaired, and4-bit arithmetic retains wraparound of type/operand.
    if code == 0x48: typ, num = a.r[32], a.r[29]
    elif code == 0x8B: typ, num = a.r[32], a.r[29]-a.r[2]-1
    elif code == 0x79: typ, num = a.r[32]+1, a.r[29]+6-a.r[2]-1
    else:
        typ = a.r[32]+{0x65: 4, 0x7B: 3, 0xB7: 2, 0x45: 1}[code]
        num = a.r[29]+a.s1-a.r[2]-1
    return Not(And(UGE(typ, 4), num == 12))


def resolver_no_direct_c():
    # These source inductions were not needed for the flag-only54 result:
    # retain number/type/mode correlation, not just the low flag.
    checked_dependency('complete1213/1525 odd-kind type/number/mode sources',
                       loops['inlet']['joint_induction'])
    checked_dependency('complete1213/1525 A/C type/number/mode sources',
                       loops['all_ac_source_packets'])
    loops['complete_loop_coverage']()

    def inv(a, code):
        if code in (0x7B, 0x79): return safe_dispatch(a, code)
        return loops['module_packet'](a, code)

    for code, destination in ((0xFA, 0x7A), (0x28, 0x7E)):
        label = f'directC_resolver_source_{code:02X}'
        a = q['State'](label); p = w['base'](a, code)
        if code == 0x28:
            p.add(loops['inlet']['invariant'](a, code),
                loops['ac_source_invariant'](a, code),
                highkind['high_kind_origin_invariant'](a, code), a.r[26] != 0)
        b = execute(a, p, code, label)
        w['prove'](p, Implies(w['ip'](b) == destination, inv(b, destination)),
            f'ORIGINAL{code:02X} establishes complete resolver data packet')
    for code, destinations in ((0x7A, (0x7B, 0x7C)),
        (0x7C, (0x7A, 0x7B, 0x7C, 0x7E, 0x79)),
        (0x7E, (0x7A, 0x7B, 0x7C, 0x7E, 0x79))):
        label = f'directC_resolver_induction_{code:02X}'
        a = q['State'](label); p = w['base'](a, code); p.add(inv(a, code))
        b = execute(a, p, code, label)
        w['prove'](p, And(*[Implies(w['ip'](b) == dst, inv(b, dst))
                           for dst in destinations]),
            f'ALL ORIGINAL{code:02X} resolver exits preserve not-high-type/operandC')
    print('PASS ALL resolver79/7B sources: the COMPLETE538/1262 loop '
          'induction supplies the decoder predicate, including direct7E '
          'and unlimited loops. Not only selected positive paths.', flush=True)


def physical8a_data_packets():
    for prefix in ((0x35, 0xC5, 0x8A, 0x65), (0xFA, 0x8A, 0x65)):
        label = 'directC_public8A_'+f'{prefix[0]:02X}'
        a = q['State'](label); p = w['base'](a, prefix[0]); b = a
        for index, code in enumerate(prefix):
            p.add(w['ip'](b) == code); assert p.check() == sat
            kx, ky = q['arbitrary_keys'](label+f'_keys{index}')
            p.add(*[Or(And(xx == 0, yy == 0), And(UGE(xx, 2), ULE(xx, 11),
                Or(yy == 1, yy == 8, yy == 9))) for xx, yy in zip(kx, ky)])
            b = w['ex'](b, code, kx, ky,
                serial_inputs=q['State'](label+f'_serial{index}').m)
        w['prove'](p, And(w['ip'](b) == 0x7B, safe_dispatch(b, 0x7B)),
            f'ALL public-matrix actual{prefix}->7B preserves directC exclusion')


def other65_data_packets():
    a = q['State']('directC_actual56'); p = w['base'](a, 0x54)
    b = execute(a, p, 0x54, 'directC_actual56_54')
    p.add(w['ip'](b) == 0x56); assert p.check() == sat
    b = execute(b, p, 0x56, 'directC_actual56_56')
    # Some real54/56 inputs exit through57 instead. Select the actual
    #56->65 branch, rather than assuming every56 caller reaches65.
    p.add(w['ip'](b) == 0x65); assert p.check() == sat
    b = walk(b, p, (0x65,), 'directC_actual56_call')
    w['prove'](p, And(w['ip'](b) == 0x7B, safe_dispatch(b, 0x7B)),
        'ALL actual54->56/65 cleanup has safe7B/type0, regardless of numeric data')

    # COMPLETE68 joint induction was verified by the54 source proof's
    # independent65 audit. Never enlarge these real ready fields to an
    # arbitrary high type/operand; that would restore the false C route.
    a = q['State']('directC_actual68'); p = w['base'](a, 0x68)
    p.add(a.r[38] == 14, a.r[26] != 0, a.r[2] == 15, a.r[5] == 0,
        a.r[23] == 0, a.s1 == 0, a.r[29] == a.r[32]+1,
        Or(*[a.r[32] == v for v in (6, 8, 10, 12)]))
    b = walk(a, p, (0x68, 0x65), 'directC_actual68_call')
    w['prove'](p, And(w['ip'](b) == 0x7B, safe_dispatch(b, 0x7B)),
        'ALL actual eligible68/65: even type/odd number survives as safe7B packet')
    print('PASS ALL independent65 parents8A/56/68 supply safe7B, '
          'not a free candidate decoder input.', flush=True)


def join_all8b_packets():
    def inv(a, code):
        if code in (0x35, 0xFA): return And()
        if code in (0xB5, 0x83, 0x0A): return a.r[32] == 15
        if code == 0x54: return ULE(a.r[32], 2)
        return safe_dispatch(a, code)
    outgoing = {0x35: (0xB5, 0x45), 0xFA: (0x0A,),
        0xB5: (0x83, 0xB7), 0x83: (0x45,), 0x0A: (0xB7,),
        0x7B: (0xB7,), 0x54: (0xB7,), 0xB7: (0x45,),
        0x79: (0x45,), 0x45: (0x8B,), 0x8B: (0x48,)}
    for code, destinations in outgoing.items():
        label = f'directC_all8B_{code:02X}'
        a = q['State'](label); p = w['base'](a, code); p.add(inv(a, code))
        b = execute(a, p, code, label)
        w['prove'](p, And(*[Implies(w['ip'](b) == dst, inv(b, dst))
                           for dst in destinations]),
            f'ORIGINAL{code:02X} preserves ALL8B source directC exclusion')
    print('PASS ALL857 8B->48 edges: never TYPE>=4 AND operandC. '
          'The now-complete native54/type0..2 theorem prevents EVERY '
          '54-origin high decoder type, not only the previous selected bridge.', flush=True)


def independent60_no_direct_c():
    # The C-selector branch uses the SAME complete last25 source cut
    # as the earlier parity result, not the distinct E-selector68 inlet.
    checked_dependency('complete1070/1340 nonzero25 kind7/even-type source',
                       parity['all_nonzero_kind7_cut'])
    checked_dependency('complete388 last25 C-selector/odd-operand source',
                       parity['high77_operand_cut'])
    packet = lambda a: Or(a.r[38] != 12, a.r[26] == 0,
        And(a.r[32] == 0, a.r[29] == 0), And(even(a), odd(a)))
    for code in (7, 0x77, 0x6D, 0x6C, 0x60):
        label = f'directC_independent60_{code:02X}'
        a = q['State'](label); p = w['base'](a, code)
        if code == 7: p.add(Or(a.r[38] == 8, And(a.r[32] == 0, a.r[29] == 0)))
        elif code in (0x77, 0x6D, 0x60): p.add(packet(a))
        b = execute(a, p, code, label)
        if code in (7, 0x77): claim = Implies(w['ip'](b) == 0x6D, packet(b))
        elif code in (0x6D, 0x6C):
            claim = Implies(w['ip'](b) == 0x60, And(packet(b),
                Implies(code == 0x6D, b.r[26] != 0)))
        else:
            p.add(a.r[26] != 0)
            claim = Implies(w['ip'](b) == 0x48, safe_dispatch(b, 0x48))
        w['prove'](p, claim, f'ORIGINAL{code:02X} preserves independent60 no-directC packet')
    print('PASS ALL19 independent60->48 edges: selectorC/nonzero-counter '
          'comes with zero type/number OR even-type/odd-operand. '
          'Other6C callers set selector8 and cannot select48.', flush=True)


def no_native_b3_to_bc():
    def inv(a, code):
        if code == 0x48: return safe_dispatch(a, code)
        if code == 0xB1: return a.r[29] != 12
        assert code == 0xB3
        return And(UGE(a.r[29], 8), a.r[29] != 12)
    for code, destinations in ((0x48, (0xB1,)),
        (0xB1, (0xB3,)), (0xB3, (0xB1, 0xB3))):
        label = f'directC_global_b3_{code:02X}'
        a = q['State'](label); p = w['base'](a, code); p.add(inv(a, code))
        b = execute(a, p, code, label)
        w['prove'](p, And(*[Implies(w['ip'](b) == dst, inv(b, dst))
                           for dst in destinations],
            w['ip'](b) != 0xBC if code == 0xB3 else And()),
            f'ALL ORIGINAL{code:02X} establishes complete native B3 operand!=C')
    print('PASS GLOBAL ALL46648: high TYPE>=4 excludes operandC. '
          'PASS GLOBAL native B3->BC has NO execution from reset under '
          'public keys. All30 graph B3/BC edges are false candidates. '
          'BB and other writers/later adapters remain outside this exclusion.', flush=True)


def all_bb_tail_provenance():
    fa = lambda a: And(a.r[37] == 15, a.r[40] == 10)
    a3 = lambda a: And(a.r[37] == 3, a.r[40] == 10)
    for code, destinations in ((0x48, (0xB1,)), (0xB1, (0xB3,)),
        (0xB3, (0xB1, 0xB3, 0xBA, 0xBB)), (0xBA, (0xCC,)), (0xCC, (0xBB,))):
        label = f'bb_F_tail_source_{code:02X}'
        a = q['State'](label); p = w['base'](a, code)
        if code != 0x48: p.add(fa(a))
        b = execute(a, p, code, label)
        w['prove'](p, And(*[Implies(w['ip'](b) == dst, fa(b)) for dst in destinations]),
            f'ORIGINAL{code:02X} constructs/holds complete decoder tailF,A')
    # COMPLETE coverage above excludes4-origin BA from the selected
    # CC->BB family, so the BA boundary really is supplied only by B3.
    a = q['State']('bb_A3_tail_source'); p = w['base'](a, 0xA3)
    b = execute(a, p, 0xA3, 'bb_A3_tail_source')
    w['prove'](p, And(a3(b), eq(B(b), B(a))),
        'ALL ORIGINAL A3 swaps its IP into B tail3,A, holds numericB12')
    a = q['State']('bb_CC_A3_tail'); p = w['base'](a, 0xCC); p.add(a3(a))
    b = execute(a, p, 0xCC, 'bb_CC_A3_tail')
    w['prove'](p, Implies(w['ip'](b) == 0xBB,
        And(a3(b), eq(b.r[1:42:3], a.r[1:42:3]))),
        'ALL ORIGINAL CC preserves actual A3 tail and ALL14 B tetras on BB exit')
    a = q['State']('bb_ALL_tail_types'); p = w['base'](a, 0xBB)
    p.add(Or(fa(a), a3(a)))
    b = execute(a, p, 0xBB, 'bb_ALL_tail_types')
    w['prove'](p, And(w['ip'](b) == 0xBC, Or(b.r[34] == 3, b.r[34] == 15),
        b.r[31] == a.r[34], eq(b.r[1:42:3], [*a.r[4:42:3], a.r[1]])),
        'ALL real-source BB entries: after full14 rotation byte-high is3 orF')
    print('PASS GLOBAL ALL BB-origin BC immediate numeric-byte interface '
          'is bounded by30..3F OR F0..FF (AT MOST32 values, not a native '
          'coverage claim). BC does not alter this numericB pair. '
          'Other payload tetras, adapters after BC, full-word encodings '
          'and non-BC writers are NOT bounded by this byte theorem.', flush=True)


def final_byte_bound():
    a = q['State']('bc_global_immediate_byte'); p = w['base'](a, 0xBC)
    p.add(Or(a.r[34] == 3, a.r[34] == 15))
    b = execute(a, p, 0xBC, 'bc_global_immediate_byte')
    w['prove'](p, And(b.r[31] == a.r[31], b.r[34] == a.r[34]),
        'ALL ORIGINAL BC holds the proven3/F-high numeric-byte pair')
    for value in (0x00, 0x12, 0x3B, 0x3C, 0xA3, 0xF0, 0xFF):
        p.push(); p.add(w['byte'](a.r[31], a.r[34]) == value)
        outcome = p.check(); p.pop()
        assert outcome == (sat if value >> 4 in (3, 15) else unsat)
    print('PASS abstract-bound nonempty/negative controls:3B/3C/F0/FF '
          'compatible;00/12/A3 excluded at this immediate interface. '
          'Compatible values are NOT native Ms-bytes or key recipes.', flush=True)


def verify_native54_boundary():
    # Fully rerun the previous joined proof; a positive partial path or
    # an assumed type3 exclusion is not used as a substitute for it.
    zero = highkind['all_high_kind_zero07_sources']()
    highkind['nonzero07_high_kind_sources'](zero)
    highkind['initial28_high_kind_flag']()
    highkind['exclude_four_conditional_bb_packets']()
    native54['complete_callers']()
    native54['exclude_false_b3_callers']()
    native54['module_low_flag_packets']()
    native54['all65_to7b_packets']()
    native54['all8b_type3_flags']()
    native54['independent60_type3_flags']()
    native54['complete54_gate_induction']()


if __name__ == '__main__':
    r['inlet']['immutable_reference']()
    complete_writer_callers()
    checked_dependency('ALL46648/23054 joined native TYPE3/flag exclusion',
                       verify_native54_boundary)
    resolver_no_direct_c()
    physical8a_data_packets()
    other65_data_packets()
    join_all8b_packets()
    independent60_no_direct_c()
    no_native_b3_to_bc()
    all_bb_tail_provenance()
    final_byte_bound()
    r['inlet']['immutable_reference']()
    print('PASS joined BC source audit. No native/live/ALL5/key-search '
          'experiment, state/IP/return/ROM repair or general partialK2 '
          'impossibility claim.', flush=True)
