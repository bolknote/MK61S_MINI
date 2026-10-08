#!/usr/bin/env python3
"""Reject an ELF whose CDC queue-full call bypasses the NAK wrapper."""
import argparse
from pathlib import Path
import re
import subprocess


def check(disassembly: str) -> None:
    calls = re.findall(r'\s(?:b|bl|blx)(?:\.[a-z]+)?\s+[0-9a-f]+\s+<([^>]+)>', disassembly)
    if '__wrap_USBD_CDC_ClearBuffer' not in calls:
        raise ValueError('no call reaches the CDC receive guard')
    if 'USBD_CDC_ClearBuffer' in calls:
        raise ValueError('CDC queue-full call bypasses --wrap (LTO resolved it early)')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf', type=Path)
    parser.add_argument('--objdump', required=True)
    args = parser.parse_args()
    check(subprocess.check_output([args.objdump, '-d', str(args.elf)], text=True))
    print('USB CDC receive ELF check: OK')
