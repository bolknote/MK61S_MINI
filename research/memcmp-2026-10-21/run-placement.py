#!/usr/bin/env python3
"""Run a prepared copy/move placement APP using its original preservation runner."""
import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / 'tests'))
from transfer import write_file

assert len(sys.argv) > 1 and sys.argv[1] in ('memcpy', 'memmove'), 'First argument: memcpy or memmove'
operation = sys.argv.pop(1)
spec = importlib.util.spec_from_file_location('placement_runner', HERE.parent / (operation + '-2026-10-21/run.py'))
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
runner.NAMES[7] = 'flash'
runner.write_file = write_file
runner.main()
