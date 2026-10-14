#!/usr/bin/env python3
"""Local contracts for the keyboard Z/W entry and its next request barrier."""
import runpy
from pathlib import Path
root=Path(__file__).resolve().parent

if __name__=='__main__':
    reader=runpy.run_path(str(root/'k1-ytv-reader-map.py'))['reader']
    # Either visible ENTER origin has the same late P7 read. Only the
    # observed origin is used by the native audit; the other is conditional.
    for origin in ('control','Z'):reader(origin,0x0E)
    reader('control',0x68,('Z','V'))
    fmt=runpy.run_path(str(root/'k1-q-formatter-check.py'))['check']
    # Scientific classes 0..4, decimal classes 1..4; both number signs
    # are unconstrained by the formatter checker. Zero is not in scope.
    for header,zeroes,decimal in [(h,z,False) for h in (0,9) for z in range(5)]+[(0,z,True) for z in range(4)]:
        fmt(header,zeroes,decimal,source_slot='P7',marker_slots=('marker','Z','V'),target_by_class=['X']*9)
        fmt(header,zeroes,decimal,source_slot='X',marker_slots=('marker','Z','W'),target_by_class=['V']*9)
    request=runpy.run_path(str(root/'k1-ytv-request-path-check.py'))['request']
    for code in (0x14,0x25):
        for origin in ('control','T','Q'):request(origin,code,('Z','W'))
    print('LIMIT: entry suffix classes 0..4 only; no universal keyboard prefix or safe continuation theorem.',flush=True)
