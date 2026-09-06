#!/usr/bin/env python3
"""Keep ELF debug metadata out of APPs without overlooking allocated sections."""
from pathlib import Path
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools/.mk61-app'))
from app_relocations import extract

BASE = 0x20000000


def elf_fixture(extra_name, extra_flags=0, extra_size=4, debug_relocations=False):
    # A linked ARM ELF with one initialized pointer to its BSS, plus an orphan
    # section. It needs no host ARM toolchain, so all CI hosts exercise the gate.
    names = ['', '.module_image', '.module_bss', '.symtab',
             '.rel.module_image', '.shstrtab', extra_name, '.rel.debug_frame']
    strings = b''
    offsets = []
    for name in names:
        offsets.append(len(strings))
        strings += name.encode('ascii') + b'\0'
    data = bytearray(52)
    sections = [(0,) * 10]

    def section(index, kind, flags, address, payload, size=None, link=0, info=0, entry=0):
        data.extend(bytes(-len(data) % 4))
        offset = len(data)
        data.extend(payload)
        sections.append((offsets[index], kind, flags, address, offset,
                         len(payload) if size is None else size, link, info, 4, entry))

    section(1, 1, 3, BASE, struct.pack('<I', BASE + 4))
    section(2, 8, 3, BASE + 4, b'', size=4)
    symbols = bytes(16) + struct.pack('<IIIBBH', 0, BASE + 4, 4, 1, 0, 2)
    section(3, 2, 0, 0, symbols, link=5, info=2, entry=16)
    section(4, 9, 0, 0, struct.pack('<II', BASE, (1 << 8) | 2), link=3, info=1, entry=8)
    section(5, 3, 0, 0, strings)
    section(6, 1, extra_flags, 0, bytes(extra_size))
    if debug_relocations:
        # Debug-only relocations need not be APP-supported relocation kinds.
        section(7, 9, 0, 0, struct.pack('<II', 0, (1 << 8) | 255), link=3, info=6, entry=8)
    data.extend(bytes(-len(data) % 4))
    section_offset = len(data)
    for header in sections:
        data.extend(struct.pack('<10I', *header))
    struct.pack_into('<16sHHIIIIIHHHHHH', data, 0,
                     b'\x7fELF\x01\x01\x01' + bytes(9), 2, 40, 1, BASE, 0,
                     section_offset, 0, 52, 0, 0, 40, len(sections), 5)
    return data


class AppSectionTests(unittest.TestCase):
    def extract_fixture(self, *args, **kwargs):
        with tempfile.TemporaryDirectory(prefix='mk61-elf-sections-') as directory:
            elf = Path(directory) / 'app.elf'
            elf.write_bytes(elf_fixture(*args, **kwargs))
            return extract(elf, BASE, 4, 8)

    def test_debug_metadata_preserves_pointer_relocations(self):
        self.assertEqual(self.extract_fixture('.debug_frame'), ([0], b'\0'))

    def test_debug_relocations_are_not_runtime_relocations(self):
        self.assertEqual(self.extract_fixture('.debug_frame', debug_relocations=True),
                         ([0], b'\0'))

    def test_other_metadata_does_not_need_packing(self):
        self.assertEqual(self.extract_fixture('.metadata'), ([0], b'\0'))

    def test_allocated_orphan_is_rejected_regardless_of_name(self):
        for name in ('.unexpected', '.debug_frame', '.rel.unexpected'):
            with self.subTest(name=name):
                with self.assertRaisesRegex(ValueError, 'unpacked ELF section'):
                    self.extract_fixture(name, extra_flags=2)

    def test_empty_orphan_needs_no_storage(self):
        self.assertEqual(self.extract_fixture('.empty', extra_flags=2, extra_size=0),
                         ([0], b'\0'))


if __name__ == '__main__':
    unittest.main()
