#!/usr/bin/env python3
"""Capture real ROM frames, then rasterize the production UC1609 segment planes.

Offline only. Uses ordinary keys, with no injected game state or device I/O.
Pillow is needed only for the preview, not for building or running the game.
"""
import argparse
import json
from pathlib import Path
import re
import sys
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tests'))
from runner_game_test import Game, campaign


def captures(binary):
    rows = []
    g = Game(binary)
    try:
        rows.append(('Уровень 1: старт', g.state.copy()))
        for _ in range(2):
            g.send('advance 2030')
        rows.append(('Преследователь спустился по лестнице', g.state.copy()))
        g.tap(0); g.tap(6); g.tap(6)
        for _ in range(9):
            if g.state['regs'][5] == 16:
                break
            g.send('advance 2030')
        assert g.state['regs'][5] == 16, g.state
        g.tap(9)
        assert g.state['regs'][7] == 15
        g.send('advance 2030')
        assert g.state['regs'][5] == g.state['regs'][7] == 15, g.state
        rows.append(('Враг пойман в прожиге', g.state.copy()))
        g.tap(5)
        rows.append(('Счёт: уровень и оставшиеся клады', g.state.copy()))
        g.send('advance 900')
        g.tap(0)
        for _ in range(30):
            g.send('advance 2030')
            if g.state['regs'][4] < 0:
                break
        assert g.state['regs'][4] == -1
        rows.append(('Столкновение: 0 повторяет уровень', g.state.copy()))
    finally:
        g.close()
    for level in (2, 3):
        g = Game(binary, level)
        try:
            rows.append((f'Уровень {level}: другая карта лестниц', g.state.copy()))
            if level == 2:
                for _ in range(5):
                    g.send('advance 1030')
                assert g.state['regs'][4] >= 0
                rows.append(('Два врага на одном этаже', g.state.copy()))
        finally:
            g.close()
    won = campaign(binary)['level3_clear']
    rows.append(('Все три уровня пройдены', won))
    return rows


def render(rows, output):
    source = (ROOT / 'code/calculator_face.cpp').read_text()
    body = re.search(r'SEGMENT_ROWS\[8\]\[SOURCE_HEIGHT\]\s*=\s*\{(.*?)\n\};', source, re.S).group(1)
    planes = [[int(x, 0) for x in re.findall(r'0x[0-9A-Fa-f]+|\b0\b', row)]
              for row in re.findall(r'\{([^{}]+)\}', body)]
    assert len(planes) == 8 and all(len(row) <= 35 for row in planes)
    planes = [row+[0]*(35-len(row)) for row in planes]
    try:
        font = ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial.ttf', 20)
    except OSError:
        font = ImageFont.load_default(size=20)
    scale, margin, row_height = 4, 24, 148
    image = Image.new('RGB', (192*scale+2*margin, len(rows)*row_height+margin), '#f3f4ee')
    draw = ImageDraw.Draw(image)
    for number, (title, state) in enumerate(rows):
        draw.text((margin, number*row_height+12), title, font=font, fill='#25352b')
        # Same source planes, pitch, rounding, inset and vertical placement as
        # drawSegmentsPage in calculator_face.cpp. Crop only the blank margins.
        glass = Image.new('RGB', (192, 28), '#c8d39f')
        pixels = glass.load()
        for slot, mask in enumerate(state['frame']):
            for sy in range(35):
                bits = 0
                for segment in range(8):
                    if mask & (1 << segment):
                        bits |= planes[segment][sy]
                for sx in range(16):
                    if bits & (0x8000 >> sx):
                        x = slot*16+3+(sx*16+13)//27
                        y = 3+(sy*16+13)//27
                        pixels[x, y] = (24, 39, 29)
        image.paste(glass.resize((192*scale, 28*scale), Image.Resampling.NEAREST),
                    (margin, number*row_height+42))
    image.save(output)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--runner', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    rows = captures(str(args.runner.resolve()))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    render(rows, args.output)
    args.output.with_suffix('.frames.json').write_text(json.dumps(
        [{'caption': name, **state} for name, state in rows], indent=2, ensure_ascii=False)+'\n')
    print(args.output)


if __name__ == '__main__':
    main()
