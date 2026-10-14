#!/usr/bin/env python3
"""Conditional word-level proof of the new allocation and V/Q buffer.

The native tests establish the contracts of the reader, pure upper push,
lower push and secondary Q read. This model composes those contracts for
arbitrary 48-bit words; it does not prove native reachability or timings.
"""
from z3 import And, BitVec, BitVecVal, Bool, If, Not, Solver, sat, unsat

original = [BitVec('original_' + str(i), 48) for i in range(4)]
zero = BitVecVal(0, 48)
guard = BitVecVal(int('958912345678', 16), 48)


def protocol(skip_bridge=False, reverse_first_two=False):
    # The separately checked reader's handoff. Lower Ms is already scratch.
    a, b, c, d = original
    upper = [If(Bool('reader_keeps_d'), d, guard), guard, guard, guard]
    lower = [BitVec('reader_lower_' + str(i), 48) for i in range(4)]
    regs = {'1': a, '6': b, 'B': c, 'A': d, '3': zero}
    reader_number = 0

    def lower_push(source):
        nonlocal lower
        lower = [source] + lower[:3]

    def upper_push(source_reg):
        nonlocal lower, upper
        # Only A/B sources are used; P6 and E are consumed by scratch setup.
        assert source_reg in ('A', 'B')
        regs['6'] = BitVecVal(2 if source_reg == 'A' else 3, 48)
        regs['E'] = BitVecVal(2, 48)
        upper = [regs[source_reg]] + upper[:3]
        lower = [zero, guard, lower[0], lower[1]]

    def read_q():
        nonlocal lower, reader_number
        # Exact numeric Q read, P9 output; lower side effects are deliberately
        # unconstrained here because this protocol never relies on them.
        assert str(regs['3']) == str(zero)
        regs['9'] = lower[3]
        lower = [BitVec(f'q_reader_{reader_number}_lower_{i}', 48) for i in range(4)]
        reader_number += 1

    lower_push(zero)  # Explicit U cleanup after the final upper reader.
    regs['3'] = regs['6']
    for source in (('B', 'A') if reverse_first_two else ('A', 'B')):
        upper_push(source)

    # Park d before A is reused for b. P3 is zero only while b lives in E.
    regs['E'], regs['3'] = regs['3'], zero
    regs['9'] = regs['A']
    lower_push(regs['9'])
    regs['9'] = zero
    lower_push(regs['9'])
    regs['3'] = regs['E']
    regs['A'] = regs['3']
    upper_push('A')  # d: V -> Q; upper now (b,c,d,s).

    if not skip_bridge:
        regs['E'], regs['3'] = regs['3'], zero
        read_q()
        lower_push(regs['9'])
        regs['9'] = zero
        lower_push(regs['9'])  # d back in V, U=0.
        regs['3'] = regs['E']

    regs['A'] = regs['1']
    upper_push('A')  # upper restored; d travels V -> Q once more.
    regs['E'], regs['3'] = regs['3'], zero
    read_q()
    regs['6'] = regs['9']
    regs['9'] = zero
    for _ in range(4):
        lower_push(regs['9'])
    regs['3'] = regs['E']
    return upper, lower, [regs[k] for k in ('1', '3', 'B', '6')]


def prove(expressions):
    solver = Solver()
    assert solver.check() == sat
    solver.add(Not(And(*expressions)))
    assert solver.check() == unsat


upper, lower, copies = protocol()
prove([x == y for x, y in zip(upper, original)]
      + [x == y for x, y in zip(copies, original)]
      + [x == zero for x in lower])
print('PASS: arbitrary four upper words are restored and retained in P1/P3/B/P6; lower half is zero, independent of allowed reader side effects.')

upper, lower, copies = protocol(skip_bridge=True)
prove([x == y for x, y in zip(upper, original)]
      + [x == y for x, y in zip(copies[:3], original[:3])]
      + [copies[3] == guard] + [x == zero for x in lower])
print('PASS negative formula: skipping the V/Q bridge restores upper Ms but loses the fourth retained copy to the guard.')

upper, lower, copies = protocol(reverse_first_two=True)
prove([x == y for x, y in zip(upper, [original[i] for i in (0, 1, 3, 2)])]
      + [x == y for x, y in zip(copies, original)]
      + [x == zero for x in lower])
print('PASS negative formula: reversing the first two writes preserves readouts but swaps the restored upper tail.')
print('LIMIT: word-level composition of native-tested contracts, not a whole-ROM theorem, physical validation or eight-word K1.')
