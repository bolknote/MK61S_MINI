#!/usr/bin/env python3
"""Close the reverse read prefix down to the four cycle-type contexts.

Uses independently completed reset bounds on A3/68, the A4-created A5
return-tag lifetime, and analyze_dd0_inputs.py's exclusion of marker0/2C
in the required stack contexts. All local facts allow arbitrary keys/ring.
This does not prove that a high-mode cycle context is reachable.
"""
import runpy
from pathlib import Path

from z3 import And, Or, UGE, ZeroExt, sat, unsat

root = Path(__file__).resolve().parent
q = runpy.run_path(str(root / 'ik1302_symbolic.py'))
State, execute, base, keys = (q[n] for n in
    ('State', 'execute_command', 'base_solver', 'arbitrary_keys'))
byte = lambda lo, hi: ZeroExt(4, lo) | (ZeroExt(4, hi) << 4)
address = lambda a: byte(a.r[36], a.r[39])
stack = lambda a: [byte(a.st[36+i], a.st[39+i]) for i in range(3)]
targets = (0x1D, 0x1B, 0x18, 0x1A, 0x60)
sources = {target: set() for target in targets}
pushers = {target: set() for target in targets}
templates = {}
for ip in range(256):
    a = State(f'cycle_source_{ip}')
    b = execute(a, ip, *keys(f'cycle_source_keys_{ip}'))
    templates[ip] = a, b
    old, new = stack(a), stack(b)
    pushed = (ip & 0xF0) | ((ip+1) & 15)
    p = base(a, ip)
    for kind, expected in (('same', old), ('rotate', old[1:]+old[:1]),
                           ('push', [pushed]+old[:2])):
        p.push()
        p.add(~And(*[x == y for x, y in zip(new, expected)]))
        valid = p.check() == unsat
        p.pop()
        if valid:
            break
    else:
        raise AssertionError(('unknown stack transformation', ip))
    if kind == 'push' and pushed in pushers:
        pushers[pushed].add(ip)
    if ip in (0xC7, 0xC8):
        continue
    if ip == 0xA3:
        p.add(Or(a.r[37] == a.r[40], *[
            byte(a.r[37], a.r[40]) == n for n in (0x90, 0x93, 0xCC, 0xD3, 0xD8)]))
    for target in targets:
        p.push()
        p.add(address(b) == target, *[n != target for n in old])
        outcome = p.check()
        assert outcome in (sat, unsat)
        if outcome == sat:
            sources[target].add(ip)
        p.pop()
    if ip % 64 == 63:
        print(f'checked {ip+1}/256 source commands and stack transforms', flush=True)
assert sources == {0x1D: {0x1B, 0x1F}, 0x1B: {0x18, 0x1F},
                   0x18: {0x1A, 0x1F, 0x60}, 0x1A: {0x1F},
                   0x60: {0x6C, 0x6D}}, sources
assert not any(pushers.values()), pushers
print('PASS: no return tags 1D/1B/18/1A/60 can be created. All ordinary '
      'sources are covered, including the exceptional 60->18 edge.', flush=True)

facts = 0


def prove(ip, label, claim, condition=None):
    global facts
    a, b = templates[ip]
    p = base(a, ip)
    if condition is not None:
        p.add(condition(a, b))
    assert p.check() == sat, ('empty premise', label)
    p.add(~claim(a, b))
    assert p.check() == unsat, label
    facts += 1
    print('PASS:', label, flush=True)


prove(0x6C, '6C always assigns selector8', lambda a, b: b.r[38] == 8)
prove(0x6D, '6D->60 requires and preserves a nonzero marker',
      lambda a, b: And(a.r[26] != 0, b.r[26] == a.r[26]),
      lambda a, b: address(b) == 0x60)
prove(0x60, '60->18 requires selector9 and preserves the marker',
      lambda a, b: And(a.r[38] == 9, b.r[26] == a.r[26]),
      lambda a, b: address(b) == 0x18)
print('PASS by complete predecessor coverage: 60->18 cannot have marker0 '
      'before first C7/C8. Its only two sources conflict with 9/0.', flush=True)

for ip in (0x1A, 0x18, 0x1B, 0x1D, 0x2E, 0x01, 0x02, 0x03, 0x04, 0xBA, 0xCB):
    prove(ip, f'{ip:02X} preserves R0/R2/R26/R35/R38',
          lambda a, b: And(*[b.r[i] == a.r[i] for i in (0, 2, 26, 35, 38)]))
for ip in (0x01, 0x02, 0x03, 0x04, 0xBA, 0xCB):
    prove(ip, f'{ip:02X} has reverse-closed S1=6/vectorFF/whole-stack context',
          lambda a, b: And(a.s1 == 6, byte(a.r[37], a.r[40]) == 0xFF,
                           *[x == y for x, y in zip(stack(a), stack(b))]),
          lambda a, b: And(b.s1 == 6, byte(b.r[37], b.r[40]) == 0xFF))
prove(0x2E, '2E inserts 2F and preserves the two prior top bytes',
      lambda a, b: And(stack(b)[0] == 0x2F, stack(b)[1] == stack(a)[0],
                       stack(b)[2] == stack(a)[1]))
for ip in (0x2E, 0x01, 0x02, 0x03, 0x04, 0xBA, 0xCB):
    prove(ip, f'{ip:02X} preserves the cycle read index R32',
          lambda a, b: b.r[32] == a.r[32])

# No read-prefix instruction changes the surviving first two return bytes.
# Thus the completed marker0/2C exclusion remains applicable backwards.
for ip in (0x1F, 0x1A, 0x18, 0x1B, 0x1D):
    prove(ip, f'{ip:02X} preserves the entire address stack and marker',
          lambda a, b: And(b.r[26] == a.r[26],
                           *[x == y for x, y in zip(stack(a), stack(b))]))
prove(0x1F, '1F dispatches by its preserved S1, clears the read index',
      lambda a, b: And(address(b) == (0x10 | ZeroExt(4, a.s1)),
                       b.s1 == a.s1, b.r[32] == 0))
prove(0x4F, '4F cannot supply cycle selectors to 1F', lambda a, b: b.s1 == 0)
prove(0xAB, 'direct AB->A5 carries markerF, not zero', lambda a, b: b.r[26] == 15)

cycles = {0xD: ('L0', []), 0xB: ('L1', [0x1B]),
          0x8: ('L2', [0x18, 0x1B]), 0xA: ('L3', [0x1A, 0x18, 0x1B])}
for low, (label, middle) in cycles.items():
    a = State(f'cycle_exact_{low}')
    p = base(a, 0xAD)
    b = a
    seq = [0xAD, 0xA5, 0x1F]+middle+[0x1D, 0x2E]
    for i, (ip, nxt) in enumerate(zip(seq, seq[1:])):
        b = execute(b, ip, *keys(f'cycle_exact_keys_{low}_{i}'))
        p.add(address(b) == nxt)
    assert p.check() == sat, ('empty cycle path', label)
    p.push()
    p.add(~And(a.r[35] == 5, a.r[32] == low, b.r[35] == 5,
               b.r[32] == len(middle), b.r[26] == 0, b.r[38] == 13,
               b.r[2] == a.r[2], b.r[0] == a.r[0],
               *[x == y for x, y in zip(stack(a), stack(b))]))
    assert p.check() == unsat, ('cycle data-flow', label)
    p.pop()
    print(f'PASS: {label}/5{low:X}: '+' '.join(f'{ip:02X}' for ip in seq)
          +f'; read index R32={len(middle)}, R35=5, R38=D, marker0, R2/R0 preserved.', flush=True)

print(f'PASS: {facts} one-command facts, complete five-entry source coverage, '
      'and four exact cycle-type paths. With the prior A5 lifetime and '
      'DD0/2C projection, a necessary last-DD preparation passes AD->A5->1F '
      'in one of the four cycle contexts. This need not be ordinary user '
      'program execution; high R2 at AD is still unproved from reset.', flush=True)

# A useful next provenance boundary: this genuine restore route does not
# produce a fresh arbitrary mode. It reads two numeric ST cells, distinct
# from the three return-address bytes at ST[36..41]. No assertion is made
# here that every possible 9A entry has this prefix.
a = State('cycle_restore93')
p = base(a, 0x93)
b = a
seq = (0x93, 0x94, 0x95, 0x98, 0x9A)
for i, ip in enumerate(seq):
    b = execute(b, ip, *keys(f'cycle_restore93_keys_{i}'))
    if i+1 < len(seq):
        p.push()
        p.add(address(b) != seq[i+1])
        assert p.check() == unsat, ('restore93 edge is not forced', ip)
        p.pop()
p.add(~And(b.r[2] == a.st[0], b.r[5] == a.st[3]))
assert p.check() == unsat, 'numeric ST source of restored modes'
print('PASS: forced 93->94->95->98->9A restores R2 from the ORIGINAL ST[0] '
      'and R5 from ST[3]. This is a path-specific data-flow fact, not '
      'an assumption that all 9A calls have this prefix.', flush=True)
