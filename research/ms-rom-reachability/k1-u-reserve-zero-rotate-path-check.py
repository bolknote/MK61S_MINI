#!/usr/bin/env python3
"""Exact guarded rotation at real/T: no numerical absorption assumption."""
import runpy
from pathlib import Path

root=Path(__file__).resolve().parent
if __name__=='__main__':
    producer=runpy.run_path(str(root/'k1-u-reserve-control-mask-check.py'))['producer']
    producer('control',0x25,('T',),'W','X1','U')
    rotation=runpy.run_path(str(root/'k1-upper-replay-map-check.py'))['rotation']
    rotation('T',('T',),[('W','Q'),('Q','P7'),('P7','P8'),('P8','W')],['U','U'])
    formatter=runpy.run_path(str(root/'k1-q-formatter-check.py'))['check']
    formatter(0,7,True,True,source_slot='X',marker_slots=('marker','T'),target_by_class=['W']*6+['X']*3)
    clear_t=runpy.run_path(str(root/'k1-y-t-swap-v-path-check.py'))['clear_t']
    clear_t('control');clear_t('U')
    formatter(9,1,source_slot='X',marker_slots=('marker',),target_by_class=['X']*9)
    print('LIMIT: local accepted primary entry, secondary 6E(T)/R29=0/top3A/top3A, '
          'fixed markers, zero late X; no universal keyboard-entry or full K1 theorem.',flush=True)
