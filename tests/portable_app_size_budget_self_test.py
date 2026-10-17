#!/usr/bin/env python3
"""Keep compactness ceilings in CI and allow valid larger ordinary APP builds."""

import importlib.util
import os
from pathlib import Path
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "build_portable_app", ROOT / "tools/build_portable_app.py")
assert SPEC is not None and SPEC.loader is not None
BUILDER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILDER)

# Expected CI ceilings, including optimal/Windows packing, compiler frontends,
# tracing and both split VM math profiles. Hard format limits live in packers.
PROFILES = (
    ("setup", {}, {"app_bytes": 10000, "memory_bytes": 20480}),
    ("focal", {}, {"app_bytes": 12000, "memory_bytes": 17000}),
    ("explorer", {}, {"app_bytes": 8000, "memory_bytes": 10000}),
    ("language-input", {}, {"app_bytes": 12800, "memory_bytes": 17152}),
    ("source-editor", {}, {"app_bytes": 13568, "memory_bytes": 18176}),
    ("focal", {"local_float_math": True},
     {"app_bytes": 14000, "memory_bytes": 20000}),
    ("tinybasic", {"local_float_math": True},
     {"app_bytes": 12000, "memory_bytes": 17500}),
    ("focal", {"greedy_packer": True},
     {"app_bytes": 13500, "memory_bytes": 17000}),
    ("focal", {"local_float_math": True, "greedy_packer": True},
     {"app_bytes": 15100, "memory_bytes": 20000}),
    ("tinybasic", {"local_float_math": True, "greedy_packer": True},
     {"app_bytes": 13000, "memory_bytes": 17500}),
    ("language-input", {"greedy_packer": True},
     {"app_bytes": 14144, "memory_bytes": 17152}),
    ("source-editor", {"greedy_packer": True},
     {"app_bytes": 14848, "memory_bytes": 18176}),
    ("focal", {"language_vm_compiler": True},
     {"app_bytes": 14560, "memory_bytes": 19648}),
    ("focal", {"language_vm_compiler": True, "greedy_packer": True},
     {"app_bytes": 15360, "memory_bytes": 19648}),
    ("language-vm", {"split_language_vm": True}, {"memory_bytes": 19520}),
    ("language-vm", {"split_language_vm": True, "local_float_math": True},
     {"memory_bytes": 19968}),
)


class PortableAppSizeBudgetSelfTest(unittest.TestCase):
    def test_ordinary_builds_skip_all_compactness_ceilings(self):
        for ci in (None, "", "false", "0"):
            with self.subTest(ci=ci), patch.dict(os.environ):
                if ci is None:
                    os.environ.pop("CI", None)
                else:
                    os.environ["CI"] = ci
                for system, options, _limits in PROFILES:
                    for trace in (False, True):
                        BUILDER.enforce_system_size_budget(system, {
                            "app_bytes": 20000, "memory_bytes": 20480,
                            "focal_trace": trace,
                        }, **options)

    def test_ci_keeps_each_existing_ceiling(self):
        for ci in ("true", "TRUE", "1", " true "):
            with patch.dict(os.environ, CI=ci):
                for system, options, limits in PROFILES:
                    for trace in (False, True):
                        expected = dict(limits)
                        if (system == "focal" and
                                options.get("language_vm_compiler") and trace):
                            expected["memory_bytes"] = 19840
                        with self.subTest(ci=ci, system=system,
                                          options=options, trace=trace):
                            report = {"app_bytes": 1, "focal_trace": trace, **expected}
                            BUILDER.enforce_system_size_budget(system, report, **options)
                            for field, limit in expected.items():
                                oversized = {**report, field: limit + 1}
                                with self.assertRaisesRegex(
                                        ValueError, f"{field}={limit + 1} > {limit}"):
                                    BUILDER.enforce_system_size_budget(system, oversized, **options)

    def test_reported_focal_build_and_extra_ram_are_ordinary_builds(self):
        for report in ({"app_bytes": 15631, "memory_bytes": 19404},
                       {"app_bytes": 14238, "memory_bytes": 20000}):
            with self.subTest(report=report):
                with patch.dict(os.environ, CI="false"):
                    BUILDER.enforce_system_size_budget(
                        "focal", report, greedy_packer=True, language_vm_compiler=True)
                with patch.dict(os.environ, CI="true"), self.assertRaises(ValueError):
                    BUILDER.enforce_system_size_budget(
                        "focal", report, greedy_packer=True, language_vm_compiler=True)

    def test_ci_does_not_invent_ceilings_for_other_modules(self):
        with patch.dict(os.environ, CI="true"):
            BUILDER.enforce_system_size_budget(
                "tinybasic", {"app_bytes": 20000, "memory_bytes": 20480})


if __name__ == "__main__":
    unittest.main()
