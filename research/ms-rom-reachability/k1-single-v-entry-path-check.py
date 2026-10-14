#!/usr/bin/env python3
"""Conditional F-comma dispatch: arbitrary X -> V after accepted U.

The keyboard prefix and the late formatter are separate native checks.
"""
import runpy
from pathlib import Path

writer=runpy.run_path(str(Path(__file__).with_name('check_ms_e9_upper_path.py')))['writer']
writer('T',request=0x25)
print('PASS accepted U and request 25h: connected primary path copies arbitrary X into V.',flush=True)
print('LIMIT: conditional primary copier, not a complete upper exchange or cleanup.',flush=True)
