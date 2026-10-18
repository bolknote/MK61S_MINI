#!/usr/bin/env python3
"""Reject libgcc archive members in a PicoCalc owned-runtime link map."""
import argparse
from pathlib import Path
import re

def check(path):
    text=Path(path).read_text()
    if 'Linker script and memory map' not in text:
        raise ValueError('Not a GNU linker map')
    # A LOAD libgcc.a line is harmless: it contributes no code. Reject any
    # extracted member, even if section GC subsequently discards part of it.
    if re.search(r'(?<![A-Za-z0-9_])libgcc\.a\(',text):
        raise ValueError('Unexpected libgcc archive member in owned M0 firmware')
    for symbol in ('__aeabi_dadd','__aeabi_ddiv','__aeabi_fmul','__aeabi_llsr','mk61_m0_sqrtf'):
        if not re.search(r'\b'+re.escape(symbol)+r'\b',text):
            raise ValueError('M0 runtime export missing: '+symbol)
    for source in ('native_eabi_m0.cpp.o','native_eabi_m0.S.o'):
        if source not in text:raise ValueError('M0 runtime source missing: '+source)
    print('Owned ARMv6-M runtime: no libgcc archive members PASS')

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('map',type=Path)
    args=parser.parse_args()
    try:check(args.map)
    except ValueError as error:parser.exit(1,str(error)+'\n')
