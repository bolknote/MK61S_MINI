#!/usr/bin/env python3
import importlib.util
from pathlib import Path
import struct
import unittest

spec = importlib.util.spec_from_file_location("picocalc_uf2", Path(__file__).resolve().parents[1] / "ports/picocalc/uf2.py")
uf2 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(uf2)


class TransportTests(unittest.TestCase):
    def test_rom_headers_and_reassembly(self):
        image = bytes(range(256)) + b"last byte"
        data = uf2.encode(image)
        self.assertEqual(len(data), 1024)
        first = struct.unpack_from("<8I", data)
        self.assertEqual(first, (0x0A324655, 0x9E5D5157, 0x2000, 0x10000000,
                                 256, 0, 2, 0xE48BFF56))
        self.assertEqual(struct.unpack_from("<I", data, 508)[0], 0x0AB16F30)
        self.assertEqual(struct.unpack_from("<I", data, 512 + 12)[0], 0x10000100)
        self.assertEqual(data[32:288] + data[544:553], image)
        uf2.validate(data, image)

    def test_exact_block_has_no_extra_write(self):
        self.assertEqual(len(uf2.encode(bytes(256))), 512)

    def test_rejects_wrong_family_and_corruption(self):
        image = bytes(512)
        for offset in (0, 8, 12, 16, 20, 24, 28, 32, 508):
            data = bytearray(uf2.encode(image))
            data[offset] ^= 1
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                uf2.validate(data, image)

    def test_board_capacity(self):
        for image in (b"", bytes(2 * 1024 * 1024 + 1)):
            with self.assertRaises(ValueError):
                uf2.encode(image)


if __name__ == "__main__":
    unittest.main()
