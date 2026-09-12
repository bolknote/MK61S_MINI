#!/usr/bin/env python3
"""Complete notices survive bundle/ZIP packaging byte for byte."""

import importlib.util
from pathlib import Path
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("licenses", ROOT / "tools/.fmk-font/package_ui_font_licenses.py")
licenses = importlib.util.module_from_spec(spec)
spec.loader.exec_module(licenses)


class PackagingTest(unittest.TestCase):
    def test_bundle_and_deterministic_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            bundle = target / "bundle"
            archive = target / "licenses.zip"
            licenses.package(bundle, archive)
            original = archive.read_bytes()
            licenses.package(bundle, archive)
            self.assertEqual(archive.read_bytes(), original)
            with zipfile.ZipFile(archive) as reader:
                self.assertEqual(set(reader.namelist()), set(licenses.FILES))
                for name, source in licenses.FILES.items():
                    expected = (licenses.SOURCES / source).read_bytes()
                    self.assertGreater(len(expected), 100)
                    self.assertEqual((bundle / name).read_bytes(), expected)
                    self.assertEqual(reader.read(name), expected)

    def test_f411_release_builders_include_notices(self):
        self.assertIn("tools/.fmk-font/package_ui_font_licenses.py",
                      (ROOT / "tests/run_f411_release_matrix.sh").read_text())
        for name in ("tools/build_f401_bundle.sh", "tools/.mk61-gcc/build.ps1"):
            self.assertNotIn("tools/.fmk-font/package_ui_font_licenses.py",
                             (ROOT / name).read_text())
            self.assertIn("MK61_PORTABLE_UI_FONTS=0", (ROOT / name).read_text())
        self.assertIn("--no-ui-fonts",
                      (ROOT / "system_apps/.tool/build.ps1").read_text())
        workflow = (ROOT / ".github/workflows/firmware-release.yml").read_text()
        self.assertIn("test -s firmware/UI_FONT_LICENSES.zip", workflow)
        self.assertIn("firmware/*.zip", workflow)


if __name__ == "__main__":
    unittest.main()
