#!/usr/bin/env python3
"""Conditional formatter after U removal and rotation of Z's marker to Y.

Not a proof of the entire keyboard entry or of reaching the last Ms words.
"""
import runpy
from pathlib import Path

check=runpy.run_path(str(Path(__file__).with_name('k1-q-formatter-check.py')))['check']
targets={i:'U' if i<=3 else 'X' for i in range(9)}
for header in (9,0):
    for small in ([False] if header==9 else [False,True]):
        for zeros in range(8):
            check(header,zeros,small,source_slot='X',
                  marker_slots=('marker','Y'),target_by_class=targets)
check(0,7,True,True,source_slot='X',marker_slots=('marker','Y'),target_by_class=targets)
print('PASS local EE(X)/E3 with Y marker: classes 0..3 copy to U; 4..8, including zero, to X.',flush=True)
print('LIMIT: entry/control/other-chip timing remain separate obligations; no full K1 claim.',flush=True)
