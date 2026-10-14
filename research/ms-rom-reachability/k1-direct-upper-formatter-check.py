#!/usr/bin/env python3
"""All canonical Q formatter classes with only the extra U marker.

The local classification is independent of how the keyboard reaches EE(Q).
It exposes a return hazard, not impossibility of all upper exchange paths.
"""
import runpy
from pathlib import Path

check=runpy.run_path(str(Path(__file__).with_name('k1-q-formatter-check.py')))['check']
targets={i:('Q' if i==8 else 'X') for i in range(9)}
for header in (9,0):
    for small in ([False] if header==9 else [False,True]):
        for zeros in range(8):
            check(header,zeros,small,source_slot='Q',marker_slots=('marker','U'),target_by_class=targets)
check(0,7,True,True,source_slot='Q',marker_slots=('marker','U'),target_by_class=targets)
print('PASS local EE(Q)/E3 classification: classes 0..7 write X; class 8 and exact zero write Q.',flush=True)
print('LIMIT: this is not keyboard reachability, a closed exchange, or general impossibility of K1.',flush=True)
