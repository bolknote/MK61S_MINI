"""Reduce a linked ARM ELF's relocation records to bounded APP word fixups.

The firmware never parses ELF. Unsupported relocation types fail the build;
integers that happen to look like SRAM addresses are never guessed as pointers.
"""
import struct
from pathlib import Path

ABS32 = 2
PC_RELATIVE = {3, 10, 30, 42}  # REL32, THM_CALL, THM_JUMP24, PREL31


def encode_offsets(offsets):
    output = bytearray()
    end = 0
    for offset in offsets:
        gap = offset - end
        if gap < 0 or offset > 20480 - 4:
            raise ValueError('overlapping or out-of-range APP relocation')
        while gap >= 128:
            output.append((gap & 127) | 128)
            gap >>= 7
        output.append(gap)
        end = offset + 4
    return bytes(output)


def extract(path: Path, base: int, image_size: int, memory_size: int):
    data = path.read_bytes()
    if len(data) < 52:
        raise ValueError('truncated ELF')
    h = struct.unpack_from('<16sHHIIIIIHHHHHH', data)
    if h[0][:7] != b'\x7fELF\x01\x01\x01' or h[1:3] != (2, 40) or h[11] != 40:
        raise ValueError('expected linked little-endian ARM ELF32')
    sections = [struct.unpack_from('<10I', data, h[6] + i * 40) for i in range(h[12])]
    def contents(section):
        start, size = section[4:6]
        if start > len(data) or size > len(data) - start:
            raise ValueError('truncated ELF section')
        return data[start:start + size]
    strings = contents(sections[h[13]])
    def name(section):
        start = section[0]
        return strings[start:strings.index(0, start)].decode('ascii')
    module_sections = {i for i, section in enumerate(sections)
                       if name(section) in ('.module_image', '.module_bss')}
    if not module_sections:
        raise ValueError('missing APP sections')
    offsets, records = [], 0
    for section in sections:
        if section[1] not in (4, 9):
            continue
        target = section[7]
        if not sections[target][2] & 2:  # Ignore relocations of debug metadata.
            continue
        if section[1] != 9 or section[9] != 8 or target not in module_sections:
            raise ValueError('unsupported ELF relocation section')
        table = contents(section)
        symbols = sections[section[6]]
        if symbols[1] != 2 or symbols[9] != 16:
            raise ValueError('invalid ELF symbol table')
        sym_data = contents(symbols)
        for i in range(0, len(table), 8):
            address, info = struct.unpack_from('<II', table, i)
            kind, symbol_index = info & 255, info >> 8
            symbol = struct.unpack_from('<IIIBBH', sym_data, symbol_index * 16)
            target_section = symbol[5]
            records += 1
            if kind in (0, 40):  # NONE, V4BX: no address changes on Cortex-M4.
                continue
            if kind in PC_RELATIVE:
                if target_section not in module_sections:
                    raise ValueError(f'PC-relative relocation {kind} leaves APP at {address:#x}')
                continue
            if kind != ABS32:
                raise ValueError(f'unsupported ARM relocation {kind} at {address:#x}; use -mword-relocations')
            if target_section == 0xfff1:  # SHN_ABS: deliberate fixed address, e.g. MMIO.
                continue
            if target_section not in module_sections:
                raise ValueError(f'absolute relocation leaves APP at {address:#x}')
            offset = address - base
            if offset < 0 or offset + 4 > image_size:
                raise ValueError('relocation destination outside image')
            source = sections[target]
            pointer = struct.unpack_from('<I', data, source[4] + address - source[3])[0]
            if not base <= pointer <= base + memory_size:
                raise ValueError('relocation target outside APP memory (including one-past-end)')
            offsets.append(offset)
    if not records:
        raise ValueError('ELF contains no relocation records; link with --emit-relocs')
    offsets.sort()
    return offsets, encode_offsets(offsets)
