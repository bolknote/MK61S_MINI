#!/usr/bin/env python3

from __future__ import annotations

from dataclasses import dataclass
import tempfile
from pathlib import Path
import unittest

import hil_release_qualification as qualification
from hil_multi_device_identity import Identity, Target


def identity(public: str, usb: str, build: str, profile: str) -> Identity:
    return Identity(public, public[-8:], usb, "1234ABCD", build, profile)


class FakeDevice:
    def __init__(self, name: str, address: str) -> None:
        self.name = name
        self.address = address


class QualificationSelfTest(unittest.TestCase):
    def setUp(self) -> None:
        self.targets = {
            "uc1609": Target(
                "/dev/uc",
                identity("AEB505B6E0067623", "2068336B4731", "EDD35F1B",
                         qualification.UC1609_PROFILE),
            ),
            "ws0010": Target(
                "/dev/ws",
                identity("6FF33152484A4488", "3688388E3233", "3F1AC322",
                         qualification.WS0010_PROFILE),
            ),
        }

    def test_smoke_plan_assigns_every_meter_step_only_to_uc1609(self) -> None:
        plan = qualification.qualification_plan(
            "smoke", True, False, True, include_stop_power=True
        )
        meter_steps = [step for step in plan if step.requires_meter]
        self.assertEqual(len(meter_steps), 2)
        for step in meter_steps:
            self.assertEqual(step.target_roles, ("uc1609",))
            self.assertNotIn("{ws0010_port}", step.arguments)
        flash = next(
            step for step in meter_steps
            if step.script == "hil_fnb58_flash_power.py"
        )
        self.assertEqual(
            flash.arguments[flash.arguments.index("--passes") + 1], "16"
        )

    def test_release_counts_and_optional_dfu_are_explicit(self) -> None:
        without_dfu = qualification.qualification_plan(
            "release", False, False, False
        )[0]
        with_dfu = qualification.qualification_plan(
            "release", False, True, False
        )[0]
        args_without = qualification.materialize_arguments(
            without_dfu, self.targets, "", 0, ""
        )
        args_with = qualification.materialize_arguments(
            with_dfu, self.targets, "", 0, "/usr/bin/dfu-util"
        )
        self.assertEqual(args_without[args_without.index("--dfu-cycles") + 1], "0")
        self.assertEqual(args_with[args_with.index("--dfu-cycles") + 1], "20")
        self.assertNotIn("--dfu-util", args_without)
        self.assertIn("/usr/bin/dfu-util", args_with)

    def test_production_plan_does_not_force_usb_disconnect(self) -> None:
        plan = qualification.qualification_plan(
            "smoke", False, False, False
        )
        self.assertFalse(any(step.script == "hil_deep_idle.py" for step in plan))
        direct = qualification.qualification_plan(
            "smoke", False, False, False, include_direct_stop=True
        )
        self.assertEqual(
            sum(step.script == "hil_deep_idle.py" for step in direct), 2
        )

    def test_expected_identity_is_role_specific(self) -> None:
        qualification.require_expected_ids(
            self.targets, "AEB505B6E0067623", "6FF33152484A4488"
        )
        with self.assertRaisesRegex(AssertionError, "wrong ws0010 board"):
            qualification.require_expected_ids(
                self.targets, "AEB505B6E0067623", "0000000000000000"
            )

    def test_meter_selection_is_unambiguous_and_serial_aware(self) -> None:
        selected = qualification.select_meter(
            [FakeDevice("Other", "0"), FakeDevice("FNB58-051910", "1")],
            51910,
        )
        self.assertEqual(selected.address, "1")
        with self.assertRaisesRegex(AssertionError, "expected one FNB58"):
            qualification.select_meter(
                [FakeDevice("FNB58-051910", "1"),
                 FakeDevice("FNB58-051910", "2")],
                51910,
            )

    def test_evidence_is_atomic_and_markdown_links_logs(self) -> None:
        evidence = {
            "result": "passed",
            "mode": "smoke",
            "started_utc": "2026-09-01T00:00:00+00:00",
            "finished_utc": "2026-09-01T00:01:00+00:00",
            "git": {"sha": "abc"},
            "targets": [
                {"role": role, **vars(target.identity)}
                for role, target in self.targets.items()
            ],
            "meter": {
                "enabled": True, "name": "FNB58-051910", "address": "uuid",
                "serial": 51910,
            },
            "steps": [{
                "name": "smoke", "status": "passed",
                "duration_seconds": 1.25, "log": "smoke.log",
            }],
        }
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            qualification.write_evidence(output, evidence)
            self.assertTrue((output / "evidence.json").is_file())
            report = (output / "report.md").read_text(encoding="utf-8")
            self.assertIn("FNB58-051910", report)
            self.assertIn("[smoke.log](smoke.log)", report)
            self.assertFalse((output / "evidence.json.tmp").exists())


if __name__ == "__main__":
    unittest.main()
