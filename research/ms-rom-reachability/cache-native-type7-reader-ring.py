#!/usr/bin/env python3
"""Native early T7 plus two remaining early conditional fields.

The complete native source is validated on ALL5 fields/wires/phase/tags.
The native calculator receives only keys; T7 is NOT assigned in the model.
Only ordinary C.M1[24]=F and working X.M2[22]=F are counterfactual, before
the native last AC. All256^3 raw program triples vary jointly.
"""
import json
from pathlib import Path
import runpy
import subprocess
import sys

root = Path(__file__).resolve().parent
r = runpy.run_path(str(root / 'cache-digit-redirect-ring.py'))
data = json.loads(subprocess.check_output(
    ['node', str(root / 'cache-early-type7-native.cjs'), '--proof-input'], text=True))
# These functions share their execution-module globals, not necessarily the
# copy returned by run_path. Replace the NATIVE input, never any ROM/model.
r['source_run'].__globals__['data'] = data
assert r['baseline'].__globals__['data'] is data
assert r['conditional'].__globals__['data'] is data
if '--conditional-only' not in sys.argv:
    r['baseline']()
if '--baseline-only' not in sys.argv:
    r['conditional']('X', 'T', prepare_header=False)
