#!/usr/bin/env python3
"""Manual removal requested by the user: no top switches or protruding USB.

Only the empty background/top edge and the exterior side strip are repaired.
The keyboard, display, LED, case proportions and screws are left unchanged.
"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter

HERE = Path(__file__).resolve().parent
source = Image.open(HERE / 'bases/mini-original.png').convert('RGB')
assert source.size == (1672, 941)
result = source.copy()
# Match the brown illumination on both sides of the unwanted top protrusion,
# row by row. The case begins at y=74; it is outside this repair rectangle.
for y in range(0, 74):
    left = source.getpixel((735, y))
    right = source.getpixel((902, y))
    for x in range(744, 893):
        t = (x - 735) / (902 - 735)
        colour = tuple(round(a * (1 - t) + b * t) for a, b in zip(left, right))
        fade = min(1, (x - 744) / 6, (892 - x) / 6)
        old = source.getpixel((x, y))
        result.putpixel((x, y), tuple(round(a * fade + b * (1 - fade))
                                     for a, b in zip(colour, old)))
# The side edge and its soft shadow are straight: clone the same strip from
# below the unused connector, keeping the original case edge in place.
box = (1240, 230, 1300, 365)
donor = source.crop((1240, 400, 1300, 535))
mask = Image.new('L', donor.size, 0)
ImageDraw.Draw(mask).rectangle((3, 3, donor.width-4, donor.height-4), fill=255)
mask = mask.filter(ImageFilter.GaussianBlur(1))
result.paste(donor, (box[0], box[1]), mask)
result.save(HERE / 'bases/mini.png')
print('Removed mini top switch and external USB connector manually')
