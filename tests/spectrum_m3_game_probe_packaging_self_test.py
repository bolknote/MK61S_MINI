#!/usr/bin/env python3
"""Regression test: a finite Spectrum probe is never packaged without its ROMs."""
import importlib.util
from pathlib import Path
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/'tools/apps/spectrum/build_spectrum_m3_game_probe.py'
sys.path.insert(0,str(SCRIPT.parent))
spec=importlib.util.spec_from_file_location('spectrum_m3_game_probe',SCRIPT)
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

with tempfile.TemporaryDirectory() as temporary:
    root=Path(temporary);runtime=root/'runtime';app=root/'app'
    runtime.mkdir();app.mkdir()
    files={'AY.S3M':b'S3M1'+bytes(60),'48.rom':bytes(16384),
           '128-0.rom':bytes([1])*16384,'128-1.rom':bytes([2])*16384}
    for name,data in files.items():(runtime/name).write_bytes(data)
    hashes=module.stage_runtime(runtime,app)
    assert set(hashes)==set(files)
    assert all((app/name).read_bytes()==data for name,data in files.items())
    alternate=module.stage_runtime(runtime,app,'AY32.S3M')
    assert set(alternate)=={'AY32.S3M','48.rom','128-0.rom','128-1.rom'}
    assert (app/'AY32.S3M').read_bytes()==files['AY.S3M']
    try:module.stage_runtime(runtime,app,'../AY.S3M')
    except ValueError as error:assert 'basename' in str(error)
    else:raise AssertionError('module path traversal accepted')
    (runtime/'48.rom').write_bytes(b'short')
    try:module.stage_runtime(runtime,app)
    except ValueError as error:assert '16384' in str(error)
    else:raise AssertionError('short 48.rom was accepted')

print('Spectrum M3 game probes include AY.S3M and all three exact-size ROMs: PASS')
