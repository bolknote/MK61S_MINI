#!/usr/bin/env python3
"""Exclude the direct 48/4A/4C keyboard prefix of the mode07 candidate.

This is a local, reset-independent data-flow proof with arbitrary keys and
ring inputs. It covers any number of 9B waits, not all routes through 4B.
All addresses and fields belong to the internal IK1302 machine.
"""
import runpy
from pathlib import Path

from z3 import And, Or, UGE, ULT, ZeroExt, sat, unsat

q = runpy.run_path(str(Path(__file__).with_name('ik1302_symbolic.py')))
State, execute, base, keys = (q[n] for n in
    ('State', 'execute_command', 'base_solver', 'arbitrary_keys'))


def address(a):
    return ZeroExt(4, a.r[36]) | (ZeroExt(4, a.r[39]) << 4)


count = 0


def prove(ip, label, claim, condition=None):
    global count
    a = State(f'decode_{ip}')
    b = execute(a, ip, *keys(f'decode_keys_{ip}'))
    p = base(a, ip)
    if condition is not None:
        p.add(condition(a))
    assert p.check() == sat, ('empty precondition', label)
    p.add(~claim(a, b))
    assert p.check() == unsat, label
    count += 1
    print('PASS:', label, flush=True)


prove(0x48, '48 enters 4A iff R32<4, without changing R32/R35',
      lambda a, b: And((address(b) == 0x4A) == ULT(a.r[32], 4),
                       b.r[32] == a.r[32], b.r[35] == a.r[35]))
prove(0x4A, '4A swaps R32/R35; its direct 4C exit tests R23=0',
      lambda a, b: And(b.r[32] == a.r[35], b.r[35] == a.r[32],
                       (address(b) == 0x4C) == (a.r[23] == 0)))
prove(0x4C, '4C swaps R32/R35 back and enters 4E',
      lambda a, b: And(b.r[32] == a.r[35], b.r[35] == a.r[32],
                       address(b) == 0x4E))
prove(0x4E, '4E copies R32 to opcode high nibble R33 and enters 97',
      lambda a, b: And(b.r[33] == a.r[32], address(b) == 0x97))
for ip in (0x97, 0x99, 0x9B, 0x9C, 0x9E):
    prove(ip, f'{ip:02X} preserves the opcode high nibble',
          lambda a, b: b.r[33] == a.r[33])
prove(0x9B, '9B only waits or enters 9C',
      lambda a, b: Or(address(b) == 0x9B, address(b) == 0x9C))
prove(0x9F, '9F requires opcode high nibble >=4 to enter AA',
      lambda a, b: And((address(b) == 0xAA) == UGE(a.r[33], 4),
                       b.r[33] == a.r[33]))

# Check that the prefix itself has models, so its exclusion is not based on
# an accidentally empty starting condition. Both possible R2 classes survive
# the prefix; the contradiction is in the opcode, not in the R2 mode gate.
a = State('decode_direct_prefix')
p = base(a, 0x48)
b = a
for index, (ip, nxt) in enumerate(zip((0x48, 0x4A, 0x4C), (0x4A, 0x4C, 0x4E))):
    b = execute(b, ip, *keys(f'decode_prefix_keys_{index}'))
    p.add(address(b) == nxt)
assert p.check() == sat, 'the direct prefix must be nonempty'
p.push()
p.add(UGE(b.r[32], 4))
assert p.check() == unsat, 'the double swap must preserve R32<4'
p.pop()
for condition in (ULT(a.r[2], 5), UGE(a.r[2], 5)):
    p.push()
    p.add(condition)
    assert p.check() == sat, 'both initial R2 classes must be possible'
    p.pop()
print(f'PASS: {count} local facts and a nonempty exact prefix: '
      '48->4A->4C->4E->97->99->9B*->9C->9E->9F cannot reach AA. '
      'This closes the third abstract mode07 candidate family, independent '
      'of reset and of 9B waiting duration; other 4B routes remain open.', flush=True)

# The keyboard prefix also preserves a mode value in R5. Treating each R2
# assignment as fresh input loses this save/restore pair. This statement is
# local: it does not prove the initial mode was zero or exclude other exits.
for ip in (0x7F, 0x8B):
    prove(ip, f'{ip:02X} exchanges R2/R5 exactly',
          lambda a, b: And(b.r[2] == a.r[5], b.r[5] == a.r[2]))
for ip in (0x33, 0x35, 0x45):
    prove(ip, f'{ip:02X} preserves both R2/R5 during keyboard scanning',
          lambda a, b: And(b.r[2] == a.r[2], b.r[5] == a.r[5]))
print('PASS: the 7F->33*->35*->45->8B family restores the R2 value from '
      'before 7F, for any number of 33/35 waits. The second exchange does '
      'not supply a fresh arbitrary mode nibble.', flush=True)
print(f'PASS: {count} one-command facts total', flush=True)
