#!/usr/bin/env python3
"""Build the 7x7 chess-cell FMK2 face. Base text raster: Matrix Font, PD."""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'))
from generate_highnoon_font import BitWriter,crc16,put_le16,source_glyphs,WIDE_GLYPHS
from m8_codec import encode as m8

SHAPES={
    1:("..###..","..###..","...#...","..###..",".#####.","#######",".#####."),
    2:("..####.",".#####.","##.###.","...###.","..####.",".#####.","#######"),
    3:("...#...","..###..","..##...","...#...","..###..",".#####.","#######"),
    4:(".#.#.#.",".#####.","..###..","..###..",".#####.",".#####.","#######"),
    5:(".#.#.#.",".#####.","..###..","...#...","..###..",".#####.","#######"),
    6:("...#...","..###..","...#...",".#####.",".#####.","#######",".#####."),
}
OUTLINES={
    1:("..###..","..#.#..","...#...","..#.#..",".#...#.","#.....#","#######"),
    2:("..####.",".#...#.","##.#.#.","...#.#.","..#..#.",".#...#.","######."),
    3:("...#...","..#.#..","..##...","...#...","..#.#..",".#...#.","#######"),
    4:(".#.#.#.",".#####.","..#.#..","..#.#..",".#...#.",".#...#.","#######"),
    5:(".#.#.#.",".#...#.","..#.#..","...#...","..#.#..",".#...#.","#######"),
    6:("...#...","..###..","...#...",".#...#.",".#...#.",".#...#.","#######"),
}

def tile(piece:int,dark:int,selected:bool=False)->list[list[int]]:
    pixels=[[dark]*7 for _ in range(7)]
    if piece:
        rows=(SHAPES if (piece<0)!=bool(dark) else OUTLINES)[abs(piece)]
        pixels=[[int(c=='#')^dark for c in row] for row in rows]
    if selected:
        for x,y in ((0,0),(0,6),(6,0),(6,6)):pixels[y][x]^=1
    return pixels

def glyphs():
    source=source_glyphs();result={}
    codepoints=list(range(0x20,0x7f))+[0x401]+list(range(0x410,0x42f+1))+list(range(0x430,0x449+1))
    for codepoint in codepoints:
        pixels=[[0]*7 for _ in range(7)]
        width,rows=WIDE_GLYPHS.get(codepoint,(3,source.get(codepoint,source[ord('?')])) )
        for y,row in enumerate(rows):
            for x in range(width):pixels[y+1][x+(7-width)//2]=(row>>x)&1
        result[m8(chr(codepoint))[0]]=pixels
    for dark in (0,1):
        for piece in range(-6,7):
            index=13*dark+piece+6
            result[ord('A')+index]=tile(piece,dark)
            result[m8(chr(0x430+index))[0]]=tile(piece,dark,True)
    return result

def build()->bytes:
    all_glyphs=glyphs();codes=sorted(all_glyphs);ranges=[]
    first=prev=codes[0]
    for code in codes[1:]:
        if code!=prev+1:ranges.append((first,prev-first+1));first=code
        prev=code
    ranges.append((first,prev-first+1))
    header=bytearray(16);header[:4]=b'FMK2'
    header[4:8]=bytes((1,7,7,0x60));put_le16(header,8,len(codes));header[10]=len(ranges)
    for first,count in ranges:header+=bytes((first,count-1))
    writer=BitWriter(header)
    for code in codes:
        writer.write(0,1)
        for row in all_glyphs[code]:
            for pixel in row:writer.write(pixel,1)
    put_le16(writer.data,12,len(writer.data));put_le16(writer.data,14,crc16(writer.data))
    return bytes(writer.data)

def preview(path:Path):
    from PIL import Image,ImageDraw
    board=[[0]*8 for _ in range(8)]
    board[0]=[-4,-2,-3,-5,-6,-3,-2,-4];board[1]=[-1]*8
    board[6]=[1]*8;board[7]=[4,2,3,5,6,3,2,4]
    pixels=Image.new('1',(192,64),1)
    g=glyphs()
    def text(x,y,line):
        for char in line:
            bits=g[m8(char)[0]]
            for yy,row in enumerate(bits):
                for xx,bit in enumerate(row):pixels.putpixel((x+xx,y+yy),1-bit)
            x+=7
    text(2,0,' abcdefgh  ТУРОЧЕМП')
    for r in range(8):
        text(2,7+r*7,str(8-r))
        for f in range(8):
            p=board[r][f];index=13*((r+f)%2)+p+6
            char=chr(0x430+index) if(r,f)==(6,4) else chr(ord('A')+index)
            text(9+7*f,7+7*r,char)
    for y,line in enumerate(('БЕЛЫЕ','ВАШ ХОД','ХОД 1','ОТ -','НА e2','ХОД -','С/П МЕНЮ','ОК ВЫБОР'),1):
        text(79,7*y,line)
    path.parent.mkdir(parents=True,exist_ok=True)
    pixels.convert('RGB').resize((1152,384),Image.Resampling.NEAREST).save(path)

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--check',action='store_true')
    ap.add_argument('--preview',type=Path);args=ap.parse_args()
    path=ROOT/'programs/games/Turochamp/Turochamp.FMK';data=build()
    if args.check:
        if not path.is_file() or path.read_bytes()!=data:raise SystemExit('stale Turochamp.FMK')
    else:path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
    if args.preview:preview(args.preview)
    print(f'Turochamp.FMK: {len(data)} bytes; 7x7 board cells, 52 piece/cursor variants')

if __name__=='__main__':main()
