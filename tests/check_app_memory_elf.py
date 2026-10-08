#!/usr/bin/env python3
"""Check the ABI 6 shared dynamic-RAM range and newlib allocator binding."""
import argparse
import struct
import zlib
from pathlib import Path


APP_MAX_SIZE = 20 * 1024
STAGE_INDEX_SIZE = 640 * 4
APP_ALIGNMENT = 32


def app_memory_size(path):
    data = path.read_bytes()
    assert len(data) >= 64 and data[:8] == b'MK61APP\0', f'{path}: invalid APP header'
    assert struct.unpack_from('<3H', data, 8) == (1, 64, 6), f'{path}: incompatible APP'
    assert data[14] in (1, 2, 3, 5, 6, 7, 8, 9, 10, 11), f'{path}: not a System APP'
    assert zlib.crc32(data[:60]) == struct.unpack_from('<I', data, 60)[0], f'{path}: header CRC'
    stored, image, memory = struct.unpack_from('<3I', data, 24)
    assert len(data) == 64 + stored, f'{path}: truncated APP'
    assert zlib.crc32(data[64:]) == struct.unpack_from('<I', data, 48)[0], f'{path}: stored CRC'
    assert 0 < image <= memory <= APP_MAX_SIZE, f'{path}: invalid APP memory size'
    return memory


def system_memory_sizes(directory):
    apps = sorted(directory.glob('*.APP'))
    assert apps, f'{directory}: System APP bundle is missing or empty'
    sizes = {path.name: app_memory_size(path) for path in apps}
    disk = directory / 'USBDISK.APP'
    assert disk.name in sizes, f'{directory}: USBDISK.APP is missing'
    assert disk.read_bytes()[14] == 8, f'{disk}: incorrect USBDISK kind'
    return max(sizes.values()), sizes[disk.name]


def check_pool(free, disk_memory):
    # APP_MAX_SIZE is a format ceiling, not a reserved allocation. Qualify the
    # actual USB module against the full (512-KiB-volume) staging index.
    # Other APPs may release an unlocked stage cache, never a live index.
    assert free >= APP_MAX_SIZE, f'maximum standalone APP cannot fit: {free} < {APP_MAX_SIZE}'
    rounded = (disk_memory + APP_ALIGNMENT - 1) & ~(APP_ALIGNMENT - 1)
    assert free >= rounded + STAGE_INDEX_SIZE, (
        f'USBDISK APP and full stage index cannot coexist: '
        f'{free} < {rounded} + {STAGE_INDEX_SIZE}')


def check(path, module_memory=APP_MAX_SIZE, disk_memory=APP_MAX_SIZE):
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
    check_pool(free, disk_memory)
    # Some builds never call malloc, so section GC may remove both _sbrk
    # implementations. If present, it must be our strong override, not Core's.
    assert '_sbrk' not in symbols or symbols['_sbrk'][1] == 1, 'weak Core _sbrk can overlap APP'
    print(f'APP RAM: {path}: reserve=0 free={free} system_max={module_memory} '
          f'usbdisk={disk_memory} stage={STAGE_INDEX_SIZE} top={end:#x} heap=guarded PASS')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--system-dir', type=Path,
                        help='qualify every APP in the matching built System bundle')
    parser.add_argument('elf', type=Path, nargs='+')
    args = parser.parse_args()
    memory, disk = (system_memory_sizes(args.system_dir) if args.system_dir
                    else (APP_MAX_SIZE, APP_MAX_SIZE))
    for path in args.elf:
        check(path, memory, disk)
