#!/usr/bin/env python3
"""Reject an ELF whose CDC queue-full call bypasses the NAK wrapper."""
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
