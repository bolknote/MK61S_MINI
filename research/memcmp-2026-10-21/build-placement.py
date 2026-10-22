#!/usr/bin/env python3
"""Prepare SRAM-versus-Flash copy/move APPs without altering prior experiments."""
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--operation', choices=('memcpy', 'memmove'), required=True)
parser.add_argument('--payload', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--directory', required=True)
parser.add_argument('--arm-toolchain-bin', type=Path, required=True)
args = parser.parse_args()
previous = HERE.parent / (args.operation + '-2026-10-21')
prefix, name, symbol = ('MCPY', 'COPYBEN', 'COPY') if args.operation == 'memcpy' else ('MOVE', 'MOVEBEN', 'MOVE')
assert re.fullmatch('/' + prefix + r'[A-Za-z0-9-]*', args.directory)
layout = json.loads((args.payload / 'layout.json').read_text())
assert layout['cpu'] == 'm0'
args.output.mkdir(parents=True, exist_ok=True)
source = (previous / 'benchmark.c').read_text()
entry = next(line for line in source.splitlines() if 'Copy functions[FUNCTIONS]=' in line)
replacement = entry + '\n' + f'''    report.h[25]=crc((const void*)PAYLOAD_BASE,PAYLOAD_BYTES);
    if(report.h[25]!=PAYLOAD_CRC) goto finished;
    functions[7]=(Copy)FLASH_{symbol};'''
source = source.replace(entry, replacement)
source = ('#define BENCH_ROOT ' + json.dumps(args.directory) + '\n#include ' +
          json.dumps(str((args.payload / 'flash-layout.h').resolve())) + '\n' + source)
(args.output / 'benchmark.c').write_text(source)
for filename in ('baseline-memory.h', 'candidates.S'):
    shutil.copyfile(previous / filename, args.output / filename)
subprocess.run([sys.executable, str(ROOT / 'tools/build_portable_app.py'),
                '--target', 'picocalc-pico-h', '--name', name,
                '--source', str(args.output / 'benchmark.c'),
                '--source', str(args.output / 'candidates.S'), '--output-dir', str(args.output / 'app'),
                '--arm-toolchain-bin', str(args.arm_toolchain_bin)], check=True)
metadata = dict(operation=args.operation, payload_sha256=layout['sha256'],
                flash_address=layout['entries'][symbol]['address'],
                column_7='flash', comparison='sdk is the same production algorithm in SRAM',
                app_sha256=hashlib.sha256((args.output / 'app' / (name + '.APP')).read_bytes()).hexdigest())
(args.output / 'placement.json').write_text(json.dumps(metadata, indent=2) + '\n')
