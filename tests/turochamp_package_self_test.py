#!/usr/bin/env python3
"""Offline C6 quotas, dispatcher, call depth and actual FMK raster checks."""
from __future__ import annotations
import binascii
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
sys.path.insert(0, str(ROOT/'tools/turochamp'))
from m8_codec import encode
from layout import MODULES, MAX_ARRAY_INDEX, SOURCE_BUDGET
GAME = ROOT/'programs/games/Turochamp'
SOURCE = ROOT/'tools/turochamp/basic'


def decode_font(data):
    assert data[:8] == b'FMK2'+bytes((1,7,7,0x60))
    assert int.from_bytes(data[12:14], 'little') == len(data)
    assert binascii.crc_hqx(data[:14]+b'\0\0'+data[16:], 0xffff) == int.from_bytes(data[14:16], 'little')
    bit = (16+2*data[10])*8
    def read(n):
        nonlocal bit
        value = 0
        for _ in range(n):
            value = (value << 1) | ((data[bit//8] >> (7-bit % 8)) & 1)
            bit += 1
        return value
    result = {}
    for i in range(data[10]):
        first, count = data[16+2*i:18+2*i]
        for c in range(first, first+count+1):
            assert read(1) == 0
            result[c] = tuple(read(7) for _ in range(7))
    assert len(result) == int.from_bytes(data[8:10], 'little')
    assert (bit+7)//8 == len(data)
    return result


def main():
    for tool in ('assemble.py', 'font.py'):
        subprocess.run([sys.executable, ROOT/'tools/turochamp'/tool, '--check'], check=True)
    assert {p.stem for p in GAME.glob('*.tbi')} == set(MODULES)
    driver = (GAME/'autoexec.m61').read_text()
    assert len(driver.encode())+driver.count('\n') <= 1536
    for name, ident in MODULES.items():
        assert f'if re=={ident} open {name}.tbi' in driver
    assert driver.startswith('reinit\nloadfont Turochamp\nopen init.tbi\n')
    assert driver.endswith('if re==99 ret\nrun :dispatch\n')
    font_data = (GAME/'Turochamp.FMK').read_bytes()
    assert len(font_data) <= 1536
    glyphs = decode_font(font_data)
    for name in ('manual.md','rules.md','algorithm.md'):
        data = (GAME/name).read_bytes()
        assert len(data)+data.count(b'\n') <= 1536, name
    largest = 0
    graph = {}
    for name in MODULES:
        text = (GAME/(name+'.tbi')).read_text()
        m8 = encode(text)
        cost = len(m8)+m8.count(b'\n')
        assert cost <= SOURCE_BUDGET, (name, cost)
        assert (3584-cost)//2+1 > MAX_ARRAY_INDEX
        assert len(text.encode())+text.count('\n') <= 3584, name
        lines = text.splitlines()
        assert len(lines) <= 192 and max(map(len, map(encode,lines))) <= 239, name
        for literal in re.findall(r'"([^"]*)"', text):
            assert set(encode(literal)) <= glyphs.keys(), (name,literal)
        template = (SOURCE/(name+'.bas')).read_text()
        graph[name] = re.findall(r'^CALL (\w+) ',template,re.M)
        largest = max(largest,cost)
    def depth(name, ancestors=()):
        assert name not in ancestors, ('recursive M61 call', ancestors, name)
        return max((1+depth(c,ancestors+(name,)) for c in graph[name]),default=0)
    assert max(map(depth,graph)) <= 10
    normal = [glyphs[ord('A')+i] for i in range(26)]
    assert len(set(normal)) == 26
    for i, rows in enumerate(normal):
        selected = glyphs[encode(chr(0x430+i))[0]]
        assert selected == tuple(row ^ (0x41 if y in (0,6) else 0)
                                 for y,row in enumerate(rows))
    assert glyphs[ord('G')] == (0,)*7
    assert glyphs[ord('T')] == (127,)*7
    print(f'Turochamp package: 29 BASIC parts, maximum {largest} M8/CRLF bytes, '
          f'{len(font_data)}-byte 7x7 font, C6 quotas and call stack PASS')


if __name__ == '__main__':
    main()
