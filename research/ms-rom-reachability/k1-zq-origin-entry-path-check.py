#!/usr/bin/env python3
"""Local Z/W -> absent-real-marker -> Z/Q contracts, not a clean exit."""
import runpy
from pathlib import Path

root=Path(__file__).resolve().parent

if __name__=='__main__':
    reader=runpy.run_path(str(root/'k1-ytv-reader-map.py'))['reader']
    # RCL0 itself replaces the physical marker. The connected model carries
    # that change into its second EE, rather than assuming a new geometry.
    r=reader('control',0x60,('Z','W'))
    assert r['register']=='U' and r['reads']==['V','V']
    assert r['push']==['P8','P9','P10','marker']
    r=reader('T',0x0F,('Z','W'),real=False)
    assert r['reads']==['P7','V'] and r['push']==['V','W','Q','P7']
    # The other actual scanner origin reads U, not the endangered P7.
    r=reader('Q',0x0F,('Z','W'),real=False)
    assert r['reads']==['U','V'] and r['push']==['V','W','Q','P7']
    fmt=runpy.run_path(str(root/'k1-q-formatter-check.py'))['check']
    # a must finish in P8 (or leave the same a in V); classes 0..3 are
    # the sufficient P8-copy contract used by the native entry.
    for h,z,decimal in [(h,z,False) for h in (0,9) for z in range(4)]+[(0,z,True) for z in range(3)]:
        fmt(h,z,decimal,source_slot='V',marker_slots=('Z','W'),target_by_class=['P8']*9)
    # LastX has just copied p to V. Long p would overwrite b in P9;
    # classes 5..8 return to V, with both signs and exact zero covered.
    for h,z,decimal in [(h,z,False) for h in (0,9) for z in range(8)]+[(0,z,True) for z in range(8)]:
        fmt(h,z,decimal,source_slot='V',marker_slots=('Z','Q'),target_by_class=['P9']*5+['V']*4)
    fmt(0,7,True,True,source_slot='V',marker_slots=('Z','Q'),target_by_class=['P9']*5+['V']*4)
    request=runpy.run_path(str(root/'k1-ytv-request-path-check.py'))['request']
    for code in (0x14,0x25):
        for origin in ('T','P7'):
            r=request(origin,code,('Z','Q'),real=False)
            assert r['writes']==([('E9','U'),('A3','P7')] if origin=='T' else [('E9','P8'),('A3','T')])
            assert r['reads'][0] not in ('T','P7')
    print('LIMIT: connected local contracts only. Physical marker remains occupied; no clean exit or full K1.',flush=True)
