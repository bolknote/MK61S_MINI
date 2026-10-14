#!/usr/bin/env python3
"""All ROM sources of the restore chain and numeric ST[0..35] operations.

Sources using old return addresses are listed separately. No such address
is assumed absent unless its complete pusher set proves that from reset.
Only the previously proved first-entry A3 vector bound is used.
"""
import runpy
from pathlib import Path

from z3 import And, Or, ZeroExt, sat, unsat

root = Path(__file__).resolve().parent
q = runpy.run_path(str(root / 'ik1302_symbolic.py'))
State, execute, base, keys = (q[n] for n in
    ('State', 'execute_command', 'base_solver', 'arbitrary_keys'))
byte = lambda lo, hi: ZeroExt(4, lo) | (ZeroExt(4, hi) << 4)
address = lambda a: byte(a.r[36], a.r[39])
stack = lambda a: [byte(a.st[36+i], a.st[39+i]) for i in range(3)]
TARGETS = (0x9A, 0x98, 0x95, 0x94, 0x93, 0x92, 0x91, 0x40, 0x47)
sources = {ip: set() for ip in TARGETS}
pushers = {ip: set() for ip in TARGETS}
numeric = {}
templates = {}
for ip in range(256):
    a = State(f'restore_structure_{ip}')
    b = execute(a, ip, *keys(f'restore_structure_keys_{ip}'))
    old, new = stack(a), stack(b)
    p = base(a, ip)
    for kind, expected in (('same', old), ('rotate', old[1:]+old[:1]),
                           ('push', [(ip & 0xF0) | ((ip+1) & 15)]+old[:2])):
        p.push()
        p.add(~And(*[v == w for v, w in zip(new, expected)]))
        valid = p.check() == unsat
        p.pop()
        if valid:
            break
    else:
        raise AssertionError(('unclassified return stack', ip))
    pushed = (ip & 0xF0) | ((ip+1) & 15)
    if kind == 'push' and pushed in pushers:
        pushers[pushed].add(ip)
    templates[ip] = a, b, kind
    pushed_word = [v for j in range(0, 36, 3)
                   for v in (a.r[j], a.st[j], a.st[j+1])]
    rotated_word = [v for j in range(0, 36, 3)
                   for v in (a.st[j+1], a.st[j+2], a.st[j])]
    forms = {'same': a.st[:36], 'push_word': pushed_word,
             'rotate_word': rotated_word,
             'push_tail': a.st[:27]+pushed_word[27:],
             'rotate_tail': a.st[:27]+rotated_word[27:]}
    for label, expected in forms.items():
        p.push()
        p.add(~And(*[v == w for v, w in zip(b.st[:36], expected)]))
        valid = p.check() == unsat
        p.pop()
        if valid:
            break
    else:
        raise AssertionError(('unclassified numeric stack', ip))
    numeric[ip] = label
    if ip in (0xC7, 0xC8):
        continue
    if ip == 0xA3:
        p.add(Or(a.r[37] == a.r[40], *[
            byte(a.r[37], a.r[40]) == n for n in (0x90, 0x93, 0xCC, 0xD3, 0xD8)]))
    for target in TARGETS:
        p.push()
        p.add(address(b) == target, *[v != target for v in old])
        outcome = p.check()
        assert outcome in (sat, unsat)
        if outcome == sat:
            sources[target].add(ip)
        p.pop()
    if ip % 64 == 63:
        print(f'checked {ip+1}/256 restore sources and numeric-stack transforms', flush=True)
assert {ip for ip, label in numeric.items() if label == 'push_word'} == {0x40, 0x93}
assert {ip for ip, label in numeric.items() if label == 'rotate_word'} == {0x47, 0x94, 0x95}
assert {ip for ip, label in numeric.items() if label == 'push_tail'} == {0xBE}
assert {ip for ip, label in numeric.items() if label == 'rotate_tail'} == {0x8C, 0xAC}
print('PASS: full numeric word ST[0..35]: pushes only at 40/93, rotations '
      'only at 47/94/95. Three tail triples ST[27..35] alone are pushed '
      'by BE and rotated by 8C/AC. Other commands preserve all 36 cells.', flush=True)
for target in TARGETS:
    print(f'{target:02X}: non-return sources='+','.join(f'{ip:02X}' for ip in sorted(sources[target]))
          +'; tag pushers='+','.join(f'{ip:02X}' for ip in sorted(pushers[target])), flush=True)

# A restore shifts entire lanes, including both the saved mode and the
# opcode metadata. The partial-tail operations above can break their
# previous alignment; they must not be silently treated as whole words.
a = State('restore_single_pass')
p = base(a, 0x93)
b = a
seq = (0x93, 0x94, 0x95, 0x98, 0x9A)
for i, ip in enumerate(seq):
    b = execute(b, ip, *keys(f'restore_single_keys_{i}'))
    expected = seq[i+1] if i+1 < len(seq) else stack(a)[0]
    p.push()
    p.add(address(b) != expected)
    assert p.check() == unsat, ('single-pass edge is not forced', ip, i)
    p.pop()
p.add(~And(*[claim for j in range(0, 36, 3) for claim in
             (b.r[j] == a.r[j+1], b.r[j+1] == a.r[j+2],
              b.r[j+2] == a.st[j])], b.s1 == a.s1,
           b.r[37] == a.r[33], b.r[40] == a.r[33]))
assert p.check() == unsat, 'single-pass lane restoration'
print('PASS: single restore shifts each R lane and restores its third '
      'nibble from ST: R2=old ST0, R32=old ST30, R35=old ST33; S1 is '
      'preserved, vector becomes old R33 repeated.', flush=True)

# 92 creates an immediate 93 return, so its restore is a genuine double
# pass, not a single 93/9A suffix with an invented caller return.
a = State('restore_double_pass')
p = base(a, 0x91)
b = a
seq = (0x91, 0x92, 0x93, 0x94, 0x95, 0x98, 0x9A,
       0x93, 0x94, 0x95, 0x98, 0x9A)
for i, ip in enumerate(seq):
    b = execute(b, ip, *keys(f'restore_double_keys_{i}'))
    expected = seq[i+1] if i+1 < len(seq) else stack(a)[0]
    p.push()
    p.add(address(b) != expected)
    assert p.check() == unsat, ('double-pass edge is not forced', ip, i)
    p.pop()
p.add(~And(b.r[0] == a.r[0], b.r[2] == a.st[1], b.r[5] == a.st[4]))
assert p.check() == unsat, 'double-pass source of mode'
print('PASS: 91->92 forces TWO 93/94/95/98/9A passes, returns through '
      'the original caller byte, preserves original R0, restores R2 from '
      'original ST[1] and R5 from ST[4].', flush=True)
