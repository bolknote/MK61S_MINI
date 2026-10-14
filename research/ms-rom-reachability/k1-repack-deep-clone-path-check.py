#!/usr/bin/env python3
"""Conditional SIGN dispatch from accepted U: exact arbitrary X -> V.

This proves the connected primary copier, not the keyboard prefix or the
other chips' actions. The native test supplies the logical marker as X.
"""
import runpy
from pathlib import Path

writer=runpy.run_path(str(Path(__file__).with_name('check_ms_e9_upper_path.py')))['writer']
writer('T',request=0x32)
print('PASS accepted U and request 32h: connected primary path copies arbitrary X into V.',flush=True)
print('LIMIT: marker placement, late formatting, other chips and normal exit are separate obligations.',flush=True)
