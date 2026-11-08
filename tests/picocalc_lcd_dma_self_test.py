#!/usr/bin/env python3
"""Exercise production LCD DMA setup/fill against a paced host endpoint."""
import os
from pathlib import Path
import subprocess
import tempfile
ROOT=Path(__file__).resolve().parents[1]
source=(ROOT/'ports/picocalc/hardware.cpp').read_text()
setup=source[source.index('void Panel::configure_dma(bool chain) {'):source.index('void Panel::abort_dma() {')]
finish=source[source.index('bool Panel::finish_scanline() {'):source.index('void Panel::transfer() {')]
worker=(ROOT/'ports/picocalc/io_worker.cpp').read_text()
wait=worker[worker.index('void wait_for_progress() {'):worker.index('void drain() {')]
with tempfile.TemporaryDirectory(prefix='picocalc-lcd-dma-') as directory:
    work=Path(directory);(work/'picocalc_lcd_dma_production.inc').write_text(
        'namespace io_worker {\n'+wait+'}\n'+setup+finish)
    command=[os.environ.get('CXX','clang++'),'-std=c++17','-O2','-Wall','-Wextra','-Werror',
             '-I'+str(work),'-I'+str(ROOT/'ports/picocalc'),'-I'+str(ROOT/'code')]
    if os.environ.get('MK61_TEST_SANITIZERS')=='1':command+=['-fsanitize=address,undefined','-fno-omit-frame-pointer']
    binary=work/'test'
    subprocess.run(command+[str(ROOT/'tests/picocalc_lcd_dma_self_test.cpp'),'-o',str(binary)],check=True)
    subprocess.run([str(binary)],check=True)
    probe=work/'probe-test'
    flags=['-fsanitize=address,undefined','-fno-omit-frame-pointer'] if os.environ.get('MK61_TEST_SANITIZERS')=='1' else []
    subprocess.run([os.environ.get('CC','clang'),'-std=c11','-O2','-Wall','-Wextra','-Werror',*flags,
                    '-I'+str(ROOT/'sdk/portable/include'),'-I'+str(ROOT/'code'),
                    str(ROOT/'tests/picocalc_lcd_color_probe_self_test.c'),'-o',str(probe)],check=True)
    subprocess.run([str(probe)],check=True)
