#!/usr/bin/env python3
"""Connected NOP plus its canonical class-0 late copy: remove V, keep a.

Local accepted 9C/control and formatter contracts; native timing and the
complete keyboard prefix are checked separately on two positive-exponent
fixtures, not on the whole symbolic numerical domain.
"""
import runpy
from pathlib import Path
root=Path(__file__).resolve().parent
r=runpy.run_path(str(root/'k1-ytv-reader-map.py'))['reader']('control',0x54,('Z','V'))
assert r['reads']==['V','X'] and r['push']==[]
fmt=runpy.run_path(str(root/'k1-q-formatter-check.py'))['check']
for header in (0,9):
    fmt(header,0,source_slot='X',marker_slots=('marker','Z','V'),target_by_class=['V']*9)
print('PASS class-0 NOP removes V without A3 or stack push; no native whole-domain claim.',flush=True)
