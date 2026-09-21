#!/usr/bin/env python3
import importlib.util
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("m8_codec", ROOT / "tools/m8_codec.py")
m8 = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(m8)


class M8CodecTest(unittest.TestCase):
    def test_roundtrip_and_private_symbols(self):
        text = "ASCII Ёжик → ≤ ↵ № €\n"
        encoded = m8.encode(text)
        self.assertEqual(encoded[11:14], bytes((0x0f, 0x20, 0x16)))
        self.assertEqual(m8.decode(encoded), text)

    def test_every_valid_byte_roundtrips(self):
        data = bytes(byte for byte in range(1, 256) if m8.valid_byte(byte))
        self.assertEqual(m8.encode(m8.decode(data)), data)

    def test_invalid_input_is_rejected(self):
        with self.assertRaises(UnicodeEncodeError):
            m8.encode("emoji 😀")
        for bad in (b"\0", b"\x01", b"\x7f", b"\x98"):
            with self.assertRaises(UnicodeDecodeError):
                m8.decode(bad)

    def test_file_bom_is_external_only(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source, encoded, decoded = root / "in.txt", root / "out.m8", root / "back.txt"
            source.write_bytes(b"\xef\xbb\xbf" + "Привет".encode())
            m8.encode_file(source, encoded)
            self.assertFalse(encoded.read_bytes().startswith(b"\xef\xbb\xbf"))
            m8.decode_file(encoded, decoded)
            self.assertEqual(decoded.read_text(), "Привет")

    def test_every_shipping_text_source_is_m8_representable(self):
        suffixes = {".m61", ".tbi", ".foc", ".txt", ".md", ".markdown"}
        for path in sorted((ROOT / "programs").rglob("*")):
            if path.is_file() and path.suffix.lower() in suffixes:
                with self.subTest(path=path.relative_to(ROOT)):
                    text = path.read_text(encoding="utf-8-sig")
                    self.assertEqual(m8.decode(m8.encode(text)), text)


if __name__ == "__main__":
    unittest.main()
