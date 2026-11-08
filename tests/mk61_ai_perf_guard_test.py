#!/usr/bin/env python3
import copy
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock, patch
import hil_mk61_ai_perf as perf


class Guards(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ai-perf-guard-")
        self.root = Path(self.temp.name)
        self.phase = self.root / "phase.json"
        self.grant = self.root / "grant.json"
        self.config = dict(kernel=2, arithmetic=3, cores=2, freeze=1, filter=0,
                           mhz=125, prefill=2, decode=2, repeat=1, stress_ms=0, control=0, constrained=0)
        self.raw = ("AIPERF1\n" + "".join(f"{k}={v}\n" for k, v in self.config.items())).encode()
        def payload(name, data):
            p = self.root / name;p.write_bytes(data)
            return {"path": str(p), "bytes": p.stat().st_size, "sha256": perf.ai.sha(p)}
        items = {k: payload(k, b"owned-fixture") for k in ("benchmark", "hashprobe", "model")}
        items["config"] = payload("config", self.raw)
        items["firmware_manifest"] = payload("manifest", json.dumps({
            "build_id": "ABCDEF12", "firmware_integrity": {"crc32": "1234ABCD"},
            "ai_overclock_diagnostic": False}).encode())
        source = self.root / "source";source.write_bytes(b"source-pin")
        self.p = dict(schema=3, uid=perf.ai.UID, port=perf.ai.PORT, save_or_restore=False,
                      deadline_seconds=850, action="perf", script_sha256=perf.ai.sha(perf.__file__),
                      helper_sha256=perf.ai.sha(perf.ai.__file__), finish_helper_sha256=perf.ai.sha(perf.finish.__file__),
                      nonce="HILV3-GUARD-20261106", new_build="ABCDEF12", new_crc="1234ABCD",
                      source_pins={str(source): perf.ai.sha(source)}, payloads=items, config=self.config,
                      alternate_model=False, expected_usb_reenumerations=0, cancel_at=None)
        self.g = dict(decision="GO", coordinator_thread=perf.ai.COORDINATOR,
                      not_before=999, start_before=1030, finish_before=1850)
        self.write()
    def tearDown(self):
        self.temp.cleanup()
    def write(self):
        self.phase.write_text(json.dumps(self.p))
        self.g["phase_sha256"] = perf.ai.sha(self.phase)
        self.grant.write_text(json.dumps(self.g))
    def check(self):
        return perf.validate(self.phase, self.grant, now=1000)
    def test_valid_read_only_validation(self):
        with patch.object(perf.ai, "Serial", side_effect=AssertionError("physical I/O")):
            self.assertEqual(self.check()[0]["config"], self.config)
    def test_grant_time_and_identity(self):
        original = copy.deepcopy(self.g)
        for key, value in (("decision", "NO"), ("coordinator_thread", "other"),
                           ("not_before", 1001), ("start_before", 999), ("finish_before", 3000),
                           ("finish_before", "1850")):
            self.g = dict(original, **{key: value});self.write()
            with self.assertRaises(ValueError): self.check()
    def test_source_and_payload_pins(self):
        for name in ("model", "benchmark", "config"):
            path = Path(self.p["payloads"][name]["path"]);old = path.read_bytes()
            path.write_bytes(old + b"x")
            with self.assertRaises(ValueError): self.check()
            path.write_bytes(old)
        Path(next(iter(self.p["source_pins"]))).write_bytes(b"changed")
        with self.assertRaises(ValueError): self.check()
    def test_scope_cannot_expand(self):
        original = copy.deepcopy(self.p)
        for key, value in (("uid", "OTHER"), ("port", "/dev/other"), ("action", "reset"),
                           ("save_or_restore", True), ("nonce", "../OTHER"), ("deadline_seconds", 9999),
                           ("expected_usb_reenumerations", 2)):
            self.p = dict(original, **{key: value});self.write()
            with self.assertRaises(ValueError): self.check()
    def test_parser_rejects_unsupported_requests(self):
        self.assertEqual(perf.parse_config(self.raw), self.config)
        for raw in (self.raw + b"mhz=300\n", self.raw.replace(b"mhz=125", b"mhz=301"),
                    self.raw.replace(b"cores=2", b"cores=0"), self.raw.replace(b"kernel=2", b"kernel=0"),
                    self.raw.replace(b"filter=0", b"filter=1"), self.raw.replace(b"\n", b"\r\n"),
                    self.raw + b"unknown=1\n", self.raw + b"\0"):
            with self.assertRaises((ValueError, UnicodeError)): perf.parse_config(raw)
    def test_oc_requires_separate_image_and_scope(self):
        self.p["config"] = dict(self.config, mhz=250)
        path = Path(self.p["payloads"]["config"]["path"])
        path.write_bytes(self.raw.replace(b"mhz=125", b"mhz=250"))
        self.p["payloads"]["config"].update(bytes=path.stat().st_size, sha256=perf.ai.sha(path))
        self.p["expected_usb_reenumerations"] = 2;self.write()
        with self.assertRaises(ValueError): self.check()
    def test_prefetch_requires_explicit_version_and_valid_kernel(self):
        raw=self.raw.replace(b"AIPERF1",b"AIPERF2")+b"prefetch=1\n"
        self.assertEqual(perf.parse_config(raw),dict(self.config,prefetch=1))
        for invalid in (raw.replace(b"prefetch=1",b"prefetch=2"),
                        self.raw+b"prefetch=1\n",raw.replace(b"AIPERF2",b"AIPERF1"),
                        raw.replace(b"cores=2",b"cores=1").replace(b"kernel=2",b"kernel=0"),
                        raw+b"prefetch=1\n"):
            with self.assertRaises(ValueError): perf.parse_config(invalid)
    def test_preflight_fault_closes_without_cleanup(self):
        p = Mock();p.status.return_value = "BUILD=WRONG\n";p.fd = 17
        def close(): p.fd = -1
        p.close.side_effect = close
        grant = {"finish_before": time.time() + 850}
        with patch.object(perf.ai, "wait_usb_identity"), patch.object(perf.ai, "Serial", return_value=p), patch.object(perf.ai, "cleanup") as cleanup:
            with self.assertRaises(RuntimeError): perf.worker(self.p, grant, self.root)
            cleanup.assert_not_called();p.close.assert_called_once()
        receipt = json.loads((self.root / "receipt.json").read_text())
        self.assertEqual(receipt["status"], "HOLD")
        self.assertTrue(receipt["cdc_closed"])
        self.assertFalse(receipt["temporary_removed"])
    def test_m3_requires_same_arithmetic_clocks_and_pinned_module(self):
        raw=(self.raw.replace(b"AIPERF1",b"AIPERF2").replace(b"cores=2",b"cores=3")
             .replace(b"control=0",b"control=1")+b"prefetch=1\n")
        self.config=perf.parse_config(raw)
        self.p["config"]=self.config
        path=Path(self.p["payloads"]["config"]["path"]);path.write_bytes(raw)
        self.p["payloads"]["config"].update(bytes=len(raw),sha256=perf.ai.sha(path))
        self.write()
        with self.assertRaises(ValueError): self.check()
        module=self.root/"M3LINE.S3M";module.write_bytes(b"owned-module")
        self.p["payloads"]["m3_module"]={"path":str(module),"bytes":module.stat().st_size,"sha256":perf.ai.sha(module)}
        lease=self.root/"ROOT-PICO-LEASE-001.json";lease.write_bytes(b"lease-test-fixture")
        self.p.update(root_lease_path=str(lease),root_lease_inode=lease.stat().st_ino)
        self.write();self.assertEqual(self.check()[0]["config"]["cores"],3)
        module.write_bytes(b"changed-module")
        with self.assertRaises(ValueError): self.check()
        self.assertEqual(perf.parse_config(raw.replace(b"arithmetic=3",b"arithmetic=1"))["arithmetic"],1)
        for invalid in (raw.replace(b"arithmetic=3",b"arithmetic=2"),
                        raw.replace(b"mhz=125",b"mhz=250"),raw.replace(b"control=1",b"control=0"),
                        raw.replace(b"stress_ms=0",b"stress_ms=1")):
            with self.assertRaises(ValueError): perf.parse_config(invalid)
    def test_m3_health_keeps_only_counters_and_rejects_faults(self):
        values=dict(BOOTS=4,CRASH="NONE",SYS_HZ=125000000,PERI_HZ=48000000,PHYSICAL_KEYS=0,
                    SETTINGS_WRITES=0,RTC_SET=0,APP_BUFFERS=0,ERRORS=0,QPI_FALLBACKS=0,TAIL_TIMEOUTS=0,
                    CRC_ERRORS=0,DMA_TIMEOUTS=0,LCD_ERRORS=0,SD_SPEED_FALLBACKS=0,SD_PROBE_FAILURES=0,
                    I2C_TIMEOUTS=0,I2C_ABORTS=0,SCREEN_ERRORS=0)
        text=" ".join(f"{k}={v}" for k,v in values.items())+" RTC=private X=private"
        self.assertEqual(perf.m3_health(text),{k:str(v) for k,v in values.items()})
        for bad in (text.replace("I2C_ABORTS=0","I2C_ABORTS=1"),text.replace("APP_BUFFERS=0","APP_BUFFERS=1"),
                    text.replace("SYS_HZ=125000000","SYS_HZ=200000000"),text.replace("CRASH=NONE","CRASH=FAULT")):
            with self.assertRaises(ValueError): perf.m3_health(bad)
        startup=text.replace("I2C_ABORTS=0","I2C_ABORTS=7").replace("QPI_FALLBACKS=0","QPI_FALLBACKS=1")
        limits={"QPI_FALLBACKS":1,"I2C_ABORTS":64}
        self.assertEqual(perf.m3_health(startup,limits)["I2C_ABORTS"],"7")
        for bad in (startup.replace("I2C_TIMEOUTS=0","I2C_TIMEOUTS=1"),
                    startup.replace("I2C_ABORTS=7","I2C_ABORTS=65"),
                    startup.replace("QPI_FALLBACKS=1","QPI_FALLBACKS=2")):
            with self.assertRaises(ValueError): perf.m3_health(bad,limits)


if __name__ == "__main__": unittest.main()
