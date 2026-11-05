#!/usr/bin/env python3
"""Terminal output following a COBS frame abort remains readable."""
import binascii
import struct
import unittest
from unittest.mock import patch

from hil_portable_apps import ScreenPort, cobs_encode


class ParserTests(unittest.TestCase):
    def test_empty_abort_before_terminal_and_beacon(self):
        raw = b"MS\x02\x10\0" + struct.pack("<HH", 7, 0)
        raw += struct.pack("<H", binascii.crc_hqx(raw, 65535))
        packet = b"\0" + cobs_encode(raw) + b"\0"
        text = b"identity\r\nMK61 ID\r\n/> "
        for stream in (b"\0" + text, packet + b"\0" + text, b"\0" + packet + b"\0" + text + packet):
            with self.subTest(stream=stream):
                p = ScreenPort.__new__(ScreenPort)
                p.fd, p.lock_fd, p.attached, p.packet, p.text = 99, -1, False, None, bytearray()
                ticks = iter(i / 1000 for i in range(100))
                responses = iter([([99], [], [])] + [([], [], [])] * 100)
                with patch("hil_portable_apps.os.read", return_value=stream), \
                     patch("hil_portable_apps.select.select", side_effect=lambda *a: next(responses)), \
                     patch("hil_portable_apps.time.monotonic", side_effect=lambda: next(ticks)):
                    p.pump(.01)
                self.assertEqual(p.text, text)


if __name__ == "__main__":
    unittest.main()
