#!/usr/bin/env python3
"""Counter detour and the L0/A3 candidates: exact local ROM proofs, not a hack."""
import json
import runpy
import subprocess
from pathlib import Path

from z3 import And, BitVecVal, If, UGE, ULT, ZeroExt, sat, unsat

ROOT = Path(__file__).resolve().parent
q = runpy.run_path(str(ROOT / 'ik1302_symbolic.py'))
State, execute, base, keys = (q[n] for n in
    ('State', 'execute_command', 'base_solver', 'arbitrary_keys'))


def byte(lo, hi):
    return ZeroExt(4, lo) | (ZeroExt(4, hi) << 4)


facts = 0
paths = 0


def prove(ip, label, claim):
    global facts
    a = State(f'counter_fact_{facts}')
    b = execute(a, ip, *keys(f'counter_keys_{facts}'))
    p = base(a, ip)
    p.add(~claim(a, b))
    assert p.check() == unsat, label
    facts += 1
    print('PASS:', label, flush=True)


prove(0x07, '07 enters 6D iff unsigned R2 >= 5',
      lambda a, b: (byte(b.r[36], b.r[39]) == 0x6D) == UGE(a.r[2], 5))
prove(0x61, '61 enters 3A iff unsigned R34 >= C',
      lambda a, b: (byte(b.r[36], b.r[39]) == 0x3A) == UGE(a.r[34], 12))
prove(0x28, '28 enters 7E iff R26 is nonzero',
      lambda a, b: (byte(b.r[36], b.r[39]) == 0x7E) == (a.r[26] != 0))
prove(0x06, '06 increments the two-nibble counter with decimal low-digit carry',
      lambda a, b: And(
          b.r[31] == If(ULT(a.r[31], 9), a.r[31] + 1, a.r[31] + 7),
          b.r[34] == a.r[34] + If(ULT(a.r[31], 9), BitVecVal(0, 4), BitVecVal(1, 4))))
prove(0x6E, '6E subtracts three with decimal low-digit borrow',
      lambda a, b: And(
          b.r[31] == If(ULT(a.r[31], 3), a.r[31] + 7, a.r[31] - 3),
          b.r[34] == a.r[34] - If(ULT(a.r[31], 3), BitVecVal(1, 4), BitVecVal(0, 4))))
prove(0xAD, 'AD sets R41 to F', lambda a, b: b.r[41] == 15)
prove(0xE5, 'E5 leaves S = R41 + C, modulo 16',
      lambda a, b: b.s == a.r[41] + 12)

preserving = [0x09, 0x99, 0x9B, 0x9C, 0x9E, 0x9F, 0xAA, 0xE5,
              0xE6, 0xED, 0xEE,
              0xAB, 0xAD, 0xA5, 0x1F, 0x1D, 0x2E, 0x01, 0x02,
              0x03, 0x04, 0xBA, 0xCB, 0xDD, 0xD6, 0x2F, 0x20,
              0x21, 0x22, 0x36, 0x37, 0x38, 0x06]
for ip in preserving:
    prove(ip, f'{ip:02X} preserves the R2 discriminator on the tested L0 route',
          lambda a, b: b.r[2] == a.r[2])
for ip in (0x01, 0x02, 0x2F, 0x20):
    prove(ip, f'{ip:02X} preserves R26 across L0 wait/normalization repetitions',
          lambda a, b: b.r[26] == a.r[26])


def path(text, label, no_keys=False):
    sequence = [int(x, 16) for x in text.split()]
    a = State(label)
    b = a
    p = base(a, sequence[0])
    states = [b]
    for n, (ip, nxt) in enumerate(zip(sequence, sequence[1:])):
        signals = (0, 0) if no_keys else keys(f'{label}_keys_{n}')
        b = execute(b, ip, *signals)
        p.add(byte(b.r[36], b.r[39]) == nxt)
        states.append(b)
    return a, b, p, states


def path_fact(text, label, claim):
    global paths
    a, b, p, _ = path(text, f'counter_path_{paths}')
    assert p.check() == sat, f'{label}: vacuous path'
    p.add(~claim(a, b))
    assert p.check() == unsat, label
    paths += 1
    print('PASS:', label, flush=True)


path_fact('6F 62 6E', '6F->62 aligns R25/R31 and sets R26 from old R4+1',
          lambda a, b: And(b.r[25] == a.r[31], b.r[31] == a.r[31],
                           b.r[34] == a.r[34], b.r[26] == a.r[4] + 1,
                           b.r[38] == a.r[38]))
path_fact('E5 E6 E9', 'E5->E6 leaves R38 = old R41+D, modulo 16',
          lambda a, b: b.r[38] == a.r[41] + 13)
path_fact('AD A5 1F 1D 2E 01 02 03 04 BA CB DD D6 2F 21 22 36 37 '
          '25 01 02 03 04 BA CB DD D4 26 28',
          'the nonzero L0 counter write leaves R26=0 at 28, blocking 7E',
          lambda a, b: And(b.r[26] == 0, b.r[35] == 5))

L0_PREFIX = 'AB AD A5 1F 1D 2E 01 02 03 04 BA CB DD D6 2F 21 22 36 37 38 06 07'
L0_DETOUR = L0_PREFIX + ' 6D 6F 62 6E ' + '61 3A 06 07 6D 60 ' * 3 + 'C8'
a, b, p, _ = path(L0_DETOUR, 'artificial_l0', no_keys=True)
assert p.check() == sat
print('PASS: three-iteration L0 candidate is SAT with arbitrary initial state/ring; '
      'this is NOT a keyboard protocol', flush=True)
paths += 1
p.push()
p.add(a.r[2] == 0)
assert p.check() == unsat
p.pop()
print('PASS: initial R2=0 alone excludes that L0 candidate with released keys', flush=True)
paths += 1

# All commands on this shorter route preserve R2, including repeated 01/02/2F/20.
# Thus this negative check is not dependent on the actual ring wait length.
a, b, p, _ = path(L0_PREFIX + ' 6D', 'l0_arbitrary_keys')
p.add(a.r[2] == 0)
assert p.check() == unsat
print('PASS: R2=0 excludes the L0 exit 07->6D even with arbitrary tick-level keys', flush=True)
paths += 1

# The program-fetch route itself establishes the opposite discriminator at
# its first 07. Every command between the two tests preserves R2, so repetitions
# of the observed wait/normalization loops cannot change this contradiction.
FETCH_PREFIX = '07 09 99 9B 9C 9E 9F AA E5 E6 ED EE '
a, b, p, _ = path(FETCH_PREFIX + L0_PREFIX, 'l0_fetch_discriminator')
assert p.check() == sat, 'ordinary L0 fetch/completion route must be feasible'
p.add(UGE(b.r[2], 5))
assert p.check() == unsat
print('PASS: ordinary program fetch through 07->09 and this L0 completion '
      'cannot change R2<5 into R2>=5', flush=True)
paths += 1

# Obtain a real starting state using only keys, then leave all FUTURE ring/key
# signals arbitrary. No host-written calculator state is used in this test.
report = json.loads(subprocess.check_output(
    ['node', str(ROOT / 'probe_l0_keyboard.cjs'), '--one', '--json'], text=True))
assert report['snapshot'] is not None
a, b, p, _ = path(L0_DETOUR, 'frozen_keyboard_l0')
for group in ('r', 'm', 'st'):
    p.add(*[v == n for v, n in zip(getattr(a, group), report['snapshot'][group])])
for name in ('s', 's1', 'l', 't', 'carry'):
    p.add(getattr(a, name) == report['snapshot'][name])
assert p.check() == unsat
print('PASS: actual keyboard-prepared L0 chip state cannot follow the candidate '
      'even with arbitrary future ring/key signals', flush=True)
paths += 1

A3_PREFIX = 'E6 E9 AD A9 93 94 95 98 9A E5 E6 E9 AD A3 77'
path_fact(A3_PREFIX, 'the tested A3->77 restoration fixes counter 79 and R38=C',
          lambda a, b: And(b.r[31] == 9, b.r[34] == 7, b.r[38] == 12,
                           b.r[26] == 0))
path_fact(A3_PREFIX + ' 6D 6F 62 6E 61',
          'that A3 detour arrives at 61 with counter 76, R25=9 and R38=C',
          lambda a, b: And(b.r[31] == 6, b.r[34] == 7, b.r[25] == 9,
                           b.r[38] == 12))
a, b, p, _ = path(A3_PREFIX + ' 6D 6F 62 6E 61 3A', 'false_a3_detour')
assert p.check() == unsat
print('PASS: that A3->77 detour cannot take 61->3A', flush=True)
paths += 1
print(f'PASS: {facts} one-command counter/mode facts and {paths} path checks', flush=True)
