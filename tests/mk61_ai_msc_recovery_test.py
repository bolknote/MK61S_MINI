#!/usr/bin/env python3
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import hil_mk61_ai as ai
import hil_mk61_ai_msc_recovery as recovery
from mk61_ai_hil_guard_test import Guards


class RecoveryGuards(unittest.TestCase):
    def run_case(self, initial, *, off_error=False, eject_timeout=False):
        calls = []

        class Port:
            fd = 42
            current = initial

            def status(self):
                calls.append("status")
                return self.current

            def commands(self):
                calls.append("commands")

            def command(self, command, *_, **__):
                calls.append(command)
                if command == "identity":
                    return ("UID=" + ai.UID).encode()
                if command == "usbdisk off":
                    if off_error:
                        return b"ERROR\r\nmk61> "
                    self.current = Guards.READY
                    return b"usbdisk off\r\nmk61> "
                if command.startswith("fsget"):
                    return b"ERROR\r\nmk61> "
                raise AssertionError(command)

            def send(self, data):
                calls.append(data)

            def close(self):
                calls.append("close")
                self.fd = -1

        phase = {"new_build": "12345678", "new_crc": "ABCDEF01", "model_sha256": "model"}
        with tempfile.TemporaryDirectory() as directory, patch.object(ai, "usb_identity"), patch.object(ai, "Serial", return_value=Port()), patch.object(ai, "bound_whole_disk", return_value="disk6"), patch.object(recovery.subprocess, "run", side_effect=subprocess.TimeoutExpired(["diskutil"], 90) if eject_timeout else AssertionError("unexpected external command")):
            try:
                recovery.recover(phase, Path(directory))
            except RuntimeError:
                pass
            return calls, json.loads((Path(directory) / "result.json").read_text())

    def test_unknown_foreground_only_closes(self):
        status = Guards.READY.replace("SERVICE=CLOSED", "SERVICE=OTHER").replace("RUNTIME=NONE", "RUNTIME=APP")
        calls, result = self.run_case(status)
        self.assertEqual(calls, ["status", "close"])
        self.assertFalse(result["passed"])

    def test_timeout_after_guarded_probe_never_sends_escape_or_off_again(self):
        status = Guards.READY.replace("SERVICE=CLOSED", "SERVICE=USB_DISK").replace("USB_DISK=0", "USB_DISK=1")
        calls, result = self.run_case(status, off_error=True, eject_timeout=True)
        self.assertEqual(calls.count("usbdisk off"), 1)
        self.assertFalse(any(isinstance(x, bytes) for x in calls))
        self.assertEqual(calls[-1], "close")
        self.assertFalse(result["passed"])

    def test_already_ejected_uses_firmware_guard_and_never_calls_diskutil(self):
        status = Guards.READY.replace("SERVICE=CLOSED", "SERVICE=USB_DISK").replace("USB_DISK=0", "USB_DISK=1")
        calls, result = self.run_case(status)
        self.assertTrue(result["passed"] and result["already_ejected"] and result["cdc_closed"])
        self.assertFalse(result["model_present"])
        self.assertEqual(calls.count("usbdisk off"), 1)


if __name__ == "__main__":
    unittest.main()
