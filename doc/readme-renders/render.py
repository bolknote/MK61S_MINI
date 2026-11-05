#!/usr/bin/env python3
"""Composite native display bitmaps and original PCB lettering over the renders."""
import argparse
import json
from pathlib import Path
import subprocess
import silkscreen

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def display(config, rasters):
    name = config['raster']
    width, height = (192, 64) if name == 'uc1609' else (96, 18)
    pixels = rasters[name]
    assert len(pixels) == width * height
    spans = []
    for y in range(height):
        x = 0
        while x < width:
            if not pixels[y * width + x]:
                x += 1
                continue
            first = x
            while x < width and pixels[y * width + x]:
                x += 1
            spans.append(f'M{first},{y}h{x-first}v1h{first-x}z')
    return (f'<g transform="translate({config["x"]},{config["y"]}) '
            f'scale({config["width"]/width},{config["height"]/height})" '
            'fill="#203124" opacity="0.96" shape-rendering="crispEdges">'
            f'<path d="{"".join(spans)}"/></g>')


def render(name, spec, rasters, canvas):
    assert (HERE / 'bases' / (name + '.png')).is_file()
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" '
             f'xmlns:xlink="http://www.w3.org/1999/xlink" '
             f'width="2000" height="1124" viewBox="0 0 {canvas[0]} {canvas[1]}">',
             f'<image xlink:href="bases/{name}.png" width="{canvas[0]}" height="{canvas[1]}"/>',
             display(spec['screen'], rasters), silkscreen.svg(spec['silkscreen'])]
    parts.append('</svg>')
    svg = HERE / (name + '.svg')
    svg.write_text('\n'.join(parts) + '\n')
    destination = ROOT / 'img/devices' / (name + '.png')
    subprocess.run(['rsvg-convert', '-w', '2000', '-h', '1124', '-o',
                    str(destination), str(svg)], check=True)
    print(destination.relative_to(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('models', nargs='*', choices=['mini', 'classic', '40th'])
    args = parser.parse_args()
    layout = json.loads((HERE / 'layout.json').read_text())
    rasters = json.loads((HERE / 'display.json').read_text())
    for name in args.models or ['mini', 'classic', '40th']:
        render(name, layout['boards'][name], rasters, layout['canvas'])


if __name__ == '__main__':
    main()
