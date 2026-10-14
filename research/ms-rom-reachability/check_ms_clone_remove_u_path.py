#!/usr/bin/env python3
"""Conditional ROM suffixes: A carrier and single-word formatter erasure.

This also runs the existing formatter regressions. Full native entry and
display-based stopping are independent checks in the JS tests.
"""
import runpy
from pathlib import Path
root=Path(__file__).parent
runpy.run_path(str(root/'check_ms_single_pointer_paths.py'))['marker_carrier']('X1')
q=runpy.run_path(str(root/'check_ms_guard_formatter.py'))
q['check']('cloned_W_remove_U','958912345678','marker',9,0x42,'U',
           ('marker','X','Y','U','W'))
q['check']('cloned_W_clear_destroys_sixth','000000000000','Z',0,0x43,'P8',
           ('marker','X','Y','W'))
print('LIMIT: conditional A7/formatter suffixes, not preparation, whole-ROM key timing or a full K1 operation.',flush=True)
