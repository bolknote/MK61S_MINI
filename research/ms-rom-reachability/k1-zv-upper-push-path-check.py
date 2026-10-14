#!/usr/bin/env python3
"""Removing V before the upper push leaves only real/Z, not real/Z/W.

The local scanner contracts precede the two full native composition tests.
No new keyboard timing or arbitrary-number theorem is implied.
"""
import runpy
from pathlib import Path
root=Path(__file__).resolve().parent
reader=runpy.run_path(str(root/'k1-ytv-reader-map.py'))['reader']
for start,early in (('control','V'),('T','X')):
    r=reader(start,0x68,('Z',))
    assert r['register']=='marker' and r['push']==['V','W','Q','P7'] and r['reads']==[early,'X']
fmt=runpy.run_path(str(root/'k1-q-formatter-check.py'))['check']
fmt(0,0,source_slot='X',marker_slots=('marker','Z'),target_by_class=['V']*9)
print('PASS upper push after NOP: hidden marker is not transported; class-0 late a returns to V.',flush=True)
