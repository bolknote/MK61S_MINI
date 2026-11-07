#!/usr/bin/env python3
"""Host-only guards for the exact physical AI phase; never opens a device."""
import json
from pathlib import Path
import plistlib
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import hil_mk61_ai as hil


class Guards(unittest.TestCase):
    READY = ("BUILD=12345678 SERVICE=CLOSED RUNTIME=NONE UI=CALCULATOR RUN=0 USB_DISK=0 "
             "PHYSICAL_KEYS=0 MATH_TEST=OK failures=0 KBD=OK PSRAM=OK BYTES=8388608 "
             "SD=OK FIRMWARE_CRC=valid EXPECTED=ABCDEF01 ACTUAL=ABCDEF01")

    def test_cached_usb_mapping_checks_both_uid_and_port(self):
        device = {"USB Serial Number": hil.UID, "IORegistryEntryChildren": [{"IOCalloutDevice": hil.PORT}]}
        tree = [{"IORegistryEntryChildren": [device]}]  # Device behind a hub.
        with patch.object(hil.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, plistlib.dumps(tree))):
            hil.usb_identity()
        device["USB Serial Number"] = "ANOTHER_DEVICE"
        with patch.object(hil.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, plistlib.dumps(tree))):
            with self.assertRaisesRegex(ValueError, "mapping mismatch"):
                hil.usb_identity()

    def test_checksum_matches_system_posix_oracle(self):
        for n in (0, 1, 95, 96, 97, 65534, 65536, 70001):
            data = bytes((i * 31) & 255 for i in range(n))
            out = subprocess.run(["/usr/bin/cksum"], input=data, capture_output=True, check=True).stdout
            self.assertEqual(hil.checksum(data), int(out.split()[0]))

    def test_exact_grant_and_files_required_before_io(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            records = {}
            for name in ("uf2", "bin", "model", "launcher", "probe", "picotool"):
                p = root / name
                p.write_bytes(name.encode())
                records[name] = {"path": str(p), "bytes": p.stat().st_size, "sha256": hil.sha(p)}
            m = root / "manifest.json"
            m.write_text(json.dumps({"uf2_sha256": records["uf2"]["sha256"],
                                    "bin_sha256": records["bin"]["sha256"], "build_id": "12345678",
                                    "firmware_integrity": {"crc32": "ABCDEF01"}}))
            records["firmware_manifest"] = {"path": str(m), "bytes": m.stat().st_size, "sha256": hil.sha(m)}
            phase = root / "phase.json"
            grant = root / "grant.json"
            body = {"schema": 1, "uid": hil.UID, "port": hil.PORT, "save_or_restore": False,
                    "controller_sha256": hil.sha(hil.__file__), "deadline_seconds": 1680,
                    "entry_mode": "installed-image",
                    "model_transport": "exclusive-msc",
                    "nonce": "HILV2-GUARD-TEST-1", "payloads": records, "new_build": "12345678", "new_crc": "ABCDEF01"}
            phase.write_text(json.dumps(body))
            approval = {"phase_sha256": hil.sha(phase), "coordinator_thread": hil.COORDINATOR, "decision": "GO"}
            grant.write_text(json.dumps(approval))
            with patch.object(hil.os, "open", side_effect=AssertionError("physical I/O forbidden")):
                self.assertEqual(hil.validate(phase, grant)["uid"], hil.UID)
                (root / "model").write_bytes(b"changed")
                with self.assertRaisesRegex(ValueError, "payload mismatch"):
                    hil.validate(phase, grant)
                body["nonce"] = "HILV2-../../OTHER"
                phase.write_text(json.dumps(body))
                with self.assertRaisesRegex(ValueError, "missing GO"):
                    hil.validate(phase, grant)
                approval["phase_sha256"] = hil.sha(phase)
                grant.write_text(json.dumps(approval))
                with self.assertRaisesRegex(ValueError, "unique directory"):
                    hil.validate(phase, grant)

    def test_gap_in_readback_rejected(self):
        class Port:
            def command(self, *_):
                return b"@MKC:GET 2 0\r\n@MKC:DATA 1 FF\r\n@MKC:END 2 0\r\nmk61> "
        with self.assertRaisesRegex(ValueError, "offset mismatch"):
            hil.download(Port(), "/AI/test")

    def test_raw_boundary_predicates(self):
        s = self.READY
        self.assertTrue(hil.readiness(s, "12345678", "ABCDEF01")["ready"])
        for wrong in ("RUN=1", "PHYSICAL_KEYS=1", "SERVICE=APP", "FIRMWARE_CRC=invalid"):
            key = wrong.split("=")[0] + "="
            old = next(w for w in s.split() if w.startswith(key))
            with self.assertRaisesRegex(ValueError, "ready predicates"):
                hil.readiness(s.replace(old, wrong), "12345678", "ABCDEF01")

    def test_collisions_and_failed_mkdir_never_become_owned_or_removed(self):
        phase = {"new_build": "12345678", "new_crc": "ABCDEF01"}
        target = "/AI/HILV2-TEST-12345678"
        for failure in ("exists", "parent-error", "parent-usage", "parent-wrong-echo", "mkdir-error", "not-empty"):
            calls = []

            class Port:
                def status(self):
                    return Guards.READY

                def send(self, value):
                    calls.append(value)

                def remaining(self, value):
                    return value

                def commands(self):
                    pass

                def command(self, command, *_):
                    calls.append(command)
                    echo = command.encode() + b"\r\n"
                    if command == 'ls "/AI"' and failure == "exists":
                        return echo + b"d\tHILV2-TEST-12345678/\r\n1 entry.\r\nmk61> "
                    if command == 'ls "/AI"' and failure == "parent-error":
                        return echo + b"ERROR\r\nmk61> "
                    if command == 'ls "/AI"' and failure == "parent-usage":
                        return echo + b"Usage: ls PATH\r\nmk61> "
                    if command == 'ls "/AI"' and failure == "parent-wrong-echo":
                        return b'ls "/OTHER"\r\n0 entries.\r\nmk61> '
                    if command.startswith("mkdir") and failure == "mkdir-error":
                        return echo + b"ERROR\r\nmk61> "
                    if command == 'ls "' + target + '"' and failure == "not-empty":
                        return echo + b"f\t1 B\tother.txt\r\n1 entry.\r\nmk61> "
                    if command.startswith("ls "):
                        return echo + b"0 entries.\r\nmk61> "
                    return echo + b"mk61> "

            with tempfile.TemporaryDirectory() as directory:
                owned = []
                with self.assertRaises(ValueError):
                    hil.create_owned(Port(), target, owned, Path(directory))
                self.assertEqual(owned, [])
                if failure.startswith("parent-") or failure == "exists":
                    self.assertFalse(any(isinstance(x, str) and x.startswith("mkdir ") for x in calls))
                with patch.object(hil, "usb_identity"):
                    hil.cleanup(Port(), phase, owned, set())
                self.assertFalse(any(isinstance(x, str) and x.startswith("rm ") for x in calls))

    def test_successful_empty_create_records_ownership(self):
        class Port:
            def command(self, command):
                return command.encode() + b"\r\n" + (b"0 entries.\r\n" if command.startswith("ls ") else b"") + b"mk61> "
        with tempfile.TemporaryDirectory() as directory:
            owned = []
            path = "/AI/HILV2-TEST-12345678"
            hil.create_owned(Port(), path, owned, Path(directory))
            self.assertEqual(json.loads((Path(directory) / "owned.json").read_text()), [path])

    def test_leave_timeout_closes_without_cleanup_commands(self):
        calls = []

        class Port:
            def status(self):
                return Guards.READY

            def command(self, command, *_):
                raise AssertionError("cleanup command after leave timeout: " + command)

            def close(self):
                calls.append("close")

        with patch.object(hil, "usb_identity"), patch.object(hil, "leave_app", side_effect=TimeoutError("leave timeout")):
            with self.assertRaises(TimeoutError):
                hil.cleanup(Port(), {"new_build": "12345678", "new_crc": "ABCDEF01"}, ["/AI/HILV2-TEST-12345678"], set(),
                            lambda _: self.fail("partial callback after leave timeout"))
        self.assertEqual(calls, ["close"])

    def test_failed_initial_readiness_only_closes(self):
        calls = []

        class Port:
            fd = 42

            def status(self):
                calls.append("status")
                return "BUILD=UNKNOWN SERVICE=OPEN RUNTIME=APP"

            def close(self):
                calls.append("close")
                self.fd = -1

            def commands(self):
                raise AssertionError("commands sent before native acceptance")

            def send(self, *_):
                raise AssertionError("mutation sent before native acceptance")

        phase = {"deadline_seconds": 1680, "_sha": "test", "payloads": {},
                 "new_build": "12345678", "new_crc": "ABCDEF01"}
        with tempfile.TemporaryDirectory() as directory, patch.object(hil, "Serial", return_value=Port()), patch.object(hil, "wait_usb_identity"):
            with self.assertRaises(RuntimeError):
                hil.worker(phase, Path(directory))
        self.assertEqual(calls, ["status", "close"])

    def test_reenumeration_wait_and_bound(self):
        with patch.object(hil, "usb_identity", side_effect=[ValueError("not enumerated"), None]) as check, patch.object(hil.time, "sleep"):
            hil.wait_usb_identity()
            self.assertEqual(check.call_count, 2)
        with patch.object(hil, "usb_identity", side_effect=ValueError("not enumerated")), patch.object(hil.time, "monotonic", side_effect=[0, 21]):
            with self.assertRaisesRegex(ValueError, "not enumerated"):
                hil.wait_usb_identity()

    def test_continuation_contains_no_flash_or_reboot_commands(self):
        import inspect
        source = inspect.getsource(hil.worker)
        self.assertNotIn("subprocess.", source)
        self.assertNotIn("picotool", source)
        self.assertNotIn("\\x1e!", source)

    def test_msc_uses_uid_ancestor_not_disk_name(self):
        tree = [{"USB Serial Number": "OTHER", "IORegistryEntryChildren": [{"Whole": True, "BSD Name": "disk99"}]}]
        result = subprocess.CompletedProcess([], 0, plistlib.dumps(tree))
        with patch.object(hil.subprocess, "run", return_value=result), patch.object(hil, "disk_plist", side_effect=AssertionError("foreign diskutil query")):
            with self.assertRaisesRegex(ValueError, "no unique whole"):
                hil.bound_whole_disk()
        tree[0]["USB Serial Number"] = hil.UID
        result.stdout = plistlib.dumps(tree)
        metadata = {"DeviceIdentifier": "disk99", "BusProtocol": "USB", "Internal": False,
                    "WholeDisk": True, "Writable": True, "DeviceBlockSize": 512, "Size": 32 * 1024**3}
        with patch.object(hil.subprocess, "run", return_value=result), patch.object(hil, "disk_plist", return_value=metadata):
            self.assertEqual(hil.bound_whole_disk(), "disk99")
            metadata["Internal"] = True
            with self.assertRaisesRegex(ValueError, "unsafe whole"):
                hil.bound_whole_disk()

    def test_msc_eject_failure_never_returns_card_to_native(self):
        calls = []

        class Port:
            def remaining(self, seconds):
                return seconds

            def status(self):
                return Guards.READY if not calls else "USB_DISK=1 SERVICE=USB_DISK"

            def command(self, command, *_):
                calls.append(command)

        with tempfile.TemporaryDirectory() as output:
            with patch.object(hil, "usb_identity"), patch.object(hil, "bound_whole_disk", return_value="disk99"), patch.object(hil, "mounted_partition", side_effect=OSError("mount unavailable")), patch.object(hil.subprocess, "run", return_value=subprocess.CompletedProcess([], 1, b"busy", b"")) as run:
                with self.assertRaisesRegex(ValueError, "safe MSC eject failed"):
                    hil.install_model_msc(Port(), {"new_build": "12345678", "new_crc": "ABCDEF01"}, Path(output), b"model")
                self.assertEqual(calls, ["usbdisk"])
                self.assertEqual(run.call_args.args[0], ["/usr/sbin/diskutil", "eject", "disk99"])

    def test_bad_upload_ack_retains_raw_reply(self):
        raw = b"fsput data 0 00\r\nERROR\r\nmk61> "

        class Port:
            data = bytearray()

            def command(self, command):
                return b"@MKC:READY 1\r\nmk61> "

            def send(self, *_):
                pass

            def wait(self, *_):
                return raw

        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "fault.bin"
            with self.assertRaisesRegex(ValueError, "ACK mismatch"):
                hil.upload(Port(), "/AI/small", b"\0", target)
            self.assertEqual(target.read_bytes(), raw)

    def test_configured_early_cancel_and_budget_are_finite(self):
        clock = [0]
        sent = []

        class Port:
            data = bytearray()

            def remaining(self, seconds):
                self.seconds = seconds
                return seconds

            def send(self, data):
                sent.append(data)
                self.data.extend(b"AI_BENCH mode=0 step=0 begin\r\n" if data.startswith(b"run ") else b"AI_CANCEL\r\nmk61> ")

            def pump(self):
                clock[0] += 0.01

        with patch.object(hil.time, "monotonic", side_effect=lambda: clock[0]):
            latency = hil.benchmark(Port(), "/Apps/owned/bench.APP", cancel=True, seconds=90, cancel_step=0)
        self.assertGreaterEqual(latency, 0)
        self.assertEqual(sent[-1], b"\x1b")
        self.assertEqual(len(sent), 2)
        sent.clear()
        with self.assertRaisesRegex(ValueError, "schedule"):
            hil.benchmark(Port(), "/Apps/owned/bench.APP", seconds=1201)
        self.assertEqual(sent, [])

    def test_recovery_refuses_unknown_foreground_before_escape(self):
        class Port:
            def status(self):
                return Guards.READY.replace("SERVICE=CLOSED", "SERVICE=OPEN").replace("RUNTIME=NONE", "RUNTIME=APP") + " PATH=[/OTHER.APP]"

            def send(self, *_):
                raise AssertionError("escape sent into unknown APP")

        with patch.object(hil, "usb_identity"), self.assertRaisesRegex(ValueError, "foreground is not owned"):
            hil.cleanup(Port(), {"new_build": "12345678", "new_crc": "ABCDEF01"}, [], set())


if __name__ == "__main__":
    unittest.main()
