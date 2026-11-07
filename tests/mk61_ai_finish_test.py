#!/usr/bin/env python3
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import hil_mk61_ai as ai
import hil_mk61_ai_finish as finish


class FinishGuards(unittest.TestCase):
    def test_flash_native_mismatch_closes_before_rom_or_picotool(self):
        calls = []

        class Port:
            def status(self):
                calls.append("status")
                return "BUILD=UNKNOWN"

            def close(self):
                calls.append("close")

            def commands(self):
                raise AssertionError("commands before acceptance")

        with tempfile.TemporaryDirectory() as directory, patch.object(ai, "usb_identity"), patch.object(ai, "Serial", return_value=Port()), patch.object(finish, "drain", return_value=0), patch.object(finish.subprocess, "run", side_effect=AssertionError("picotool before acceptance")):
            with self.assertRaises(ValueError):
                finish.flash_once({"old_build": "12345678", "old_crc": "ABCDEF01"}, Path(directory))
        self.assertEqual(calls, ["status", "close"])

    def test_native_mismatch_closes_without_commands_or_cleanup(self):
        calls = []

        class Port:
            fd = 42

            def status(self):
                calls.append("status")
                return "BUILD=UNKNOWN SERVICE=OTHER"

            def close(self):
                calls.append("close")
                self.fd = -1

            def commands(self):
                raise AssertionError("command before acceptance")

        with tempfile.TemporaryDirectory() as directory, patch.object(ai, "usb_identity"), patch.object(ai, "Serial", return_value=Port()), patch.object(finish, "drain", return_value=0):
            with self.assertRaises(RuntimeError):
                finish.worker({"new_build": "12345678", "new_crc": "ABCDEF01"}, Path(directory))
            result = json.loads((Path(directory) / "result.json").read_text())
            self.assertFalse(result["passed"])
            self.assertTrue(result["cdc_closed"])
        self.assertEqual(calls, ["status", "close"])

    def test_drain_sends_no_keys_and_waits_after_last_output(self):
        clock = [0]

        class Port:
            data = bytearray()

            def remaining(self, seconds):
                return seconds

            def pump(self, *_):
                clock[0] += 1
                if clock[0] == 1:
                    self.data.extend(b"@MKC:DATA 1 FF\r\n")
                if clock[0] == 3:
                    self.data.extend(b"@MKC:END\r\nmk61> ")

            def send(self, *_):
                raise AssertionError("command while draining")

        with patch.object(finish.time, "monotonic", side_effect=lambda: clock[0]):
            self.assertGreater(finish.drain(Port()), 0)
        self.assertEqual(clock[0], 8)

    def test_continuation_has_no_model_write_or_msc(self):
        import inspect
        source = inspect.getsource(finish.worker)
        self.assertNotIn("install_model_msc", source)
        self.assertNotIn("usbdisk", source)
        self.assertNotIn("subprocess.", source)


if __name__ == "__main__":
    unittest.main()
