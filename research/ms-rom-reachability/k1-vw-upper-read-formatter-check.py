#!/usr/bin/env python3
"""Local exact late-write classification for the preserving V/W reader.

LastX temporarily puts a marker in X. This extra marker is material:
classes 7/8 return P7 into T, overwriting the saved lower Q in the fixture.
"""
import runpy
from pathlib import Path
check=runpy.run_path(str(Path(__file__).with_name('k1-q-formatter-check.py')))['check']
targets=['P8']+['X']*6+['T']*2
for h in (9,0):
    for small in ([False] if h==9 else [False,True]):
        for z in range(8):
            check(h,z,small,source_slot='P7',marker_slots=('marker','X','V','W'),
                  target_by_class=targets)
check(0,7,True,True,source_slot='P7',marker_slots=('marker','X','V','W'),target_by_class=targets)
print('PASS local classes: 0 -> P8; 1..6 -> X; 7..8 (including zero) -> T.',flush=True)
print('LIMIT: local late formatter only; a successful read is not a closed K1.',flush=True)
