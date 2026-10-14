#!/usr/bin/env python3
"""Word-level composition, not a new microcode or whole-keyboard theorem.

Native tests establish each 48-tetra rotation, 12-tetra copy, guarded prime
and tail-preserving exit. Here arbitrary 48-bit words check the resulting
data flow through three separately entered readers.
"""
from z3 import And, BitVec, BitVecVal, Bool, If, Solver, sat, unsat

original = [BitVec('upper_' + str(i), 48) for i in range(4)]
guard = BitVecVal(int('958912345678', 16), 48)
words = original[:]
copies = [words[0]]
for i in range(3):
    # Guard replaces only the top, whose source was already copied (or is
    # disposable). Native IK1303 then rotates all four full numeric words.
    words[0] = guard
    words = words[1:] + words[:1]
    copies.append(words[0])
    # The later formatter may keep the read value or replace it with guard.
    # The native trace separately checks that it cannot alter the tail.
    words[0] = If(Bool('formatter_keeps_source_' + str(i)), words[0], guard)

s = Solver()
assert s.check() == sat
s.add(~And(*[x == y for x, y in zip(copies, original)]))
assert s.check() == unsat
print('PASS: three guarded four-word rotations/copies recover all four arbitrary 48-bit originals, for either allowed formatter result at every exit.')
print('LIMIT: compositional word algebra; concrete native entries, services, ordinary-register lifetimes and exits remain test obligations.')
