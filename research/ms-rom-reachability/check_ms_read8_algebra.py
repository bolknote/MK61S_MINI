#!/usr/bin/env python3
"""Conditional composition of the native-tested eight-word contracts.

All numeric words below are arbitrary 48-bit values. The native entry
conditions are assumptions of these word-level primitives, not proved by
this model. In particular this is NOT an all-bit-pattern keyboard theorem.
Unneeded lower side effects and the reader's retained top are left free.
"""
from z3 import And, BitVec, BitVecVal, Bool, If, Not, Or, Solver, sat, unsat

original = [BitVec('ms_' + n, 48) for n in ('u', 'v', 'w', 'q', 'a', 'b', 'c', 'd')]
zero = BitVecVal(0, 48)
guard = BitVecVal(int('958912345678', 16), 48)
marker = BitVecVal(int('0000F0000000', 16), 48)


def protocol(skip_reader_bridge=False, skip_writer_bridge=False):
    u, v, w, q, a, b, c, d = original
    lower, upper = original[:4], original[4:]
    regs = {i: BitVec('old_reg_' + str(i), 48) for i in range(15)}
    q_reads = 0
    q_entry_u = []

    def push():
        nonlocal lower
        assert str(regs[3]) == str(zero)
        lower = [regs[9]] + lower[:3]

    def park():
        push()
        regs[9] = zero
        push()

    def read_q():
        nonlocal lower, q_reads
        assert str(regs[3]) == str(zero)
        q_entry_u.append(lower[0])
        regs[9] = lower[3]
        lower = [BitVec('q_read_%d_lower_%d' % (q_reads, i), 48) for i in range(4)]
        q_reads += 1

    def read_upper(i):
        nonlocal lower, upper
        assert str(regs[3]) == str(zero)
        assert str(lower[0]) == str(zero)
        # E backup in P9; A temporarily carries the marker, then the copy.
        regs[9], old_e = regs[14], regs[14]
        regs[14], regs[10] = BitVecVal(2, 48), marker
        if i == 0:
            regs[8] = upper[0]
        seed = zero if i == 0 else regs[8]
        captured = upper[1]
        lower = [If(Bool('reader_%d_U_is_zero' % i), zero, seed), guard,
                 BitVec('reader_%d_damaged_W' % i, 48), lower[1]]
        upper = [BitVec('reader_%d_unused_top' % i, 48), upper[2], upper[3], guard]
        for index in (0, 5, 7, 12):
            regs[index] = BitVec('reader_%d_scratch_%d' % (i, index), 48)
        regs[2], regs[4], regs[10], regs[14] = marker, guard, captured, old_e

    def write_upper(index):
        nonlocal lower, upper
        assert index in (8, 10, 14)
        assert str(lower[0]) == str(zero)
        source = regs[index]
        upper = [source] + upper[:3]
        lower = [regs[8], guard, lower[0], lower[1]]
        # P6 alone is the source pointer. D/E never become scratch.
        for scratch in (0, 2, 4, 5, 6, 7, 9, 12):
            regs[scratch] = BitVec('writer_%d_scratch_%d' % (index, scratch), 48)
        regs[0] = zero

    def save_p3():
        regs[7], regs[3] = regs[3], zero

    def bridge():
        save_p3()
        read_q()
        park()
        regs[3] = regs[7]

    # Lower-four read/restore contract followed by native ordinary copies.
    regs[3] = zero
    regs[1], regs[6], regs[11], regs[13] = u, v, w, q
    regs[9] = zero
    push()
    read_upper(0)
    regs[9] = regs[8]
    park()
    regs[8] = regs[10]
    read_upper(1)
    regs[14] = regs[10]
    if skip_reader_bridge:
        # Still clean U for the third reader, but discard the Q->V copy.
        lower[0] = zero
    else:
        read_q()
        park()
    read_upper(2)
    read_q()
    regs[12] = regs[9]
    handoff = [regs[i] for i in (1, 6, 11, 13, 12, 8, 14, 10)]

    regs[3] = regs[6]
    save_p3()
    regs[9] = regs[12]
    park()
    regs[3] = regs[7]
    for index in (10, 14, 8):
        write_upper(index)
        if index != 8:
            if skip_writer_bridge and index == 14:
                # U cleanup alone cannot replace the Q->V buffer move.
                lower[0] = zero
            else:
                bridge()
    save_p3()
    read_q()
    regs[12] = regs[9]
    regs[9] = regs[10]
    park()
    regs[10] = regs[12]
    regs[3] = regs[7]
    write_upper(10)
    save_p3()
    read_q()
    regs[6] = regs[9]
    regs[5] = regs[7]
    for index in (13, 11, 5, 1):
        regs[9] = regs[index]
        push()
    copies = [regs[i] for i in (1, 5, 11, 13, 10, 8, 14, 6)]
    return handoff, lower + upper, copies, q_entry_u


def prove(expressions):
    p = Solver()
    assert p.check() == sat
    p.add(Not(And(*expressions)))
    result = p.check()
    assert result == unsat, p.model() if result == sat else result


handoff, restored, copies, entries = protocol()
prove([x == y for collection in (handoff, restored, copies) for x, y in zip(collection, original)])
print('PASS: eight simultaneous readouts at handoff; eight words restored; all eight final copies, independent of unused lower side effects.')
assert len(entries) == 6
prove([Or(x == zero, x == original[5]) for x in entries])
print('PASS: every new Q-reader entry has U=0 or original b, assuming the corrected late-zero reader contract; b must satisfy the native entry domain.')

for option in ('skip_reader_bridge', 'skip_writer_bridge'):
    handoff, restored, copies, _ = protocol(**{option: True})
    expected = original[:4] + [guard] + original[5:]
    prove([x == y for collection in (restored, copies) for x, y in zip(collection, expected)])
    if option == 'skip_reader_bridge':
        prove([x == y for x, y in zip(handoff, expected)])
    else:
        prove([x == y for x, y in zip(handoff, original)])
    print('PASS negative formula:', option, 'loses a to the guard, despite preserving the other seven words.')
print('LIMIT: conditional allocation algebra; not universal numeric entry, physical validation, or exchange with the original ordinary bank.')
