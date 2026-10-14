#!/usr/bin/env python3
"""DD9 bootstrap exclusions with arbitrary initial R2 and R26.

Together with the separate DD context inventory and universal return
suffixes, only D6/2F can remain after the last selector9 assignment.
This does not itself close that read family or prove C8 unreachable.
"""
import runpy
from pathlib import Path

from z3 import And, ZeroExt

root = Path(__file__).resolve().parent
m = runpy.run_path(str(root / 'analyze_1f_lifetime.py'))
for value in range(16):
    if value in (4, 6):
        continue
    report = m['run'](f'dd-{value:x}', selector_value=9, bootstrap=True,
                      proved_type7_gate=True)
    assert report['excluded'], ('unclosed DD9 exit', value)

byte = lambda lo, hi: ZeroExt(4, lo) | (ZeroExt(4, hi) << 4)
report = m['run']('dd-4', selector_value=9, bootstrap=True,
    proved_type7_gate=True, seed_constraints=lambda a: And(
        byte(a.st[36], a.st[39]) == 0x26, byte(a.r[37], a.r[40]) == 0xFF))
assert report['excluded'], 'unclosed DD9 D4/26 write family'
for entry in ('at-dc', 'at-63'):
    report = m['run'](entry, selector_value=9, bootstrap=True, proved_type7_gate=True)
    assert report['excluded'], ('unclosed continuation', entry)

print('PASS: 14 DD9 exits, D4/26 write, DC and failed-counter 63 '
      'lifetimes excluded with arbitrary initial R2/R26. Combine with '
      'analyze_dd_contexts.py --selector 9 --check-marker-classes and '
      'check_dd_return_suffixes.py; no restriction to low mode is used.', flush=True)
