#!/usr/bin/env python3
"""Compile the actual resident frame loop against a delayed host LCD."""
import argparse, os, subprocess, tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--main',type=Path,default=ROOT/'ports/picocalc/main.cpp')
    args=parser.parse_args()
    source=args.main.read_text()
    start='        const u64 frame_started=time_us_64();\n        if(frame_started >= next_frame) {'
    end='        if(screen.bootloader_pending() &&'
    assert source.count(start)==1 and source.count(end)==1,'resident frame extraction boundary changed'
    block=source[source.index(start):source.index(end,source.index(start))]
    with tempfile.TemporaryDirectory(prefix='picocalc-frame-schedule-') as tmp:
        work=Path(tmp);(work/'picocalc_frame_schedule_production.inc').write_text(block)
        flags=['-fsanitize=address,undefined','-fno-omit-frame-pointer'] if os.environ.get('MK61_TEST_SANITIZERS')=='1' else []
        binary=work/'test'
        subprocess.run([os.environ.get('CXX','clang++'),'-std=c++17','-O2','-Wall','-Wextra','-Werror',*flags,
            '-I'+str(work),'-I'+str(ROOT/'ports/picocalc'),str(ROOT/'tests/picocalc_frame_schedule_self_test.cpp'),'-o',str(binary)],check=True)
        subprocess.run([str(binary)],check=True)
if __name__=='__main__': main()
