#!/usr/bin/env python3
"""Local reader/drop/formatter contracts behind the new closed suffix.

No universal max, inter-chip timing or full keyboard-prefix theorem is
claimed here. Those compositions have two separate native fixtures.
"""
import runpy
from pathlib import Path

root=Path(__file__).resolve().parent
reader=runpy.run_path(str(root/'k1-ytv-reader-map.py'))['reader']
for origin,code,markers,early,register in (
    ('control',0x0F,('Y',),'T',None),
    ('T',0x61,('Z',),'X','V'),
    ('U',0x61,('T',),'X','V'),
):
    r=reader(origin,code,markers)
    assert r['reads']==[early,'X'] and r['push']==['X','Y','Z','T'] and r['register']==register
runpy.run_path(str(root/'k1-ytv-rcl-drop-check.py'))['subtract']()
fmt=runpy.run_path(str(root/'k1-q-formatter-check.py'))['check']
fmt(9,0,source_slot='X',marker_slots=('marker','Y'),target_by_class=['U']*9)
fmt(9,0,source_slot='X',marker_slots=('marker','Z'),target_by_class=['V']*9)
for markers in (('marker','T'),('marker',)):
    fmt(0,5,True,source_slot='X',marker_slots=markers,target_by_class=['X']*9)
print('PASS local subtraction + LastX + two RCL1 contracts. Native max/order and phase assumptions remain explicit.',flush=True)
