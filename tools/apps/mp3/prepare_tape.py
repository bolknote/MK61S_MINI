#!/usr/bin/env python3
"""Pack the cassette and reel mockup layers into resident INDEX4 strips."""
import argparse
import math
from pathlib import Path
import struct

import numpy as np
from PIL import Image, ImageDraw

WIDTH, HEIGHT, BAND = 320, 320, 16
RINGS = 16
PALETTES = {
    'cassette': ('11100f', '6b5b49', 'faead2', 'a4927c', 'cc7948', '302c27', '201e1b', '494239',
                 '382820', '5d3f2e', '916044', 'bba178', '8d7963', 'd4b787', 'e5ca9e', 'f0d9b3'),
    'reel': ('10110f', '3b3a37', 'f5efe1', 'c3c1b7', 'e7ba7e', '2b2c29', '1b1c1a', '52514d',
             '30221b', '4f3628', '715039', 'c7864e', '6b6a64', '87857f', 'a5a39d', 'd9d7cf'),
}


def rgb(value):
    return tuple(bytes.fromhex(value))


def rgb565(color):
    r, g, b = color
    return (r >> 3) << 11 | (g >> 2) << 5 | (b >> 3)


def expand(value):
    r, g, b = value >> 11, (value >> 5) & 63, value & 31
    return (r << 3 | r >> 2, g << 2 | g >> 4, b << 3 | b >> 2)


def quantize(image, palette, transparent=False):
    pixels = np.asarray(image, dtype=np.int32)
    used = palette[1:] if transparent else palette
    difference = pixels[:, :, None, :3] - np.asarray(used, dtype=np.int32)
    distance = (difference * difference * [3, 5, 2]).sum(axis=3)
    indexes = distance.argmin(axis=2).astype(np.uint8)
    if transparent:
        indexes = np.where(pixels[:, :, 3] >= 128, indexes + 1, 0).astype(np.uint8, copy=False)
    return (indexes[:, ::2] << 4 | indexes[:, 1::2]).tobytes()


def packbits(data):
    result = bytearray()
    at = 0
    while at < len(data):
        end = at + 1
        while end < min(at + 128, len(data)) and data[end] == data[at]:
            end += 1
        if end - at >= 3:
            result.extend((127 + end - at, data[at]))
        else:
            while end < min(at + 128, len(data)):
                if end + 2 < len(data) and data[end] == data[end + 1] == data[end + 2]:
                    break
                end += 1
            result.append(end - at - 1)
            result.extend(data[at:end])
        at = end
    return result


def gradient(image, box, stops):
    left, top, right, bottom = box
    draw = ImageDraw.Draw(image)
    at = 0
    for y in range(top, bottom):
        p = (y - top) / (bottom - top - 1)
        while p > stops[at + 1][0]:
            at += 1
        a, c = stops[at]
        b, d = stops[at + 1]
        t = (p - a) / (b - a)
        line = tuple(round(m + (n - m) * t) for m, n in zip(rgb(c), rgb(d)))
        draw.line((left, y, right - 1, y), fill=line)


def backdrop(source, kind, colors):
    image = Image.new('RGB', (WIDTH, HEIGHT), colors[0])
    draw = ImageDraw.Draw(image)
    if kind == 'cassette':
        shell = Image.open(source / 'cassette-shell.webp').convert('RGB')
        image.paste(shell.resize((320, 208), Image.Resampling.LANCZOS), (0, 15))
        opening = (45, 86, 275, 139)
        mask = Image.new('1', image.size)
        ImageDraw.Draw(mask).rounded_rectangle((45, 86, 274, 138), radius=4, fill=1)
        fill = image.copy()
        gradient(fill, opening, ((0, '211b18'), (.22, '2b2420'), (.74, '231e1b'), (1, '302721')))
        image.paste(fill, mask=mask)
        draw.rectangle((0, 220, 319, 279), fill=colors[6])
    else:
        plate = Image.open(source / 'reel-plate.webp').convert('RGB')
        image.paste(plate.resize((320, 192), Image.Resampling.LANCZOS), (0, 0))
        gradient(image, (0, 191, 320, 233), ((0, '52504c'), (.13, '333230'), (.91, '272826'), (1, '141513')))
        draw.line((0, 191, 319, 191), fill=colors[12])
        for x in (10, 219):
            draw.rectangle((x, 195, x + 90, 227), fill=colors[0])
            draw.rectangle((x + 1, 196, x + 89, 226), fill=colors[7])
            draw.rectangle((x + 2, 197, x + 88, 224), fill=colors[6])
            gradient(image, (x + 3, 198, x + 88, 223), ((0, 'c38e5d'), (.38, 'edd19c'), (1, 'e0ad6d')))
            cx, cy = x + 46, 225
            for step in range(13):
                angle = -2.61 + (2.61 - .54) * step / 12
                inner = 19 if step % 3 == 0 else 21
                def point(radius):
                    return (round(cx + radius * math.cos(angle)), round(cy + radius * math.sin(angle)))
                draw.line((point(23), point(inner)), fill=colors[10 if step > 9 else 7])
            draw.line((x + 3, 222, x + 87, 222), fill=colors[10])
        draw.rectangle((108, 196, 211, 226), fill=colors[0])
        draw.line((108, 196, 211, 196), fill=colors[7])
        draw.rectangle((0, 280, 319, 319), fill=colors[6])
    draw.line((0, 280, 319, 280), fill=colors[7])
    return image


def sprite_bands(source, kind, side, phase, phases):
    sprite = Image.open(source / f'{kind}-{side}.png').convert('RGBA')
    if kind == 'cassette':
        cx = (229.3, 550.8)[side] * 320 / 780
        cy, width, height, aspect, top, bands = 111.1, 46.77, 45.6, .97, 80, 4
    else:
        cx = (194.5, 586.2)[side] * 320 / 780
        cy = (208.8, 209.0)[side] * 192 / 520
        width, height, aspect, top, bands = 162.45, 158.03, .972, 0, 12
    cx -= side * (WIDTH // 2)
    cy -= top
    angle = phase * math.tau / phases
    cos, sin = math.cos(angle), math.sin(angle)
    sx, sy = sprite.width / width, sprite.height * aspect / height
    transform = (sx * cos, sx * sin / aspect, sprite.width / 2 - sx * (cos * cx + sin * cy / aspect),
                 -sy * sin, sy * cos / aspect, sprite.height / 2 + sy * (sin * cx - cos * cy / aspect))
    rotated = sprite.transform((WIDTH // 2, BAND * bands), Image.Transform.AFFINE, transform, Image.Resampling.BILINEAR)
    return [rotated.crop((0, y, WIDTH // 2, y + BAND)) for y in range(0, BAND * bands, BAND)]


def pack(source, kind):
    palette = [rgb565(rgb(c)) for c in PALETTES[kind]]
    assert len(set(palette)) == 16
    colors = [expand(value) for value in palette]
    base = backdrop(source, kind, colors)
    strips = [quantize(base.crop((0, y, WIDTH, y + BAND)), colors) for y in range(0, HEIGHT, BAND)]
    phases = 128 if kind == 'reel' else 64
    damage = bytearray()
    for side in range(2):
        first = len(strips)
        for phase in range(phases):
            strips.extend(quantize(image, colors, True) for image in sprite_bands(source, kind, side, phase, phases))
        if kind == 'reel':
            # A constant pair (including transparency) always composites to
            # the same pixels while the winding underneath is stationary.
            frames = np.frombuffer(b''.join(strips[first:]), dtype=np.uint8).reshape(phases, -1, BAND, WIDTH // 4)
            for band in np.any(frames != frames[0], axis=0):
                rows, cols = np.where(band)
                damage.extend((int(cols.min()), int(cols.max()) + 1, int(rows.min()), int(rows.max()) + 1)
                              if rows.size else (0, 0, 0, 0))
    texture = np.asarray(Image.open(source / 'tape-pack.webp').convert('RGB'), dtype=np.int32)
    cy, cx = (np.array(texture.shape[:2]) - 1) / 2
    y, x = np.indices(texture.shape[:2])
    radius = np.hypot((x - cx) / cx, (y - cy) / cy)
    rings = []
    for ring in range(RINGS):
        section = (radius >= ring / RINGS) & (radius < (ring + 1) / RINGS)
        color = np.median(texture[section], axis=0)
        nearest = ((np.array(colors) - color) ** 2 * [3, 5, 2]).sum(axis=1)
        rings.append(nearest.argmin())
    header = (b'TV03' if damage else b'TV02') + struct.pack('<16H', *palette) + bytes(rings) + damage
    cursor = len(header) + len(strips) * 6
    offsets = bytearray()
    payload = bytearray()
    locations = {}
    for band in strips:
        encoded = bytes(packbits(band))
        assert len(encoded) <= 2580
        if encoded not in locations:
            locations[encoded] = cursor
            payload.extend(encoded)
            cursor += len(encoded)
        offsets.extend(struct.pack('<IH', locations[encoded], len(encoded)))
    return header + offsets + payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('layers', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    for kind in PALETTES:
        output = args.output / (kind.upper() + '.TV')
        output.write_bytes(pack(args.layers, kind))
        print(f'{output.name} {output.stat().st_size} bytes')


if __name__ == '__main__':
    main()
