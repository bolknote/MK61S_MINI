#!/usr/bin/env python3
"""Host-only UI typography study. Requires Pillow and the FreeType atlas exporter.

This is a layout proposal, not a firmware screenshot. Never resample glyphs;
only enlarge completed displays with nearest-neighbour for visual inspection.
"""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
SAMPLES = {
    "menu": ["DFU прошивка", "USB-диск", "Настройки", "Проводник", "Библиотека", "Разработка"],
    "english": ["DFU mode enable", "USB Disk", "Settings", "Explorer", "MK61 library", "Development"],
    "settings": ["Громкость 10", "Скорость турбо", "Память 112ШГ+ПF", "К СЧ MK61s", "Поправка RTC", "Дата и время"],
    "files": ["manual.md", "autoexec.m61", "Infinity Story.m61", "Bumblebee Fly.m61", "Fox Hunting.m61", "space-invaders.ch8"],
    "manual": ["Вы - полицейский. Найдите машину мафиози в городе из домов и дорог и остановите её. Короткое нажатие LEFT или RIGHT прокручивает инструкцию на строку."],
    "stress": ["ЙЁДЦЩруф ЖШMW il1 0O", "ЙЁДЦЩруф ЖШMW il1 0O", "USB-диск: Ёжик.m61", "Память 112ШГ+ПF", "AVATAR, ТАУ, Ёлка; руду", "12.09.2026 21:05"],
}


class Font:
    def __init__(self, path, fixed=False):
        self.atlas = json.loads(path.read_text())
        self.glyphs = {chr(g["codepoint"]): g for g in self.atlas["glyphs"]}
        self.fixed = fixed
        self.height = self.atlas["height"]
        self.ascent = self.atlas["ascent"]

    def glyph(self, char):
        if char not in self.glyphs:
            raise ValueError(f"missing {char!r} in {self.atlas['family']}")
        return self.glyphs[char]

    def advance(self, char, prose=False):
        return (6 if prose else 12) if self.fixed else self.glyph(char)["advance"]

    def measure(self, text, prose=False):
        return sum(self.advance(c, prose) for c in text)

    def draw(self, im, text, x, top, prose=False):
        for char in text:
            glyph = self.glyph(char)
            left = x + ((0 if prose else 3) if self.fixed else glyph["safe_bearing_x"])
            y0 = top + self.ascent - glyph["bearing_y"]
            for y, row in enumerate(glyph["rows"]):
                for dx, bit in enumerate(row):
                    if bit == "1" and 0 <= left + dx < im.width and 0 <= y0 + y < im.height:
                        im.putpixel((left + dx, y0 + y), 1)
            x += self.advance(char, prose)


def wrap(font, text, width, prose=False):
    lines, line = [], ""
    for word in text.split():
        candidate = (line + " " + word).lstrip()
        if font.measure(candidate, prose) <= width:
            line = candidate
            continue
        if line:
            lines.append(line)
        line = ""
        for char in word:
            if line and font.measure(line + char, prose) > width:
                lines.append(line)
                line = ""
            line += char
    if line:
        lines.append(line)
    return lines


def ellipsize(font, text, width, prose=False):
    if font.measure(text, prose) <= width:
        return text
    suffix = "..."  # Also available in the existing 5x8 repertoire.
    while text and font.measure(text + suffix, prose) > width:
        text = text[:-1]
    return text + suffix


def frame(font, scene, gap=2, inverse=False):
    image = Image.new("1", (192, 64))
    prose = scene == "manual"
    top, x = (0, 0) if font.fixed else (1, 2)
    pitch = font.height + gap
    count = (64 - top + gap) // pitch
    lines = wrap(font, SAMPLES[scene][0], 192 - 2*x, prose) if prose else SAMPLES[scene]
    displayed, truncated = [], 0
    list_scene = scene in ("menu", "english", "settings", "files")
    gutter = max(font.advance(">"), font.advance(" ")) if list_scene else 0
    for row, text in enumerate(lines[:count]):
        selected = row == 1 and list_scene
        prefix = "" if prose or scene == "stress" else (">" if selected else " ")
        actual = ellipsize(font, text, 192 - 2*x - gutter, prose)
        truncated += actual != text
        if selected:
            font.draw(image, ">", x, top + row*pitch, prose)
        font.draw(image, actual, x + gutter, top + row*pitch, prose)
        if selected and inverse and not font.fixed:
            for y in range(top + row*pitch - 1, min(64, top + row*pitch + font.height + 1)):
                for px in range(192):
                    image.putpixel((px, y), not image.getpixel((px, y)))
        displayed.append(prefix + actual)
    return image, {"rows": count, "visible": displayed, "truncated_lines": truncated,
                   "hidden_lines": max(0, len(lines)-count), "pitch": pitch}


def hex_rows(image):
    return [format(sum((1 if image.getpixel((x, y)) else 0) << (image.width-1-x)
                       for x in range(image.width)), f"0{image.width//4}x")
            .rstrip("0") for y in range(image.height)]


def colored(image, scale=1, oled=False):
    out = Image.new("RGB", image.size, "#101810" if oled else "#143555")
    ink = (115, 255, 135) if oled else (220, 241, 243)
    for y in range(image.height):
        for x in range(image.width):
            if image.getpixel((x, y)):
                out.putpixel((x, y), ink)
    return out.resize((image.width*scale, image.height*scale), Image.Resampling.NEAREST)


def physical_ws(image):
    # Published WEH001602A geometry at exactly 20 pixels/mm (not optical simulation).
    result = Image.new("RGB", (1139, 237), "#101810")
    draw = ImageDraw.Draw(result)
    for y in range(16):
        for x in range(80):
            if image.getpixel((x, y)):
                left, top = 12*x + 12*(x//5), 14*y + 14*(y//8)
                draw.rectangle((left, top, left+10, top+12), fill="#73ff87")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exporter", type=Path, required=True)
    parser.add_argument("--roboto", type=Path, required=True)
    parser.add_argument("--dejavu", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=ROOT / "tmp/ui-font-study")
    parser.add_argument("--html", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    atlas_dir = args.out / "atlases"
    atlas_dir.mkdir(exist_ok=True)
    builtin_path = atlas_dir / "builtin.json"
    subprocess.run([str(args.exporter), "--builtin", str(builtin_path)], check=True)
    builtin = Font(builtin_path, fixed=True)
    fonts = {}
    for name, path in (("roboto", args.roboto), ("dejavu", args.dejavu)):
        for height in (8, 10, 12, 14):
            output = atlas_dir / f"{name}-{height}.json"
            subprocess.run([str(args.exporter), str(path), str(output), "--height", str(height)], check=True)
            fonts[f"{name}-{height}"] = Font(output)

    payload = {"fonts": {}, "scenes": SAMPLES, "baseline": {}, "ws": {}}
    for scene in SAMPLES:
        image, info = frame(builtin, scene)
        payload["baseline"][scene] = {"pixels": hex_rows(image), **info}
        image.save(args.out / f"baseline-{scene}-1x.png")
    metrics = {}
    for name, font in fonts.items():
        data = {k: font.atlas[k] for k in ("family", "height", "ppem", "ascent", "descent", "missing")}
        bitmap_bytes = sum((g["width"]*g["height"]+7)//8 for g in font.glyphs.values())
        metrics[name] = {**data, "glyph_count": len(font.glyphs), "tight_bitmap_bytes": bitmap_bytes,
                         "safe_minimum_gap": 1, "settings_width": font.measure("Память 112ШГ+ПF")}
        data["frames"] = {}
        for scene in SAMPLES:
            for gap in (1, 2, 3):
                for inverse in (False, True):
                    image, info = frame(font, scene, gap, inverse)
                    data["frames"][f"{scene}-{gap}-{int(inverse)}"] = {"pixels": hex_rows(image), **info}
                    if gap == 2 and not inverse:
                        image.save(args.out / f"{name}-{scene}-1x.png")
        payload["fonts"][name] = data

    # A contact sheet: identical menu and stress scenes, enlarged only by integer factors.
    label_font = ImageFont.truetype(str(args.dejavu), 20)
    sheet = Image.new("RGB", (1224, 1100), "#eef1ed")
    draw = ImageDraw.Draw(sheet)
    draw.text((20, 12), "UC1609 / 192 x 64 / 1-bit / 3x nearest-neighbour", font=label_font, fill="#182b29")
    for col, family in enumerate(("roboto", "dejavu")):
        for row, height in enumerate((8, 10, 12, 14)):
            font = fonts[f"{family}-{height}"]
            x, y = 20 + 612*col, 58 + row*257
            text = f"{font.atlas['family']} | {font.height}px ink / {font.atlas['ppem']}ppem / gap 2"
            draw.text((x, y), text, font=label_font, fill="#182b29")
            # Identical real menu for every candidate; stress sheet follows below.
            image, _ = frame(font, "menu")
            sheet.paste(colored(image, 3), (x, y+34))
    sheet.save(args.out / "comparison-menu.png")
    for col, family in enumerate(("roboto", "dejavu")):
        for row, height in enumerate((8, 10, 12, 14)):
            image, _ = frame(fonts[f"{family}-{height}"], "stress")
            sheet.paste(colored(image, 3), (20+612*col, 92+row*257))
    sheet.save(args.out / "comparison-cyrillic.png")

    for name, font in fonts.items():
        image = Image.new("1", (80, 16))
        lines = [ellipsize(font, s, 80) for s in ("USB-диск",)]
        for row, line in enumerate(lines):
            font.draw(image, line, 0, row*(font.height+2))
        payload["ws"][name] = {"pixels": hex_rows(image), "lines": lines, "height": font.height}
        image.save(args.out / f"ws-{name}-1x.png")
        physical_ws(image).save(args.out / f"ws-{name}-physical.png")

    manifest = {"scope": "Host raster/layout experiment only; no flashed firmware or optical validation",
                "fonts": {"roboto": {"sha256": hashlib.sha256(args.roboto.read_bytes()).hexdigest(),
                                      "source": "https://github.com/googlefonts/roboto-2/tree/38062f4b4a0be4346d07a928408da21602545e9e/src/hinted"},
                          "dejavu": {"sha256": hashlib.sha256(args.dejavu.read_bytes()).hexdigest(),
                                     "source": "https://github.com/dejavu-fonts/dejavu-fonts/releases/tag/version_2_37"}},
                "metrics": metrics, "samples": SAMPLES,
                "notes": ["Bitmap bytes exclude indices, metrics, headers and padding; not final firmware size.",
                          "No kerning, synthetic bold, scaling or antialiasing. Conservative one-pixel ink gap.",
                          "Baseline uses current builtin 5x8, 12px menu stride; prose uses 6px stride.",
                          "File truncation and word wrapping are proposed layout, not firmware capture.",
                          "WS geometry: .55x.65mm dots, .60x.70 pitch, .60/.70 extra group spacing."]}
    (args.out / "measurements.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+"\n")
    template = (ROOT / "tools/.fmk-font/font_preview.html").read_text()
    assert template.count("__FONT_STUDY_DATA__") == 1
    args.html.parent.mkdir(parents=True, exist_ok=True)
    args.html.write_text(template.replace("__FONT_STUDY_DATA__", json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")))
    if args.html.stat().st_size >= 1_000_000:
        raise ValueError("inline comparison exceeds 1 MB")
    print(json.dumps({"out": str(args.out), "html": str(args.html), "bytes": args.html.stat().st_size,
                      "font_variants": len(metrics)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
