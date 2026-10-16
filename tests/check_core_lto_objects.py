#!/usr/bin/env python3
"""Verify the shipping F411 core is native while cold objects retain LTO."""
import argparse
import json
from pathlib import Path
import subprocess
from check_usb_cdc_rx_elf import objdump_from_database
from analyze_stack_usage import entry_arguments


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compile-commands', type=Path, required=True)
    args = parser.parse_args()
    entries = json.loads(args.compile_commands.read_text())
    core = next(v for v in entries if v['file'].endswith('/mk61emu_core.cpp'))
    flags = entry_arguments(next(v for v in entries if v['file'].endswith('/terminal.cpp')))
    lto = False
    for flag in flags:
        if flag == '-flto' or flag.startswith('-flto='):
            lto = True
        elif flag == '-fno-lto':
            lto = False
    if '-DSTM32F411xE' not in flags or not lto:
        print('Core LTO objects: native F411 policy not required')
    else:
        tool = objdump_from_database(args.compile_commands)
        for filename, expected in (('mk61emu_core.cpp', False), ('terminal.cpp', True)):
            entry = next(v for v in entries if v['file'].endswith('/' + filename))
            command = entry_arguments(entry)
            obj = Path(command[command.index('-o') + 1])
            if not obj.is_absolute():
                obj = Path(entry['directory']) / obj
            sections = subprocess.check_output([str(tool), '-h', str(obj)], text=True)
            present = '.gnu.lto_' in sections
            if present != expected:
                raise SystemExit(f'{filename}: expected LTO={expected}, actual={present}')
        print('Core LTO objects: native core + LTO cold firmware OK')
