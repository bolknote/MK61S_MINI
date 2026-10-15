#!/usr/bin/env python3
"""Original 9C's exact control-header predicate; no entry/reachability claim."""
import runpy
from pathlib import Path
from z3 import And, BitVecVal, If, UGE, ZeroExt, sat, unsat

q = runpy.run_path(str(Path(__file__).with_name('ik1302_symbolic.py')))
a = q['State']('writer_ready_control')
solver = q['base_solver'](a, 0x9C)
out = []
b = q['execute_command'](a, 0x9C, *q['arbitrary_keys']('ready_keys'), emitted_outputs=out)
address = lambda s: ZeroExt(4, s.r[36]) | (ZeroExt(4, s.r[39]) << 4)
accept = If(a.m[31] == 15, UGE(a.m[34], 1), UGE(a.m[34], 7))
claim = And(address(b) == If(accept, BitVecVal(0x9E, 8), BitVecVal(0x9D, 8)),
            *[x == y for x, y in zip(out, a.m)])
assert solver.check() == sat
solver.add(~claim)
assert solver.check() == unsat
print('PASS 9C: accepts iff (M31=F and M34>=1) or (M31!=F and M34>=7); '
      'all 42 ring outputs held, arbitrary other state/keys/serial input.')
print('CONSEQUENCE: original 0xx rejected; the produced 1Fx reply accepted. '
      'Keyboard scan phase and subsequent writer are separate obligations.')
