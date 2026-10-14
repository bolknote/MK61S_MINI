#!/usr/bin/env python3
"""Local EE(X)/E3 return with the neutral-marker route's Z/U markers.

This verifies the destination for every canonical normalization class.
It does not establish the keyboard entry or a full-domain upper cycle.
"""
import runpy
from pathlib import Path

check = runpy.run_path(str(Path(__file__).with_name('k1-q-formatter-check.py')))['check']
targets = {i: 'V' if i <= 4 else 'Q' if i <= 6 else 'X' for i in range(9)}
for header in (9, 0):
    for small in ([False] if header == 9 else [False, True]):
        for zeros in range(8):
            check(header, zeros, small, source_slot='X',
                  marker_slots=('marker', 'Z', 'U'), target_by_class=targets)
check(0, 7, True, True, source_slot='X',
      marker_slots=('marker', 'Z', 'U'), target_by_class=targets)
print('PASS local EE(X)/E3: classes 0..4 copy to V; 5..6 to Q; 7..8 (including zero) to X.', flush=True)
targets_after_cleanup = {i: 'V' if i <= 4 else 'X' for i in range(9)}
for header in (9, 0):
    for small in ([False] if header == 9 else [False, True]):
        for zeros in range(8):
            check(header, zeros, small, source_slot='X',
                  marker_slots=('marker', 'Z'), target_by_class=targets_after_cleanup)
check(0, 7, True, True, source_slot='X',
      marker_slots=('marker', 'Z'), target_by_class=targets_after_cleanup)
print('PASS after U cleanup: classes 0..4 copy to V; 5..8 (including zero) to X.', flush=True)
print('LIMIT: later SIGN needs an accepted control header too; these are not sufficient full-cycle conditions.', flush=True)
