#!/usr/bin/env python3
"""Characterize the release matrix before its consumers are migrated."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
import sys

sys.path.insert(0, str(TOOLS))
import release_contract  # noqa: E402


class ReleaseContractTest(unittest.TestCase):
    def setUp(self):
        self.contract = release_contract.load_contract()
        self.profiles = release_contract.profile_index(self.contract)
        self.cases = release_contract.case_index(self.contract)

    def test_characterized_release_groups_are_complete_and_ordered(self):
        expected = {
            "f411-release": [
                "f411-lcd1602-a00",
                "f411-lcd1602-a00-usb-screen",
                "f411-lcd1602-a00-lto",
                "f411-lcd1602-a02",
                "f411-oled1602-ws0010",
                "f411-oled1602-ws0010-usb-screen",
                "f411-oled1602-ws0010-no-graphics",
                "f411-oled1602-ws0010-graphics-wbmp",
                "f411-oled1602-ws0010-graphics-wbmp-markdown",
                "f411-oled1602-ws0010-usb-screen-no-graphics",
                "f411-mini-v2-a00",
                "f411-mini-v2-a02",
                "f411-classic-v2",
                "f411-classic-v3",
                "f411-classic-v3-usb-screen",
                "f411-40th",
            ],
            "f411-stop": [
                "f411-stop-ws0010", "f411-stop-classic-v3-uc1609"
            ],
            "f401-arduino": ["f401-arduino-classic-v3"],
            "f401-product": [
                "f401-product-a00",
                "f401-product-ws0010",
                "f401-product-mini-v2-a00",
                "f401-product-classic-v3",
            ],
            "f401-capability": [
                "f401-capability-a00-usb",
                "f401-capability-ws-usb",
                "f401-capability-ws-graphics",
                "f401-capability-ws-usb-graphics",
            ],
        }
        for group, ids in expected.items():
            with self.subTest(group=group):
                actual = [case["id"] for case in
                          release_contract.cases_in_group(self.contract, group)]
                self.assertEqual(actual, ids)

    def test_profiles_are_the_existing_public_profile_set(self):
        self.assertEqual(
            list(self.profiles),
            ["mini-v3-a00", "mini-v3-a02", "mini-v3-ws0010",
             "mini-v2-a00", "mini-v2-a02", "classic-v2", "classic-v3",
             "40th"],
        )
        classic = self.profiles["classic-v3"]
        self.assertEqual(classic["defines"], ["MK61_BOARD_CLASSIC_V3"])
        self.assertEqual(classic["artifacts"]["f401"],
                         "mk61s-M-classic-v3-uc1609-f401")

    def test_product_and_laboratory_flash_contracts_differ_explicitly(self):
        for case in release_contract.cases_in_group(
                self.contract, "f401-product"):
            self.assertTrue(case["product"])
            self.assertEqual(case["budgets"]["flash_min_headroom"], 8192)
            self.assertEqual(case["budgets"]["ram_limit"], 52428)
        for case in release_contract.cases_in_group(
                self.contract, "f401-capability"):
            self.assertFalse(case["product"])
            self.assertEqual(case["budgets"]["flash_min_headroom"], 512)

    def test_profile_and_case_defines_are_combined_once(self):
        case = self.cases["f411-oled1602-ws0010-no-graphics"]
        self.assertEqual(
            release_contract.combined_defines(case, self.profiles),
            ["MK61_OLED1602_WS0010", "MK61_WS0010_GRAPHICS_100X16=0"],
        )

    def test_duplicate_case_and_definition_override_are_rejected(self):
        duplicate = copy.deepcopy(self.contract)
        duplicate["cases"].append(copy.deepcopy(duplicate["cases"][0]))
        with self.assertRaisesRegex(release_contract.ContractError,
                                    "duplicate case id"):
            release_contract.validate_contract(duplicate)

        override = copy.deepcopy(self.contract)
        target = next(case for case in override["cases"]
                      if case["id"] == "f411-oled1602-ws0010")
        target["defines"] = ["MK61_OLED1602_WS0010=1"]
        with self.assertRaisesRegex(release_contract.ContractError,
                                    "overridden twice"):
            release_contract.validate_contract(override)

    def test_invalid_product_budget_and_feature_set_are_rejected(self):
        weak = copy.deepcopy(self.contract)
        target = next(case for case in weak["cases"]
                      if case["id"] == "f401-product-a00")
        target["budgets"]["flash_min_headroom"] = 512
        with self.assertRaisesRegex(release_contract.ContractError,
                                    "at least 8192"):
            release_contract.validate_contract(weak)

        incomplete = copy.deepcopy(self.contract)
        target = next(case for case in incomplete["cases"]
                      if case["id"] == "f401-capability-a00-usb")
        del target["features"]["lto"]
        with self.assertRaisesRegex(release_contract.ContractError,
                                    "expected exactly"):
            release_contract.validate_contract(incomplete)

    def test_tsv_has_a_stable_column_count_even_for_empty_fields(self):
        flat = release_contract.flattened_case(
            self.cases["f401-product-a00"], self.profiles)
        row = "\t".join(release_contract.scalar_text(flat[field])
                        for field in release_contract.CASE_TSV_FIELDS)
        self.assertEqual(len(row.split("\t")),
                         len(release_contract.CASE_TSV_FIELDS))
        self.assertNotIn("\t\t", row)

    def test_resource_report_is_deterministic_and_enforces_budgets(self):
        size_summary = "text data bss dec hex filename\n100 20 30 150 96 resident.elf\n"
        sections = "resident.elf  :\nsection size addr\n.text 100 0\n.data 20 100\n.bss 30 120\n"
        symbols = "10 12 T second\n20 40 B largest object\n30 12 T alpha\n"
        outputs = [size_summary, sections, symbols]
        with tempfile.TemporaryDirectory(prefix="mk61-contract-") as temporary:
            root = Path(temporary)
            elf = root / "resident.elf"
            binary = root / "resident.bin"
            size_tool = root / "arm-none-eabi-size"
            nm_tool = root / "arm-none-eabi-nm"
            stack = root / "stack.json"
            elf.write_bytes(b"ELF")
            binary.write_bytes(bytes(1000))
            size_tool.write_text("stub", encoding="utf-8")
            nm_tool.write_text("stub", encoding="utf-8")
            stack.write_text(json.dumps({"schema": 1, "max_frame": 64}),
                             encoding="utf-8")
            with mock.patch.object(release_contract, "run_tool",
                                   side_effect=outputs):
                report = release_contract.resource_report(
                    self.contract, "f401-product-a00", elf, binary, None,
                    size_tool, nm_tool, stack)
            self.assertEqual(report["status"], "ok")
            self.assertEqual(report["elf"]["summary"]["static_ram"], 50)
            self.assertEqual(
                [item["name"] for item in report["elf"]["largest_symbols"]],
                ["largest object", "alpha", "second"],
            )
            first = release_contract.write_json(report)
            second = release_contract.write_json(report)
            self.assertEqual(first, second)
            self.assertNotIn(str(root), first)

    def test_aggregate_is_sorted_and_rejects_duplicate_cases(self):
        with tempfile.TemporaryDirectory(prefix="mk61-reports-") as temporary:
            root = Path(temporary)
            reports = []
            for name in ("z-case", "a-case"):
                path = root / f"{name}.json"
                path.write_text(json.dumps({"schema": 1, "case": name,
                                            "status": "ok"}),
                                encoding="utf-8")
                reports.append(path)
            aggregate = release_contract.aggregate_reports(reports)
            self.assertEqual([item["case"] for item in aggregate["reports"]],
                             ["a-case", "z-case"])
            with self.assertRaisesRegex(release_contract.ContractError,
                                        "duplicate"):
                release_contract.aggregate_reports([reports[0], reports[0]])


if __name__ == "__main__":
    unittest.main()
