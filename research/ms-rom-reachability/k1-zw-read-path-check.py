#!/usr/bin/env python3
"""NOP P8 reader with Z/W markers, conditional on the accepted origin."""
import runpy
from pathlib import Path
root=Path(__file__).resolve().parent

if __name__=='__main__':
    reader=runpy.run_path(str(root/'k1-ytv-reader-map.py'))['reader']
    for origin in ('control','T','Q'):reader(origin,0x54,('Z','W'))
    fmt=runpy.run_path(str(root/'k1-q-formatter-check.py'))['check']
    for header,z,decimal in [(h,z,False) for h in (0,9) for z in range(6)]+[(0,z,True) for z in range(5)]:
        fmt(header,z,decimal,source_slot='P8',marker_slots=('marker','Z','W'),target_by_class=['X']*9)
    print('LIMIT: P8 formatter classes 0..5; other classes and keyboard timing are not covered.',flush=True)
