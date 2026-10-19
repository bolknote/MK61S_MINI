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
from layout import MODULES, LOCAL_ONLY, MAX_ARRAY_INDEX, SOURCE_BUDGET, PACKAGES, CLUSTERS
GAME = ROOT/'programs/games/Turochamp'
SOURCE = ROOT/'tools/turochamp/basic'


def decode_font(data, width=7, height=7):
    assert data[:8] == b'FMK2'+bytes((1,width,height,(width-1)<<4))
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
            result[c] = tuple(read(width) for _ in range(height))
    assert len(result) == int.from_bytes(data[8:10], 'little')
    assert (bit+7)//8 == len(data)
    return result


def main():
    for tool in ('assemble.py', 'font.py'):
        subprocess.run([sys.executable, ROOT/'tools/turochamp'/tool, '--check'], check=True)
    assert {p.stem for p in GAME.glob('*.tbi')} == set(PACKAGES.values()) | {'display'}
    assert {p.stem for p in SOURCE.glob('*.bas')} == set(MODULES) | LOCAL_ONLY
    storage = (ROOT/'code/program_store.hpp').read_text()
    assert SOURCE_BUDGET == int(re.search(r'MAX_LANGUAGE_SOURCE_SIZE = (\d+);', storage)[1])
    assert all(root in MODULES and members and root not in members for root, members in CLUSTERS.items())
    assert len({name for members in CLUSTERS.values() for name in members}) == sum(map(len, CLUSTERS.values()))
    assert not set(CLUSTERS).intersection(name for members in CLUSTERS.values() for name in members)
    driver = (GAME/'autoexec.m61').read_text()
    assert len(driver.encode())+driver.count('\n') <= 1536
    for name, ident in MODULES.items():
        assert f'if re=={ident} open {PACKAGES[name]}.tbi' in driver
    assert driver.startswith('reinit\nopen display.tbi\nif re==0 run :compact\nloadfont Turochamp320 Turochamp\nrun :ready\n:compact\nloadfont Turochamp\n:ready\nopen init.tbi\n')
    assert (GAME/'display.tbi').read_text() == '1 .RE=(GW>=320) AND (GH>=320)\n2 END\n'
    assert driver.endswith('if re==99 ret\nrun :dispatch\n')
    font_data = (GAME/'Turochamp.FMK').read_bytes()
    assert len(font_data) <= 1536
    glyphs = decode_font(font_data)
    large_data = (GAME/'Turochamp320.FMK').read_bytes()
    assert len(large_data) <= 8192
    large_glyphs = decode_font(large_data, 12, 24)
    for name in ('manual.md','rules.md','algorithm.md'):
        data = (GAME/name).read_bytes()
        assert len(data)+data.count(b'\n') <= 1536, name
    largest = 0
    graph = {}
    for name in set(PACKAGES.values()):
        text = (GAME/(name+'.tbi')).read_text()
        m8 = encode(text)
        cost = len(m8)+m8.count(b'\n')
        assert cost <= SOURCE_BUDGET, (name, cost)
        lines = text.splitlines()
        assert len(lines) <= 192 and max(map(len, map(encode,lines))) <= 239, name
        for literal in re.findall(r'"([^"]*)"', text):
            assert set(encode(literal)) <= glyphs.keys() | large_glyphs.keys(), (name,literal)
        largest = max(largest,cost)
    for name in MODULES:
        template = (SOURCE/(name+'.bas')).read_text()
        targets = set(re.findall(r'^(?:CALL|JUMP) (\w+)',template,re.M))
        assert targets <= MODULES.keys(), (name, targets - MODULES.keys())
        local = set(re.findall(r'^LOCAL (\w+)',template,re.M))
        assert local <= set(MODULES) | LOCAL_ONLY, (name, local)
        graph[name] = re.findall(r'^CALL (\w+) ',template,re.M)
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
    # Decode the shipped halves, checking joined tiles, both colours and all
    # cursor variants. Empty square fills and corner brackets have exact masks.
    from large_font import pair
    tiles = []
    for i in range(26):
        a,b = encode(pair(i))
        tile = tuple((left<<12)|right for left,right in zip(large_glyphs[a],large_glyphs[b]))
        tiles.append(tile)
        a,b = encode(pair(i,True))
        selected = tuple((left<<12)|right for left,right in zip(large_glyphs[a],large_glyphs[b]))
        for y in range(24):
            mask = sum(1<<(23-x) for x in range(24) if
                min(x,23-x)<=1 and min(y,23-y)<=4 or min(y,23-y)<=1 and min(x,23-x)<=4)
            assert selected[y] == tile[y]^mask
    assert len(set(tiles)) == 26
    assert tiles[6] == (0,)*24 and tiles[19] == (0xffffff,)*24
    assert MAX_ARRAY_INDEX < 385
    print(f'Turochamp package: {len(set(PACKAGES.values()))} BASIC files / {len(MODULES)} entries, '
          f'maximum {largest} M8/CRLF bytes, {len(font_data)}-byte 7x7 font, '
          'streamed-source/line quotas and call stack PASS')


if __name__ == '__main__':
    main()
