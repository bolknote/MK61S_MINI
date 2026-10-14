#!/usr/bin/env python3
"""Joint high-kind/type/flag source theorem for initial ORIGINAL28.

High kinds8..F include the four CONDITIONAL A/C limitedBB inlets. The
previous odd-kind-only theorem is not silently applied to even kinds.
The flag-coloured type bound closes the real2C swap loophole: high type
can grow through77, but77 itself clears the flag. No native/key/hardware
experiment, reference mutation, free return or physical exchange claim.
"""
from pathlib import Path
import runpy

from z3 import And, Extract, Implies, Not, Or, UGE, ULE, unsat

root = Path(__file__).resolve().parent
loops = runpy.run_path(str(root / 'cache-bc-decoder-loop-cut.py'))
basis, inlet = loops['basis'], loops['inlet']
r, w, q, states, edges, walk, execute = (loops[n] for n in
    ('r', 'w', 'q', 'states', 'edges', 'walk', 'execute'))
old = basis['old']
wanted = lambda a: UGE(a.r[35], 8)
high = lambda a: And(wanted(a), UGE(a.r[23], 3))
low_flag = lambda a: ULE(a.r[23], 2)
shape = lambda a: a.r[38] == a.r[35]+8
origin = lambda a: Implies(wanted(a), Or(low_flag(a), shape(a)))
even = lambda a: Extract(0, 0, a.r[32]) == 0
safe = lambda a: Implies(high(a), a.r[26] != 0)


def actual_onef_sources():
    # Coverage was checked by basis.zero07_cut(): selected1F has onlyA5,
    # thoseA5 onlyAB/AD. Re-prove the numeric contract for ALL high kinds,
    # rather than borrowing its earlier9/B-only conclusion.
    for code in (0xAB, 0xAD):
        label = f'high_kind_actual_1F_source_{code:02X}'
        a = q['State'](label); p = w['base'](a, code)
        b = execute(a, p, code, label); p.add(w['ip'](b) == 0xA5)
        b = walk(b, p, (0xA5,), label+'_A5')
        w['prove'](p, And(w['ip'](b) == 0x1F,
            Implies(wanted(b), And(b.r[26] == 15, UGE(b.s1, 7))),
            Implies(b.r[26] == 0, b.r[35] == 5)),
            f'ALL ORIGINAL{code:02X}/A5: high kinds8..F require counterF/S1>=7')


def zero_invariant(a, code):
    if code == 0x1F:
        return Implies(wanted(a), And(a.r[26] == 15, UGE(a.s1, 7)))
    if code == 0x1C: return safe(a)
    if code == 0x12: return Not(wanted(a))
    if code == 0xA3: return basis['correlation'](a)
    if code == 0x77: return And()
    if code in (0x22, 0x36, 0x37, 0x38, 0x55, 6):
        return Implies(high(a), Or(a.r[26] != 0, basis['before_increment'](a)))
    if code in (7, 0x6D):
        return Implies(high(a), Or(a.r[26] != 0, basis['dead_before'](a)))
    if code == 0x6F:
        return And(a.r[26] == 0, a.s1 == 14, Implies(high(a), basis['dead_before'](a)))
    if code == 0x6E: return Implies(high(a), basis['dead_before'](a))
    if code == 0x61: return Implies(high(a), basis['dead_after'](a))
    if code == 0x3A: return Not(high(a))
    return safe(a)


def all_high_kind_zero07_sources():
    region, counts, pairs = basis['zero07_cut']()
    basis['a3_diagonal_provenance']()
    basis['onef_native_sources'](region)  # verifies caller/zero-kind5 coverage
    actual_onef_sources()
    for code in sorted(counts):
        if code == 0x62: continue  # expanded together with its ONLY6F caller
        label = f'high_kind_zero07_{code:02X}'
        a = q['State'](label); p = w['base'](a, code); p.add(zero_invariant(a, code))
        b = execute(a, p, code, label)
        if code == 0x6F:
            w['prove'](p, w['ip'](b) == 0x62, 'ORIGINAL6F forces62', False)
            b = execute(b, p, 0x62, label+'_62'); destinations = [0x6E]
        else: destinations = sorted({dst for first, dst in pairs if first == code})
        w['prove'](p, And(*[Implies(w['ip'](b) == dst, zero_invariant(b, dst))
                           for dst in destinations]),
            f'ALL ORIGINAL{code:02X} preserves COMPLETE658/822 HIGH-kind source invariant')
    print('PASS GLOBAL selected zero07/high kinds8..F + flag>=3: only30/60; '
          'selected6E carries30/60 and61 cannot return3A with27/57. '
          'This includes A/C, not just the old9/B kinds.', flush=True)
    return region


def high_kind_origin_invariant(a, code):
    typ, f = a.r[32], a.r[26] == 15
    if code == 0x1F: packet = And()
    elif code == 0x1C: packet = shape(a)
    elif code == 0x6E: packet = Or(origin(a), basis['dead_before'](a))
    elif code == 0x61: packet = Or(origin(a), basis['dead_after'](a))
    elif code in (0x3A, 0x27, 0x38): packet = origin(a)
    elif code in (6, 7):
        packet = And(origin(a), Or(And(typ == 0, a.r[29] == 0), a.r[38] == 8))
    elif code in (0x6D, 0x60):
        packet = And(origin(a), Or(even(a), a.r[38] == 8))
    elif code == 0x77: packet = And(even(a), a.r[35] == 7)
    elif code == 0x1A: packet = And(typ == 0, shape(a))
    elif code in (0x18, 0x1B, 0x1D):
        parity = (Or(Extract(0, 0, typ) == 1, And(f, Or(typ == 0, typ == 2)))
                  if code == 0x1B else Or(even(a), And(f,
                      typ == 1 if code == 0x18 else Or(typ == 1, typ == 3))))
        packet = And(parity, Implies(wanted(a), Or(low_flag(a), And(f, shape(a)))))
    elif code == 0x2D: packet = And(typ == 2, shape(a))
    elif code == 0x2C: packet = And(Or(even(a), typ == 1, typ == 3), origin(a))
    else: packet = And(Implies(a.r[35] == 7, even(a)), Implies(wanted(a), low_flag(a)))

    # Essential NEW joint premise. Parity alone allows2C to import A/C
    # as the old even type. Such a high type is not allowed with a high
    # flag: the77 producer has already erased it. These bounds are
    # established by the real1F/1C/07/77 words and preserved below.
    type_bound = And()
    if code in (0x6D, 0x60): type_bound = Or(typ == 0, a.r[38] == 8)
    if code in (0x18, 0x1B, 0x1D, 0x2C):
        type_bound = ULE(typ, {0x18: 1, 0x1B: 2, 0x1D: 3, 0x2C: 3}[code])
    return And(packet, Implies(UGE(a.r[23], 3), type_bound))


def nonzero07_high_kind_sources(zero_region):
    region, counts, pairs = old['source_cut']()
    assert {i for i in region if states[i][0] == 0x6E} == {
        i for i in zero_region if states[i][0] == 0x6E}
    old['all_1c_selector_provenance']()
    for code in sorted(counts):
        label = f'high_kind_nonzero07_{code:02X}'
        a = q['State'](label); p = w['base'](a, code)
        p.add(high_kind_origin_invariant(a, code))
        if code in (0x1F, 0x1A): p.add(a.r[26] == 15)
        b = execute(a, p, code, label)
        destinations = sorted({dst for first, dst in pairs if first == code})
        w['prove'](p, And(*[Implies(w['ip'](b) == dst, high_kind_origin_invariant(b, dst))
                           for dst in destinations]),
            f'ALL ORIGINAL{code:02X} preserves COMPLETE1345/1702 HIGH-kind flag/type source')
    print('PASS GLOBAL selected nonzero07/high kinds8..F + flag>=3: '
          'selector=kind+8. The needed selector9/A cannot carry such a '
          'high kind/flag packet. No broad all-07/all-mode claim.', flush=True)


def initial28_high_kind_flag():
    counts, pairs = inlet['source_cut']()
    targets = {i for i, a in enumerate(states) if a[0] == 0x28
        and (a[7] is None or any(v != 0 for v in a[7]))}
    region = basis['backward'](targets, {7, 0x1F, 0x1C})
    native07 = {i for i, a in enumerate(states) if a[0] == 7
        and (a[5] is None or set(a[5]) & {9, 10})
        and (a[7] is None or any(v != 0 for v in a[7]))}
    assert {i for i in region if states[i][0] == 7} == native07
    assert len(region) == 1213 and len(counts) == 33
    for code in sorted(counts):
        label = f'high_kind_first28_{code:02X}'
        a = q['State'](label); p = w['base'](a, code)
        p.add(high_kind_origin_invariant(a, code))
        if code in (0x1F, 0x1A): p.add(a.r[26] == 15)
        b = execute(a, p, code, label)
        destinations = sorted({dst for first, dst in pairs if first == code})
        w['prove'](p, And(*[Implies(w['ip'](b) == dst, high_kind_origin_invariant(b, dst))
                           for dst in destinations]),
            f'ALL ORIGINAL{code:02X} preserves COMPLETE1213/1525 HIGH-kind flag source')
    print('PASS GLOBAL ALL53 initial nonzero28: kind8..F impliesR23<=2. '
          'The even A/C loophole is closed by the joint high-flag/type '
          'bound, NOT by assuming all types are low or all flags zero.', flush=True)


def exclude_four_conditional_bb_packets():
    for kind in (10, 12):
        for mode in (10, 11):
            a = q['State'](f'high_kind_limitedBB_excluded_{kind:X}_{mode:X}')
            p = w['base'](a, 0x28)
            p.add(high_kind_origin_invariant(a, 0x28), a.r[35] == kind,
                a.r[32] == 0, a.r[29] == 0, a.r[2] == mode,
                a.r[26] != 0, UGE(a.r[23], 3))
            if kind == 12: p.add(a.r[33] != 0)
            assert p.check() == unsat
    print('PASS ALL FOUR A/C × modesA/B conditional limitedBB packets '
          'UNSAT under the proved native source invariant. Their positive '
          'ROM component contracts remain valid OUTSIDE native entry. '
          'Direct low-flagBB/77-B and other48 sources remain outside '
          'this exclusion; no general partialK2 impossibility theorem.', flush=True)


if __name__ == '__main__':
    r['inlet']['immutable_reference']()
    zero_region = all_high_kind_zero07_sources()
    nonzero07_high_kind_sources(zero_region)
    initial28_high_kind_flag()
    exclude_four_conditional_bb_packets()
    r['inlet']['immutable_reference']()
    print('PASS source-driven high-kind flag/type audit. No key search, '
          'native/live/ALL5 experiment, source/ROM/state/return repair '
          'or general partialK2 impossibility claim.', flush=True)
