#!/usr/bin/env python3
"""Bound frames retained while STM32 foreground APPs run, in the shipping ELF."""
import argparse
from pathlib import Path
import re
import subprocess
from check_usb_cdc_rx_elf import objdump_from_database

def frame_size(body: str) -> int:
    size = 0
    for line in body.splitlines():
        if re.search(r'\s(?:bl|blx)\s', line):
            break
        allocation = re.search(r'\b(?:sub|subw)(?:\.w)?\s+sp,\s*(?:sp,\s*)?#(\d+)', line)
        if allocation:
            size += int(allocation[1])
        elif re.search(r'\b(?:sub|subw)(?:\.w)?\s+sp,', line):
            raise ValueError('cannot bound a register-sized stack allocation')
        registers = re.search(r'\b(push|vpush|stmdb)\b[^\{]*\{([^}]+)\}', line)
        if registers:
            count = 0
            for item in registers[2].split(','):
                item = item.strip()
                span = re.fullmatch(r'[rd](\d+)-[rd](\d+)', item)
                count += int(span[2]) - int(span[1]) + 1 if span else 1
            size += count * (8 if registers[1] == 'vpush' else 4)
    return size

def check(disassembly: str) -> dict:
    functions = dict(re.findall(r'^[0-9a-f]+ <([^>]+)>:\n(.*?)(?=\n[0-9a-f]+ <|\Z)',
                               disassembly, re.M | re.S))
    result = {}
    for pattern, limit, label in ((r'main', 128, 'main'),
                                 (r'class_terminal::execute\(bool, bool\)(?: \[clone .*\])?',
                                  768, 'terminal dispatch')):
        matches = [(name, body) for name, body in functions.items() if re.fullmatch(pattern, name)]
        if not matches:
            raise ValueError('missing ' + label)
        size = max(frame_size(body) for name, body in matches)
        if size > limit:
            raise ValueError(f'{label} retains {size} stack bytes, limit {limit}')
        result[label] = size
    return result

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf', type=Path)
    parser.add_argument('--compile-commands', type=Path, required=True)
    args = parser.parse_args()
    tool = objdump_from_database(args.compile_commands)
    result = check(subprocess.check_output([str(tool), '-d', '-C', str(args.elf)], text=True))
    print('Foreground stack ELF check: OK', result)
