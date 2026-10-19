"""Native 12x24 text cells and paired 24x24 chess tiles for 320px displays.

Text preserves the reviewed Ark Pixel 12px strike, centred without resampling.
Chess silhouettes are original pixel art. Right halves occupy CP1251 symbols
unused by the game's text; the original left-half codes stay unchanged.
"""
from generate_highnoon_font import BitWriter, crc16, put_le16
from generate_ui_fonts import load_atlases
from m8_codec import decode, encode

WIDTH, HEIGHT = 12, 24
RIGHT_CODES = tuple(c for c in range(0x80, 0xB6) if c not in (0x98, 0xA8))
assert len(RIGHT_CODES) == 52


def pair(index, selected=False):
    left = chr(0x430+index) if selected else chr(ord('A')+index)
    return left + decode(bytes((RIGHT_CODES[index+26*selected],)))


def silhouette(piece):
    p = [[0]*24 for _ in range(24)]

    def rect(x0, y0, x1, y1, value=1):
        for y in range(y0, y1+1):
            for x in range(x0, x1+1):
                p[y][x] = value

    def circle(cx, cy, radius):
        for y in range(24):
            for x in range(24):
                if (x-cx)**2+(y-cy)**2 <= radius**2:
                    p[y][x] = 1

    def polygon(points):
        for y in range(24):
            for x in range(24):
                inside = False
                for (ax, ay), (bx, by) in zip(points, points[1:]+points[:1]):
                    if (ay > y+.5) != (by > y+.5) and x+.5 < (bx-ax)*(y+.5-ay)/(by-ay)+ax:
                        inside = not inside
                if inside:
                    p[y][x] = 1

    if piece == 1:
        circle(11.5, 5.5, 3.5)
        rect(9, 10, 14, 12)
        polygon([(10,12),(14,12),(17,19),(7,19)])
    elif piece == 2:
        polygon([(8,2),(12,4),(16,4),(18,8),(17,13),(16,17),(18,19),
                 (6,19),(8,15),(12,11),(8,12),(4,10),(5,7),(8,5)])
        rect(12, 7, 13, 8, 0)
    elif piece == 3:
        polygon([(12,2),(17,8),(15,11),(13,13),(16,18),(8,18),
                 (10,13),(7,10),(7,7)])
        for y in range(5, 10):
            rect(14-(y-5)//2, y, 15-(y-5)//2, y, 0)
    elif piece == 4:
        rect(5, 3, 18, 7)
        rect(8, 3, 9, 5, 0)
        rect(14, 3, 15, 5, 0)
        rect(8, 8, 15, 17)
        rect(6, 17, 17, 19)
    elif piece == 5:
        for x in (5, 11.5, 18):
            circle(x, 4, 1.5)
        polygon([(4,6),(9,10),(12,5),(15,10),(20,6),(16,14),(8,14)])
        polygon([(9,14),(15,14),(17,19),(7,19)])
    elif piece == 6:
        rect(11, 1, 12, 6)
        rect(9, 3, 14, 4)
        polygon([(7,8),(17,8),(16,12),(14,14),(17,19),(7,19),(10,14),(8,12)])
    rect(5, 20, 18, 21)
    return p


def tile(piece, dark, selected=False):
    shape = silhouette(abs(piece)) if piece else [[0]*24 for _ in range(24)]
    solid = (piece < 0) != bool(dark)
    pixels = [[dark]*24 for _ in range(24)]
    for y in range(24):
        for x in range(24):
            if shape[y][x] and (solid or any(
                    not (0 <= x+dx < 24 and 0 <= y+dy < 24) or not shape[y+dy][x+dx]
                    for dx, dy in ((-1,0),(1,0),(0,-1),(0,1)))):
                pixels[y][x] ^= 1
    if selected:
        for y in range(24):
            for x in range(24):
                if min(x,23-x) <= 1 and min(y,23-y) <= 4 or min(y,23-y) <= 1 and min(x,23-x) <= 4:
                    pixels[y][x] ^= 1
    return pixels


def glyphs(base):
    atlas = load_atlases()[0][1]
    result = {}
    for code in base:
        cp = ord(decode(bytes((code,))))
        source = atlas['by_codepoint'][cp]
        assert source['width'] <= WIDTH-2, (cp, source['width'])
        pixels = [[0]*WIDTH for _ in range(HEIGHT)]
        left = (WIDTH-source['width'])//2
        top = (HEIGHT-atlas['height'])//2+atlas['ascent']-source['bearing_y']
        for y, row in enumerate(source['rows']):
            for x, bit in enumerate(row):
                pixels[top+y][left+x] = int(bit)
        result[code] = pixels
    for dark in (0, 1):
        for piece in range(-6, 7):
            index = 13*dark+piece+6
            for selected in (False, True):
                pixels = tile(piece, dark, selected)
                left, right = encode(pair(index, selected))
                result[left] = [row[:WIDTH] for row in pixels]
                result[right] = [row[WIDTH:] for row in pixels]
    return result


def build(base):
    all_glyphs = glyphs(base)
    codes = sorted(all_glyphs)
    ranges = []
    first = previous = codes[0]
    for code in codes[1:]:
        if code != previous+1:
            ranges.append((first, previous-first+1))
            first = code
        previous = code
    ranges.append((first, previous-first+1))
    header = bytearray(16)
    header[:4] = b'FMK2'
    header[4:8] = bytes((1, WIDTH, HEIGHT, (WIDTH-1)<<4))
    put_le16(header, 8, len(codes))
    header[10] = len(ranges)
    for first, count in ranges:
        header += bytes((first, count-1))
    writer = BitWriter(header)
    for code in codes:
        writer.write(0, 1)
        for row in all_glyphs[code]:
            for pixel in row:
                writer.write(pixel, 1)
    assert len(writer.data) <= 8192
    put_le16(writer.data, 12, len(writer.data))
    put_le16(writer.data, 14, crc16(writer.data))
    return bytes(writer.data)
