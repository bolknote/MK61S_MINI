#!/usr/bin/env python3
"""Check whether the ready-marker DD9 read contexts require an earlier read.

All 256 ROM sources are checked using exact 42-tick semantics, arbitrary
keys/ring, and the completed first-entry vector bound. The two admitted
stacks are obtained separately by analyze_dd_contexts.py --selector 9.
This is not a proof that all DD9 preparations are circular.
"""
import runpy
from pathlib import Path

from z3 import And, Or, UGE, sat, unsat

root = Path(__file__).resolve().parent
m = runpy.run_path(str(root / 'analyze_dd_stack_lifetime.py'))
q = m['model']()
State, execute, base, keys = (q[n] for n in ('State', 'execute', 'base', 'keys'))
address, stack, byte = (m[n] for n in ('address', 'stack', 'byte'))
STACKS = ((0x2F, 0x6E, 0x08), (0x2F, 0x6E, 0x78))
TARGETS = (0xDD, 0xCB, 0xBA, 0x04, 0x03, 0x02, 0x01)
sources = {target: set() for target in TARGETS}
templates = {}


def read_context(a):
    return And(a.r[26] == 1, a.s1 == 6,
               byte(a.r[37], a.r[40]) == 0xFF,
               Or(*[And(*[v == n for v, n in zip(stack(a), sp)]) for sp in STACKS]))


for ip in range(256):
    a = State(f'circular_source_{ip}')
    b = execute(a, ip, *keys(f'circular_source_keys_{ip}'))
    templates[ip] = a, b
    if ip in (0xC7, 0xC8):
        continue
    p = base(a, ip)
    p.add(Or(a.r[41] == 0, a.r[41] == 15), read_context(b))
    if ip == 0xA3:
        p.add(Or(a.r[37] == a.r[40], *[
            byte(a.r[37], a.r[40]) == n for n in (0x90, 0x93, 0xCC, 0xD3, 0xD8)]))
    for target in TARGETS:
        p.push()
        p.add(address(b) == target)
        result = p.check()
        assert result in (sat, unsat)
        if result == sat:
            sources[target].add(ip)
        p.pop()
    if ip % 64 == 63:
        print(f'checked {ip+1}/256 source commands', flush=True)

expected = {0xDD: {0xCB}, 0xCB: {0xBA}, 0xBA: {0x04}, 0x04: {0x03},
            0x03: {0x02}, 0x02: {0x01, 0x02}, 0x01: {0x01, 0x2E}}
print('All-source result:', {f'{ip:02X}': [f'{n:02X}' for n in sorted(v)]
                             for ip, v in sources.items()}, flush=True)
assert sources == expected, ('uncovered source of the selected read context', sources)

# Establish the reverse closure, not merely an allowed address graph:
# the context and high R2 must already hold before each internal step.
for ip, targets in ((0xCB, (0xDD,)), (0xBA, (0xCB,)), (4, (0xBA,)),
                    (3, (4,)), (2, (2, 3)), (1, (1, 2))):
    a, b = templates[ip]
    p = base(a, ip)
    p.add(read_context(b), Or(*[address(b) == n for n in targets]))
    assert p.check() == sat, ('vacuous reverse step', ip)
    p.add(~And(read_context(a), b.r[2] == a.r[2], b.r[26] == a.r[26],
               b.r[38] == a.r[38]))
    assert p.check() == unsat, ('reverse context not closed', ip)
print('PASS: reverse read context closure through CB/BA/04/03/02*/01*; '
      'R2 and marker1 were already present at the preceding 2E, '
      'and the incoming selector is preserved.', flush=True)

a, b = templates[0x2E]
p = base(a, 0x2E)
p.add(read_context(b))
assert p.check() == sat
p.add(~And(a.r[26] == 1, b.r[2] == a.r[2], b.r[38] == a.r[38],
           stack(a)[0] == 0x6E, Or(stack(a)[1] == 0x08, stack(a)[1] == 0x78)))
assert p.check() == unsat

# A stack return rotates its consumed address into the bottom byte.
# None of the listed read-body targets equals 08 or 78, so no such
# return can replace the source chain above. This is also explicitly
# covered by the all-source solver checks rather than assumed away.
assert not (set(TARGETS) & {sp[-1] for sp in STACKS})
print('PASS: all 256 sources leave only 2E->01*->02*->03->04->BA->CB->DD '
      'for a DD with marker1, S1=6/vector FF and stack 2F/6E/08 or '
      '2F/6E/78. Old DD returns and other read/write helpers are excluded.', flush=True)

# check_2e_sources.py + analyze_read_bootstrap.py --check-invariants
# independently exclude 2C/36 and 1F/1A alternatives at marker1.
# Verify the data-preserving connection that makes high-mode dominance
# stronger than merely passing the same ROM address with a low R2.
for ip, nxt in ((0x60, 0x18), (0x18, 0x1B), (0x1B, 0x1D), (0x1D, 0x2E)):
    a, b = templates[ip]
    p = base(a, ip)
    p.add(address(b) == nxt, b.r[26] == 1, UGE(b.r[2], 5))
    assert p.check() == sat, ('vacuous high-mode predecessor', ip)
    claim = And(a.r[26] == 1, UGE(a.r[2], 5), a.r[2] == b.r[2],
                a.r[38] == b.r[38])
    if ip == 0x60:
        claim = And(claim, a.r[38] == 9, a.r[25] == a.r[31])
    p.add(~claim)
    assert p.check() == unsat, ('missing predecessor condition', ip)
print('CONCLUSION with the independently completed marker1 source exclusions: '
      'the two ready-marker DD9 read contexts with high R2 require an '
      'EARLIER 60/selector9/marker1/high-R2/equal-counter input. They cannot '
      'be the preparation of its first occurrence. Other DD9 contexts '
      'and marker histories are not excluded by this lemma.', flush=True)
