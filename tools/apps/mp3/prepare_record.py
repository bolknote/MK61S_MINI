"""Prepare RGB565-palette animation frames for the PicoCalc color service."""

from pathlib import Path
import argparse
import math

from PIL import Image

WIDTH, HEIGHT, FRAMES = 320, 256, 128
TILES = WIDTH // 8
STRIP_HEIGHT = 32
BITMAP_BYTES = WIDTH * HEIGHT // 8
PAPER = 48

# Use most of the palette for dark vinyl and the specular reflection. Give
# the paper its own warmer ramp and reserve two colors for the desktop and ink.
VINYL = [round(7 + 154 * (i / 45)**1.75) for i in range(46)]
STOCK = [166, 182, 196, 201, 206, 209, 211, 213, 215, 217, 219, 221, 224, 228, 232, 237]
LEVELS = [18, 42, *VINYL, *STOCK]
BAYER = ((0, 2), (3, 1))


def rgb565(red, green, blue):
    return (red >> 3) << 11 | (green >> 2) << 5 | (blue >> 3)


def warm(value, paper=False):
    if paper:
        return rgb565(min(255, round(value * 1.08)), value, round(value * 0.88))
    return rgb565(round(value * 1.045), value, round(value * .93))


def nearest(value, start, end):
    return min(range(start, end), key=lambda i: (abs(value - LEVELS[i]), i))


def shade_pair(tile):
    dark = [value for value in tile if value < 174]
    if dark and len(dark) != len(tile):
        lo = nearest(sum(dark) / len(dark), 2, PAPER)
        hi = nearest((sum(tile) - sum(dark)) / (64 - len(dark)), PAPER, 64)
        return lo, hi, 174
    start, end = (2, PAPER) if dark else (PAPER, 64)
    middle = sum(tile) / len(tile)
    lows = [value for value in tile if value <= middle]
    high_count = 64 - len(lows)
    lo = nearest(sum(lows) / len(lows), start, end)
    hi = nearest((sum(tile) - sum(lows)) / high_count, start, end) if high_count else lo
    return lo, hi, None


def frame(photo, angle):
    s, c = math.sin(angle), math.cos(angle)
    scale = photo.width / 442
    du, dv = c * scale, s * scale
    center = photo.width / 2
    transform = (du, dv, center - 160 * du - 128 * dv,
                 -dv, du, center + 160 * dv - 128 * du)
    record = photo.transform((WIDTH, HEIGHT), Image.Transform.AFFINE, transform,
                             Image.Resampling.BILINEAR, fillcolor=18)
    image = record.tobytes()
    pixels = bytearray(BITMAP_BYTES)
    attrs = bytearray(BITMAP_BYTES // 4)
    for y in range(0, HEIGHT, 8):
        for column in range(TILES):
            x = column * 8
            rows = [image[(y + row) * WIDTH + x:(y + row) * WIDTH + x + 8] for row in range(8)]
            # Keep the paper and the dark spindle opening from the photograph.
            # Fade only the black surface at the edge of the controls.
            if y >= 216:
                rows = [
                    [18 + (value - 18) * (255 - y - row) // 40 if value < 174 else value
                     for value in line] for row, line in enumerate(rows)
                ]
            tile = [value for line in rows for value in line]
            lo, hi, cutoff = shade_pair(tile)
            offset = (y // 8 * TILES + column) * 2
            attrs[offset:offset + 2] = bytes((lo, hi))
            if lo == hi:
                continue
            for row, values in enumerate(rows):
                bounds = BAYER[(y + row) & 1]
                bits = 0
                for col, value in enumerate(values):
                    threshold = cutoff if cutoff is not None else (
                        LEVELS[lo] + (LEVELS[hi] - LEVELS[lo]) * (bounds[col & 1] + .5) / 4
                    )
                    bits = (bits << 1) | (value >= threshold)
                pixels[(y + row) * TILES + column] = bits
    frame = bytearray()
    for y in range(0, HEIGHT, STRIP_HEIGHT):
        pixel_offset = y * TILES
        tile_offset = (y // 8) * TILES * 2
        frame += pixels[pixel_offset:pixel_offset + STRIP_HEIGHT * TILES]
        frame += attrs[tile_offset:tile_offset + STRIP_HEIGHT * TILES // 4]
    return frame


def convert(source, output):
    photo = Image.open(source).convert("RGBA")
    base = Image.new("RGBA", photo.size, (18, 18, 18, 255))
    base.alpha_composite(photo)
    photo = base.convert("L")
    colors = [rgb565(20, 20, 19), rgb565(33, 46, 83)]
    colors += [warm(level, i >= PAPER - 2) for i, level in enumerate(LEVELS[2:])]
    with output.open("wb") as data:
        data.write(b"LP04" + b"".join(color.to_bytes(2, "little") for color in colors))
        for index in range(FRAMES):
            data.write(frame(photo, 2 * math.pi * index / FRAMES))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    convert(args.source, args.output)
