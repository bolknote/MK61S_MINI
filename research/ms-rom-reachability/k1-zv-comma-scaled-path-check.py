#!/usr/bin/env python3
"""Local contracts for two scaled test operands; not an arithmetic theorem.

The actual reciprocal value and inter-chip ordering remain obligations of
the separate complete native runs, with no injected emulator snapshots.
"""
import runpy
from pathlib import Path

root=Path(__file__).resolve().parent
sign=runpy.run_path(str(root/'k1-zv-comma-exit-path-check.py'))['sign']
for header in ('003','983'):
    sign(header)
fmt=runpy.run_path(str(root/'k1-q-formatter-check.py'))['check']
fmt(0,4,True,source_slot='X',marker_slots=('marker','Z'),target_by_class=['X']*9)
fmt(9,5,source_slot='X',marker_slots=('marker','Z'),target_by_class=['X']*9)
for header in (0,9):
    fmt(header,0,source_slot='X',marker_slots=('marker','Z'),target_by_class=['V']*9)
for markers in (('marker','T'),('marker',)):
    fmt(0,5,True,source_slot='X',marker_slots=markers,target_by_class=['X']*9)
print('PASS selected CHS and formatter contracts. LIMIT: neither arbitrary R8 nor '
      'reciprocal arithmetic/timing nor repeated full-bank exchange is proved.',flush=True)
