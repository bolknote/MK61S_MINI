#!/usr/bin/env python3
"""Check the shipped ABI 4 RAM layout and newlib allocator binding."""
import argparse
import struct
from pathlib import Path


def check(path):
    data = path.read_bytes()
    h = struct.unpack_from('<16sHHIIIIIHHHHHH', data)
    assert h[0][:6] == b'\x7fELF\x01\x01' and h[2] == 40, 'expected ARM ELF32 LE'
    sections = [struct.unpack_from('<10I', data, h[6] + i * h[11]) for i in range(h[12])]
    symbols = {}
    for s in sections:
        if s[1] != 2:
            continue
        strings = sections[s[6]]
        names = data[strings[4]:strings[4] + strings[5]]
        for off in range(s[4], s[4] + s[5], s[9]):
            name, value, _, info, _, index = struct.unpack_from('<IIIBBH', data, off)
            if index:
                symbols[names[name:names.find(b'\0', name)].decode()] = (value, info >> 4)
    value = lambda name: symbols[name][0]
    assert 'mk61_module_overlay' not in symbols, 'fixed APP reserve returned'
    assert 0x20000000 <= value('_sdata') <= value('_edata') <= value('_sbss')
    assert value('_ebss') <= value('_end') <= value('__mk61_dynamic_begin')
    assert value('__mk61_dynamic_begin') == (value('_end') + 7) & ~7
    end = value('__mk61_dynamic_end')
    assert end in (0x2000E700, 0x2001BF00), 'stack/guard budget changed'
    free = end - value('__mk61_dynamic_begin')
    assert free >= 20480 + 1536, 'maximum APP and C5 stage index must coexist'
    # Some builds never call malloc, so section GC may remove both _sbrk
    # implementations. If present, it must be our strong override, not Core's.
    assert '_sbrk' not in symbols or symbols['_sbrk'][1] == 1, 'weak Core _sbrk can overlap APP'
    print(f'APP RAM: {path}: reserve=0 free={free} top={end:#x} heap=guarded PASS')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf', type=Path, nargs='+')
    for path in parser.parse_args().elf:
        check(path)
