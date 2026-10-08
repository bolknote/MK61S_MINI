#!/usr/bin/env python3
"""Concurrency and Windows-path regressions for the Arduino System APP cache."""

from __future__ import annotations

import argparse
import concurrent.futures
import multiprocessing
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import build_system_app_bundle as bundle


def arguments(catalog: Path) -> argparse.Namespace:
    return argparse.Namespace(
        catalog_dir=catalog,
        ui_fonts=False,
        graphics=False,
        local_float_math=False,
    )


def app_payload(seed: int) -> bytes:
    payload = bytearray(80)
    payload[:8] = b"MK61APP\0"
    struct.pack_into("<H", payload, 12, 6)
    struct.pack_into("<I", payload, 64, seed)
    return bytes(payload)


def publish_worker(catalog: str, source: str, index: int) -> str:
    return str(bundle.publish_catalog(
        Path(source), f"TEST{index}.APP", f"test-{index}",
        f"build-{index}", arguments(Path(catalog))))


class SystemAppCatalogSelfTest(unittest.TestCase):
    def test_vm_variants_do_not_reuse_interpreter_or_math_packages(self) -> None:
        args = arguments(Path("catalog"))
        basic = bundle.app_variant("tinybasic", args)
        args.language_vm_compiler = True
        self.assertNotEqual(basic, bundle.app_variant("tinybasic", args))
        self.assertIn("vm-compiler-v6", bundle.app_variant("tinybasic", args))
        core = bundle.app_variant("language-vm", args)
        self.assertIn("split-v7", core)
        self.assertIn("cold-v7", bundle.app_variant("language-input", args))
        args.local_float_math = True
        self.assertNotEqual(core, bundle.app_variant("language-vm", args))
        self.assertIn("LANGVM.APP", bundle.CANONICAL)
        self.assertIn("LANGIN.APP", bundle.CANONICAL)

    def test_parallel_publish_is_complete_and_readable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalog = root / "catalog"
            sources = []
            for index in range(16):
                source = root / f"source-{index}.APP"
                source.write_bytes(app_payload(index))
                sources.append(source)

            context = multiprocessing.get_context("spawn")
            with concurrent.futures.ProcessPoolExecutor(
                    max_workers=8, mp_context=context) as executor:
                futures = [executor.submit(
                    publish_worker, str(catalog), str(source), index)
                    for index, source in enumerate(sources)]
                published = [Path(future.result()) for future in futures]

            manifest = bundle.read_catalog(catalog)
            self.assertEqual(len(manifest["apps"]), len(sources))
            self.assertTrue(all(path.is_file() for path in published))
            self.assertEqual(
                len(list((catalog / "objects").glob("*.APP"))), len(sources))
            args = arguments(catalog)
            for index in range(len(sources)):
                cached = bundle.cached_catalog_payload(
                    f"TEST{index}.APP", f"test-{index}",
                    f"build-{index}", args)
                self.assertEqual(cached, sources[index].read_bytes())

    def test_replaced_record_keeps_materialized_payload_valid(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalog = root / "catalog"
            first = root / "first.APP"
            second = root / "second.APP"
            first.write_bytes(app_payload(1))
            second.write_bytes(app_payload(2))
            args = arguments(catalog)
            old_object = bundle.publish_catalog(
                first, "FOCAL.APP", "focal", "old", args)
            old_payload = bundle.cached_catalog_payload(
                "FOCAL.APP", "focal", "old", args)
            new_object = bundle.publish_catalog(
                second, "FOCAL.APP", "focal", "new", args)
            self.assertNotEqual(old_object, new_object)
            self.assertEqual(old_payload, first.read_bytes())
            self.assertFalse(old_object.exists())
            self.assertTrue(new_object.is_file())
            self.assertEqual(len(bundle.read_catalog(catalog)["apps"]), 1)

    def test_corrupt_cache_is_a_miss_instead_of_a_build_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalog = root / "catalog"
            catalog.mkdir()
            (catalog / "catalog.json").write_text("not json", encoding="utf-8")
            args = arguments(catalog)
            self.assertIsNone(bundle.cached_catalog_payload(
                "FOCAL.APP", "focal", "build", args))
            (catalog / "catalog.json").write_text("[]", encoding="utf-8")
            self.assertIsNone(bundle.cached_catalog_payload(
                "FOCAL.APP", "focal", "build", args))
            source = root / "source.APP"
            source.write_bytes(app_payload(3))
            stored = bundle.publish_catalog(
                source, "FOCAL.APP", "focal", "build", args)
            stored.write_bytes(b"corrupt")
            self.assertIsNone(bundle.cached_catalog_payload(
                "FOCAL.APP", "focal", "build", args))
            self.assertEqual(bundle.read_catalog(catalog)["apps"], [])

    def test_cache_key_includes_stack_analysis_policy(self) -> None:
        inputs = set(bundle.catalog_source_inputs())
        self.assertIn(ROOT / "tests/analyze_stack_usage.py", inputs)
        self.assertIn(ROOT / "tests/check_stack_usage.py", inputs)

    def test_workspace_ignores_unicode_system_temp(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            unsafe_default = root / "Пользователь" / "Temp"
            unsafe_default.mkdir(parents=True)
            output = root / "ascii-build" / "bundle" / "System"
            output.mkdir(parents=True)
            with patch.object(bundle.tempfile, "tempdir", str(unsafe_default)):
                with bundle.system_app_workspace(output) as temporary:
                    work = Path(temporary)
                    self.assertEqual(work.parent, output.parent.resolve())
                    self.assertTrue(work.name.startswith(
                        ".mk61-system-app-"))


if __name__ == "__main__":
    unittest.main()
