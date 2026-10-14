#!/usr/bin/env python3
"""Return of the old upper P7 with only the false V marker left.

The four-word rotation happens while primary formatting still holds the
old P7. A late write back to P7 would overwrite the newly rotated word.
"""
import runpy
from pathlib import Path

check=runpy.run_path(str(Path(__file__).with_name('k1-q-formatter-check.py')))['check']
for markers,target in [(('marker','T','V'),'W'),(('marker','V'),'P7')]:
    for h in (9,0):
        for small in ([False] if h==9 else [False,True]):
            for z in range(8):
                check(h,z,small,source_slot='P7',marker_slots=markers,
                      target_by_class=['X']*7+[target]*2)
    check(0,7,True,True,source_slot='P7',marker_slots=markers,
          target_by_class=['X']*7+[target]*2)
print('PREPARATION: while T is still a marker, classes 7..8 return old P7 to W.',flush=True)
print('LIMIT: canonical formatter only; class 7..8 writes old P7 over the rotated P7.',flush=True)
