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
    helper=(path.name.upper()=='VMSTORE.APP' and path.parent.name.upper()=='VMCACHE') or path.name.upper() in ('SRCEDIT.APP', 'TERMINAL.APP', 'CLOCK.APP')
    assert data[14] in ((4,) if helper else (1, 2, 3, 5, 6, 7, 8, 9, 10, 11)), f'{path}: not a System APP'
    assert zlib.crc32(data[:60]) == struct.unpack_from('<I', data, 60)[0], f'{path}: header CRC'
    stored, image, memory = struct.unpack_from('<3I', data, 24)
    assert len(data) == 64 + stored, f'{path}: truncated APP'
    assert zlib.crc32(data[64:]) == struct.unpack_from('<I', data, 48)[0], f'{path}: stored CRC'
    assert 0 < image <= memory <= APP_MAX_SIZE, f'{path}: invalid APP memory size'
    return memory


def system_memory_sizes(directory):
    apps = sorted(directory.glob('*.APP'))
    helper=directory/'VMCache/VMSTORE.APP'
    if helper.is_file():apps.append(helper)
    assert apps, f'{directory}: System APP bundle is missing or empty'
    sizes = {path.name: app_memory_size(path) for path in apps}
    disk = directory / 'USBDISK.APP'
    assert disk.name in sizes, f'{directory}: USBDISK.APP is missing'
    assert disk.read_bytes()[14] == 8, f'{disk}: incorrect USBDISK kind'
    return max(sizes.values()), sizes[disk.name]


def check_pool(free, disk_memory, msc_memory=0, fs_memory=0, disk_credit=0):
    # APP_MAX_SIZE is a format ceiling, not a reserved allocation. Qualify the
    # actual USB module against the full (512-KiB-volume) staging index.
    # Other APPs may release an unlocked stage cache, never a live index.
    fs_rounded = (fs_memory + 7) & ~7
    assert free >= APP_MAX_SIZE + fs_rounded, f'maximum standalone APP plus filesystem temporaries cannot fit: {free} < {APP_MAX_SIZE} + {fs_rounded}'
    rounded = (disk_memory + APP_ALIGNMENT - 1) & ~(APP_ALIGNMENT - 1)
    msc_rounded = (msc_memory + 7) & ~7
    assert free + disk_credit >= rounded + STAGE_INDEX_SIZE + msc_rounded + fs_rounded, (
        f'USBDISK APP, full stage index, MSC session buffer and filesystem temporaries cannot coexist: '
        f'{free} + {disk_credit} < {rounded} + {STAGE_INDEX_SIZE} + {msc_rounded} + {fs_rounded}')


def thumb_calls(code, base, target):
    """Decode Thumb BL without requiring a platform-specific objdump."""
    for offset in range(0, len(code) - 3, 2):
        first, second = struct.unpack_from('<HH', code, offset)
        if first & 0xF800 != 0xF000 or second & 0xD000 != 0xD000:
            continue
        sign = (first >> 10) & 1
        i1 = 1 ^ ((second >> 13) & 1) ^ sign
        i2 = 1 ^ ((second >> 11) & 1) ^ sign
        displacement = ((sign << 24) | (i1 << 23) | (i2 << 22) |
                        ((first & 1023) << 12) | ((second & 2047) << 1))
        if sign:
            displacement -= 1 << 25
        if base + offset + 4 + displacement == (target & ~1):
            return True
    return False


def disk_graphics_credit(data, sections, symbols, sizes):
    if symbols.get('mk61_usbdisk_graphics_exclusive', (0, 0))[0] != 1:
        return 0
    graphics = symbols.get('mk61_lazy_basic_graphics_bytes', (0, 0))[0]
    if not graphics:
        return 0
    prepare = '_ZN16usb_mass_storage7prepareEv'
    guard = '_ZN14basic_graphics17prepare_disk_modeEv'
    assert prepare in symbols and guard in symbols, 'disk/graphics exclusion guard is missing'
    address = symbols[prepare][0] & ~1
    for section in sections:
        if section[3] <= address and address + sizes[prepare] <= section[3] + section[5]:
            begin = section[4] + address - section[3]
            code = data[begin:begin + sizes[prepare]]
            assert thumb_calls(code, address, symbols[guard][0]), 'USB preparation bypasses graphics guard'
            return graphics
    raise AssertionError('USB preparation code is missing')


def effective_pool(free, symbols):
    lazy = sum(symbols.get(name, (0, 0))[0] for name in (
        'mk61_lazy_workspace_bytes', 'mk61_lazy_bulk_bytes',
        'mk61_lazy_vm_cache_bytes', 'mk61_lazy_msc_bytes',
        'mk61_lazy_basic_graphics_bytes'))
    # Qualify the same simultaneous live state even when its bytes are no
    # longer permanently in BSS. Idle savings must not weaken the APP gate.
    scoped = sum(symbols.get(name, (0, 0))[0] for name in (
        'mk61_m61_runtime_bytes', 'mk61_usb_framebuffer_bytes',
        'mk61_storage_workspace_bytes'))
    # Worst case after every retained/foreground buffer has been initialized.
    # High gaps may need up to 224 bytes before a 256-aligned APP end.
    placement = symbols.get('mk61_app_placement_slack_bytes', (0, 0))[0]
    effective = (free - lazy - scoped - placement) & ~(APP_ALIGNMENT - 1)
    return effective, lazy, scoped, placement


def check(path, module_memory=APP_MAX_SIZE, disk_memory=APP_MAX_SIZE):
    data = path.read_bytes()
    h = struct.unpack_from('<16sHHIIIIIHHHHHH', data)
    assert h[0][:6] == b'\x7fELF\x01\x01' and h[2] == 40, 'expected ARM ELF32 LE'
    sections = [struct.unpack_from('<10I', data, h[6] + i * h[11]) for i in range(h[12])]
    symbols = {}
    sizes = {}
    for s in sections:
        if s[1] != 2:
            continue
        strings = sections[s[6]]
        names = data[strings[4]:strings[4] + strings[5]]
        for off in range(s[4], s[4] + s[5], s[9]):
            name, value, size, info, _, index = struct.unpack_from('<IIIBBH', data, off)
            if index:
                key = names[name:names.find(b'\0', name)].decode()
                symbols[key] = (value, info >> 4)
                sizes[key] = size
    value = lambda name: symbols[name][0]
    assert 'mk61_module_overlay' not in symbols, 'fixed APP reserve returned'
    assert 0x20000000 <= value('_sdata') <= value('_edata') <= value('_sbss')
    assert value('_ebss') <= value('_end') <= value('__mk61_dynamic_begin')
    assert value('__mk61_dynamic_begin') == (value('_end') + 7) & ~7
    end = value('__mk61_dynamic_end')
    assert end in (0x2000D700, 0x2001BF00), 'stack/guard budget changed'
    free = end - value('__mk61_dynamic_begin')
    effective, lazy, scoped, placement = effective_pool(free, symbols)
    assert effective >= 0, 'lazy resident buffers exceed dynamic RAM'
    msc = symbols.get('mk61_session_msc_bytes', (0, 0))[0]
    fs = symbols.get('mk61_fs_temporary_bytes', (0, 0))[0]
    credit = disk_graphics_credit(data, sections, symbols, sizes)
    check_pool(effective, disk_memory, msc, fs, credit)
    # Some builds never call malloc, so section GC may remove both _sbrk
    # implementations. If present, it must be our strong override, not Core's.
    assert '_sbrk' not in symbols or symbols['_sbrk'][1] == 1, 'weak Core _sbrk can overlap APP'
    print(f'APP RAM: {path}: reserve=0 free={free} system_max={module_memory} '
          f'lazy={lazy} scoped={scoped} placement={placement} effective={effective} usbdisk={disk_memory} stage={STAGE_INDEX_SIZE} '
          f'msc_session={msc} fs_temporary={fs} disk_graphics_credit={credit} top={end:#x} heap=guarded PASS')


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
