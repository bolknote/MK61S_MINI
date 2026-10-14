#!/usr/bin/env python3
"""Local ROM contracts for the changed numerical classes of the third entry.

These do not establish keyboard reachability or inter-chip timing by themselves;
the continuous native audit is a separate obligation.
"""
import runpy
from pathlib import Path

root=Path(__file__).resolve().parent

if __name__=='__main__':
    producer=runpy.run_path(str(root/'k1-u-reserve-control-mask-check.py'))['producer']
    rotate=runpy.run_path(str(root/'k1-upper-replay-map-check.py'))['rotation']
    producer('control',0x25,('T','U'),'W','X1','U')
    rotate('T',('T','U'),[('W','Q'),('Q','P7'),('P7','P8'),('P8','W')],['U','U'])
    producer('U',0x25,('T','U'),'X','V','control')
    rotate('marker',('T','U'),[('X','Y'),('Y','Z'),('Z','T'),('T','X')],['control','control'])
    producer('T',0x25,('Z','U'),'X','U','control')
    rotate('marker',('Z','U'),[('X','Y'),('Y','Z'),('Z','T'),('T','X')],['control','control'])
    producer('control',0x14,('Y',),'X','X1','Z')
    runpy.run_path(str(root/'k1-repeat-entry-adapter-path-check.py'))['remove_y']()
    formatter=runpy.run_path(str(root/'k1-q-formatter-check.py'))['check']
    formatter(9,0,source_slot='Q',marker_slots=('marker','T','U'),target_by_class=['X']*8+['W'])
    formatter(9,0,source_slot='X',marker_slots=('marker','Z','U'),target_by_class=['V']*5+['Q']*2+['X']*2)
    formatter(0,0,True,source_slot='X',marker_slots=('marker','Y'),target_by_class=['U']*4+['X']*5)
    formatter(9,0,source_slot='X',marker_slots=('marker',),target_by_class=['X']*9)
    formatter(0,5,True,source_slot='X',marker_slots=('marker',),target_by_class=['X']*9)
    print('LIMIT: local ROM contracts only; not arbitrary timing, unbounded repetition, or full K1.',flush=True)
