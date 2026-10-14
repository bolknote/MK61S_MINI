#!/usr/bin/env python3
"""Late LastX(V=m) formatter: the new X marker intercepts short a."""
import runpy
from pathlib import Path

check=runpy.run_path(str(Path(__file__).with_name('k1-q-formatter-check.py')))['check']
for header in (9,0):
    for small in ([False] if header==9 else [False,True]):
        for zeros in range(8):
            check(header,zeros,small,source_slot='P7',marker_slots=('marker','X','V'),
                  target_by_class=['X']*7+['T']*2)
check(0,7,True,True,source_slot='P7',marker_slots=('marker','X','V'),
      target_by_class=['X']*7+['T']*2)
print('PASS all 25 canonical cases: classes 0..6 -> X; classes 7/8 incl zero -> T.',flush=True)
print('COMPOSITION LIMIT: NOP clears W only for classes 7/8, precisely those '
      'which overwrite unique q in T after LastX(V=m). No phase rescue of this fixed geometry.',flush=True)
