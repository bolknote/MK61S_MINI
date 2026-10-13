#!/usr/bin/env python3
"""Reject a CDC image that bypasses the receive guard or loses USB GPIO init."""
import argparse
from pathlib import Path
import re
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from release_contract import discover_binutils


def objdump_from_database(database: Path) -> Path:
    _, nm = discover_binutils(database)
    suffix = '.exe' if nm.suffix.lower() == '.exe' else ''
    tool = nm.with_name(nm.name[:-len('nm' + suffix)] + 'objdump' + suffix)
    if not tool.is_file():
        raise ValueError(f'objdump tool not found beside compiler: {tool}')
    return tool


def check(disassembly: str) -> None:
    calls = re.findall(r'\s(?:b|bl|blx)(?:\.[a-z]+)?\s+[0-9a-f]+\s+<([^>]+)>', disassembly)
    if '__wrap_USBD_CDC_ClearBuffer' not in calls:
        raise ValueError('no call reaches the CDC receive guard')
    if 'USBD_CDC_ClearBuffer' in calls:
        raise ValueError('CDC queue-full call bypasses --wrap (LTO resolved it early)')
    functions = dict(re.findall(
        r'^[0-9a-f]+ <([^>]+)>:\n(.*?)(?=\n[0-9a-f]+ <|\Z)',
        disassembly, re.M | re.S))
    pending = ['USBD_LL_Init']
    visited = set()
    while pending:
        name = pending.pop()
        if name in visited:
            continue
        visited.add(name)
        body = functions.get(name, '')
        targets = re.findall(
            r'\s(?:b|bl|blx)(?:\.[a-z]+)?\s+[0-9a-f]+\s+<([^>]+)>', body)
        if any(re.fullmatch(r'(?:pin_function|HAL_GPIO_Init)(?:\..*)?', t)
               for t in targets):
            return
        # Fully inlined F4 setup still has actual GPIOA and RCC references.
        if '0x40020000' in body and '0x40023800' in body:
            return
        pending.extend(t for t in targets
                       if re.fullmatch(r'HAL_PCD_(?:Init|MspInit)(?:\..*)?', t))
    raise ValueError('USB initialization lost its hardware GPIO/MSP path')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf', type=Path)
    tool = parser.add_mutually_exclusive_group(required=True)
    tool.add_argument('--objdump')
    tool.add_argument('--compile-commands', type=Path)
    args = parser.parse_args()
    objdump = args.objdump or objdump_from_database(args.compile_commands)
    check(subprocess.check_output([str(objdump), '-d', str(args.elf)], text=True))
    print('USB CDC receive ELF check: OK')
