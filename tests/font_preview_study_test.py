#!/usr/bin/env python3
"""Host-only layout regression tests; no hardware or font downloads required."""
import importlib.util
from pathlib import Path
import unittest

from PIL import Image


spec = importlib.util.spec_from_file_location("study", Path(__file__).resolve().parents[1] / "tools/font_preview_study.py")
study = importlib.util.module_from_spec(spec)
spec.loader.exec_module(study)


class MetricFont:
    @staticmethod
    def measure(text, prose=False):
        return sum(2 if c in "il. " else 5 for c in text)


class LayoutTests(unittest.TestCase):
    def test_wrap_uses_advances_not_character_count(self):
        self.assertEqual(study.wrap(MetricFont(), "iiii WWWW", 21), ["iiii", "WWWW"])

    def test_long_word_can_break(self):
        self.assertEqual(study.wrap(MetricFont(), "WWWWWW", 11), ["WW", "WW", "WW"])

    def test_ellipsis_fits_exactly(self):
        result = study.ellipsize(MetricFont(), "WWWWWW", 16)
        self.assertEqual(result, "WW...")
        self.assertLessEqual(MetricFont.measure(result), 16)

    def test_hex_retains_leading_zero_and_trims_only_right(self):
        im = Image.new("1", (8, 2))
        im.putpixel((4, 0), 1)
        self.assertEqual(study.hex_rows(im), ["08", ""])

    def test_ws_geometry_is_exact(self):
        im = Image.new("1", (80, 16))
        for x, y in ((4, 7), (5, 8), (79, 15)):
            im.putpixel((x, y), 1)
        physical = study.physical_ws(im)
        self.assertEqual(physical.size, (1139, 237))
        ink = (115, 255, 135)
        self.assertEqual(physical.getpixel((1138, 236)), ink)
        self.assertEqual(physical.getpixel((72, 126)), ink)
        self.assertNotEqual(physical.getpixel((71, 126)), ink)

    def test_font_safe_bearing_and_baseline(self):
        font = study.Font.__new__(study.Font)
        font.fixed, font.height, font.ascent = False, 4, 3
        font.glyphs = {"X": {"safe_bearing_x": 1, "bearing_y": 2, "advance": 4,
                                "rows": ["11", "01", "01"]}}
        im = Image.new("1", (10, 5))
        font.draw(im, "XX", 0, 0)
        self.assertTrue(im.getpixel((1, 1)))
        self.assertTrue(im.getpixel((6, 3)))
        self.assertFalse(im.getpixel((3, 1)))
        self.assertEqual(font.measure("XX"), 8)

    def test_marker_does_not_shift_selected_label(self):
        class RecordingFont(MetricFont):
            height, fixed = 12, False
            calls = []

            @staticmethod
            def advance(char):
                return 2 if char == " " else 5

            def draw(self, im, text, x, y, prose=False):
                self.calls.append((text, x))

        font = RecordingFont()
        study.frame(font, "menu")
        labels = [(text, x) for text, x in font.calls if text != ">"]
        self.assertEqual(len(set(x for _, x in labels)), 1)
        self.assertEqual(labels[1][0], "USB-диск")


if __name__ == "__main__":
    unittest.main()
