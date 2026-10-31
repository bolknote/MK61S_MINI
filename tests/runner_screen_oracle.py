"""Decode the actual UC1609 indicator independently of calculator registers.

Uses the production segment planes, including the decimal-point plane. The
game's six masks use these planes under either calculator font preference.
"""
from functools import lru_cache
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
MASKS = (0, 8, 0x6B, 0x77, 0x7E, 0xC9)


@lru_cache(None)
def planes():
    source = (ROOT / 'code/calculator_face.cpp').read_text()
    body = re.search(r'SEGMENT_ROWS\[8\]\[SOURCE_HEIGHT\]\s*=\s*\{(.*?)\n\};', source, re.S).group(1)
    rows = [[int(x, 0) for x in re.findall(r'0x[0-9A-Fa-f]+|\b0\b', row)]
            for row in re.findall(r'\{([^{}]+)\}', body)]
    assert len(rows) == 8 and all(len(row) <= 35 for row in rows)
    return [row+[0]*(35-len(row)) for row in rows]


def indicator(masks):
    assert len(masks) == 12
    frame = bytearray(1536)
    source = planes()
    for slot, mask in enumerate(masks):
        for sy in range(35):
            bits = 0
            for segment in range(8):
                if mask & (1 << segment):
                    bits |= source[segment][sy]
            for sx in range(16):
                if bits & (0x8000 >> sx):
                    x = slot*16+3+(sx*16+13)//27
                    y = 31+(sy*16+13)//27
                    frame[(y//8)*192+x] |= 1 << (y % 8)
    return bytes(frame)


def cell_signature(frame, cell):
    if len(frame) != 1536:
        return None
    result = 0
    for y in range(31, 52):
        for x in range(cell*16, (cell+1)*16):
            result = (result << 1) | ((frame[(y//8)*192+x] >> (y % 8)) & 1)
    return result


@lru_cache(None)
def alphabet():
    result = {cell_signature(indicator([mask]*12), 0): mask for mask in MASKS}
    assert len(result) == len(MASKS)
    return result


def board(frame):
    glyphs = alphabet()
    masks = [glyphs.get(cell_signature(frame, cell)) for cell in range(12)]
    if None in masks or masks.count(0x6B) != 1:
        return None
    return dict(masks=masks, hero=masks.index(0x6B),
                guards=[cell for cell, mask in enumerate(masks) if mask == 0x77],
                holes=[cell for cell, mask in enumerate(masks) if mask == 0],
                gold=[cell for cell, mask in enumerate(masks) if mask == 0xC9])


def expected(regs, config):
    hero, enemy, offset, hole, second = map(int, regs[4:9])
    if not 0 <= hero < 36:
        return None
    floor, column = divmod(hero, 12)
    links = (config['links'][floor-1] if floor else set()) | (config['links'][floor] if floor < 2 else set())
    masks = [0x7E if x+1 in links else 8 for x in range(12)]
    if not ((offset//36) & (1 << floor)):
        masks[config['gold'][floor] % 12] = 0xC9
    masks[column] = 0x6B
    if hole//12 == floor:
        masks[hole % 12] = 0
    for guard in (enemy, second):
        if guard//12 == floor:
            masks[guard % 12] = 0x77
    return masks
