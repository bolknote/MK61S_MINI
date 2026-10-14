#!/usr/bin/env python3
"""Conditional formatter from physical X with only real/V markers.

This proves the local late copy, not native keyboard entry or a closed exit.
"""
import runpy
from pathlib import Path

check=runpy.run_path(str(Path(__file__).with_name('k1-q-formatter-check.py')))['check']
geometry={'source_slot':'X','marker_slots':('marker','V'),
          'target_by_class':['P7']*8+['X']}
for header in (9,0):
    for decimal in ([False] if header==9 else [False,True]):
        for z in range(8):
            check(header,z,decimal,**geometry)
check(0,7,True,True,**geometry)
print('LIMIT: physical EE(X), top E3, only real/V markers; class 8 stays in X.',flush=True)
