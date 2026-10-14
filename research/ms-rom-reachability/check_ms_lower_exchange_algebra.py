#!/usr/bin/env python3
"""Conditional lifetime proof for P0..P3 <-> U/V/W/Q, not ROM reachability.

The U/V/W/Q-reader contracts and lower-push contract are premises. The Q
reader may damage any lower word; all four sources have been backed up.
Numeric 48-bit values are arbitrary in this model, but not necessarily
admissible inputs to the actual keyboard readers.
"""
from z3 import And, BitVec, BitVecVal, Not, Solver, sat, unsat

ms = [BitVec('ms_' + str(i), 48) for i in range(8)]
regs = [BitVec('reg_' + str(i), 48) for i in range(15)]
zero = BitVecVal(0, 48)


def exchange(m, r, skip_save=False, forward=False, suffix='first', secondary_w=False, u_guard=False):
    m, r = m[:], r[:]
    if not skip_save:
        r[14] = r[3]
    r[3] = zero
    for i in range(3):
        r[9] = m[i]
        r[10 + i] = r[9]
        if secondary_w and i == 2:
            # W's formatter may overwrite V only AFTER the independent V
            # backup. U/W/Q are unchanged, so Q is still available.
            m[1] = BitVec(suffix + '_w_formatter_v', 48)
    if u_guard:
        m[0] = zero
        m[1] = BitVec(suffix + '_guard_v', 48)
        r[13] = BitVecVal(0x0000F0000000, 48)
    r[9] = m[3]
    m[:4] = [BitVec(suffix + '_q_side_effect_' + str(i), 48) for i in range(4)]
    r[13] = r[9]
    for i in ([0, 1, 2, 14] if forward else [14, 2, 1, 0]):
        assert str(r[3]) == str(zero)
        r[9] = r[i]
        m[:4] = [r[9]] + m[:3]
    for i in range(4):
        r[i] = r[10 + i]
    return m, r


def prove(conditions):
    s = Solver()
    assert s.check() == sat
    s.add(Not(And(*conditions)))
    result = s.check()
    assert result == unsat, s.model() if result == sat else result


after_ms, after_regs = exchange(ms, regs)
expected_ms = regs[:4] + ms[4:]
expected_regs = ms[:4] + regs[4:9] + [regs[0]] + ms[:4] + [regs[3]]
prove([x == y for x, y in zip(after_ms + after_regs, expected_ms + expected_regs)])
print('PASS: four genuine two-way pairs; upper Ms and P4..P8 retained; all six scratch outputs explicit; Q-reader damage irrelevant.')
back_ms, back_regs = exchange(after_ms, after_regs, suffix='second')
prove([x == y for x, y in zip(back_ms + back_regs[:9], ms + regs[:9])])
print('PASS: two applications restore all 8 Ms words and P0..P8; no claim that scratch P9..E is restored.')
secondary_ms, secondary_regs = exchange(ms, regs, secondary_w=True)
prove([x == y for x, y in zip(secondary_ms + secondary_regs, expected_ms + expected_regs)])
print('PASS: secondary W may replace backed-up V by ANY 48-bit word; all four exchange outputs are still exact IF Q is read correctly.')
secondary_back_ms, secondary_back_regs = exchange(secondary_ms, secondary_regs, suffix='secondary_second', secondary_w=True)
prove([x == y for x, y in zip(secondary_back_ms + secondary_back_regs[:9], ms + regs[:9])])
print('PASS: the conditional secondary-W exchange is also an involution on all Ms and P0..P8, excluding scratch.')
guard_ms, guard_regs = exchange(ms, regs, secondary_w=True, u_guard=True)
prove([x == y for x, y in zip(guard_ms + guard_regs, expected_ms + expected_regs)])
guard_back_ms, guard_back_regs = exchange(guard_ms, guard_regs, suffix='guard_second', secondary_w=True, u_guard=True)
prove([x == y for x, y in zip(guard_back_ms + guard_back_regs[:9], ms + regs[:9])])
print('PASS: U=0, arbitrary replacement of backed-up V, and temporary D marker do not change either exchange bank; the guarded composition remains an involution IF its readers succeed.')
for option in ('skip_save', 'forward'):
    bad_ms, bad_regs = exchange(ms, regs, **{option: True})
    expected = regs[:3] + [regs[14]] if option == 'skip_save' else regs[:4][::-1]
    prove([x == y for x, y in zip(bad_ms[:4], expected)])
    prove([x == y for x, y in zip(bad_regs[:4], ms[:4])])
    solver = Solver()
    solver.add(Not(And(*[x == y for x, y in zip(bad_ms[:4], regs[:4])])))
    assert solver.check() == sat
    print('PASS negative formula:', option, 'can lose the intended outgoing bank despite all incoming copies being right.')
print('LIMIT: conditional word-allocation proof, NOT full K1, universal keyboard execution, or physical-device validation.')
