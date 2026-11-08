#!/usr/bin/env python3
"""Run the production hardware CRC adapter against an RM0008 register model."""
from pathlib import Path
import subprocess
import tempfile
ROOT=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='mk61-f103-crc-') as temporary:
    work=Path(temporary)
    (work/'stm32f1xx.h').write_text('/* Register proxies are defined by the C++ test. */\n')
    binary=work/'test'
    subprocess.run(['clang++','-std=c++17','-O2','-Wall','-Wextra','-Werror',
                    '-fsanitize=address,undefined','-fno-sanitize-recover=all',
                    '-I'+str(work),'-I'+str(ROOT/'ports/picocalc'),
                    str(ROOT/'tests/picocalc_stm3_crc_self_test.cpp'),'-o',str(binary)],check=True)
    subprocess.run([str(binary)],check=True)
