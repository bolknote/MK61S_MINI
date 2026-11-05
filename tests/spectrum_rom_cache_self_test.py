#!/usr/bin/env python3
"""Keep a data-only UF2 out of the firmware image and settings sectors."""

import sys as _repo_sys
from pathlib import Path as _RepoPath
_repo_sys.path.insert(0, str(_RepoPath(__file__).resolve().parents[1]))
from pathlib import Path
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from tools.apps.spectrum.spectrum_rom_cache import CAPACITY, FLASH_OFFSET, NAMES, prepare, validate_uf2


class CacheTransportTests(unittest.TestCase):
    def test_flash_boundaries_and_corrupt_addresses(self):
        with tempfile.TemporaryDirectory(prefix='mk61-rom-cache-') as temporary:
            folder = Path(temporary)
            for index, name in enumerate(NAMES):
                (folder / name).write_bytes(bytes([index]) * (8192 if index == 4 else 16384))
            record = prepare(folder)
            transport = (folder / 'ROMCACHE.uf2').read_bytes()
            self.assertEqual(len(validate_uf2(transport, FLASH_OFFSET)), record['written_bytes'])
            self.assertLessEqual(FLASH_OFFSET + record['written_bytes'], 0x1E0000)
            with self.assertRaisesRegex(ValueError, 'firmware overlaps'):
                validate_uf2(transport, FLASH_OFFSET + 1)
            for offset, value in ((12, 0x10000000), (12, 0x101FE000),
                                  (16, 512), (20, 1), (28, 0)):
                altered = bytearray(transport)
                struct.pack_into('<I', altered, offset, value)
                with self.assertRaisesRegex(ValueError, 'block/address'):
                    validate_uf2(altered)
            for altered in (b'', transport[:-1], transport + bytes(512 * (CAPACITY // 256))):
                with self.assertRaises(ValueError):
                    validate_uf2(altered)


if __name__ == '__main__':
    unittest.main()
