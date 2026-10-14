#!/usr/bin/env python3
"""The 60/18/1B/1D read bootstrap, its exact wait count, and counter gate.

Source coverage uses the independently completed first-entry A3 vector bound.
Combine it with analyze_read_bootstrap.py --check-invariants to exclude 2C
and the 1F/1A alternatives at R26=1. Positive paths remain artificial;
arbitrary initial chip/ring contents are not a keyboard protocol.
"""
import runpy
from pathlib import Path

from z3 import And, BitVec, BitVecVal, If, Or, UGE, ULE, ULT, sat, unsat

m = runpy.run_path(str(Path(__file__).with_name('analyze_dd_stack_lifetime.py')))
q = m['model']()
State, execute, base, keys = (q[n] for n in ('State', 'execute', 'base', 'keys'))
address, stack, byte = (m[n] for n in ('address', 'stack', 'byte'))

expected_sources = {0x1D: {0x1B, 0x1F}, 0x1B: {0x18, 0x1F},
                    0x18: {0x1A, 0x1F, 0x60}, 0x1A: {0x1F},
                    0x2C: {0x2D}, 0x2D: {0x1C}, 0x1C: {0x19, 0x1E, 0x1F}}
sources = {ip: set() for ip in expected_sources}
pushers = {ip: [] for ip in expected_sources}
templates = {}
for ip in range(256):
    a = State(f'bootstrap_source_{ip}')
    b = execute(a, ip, *keys(f'bootstrap_source_keys_{ip}'))
    p = base(a, ip)
    old, new = stack(a), stack(b)
    pushed = (ip & 0xF0) | ((ip+1) & 15)
    for kind, expected in [('same', old), ('rotate', old[1:]+old[:1]),
                           ('push', [pushed]+old[:2])]:
        p.push()
        p.add(~And(*[v == w for v, w in zip(new, expected)]))
        valid = p.check() == unsat
        p.pop()
        if valid:
            break
    else:
        raise AssertionError(('unclassified stack', ip))
    templates[ip] = a, b
    if kind == 'push' and pushed in pushers:
        pushers[pushed].append(ip)
    if ip in (0xC7, 0xC8):
        continue
    if ip == 0xA3:
        p.add(Or(a.r[37] == a.r[40], *[byte(a.r[37], a.r[40]) == n
                 for n in (0x90, 0x93, 0xCC, 0xD3, 0xD8)]))
    p.add(b.r[26] == 1)
    for target in sources:
        p.push()
        p.add(address(b) == target, *[v != target for v in old])
        result = p.check()
        assert result in (sat, unsat)
        if result == sat:
            sources[target].add(ip)
        p.pop()
assert sources == expected_sources, sources
assert pushers == {ip: ([0x2B] if ip == 0x2C else []) for ip in pushers}, pushers
print('PASS: 256 source/whole-stack checks. With R26=1, 1D/1B/18 can only '
      'come through the listed 1F/1A alternatives or 60; only 2B creates '
      'tag 2C. The completed reset projection excludes 2C and all those '
      '1F/1A alternatives, leaving 60->18->1B->1D.', flush=True)

facts = 0


def prove(ip, label, claim, condition=None):
    global facts
    a, b = templates[ip]
    p = base(a, ip)
    if condition is not None:
        p.add(condition(a))
    assert p.check() == sat, ('vacuous fact', label)
    p.add(~claim(a, b))
    assert p.check() == unsat, label
    facts += 1
    print('PASS:', label, flush=True)


prove(0x60, '60->18 iff R38=9 and R25=R31; their values are preserved',
      lambda a, b: And((address(b) == 0x18) == And(a.r[38] == 9, a.r[25] == a.r[31]),
          b.r[25] == a.r[25], b.r[31] == a.r[31], b.r[34] == a.r[34]))
for ip, nxt in ((0x18, 0x1B), (0x1B, 0x1D)):
    prove(ip, f'{ip:02X}->{nxt:02X} increments R32 and preserves the counter/R26',
          lambda a, b, nxt=nxt: And(address(b) == nxt, b.r[32] == a.r[32]+1,
              *[b.r[i] == a.r[i] for i in (2, 25, 26, 31, 34, 38)]))
prove(0x1D, '1D with R26=1 enters 2E and preserves R32',
      lambda a, b: And(address(b) == 0x2E, b.r[32] == a.r[32]),
      lambda a: a.r[26] == 1)
prove(0x2E, '2E preserves R32 while entering the read helper',
      lambda a, b: And(address(b) == 1, b.r[32] == a.r[32]))
prove(1, '01 clears R29, preserves R32, and only waits or enters 02',
      lambda a, b: And(b.r[29] == 0, b.r[32] == a.r[32],
                       Or(address(b) == 1, address(b) == 2)))
prove(2, '02 increments R29, preserves R32; exits iff old R29 equals R32',
      lambda a, b: And(b.r[29] == a.r[29]+1, b.r[32] == a.r[32],
                       address(b) == If(a.r[29] == a.r[32],
                                        BitVecVal(3, 8), BitVecVal(2, 8))))

# These preserving facts cover arbitrary read waits and 2F/20 normalization
# repetitions on the selected 21->22/36/27/38 route, not every DD suffix.
preserving = (0x1D, 0x2E, 1, 2, 3, 4, 0xBA, 0xCB, 0xDD, 0xD6,
              0x2F, 0x20, 0x21, 0x22, 0x36, 0x27, 0x38,
              0x3A, 0x07, 0x6D, 0x60, 0x61)
for ip in preserving:
    prove(ip, f'{ip:02X} preserves R25/R31/R34/R26/R2',
          lambda a, b: And(*[b.r[i] == a.r[i] for i in (25, 31, 34, 26, 2)]))


def increment(lo, hi):
    return (If(ULT(lo, 9), lo+1, lo+7),
            hi+If(ULT(lo, 9), BitVecVal(0, 4), BitVecVal(1, 4)))


prove(6, '06 performs the decimal-low-digit increment and preserves R25',
      lambda a, b: And(b.r[31] == increment(a.r[31], a.r[34])[0],
          b.r[34] == increment(a.r[31], a.r[34])[1], b.r[25] == a.r[25]))
prove(0x61, '61 allows another 3A/06 cycle iff R34>=C',
      lambda a, b: (address(b) == 0x3A) == UGE(a.r[34], 12))

lo, hi = BitVec('bootstrap_counter_lo', 4), BitVec('bootstrap_counter_hi', 4)
a = State('counter_lemma')
p = base(a, 0)
first, _ = increment(lo, hi)
p.add(Or(first == lo, UGE(first, 10)))
assert p.check() == unsat
print('PASS: one increment never fixes the low digit and always leaves 0..9. '
      'Thus the nearest second 60 cannot select C8 after the initial equality.', flush=True)

# Prove the entire counter-only loop algebra, not a bounded negative search.
value, high, guards = lo, hi, []
for n in range(1, 11):
    value, high = increment(value, high)
    p = base(a, 0)
    p.add(ULT(lo, 10), value == lo if n < 10 else value != lo)
    assert p.check() == unsat, ('decimal cycle length', n)
    if n < 10:
        guards.append(UGE(high, 12))
allowed = Or(byte(lo, hi) == 0xB9, byte(lo, hi) == 0xF0,
             And(UGE(hi, 12), ULE(hi, 14), ULT(lo, 10)))
p = base(a, 0)
p.add(And(ULT(lo, 10), *guards) != allowed)
assert p.check() == unsat
print('PASS: a valid low digit first repeats after exactly 10 increments; '
      'invalid A..F never repeat on this loop. All nine 61 guards survive '
      'exactly for initial counters B9, C0..C9, D0..D9, E0..E9, F0.', flush=True)


def build(sequence, label, released=False, real_type=True):
    a = State(label)
    p = base(a, sequence[0])
    p.add(a.r[26] == 1, UGE(a.r[2], 5), a.s1 == 0,
          byte(a.r[37], a.r[40]) == 0x5E,
          *[v == n for v, n in zip(stack(a), (0x6E, 0x08, 0x39))])
    if real_type:
        p.add(a.r[32] == 0)
    b, states = a, [a]
    for i, (ip, nxt) in enumerate(zip(sequence, sequence[1:])):
        b = execute(b, ip, *((0, 0) if released else keys(f'{label}_keys_{i}')))
        p.add(address(b) == nxt)
        states.append(b)
    return a, b, p, states


def addresses(text):
    return [int(v, 16) for v in text.split()]


PREFIX = addresses('60 18 1B 1D 2E 01 02 02 02 03 04 BA CB DD D6 '
                   '2F 21 22 36 27 38 06 07 6D 60')
LOOP = addresses('61 3A 06 07 6D 60')
a, b, p, _ = build(PREFIX, 'real_read_prefix')
assert p.check() == sat, 'read prefix must be nonvacuous'
p.add(b.r[25] == b.r[31])
assert p.check() == unsat
a, b, p, _ = build(PREFIX+[0xC8], 'short_bootstrap')
assert p.check() == unsat
print('PASS: correct three-pass read is feasible, but its immediate C8 exit '
      'is UNSAT. The preserving lemmas also cover extra 01/2F/20 waits.', flush=True)

long = PREFIX + LOOP*9 + [0xC8]
a, b, p, states = build(long, 'long_bootstrap', released=True)
assert p.check() == sat, 'long counter detour remains a positive control'
actual = q['domain'](p, byte(a.r[31], a.r[34]))
expected = {0xB9, 0xF0} | {16*h+l for h in (12, 13, 14) for l in range(10)}
assert actual == expected, actual
dd = states[long.index(0xDD)]
p.push()
p.add(~And(dd.r[0] == 3, dd.r[26] == 1, dd.r[32] == 2,
           b.r[38] == 4, stack(b)[0] == 0x6E))
assert p.check() == unsat
p.pop()
print('PASS: the exact 10-increment path is SAT with released keys, R32=0 '
      'at the initial 60, a three-pass read, and exactly those 32 counters. '
      'The initial chip state and ring stream remain artificial.', flush=True)

# A misleading failure encountered during this investigation: keeping one
# 02 execution silently selects an initial type E, because 18/1B add two.
wrong = addresses('60 18 1B 1D 2E 01 02 03 04 BA CB DD D6 '
                  '2F 21 22 36 27 38 06 07 6D 60') + LOOP*9 + [0xC8]
a, b, p, _ = build(wrong, 'wrong_wait_count', real_type=False)
assert p.check() == sat
p.add(a.r[32] != 14)
assert p.check() == unsat
print('PASS: the one-pass-read variant requires initial R32=E, not zero. '
      'Its failure with R32=0 must not be mistaken for exclusion of other '
      'read-loop lengths.', flush=True)
print(f'PASS: {facts} universal facts, ROM source coverage, counter-cycle '
      'algebra, and exact positive/negative paths. No keyboard hack found.', flush=True)
