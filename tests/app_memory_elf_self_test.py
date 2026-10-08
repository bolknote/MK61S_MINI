#!/usr/bin/env python3
"""The release gate must use APP RAM (including BSS), not file/image size."""
from pathlib import Path
import struct
import tempfile
import unittest
import zlib

import check_app_memory_elf as gate


def app(memory, kind=8):
    data = bytearray(68)
    data[:8] = b'MK61APP\0'
    struct.pack_into('<3HBB', data, 8, 1, 64, 6, kind, 1)
    struct.pack_into('<3I', data, 24, 4, 8, memory)
    struct.pack_into('<I', data, 48, zlib.crc32(data[64:]))
    struct.pack_into('<I', data, 60, zlib.crc32(data[:60]))
    return data


class AppMemoryTests(unittest.TestCase):
    def test_qualified_system_bundle_and_largest_stage(self):
        self.assertEqual(gate.STAGE_INDEX_SIZE, 2560)
        gate.check_pool(21728, 18624)
        # A larger future module must fail; the old 1536-byte check would pass.
        with self.assertRaisesRegex(AssertionError, 'full stage index'):
            gate.check_pool(21728, 19200)
        with self.assertRaisesRegex(AssertionError, 'standalone APP'):
            gate.check_pool(gate.APP_MAX_SIZE - 1, 1024)

    def test_allocator_alignment_and_conservative_default(self):
        gate.check_pool(21184, 18624)
        with self.assertRaisesRegex(AssertionError, 'full stage index'):
            gate.check_pool(21184, 18625)
        gate.check_pool(23040, gate.APP_MAX_SIZE)
        with self.assertRaisesRegex(AssertionError, 'full stage index'):
            gate.check_pool(23039, gate.APP_MAX_SIZE)

    def test_bundle_reads_memory_including_bss_and_all_modules(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaisesRegex(AssertionError, 'missing or empty'):
                gate.system_memory_size(root)
            disk = root / 'USBDISK.APP'
            disk.write_bytes(app(18624))
            (root / 'BASIC.APP').write_bytes(app(20001, kind=2))
            self.assertEqual(gate.app_memory_size(disk), 18624)
            self.assertEqual(gate.system_memory_size(root), 20001)
            disk.write_bytes(app(18624)[:-1])
            with self.assertRaisesRegex(AssertionError, 'truncated'):
                gate.app_memory_size(disk)
            for offset, message in ((32, 'header CRC'), (64, 'stored CRC')):
                data = app(18624)
                data[offset] ^= 1
                disk.write_bytes(data)
                with self.assertRaisesRegex(AssertionError, message):
                    gate.app_memory_size(disk)
            disk.write_bytes(app(gate.APP_MAX_SIZE + 1))
            with self.assertRaisesRegex(AssertionError, 'memory size'):
                gate.app_memory_size(disk)


if __name__ == '__main__':
    unittest.main()
