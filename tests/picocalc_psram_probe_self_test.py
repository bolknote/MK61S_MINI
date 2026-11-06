#!/usr/bin/env python3
"""Run the production PSRAM boot probe/policy against an explicit fake bus."""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='picocalc-psram-probe-') as directory:
    binary=Path(directory)/'probe'
    command=[os.environ.get('CXX','clang++'),'-std=c++17','-O2','-Wall','-Wextra','-Werror',
             '-I'+str(ROOT/'ports/picocalc'),'-I'+str(ROOT/'code')]
    if os.environ.get('MK61_TEST_SANITIZERS')=='1':
        command+=['-fsanitize=address,undefined','-fno-omit-frame-pointer']
    subprocess.run(command+[str(ROOT/'tests/picocalc_psram_probe_self_test.cpp'),'-o',str(binary)],check=True)
    subprocess.run([str(binary)],check=True)
