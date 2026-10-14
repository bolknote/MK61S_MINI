#!/usr/bin/env python3
"""Local late formatter for NOP with the T/V/W markers still present.

This proves neither the keyboard entry nor removal of V/T. The complete
native prefix and preservation of the other chips are separate tests.
"""
import runpy
from pathlib import Path

check = runpy.run_path(str(Path(__file__).with_name('k1-q-formatter-check.py')))['check']
targets = ['P8'] + ['X'] * 6 + ['W'] * 2
for h in (9, 0):
    for small in ([False] if h == 9 else [False, True]):
        for z in range(8):
            check(h, z, small, source_slot='P7', marker_slots=('marker', 'T', 'V', 'W'),
                  target_by_class=targets)
check(0, 7, True, True, source_slot='P7', marker_slots=('marker', 'T', 'V', 'W'),
      target_by_class=targets)
print('PASS local NOP formatter: class 0 -> P8, 1..6 -> X, 7..8 -> W.', flush=True)
print('LIMIT: the complete native keyboard entry is conditional; no V/T cleanup or full K1 proof.', flush=True)
