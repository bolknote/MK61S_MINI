#!/usr/bin/env python3
"""Compile actual power.cpp against a host-only SDK clock/register boundary."""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile
ROOT=Path(__file__).resolve().parents[1]
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=ROOT/'ports/picocalc/power.cpp')
    parser.add_argument('--source-root',type=Path,default=ROOT)
    args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='picocalc-power-') as directory:
        build=Path(directory)
        for name in ('hardware/clocks.h','hardware/irq.h','hardware/pll.h',
                     'hardware/structs/scb.h','hardware/uart.h','hardware/timer.h',
                     'hardware/sync.h','pico/stdlib.h','tusb.h'):
            path=build/name;path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text('#include "picocalc_power_sdk.hpp"\n')
        command=[os.environ.get('CXX','clang++'),'-std=c++17','-O2','-Wall','-Wextra','-Werror',
                 '-I'+str(build),'-I'+str(ROOT/'tests/fixtures'),
                 '-I'+str(args.source.resolve().parent),
                 '-I'+str(args.source_root/'ports/picocalc'),'-I'+str(args.source_root/'code')]
        if os.environ.get('MK61_TEST_SANITIZERS')=='1':
            command+=['-fsanitize=address,undefined','-fno-omit-frame-pointer']
        subprocess.run(command+[str(ROOT/'tests/picocalc_power_self_test.cpp'),
                                str(args.source.resolve()),'-o',str(build/'test')],check=True)
        subprocess.run([str(build/'test')],check=True)
if __name__=='__main__':main()
