#!/usr/bin/env python3
"""Render panel-native game artwork from vectors/scans; keep compact WBMPs intact."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET

from generate_highnoon_font import BitWriter, put_le16, crc16
from generate_ui_fonts import load_atlases

ROOT=Path(__file__).resolve().parents[1]
ART=ROOT/'doc/game-artwork'
SOURCES={
    'Bumblebee/scene':'bumblebee.svg',
    'Bumblebee Fly/scene':'bumblebee-fly-tm1988-03.png',
    'Bumblebee Fly/plan':'bumblebee-plan-tm1988-03.png',
    'Chase HQ/scene':'chase-hq.svg',
    'Fox Hunting/scene':'fox-hunting-nizh1990-10.jpg',
    'Infinity Story/scene':'infinity-story-tm1988-01.png',
    'Lunolet 1/scene':'lunolet-1-tm1985-06.jpg',
    'Lunolet 1/thrust':'lunolet-1-thrust-tm1985-06.jpg',
    'Mult Lunolet/scene':'mult-lunolet.svg',
    'Naval Battle/scene':'naval-battle.svg',
    'Pogonya/map':None,'Pogonya/view':None,
    'Samurai/scene':'samurai.svg',
    'Wumpus/exits':'wumpus-exits.svg','Wumpus/scene':'wumpus-1976.jpg',
}


def native_text(value,x,y,atlas):
    paths=[]
    for char in value:
        g=atlas['by_codepoint'].get(ord(char),atlas['by_codepoint'][ord('?')])
        for dy,row in enumerate(g['rows']):
            for dx,bit in enumerate(row):
                if bit=='1':
                    paths.append(f'M{round(x)+g["safe_bearing_x"]+dx} {round(y)+atlas["ascent"]-g["bearing_y"]+dy}h1v1h-1z')
        x+=g['advance']
    return '<path fill="black" d="'+''.join(paths)+'"/>'


def native_svg(source,atlas):
    root=ET.fromstring(source.read_text())
    _,_,w,h=map(float,root.attrib['viewBox'].split())
    scale=min(320/w,224/h)
    labels=[]
    for element in list(root):
        label=element.attrib.get('aria-label')
        if label:
            points=[tuple(map(float,p)) for p in re.findall(r'M\s*([\d.-]+)[ ,]+([\d.-]+)',element.attrib['d'])]
            if points:
                x=min(p[0] for p in points)*scale;y=min(p[1] for p in points)*scale
                labels.append(native_text(label,x,y,atlas))
                root.remove(element)
    contents=''.join(ET.tostring(e,encoding='unicode') for e in root)
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="{round(w*scale)}" height="{round(h*scale)}"><g transform="scale({scale})">{contents}</g>'+''.join(labels)+'</svg>'


def pogonya(name,atlas):
    # New vector diagrams of the published six-block layout / segment view.
    # They are explanatory drawings, not enlarged historical scan pixels.
    shapes=['<rect width="320" height="208" fill="white"/>']
    if name=='map':
        for row in range(2):
            for col in range(3):
                x=8+col*104;y=8+row*100
                shapes.append(f'<rect x="{x}" y="{y}" width="96" height="92" fill="none" stroke="black" stroke-width="2"/>')
                label=(('Е','-','Е'),('Г','X','Г'))[row][col]
                shapes.append(native_text(label,x+40,y+34,atlas))
    else:
        shapes.append('<path d="M4 4H316V204H4Z M5 204L142 105M5 5L142 94M315 204L178 105M315 5L178 94" fill="none" stroke="black" stroke-width="2"/>')
        for side in (False,True):
            for index,x in enumerate((12,52,83,107,125)):
                xx=320-x if side else x
                low=190-index*19;high=18+index*16
                shapes.append(f'<path d="M{xx} {high}V{low}" stroke="black" stroke-width="2"/>')
            for y in (65,125,170):
                shapes.append(f'<path d="M{315 if side else 5} {y}L{178 if side else 142} 100" stroke="black" stroke-width="2"/>')
        shapes.append('<path d="M159 124V146M159 158V180" stroke="black" stroke-width="2"/><rect x="150" y="99" width="18" height="8" fill="none" stroke="black" stroke-width="2"/>')
    return '<svg xmlns="http://www.w3.org/2000/svg" width="320" height="208">'+''.join(shapes)+'</svg>'


def bee_font():
    glyphs={cp:[[0]*16 for _ in range(32)] for cp in (32,45,48,56)}
    for y in range(32):
        for x in range(16):
            def ring(cx,cy,rx,ry):
                return ((x-cx)/rx)**2+((y-cy)/ry)**2<=1 and ((x-cx)/(rx-1.5))**2+((y-cy)/(ry-1.5))**2>=1
            glyphs[48][y][x]=int(ring(7.5,15.5,5.5,11.5))
            glyphs[56][y][x]=int(ring(7.5,9.5,5.5,5.5) or ring(7.5,21.5,5.5,6.5))
            glyphs[45][y][x]=int(2<=x<=13 and 15<=y<=16)
    prefix=bytearray(16);prefix[:4]=b'FMK2';prefix[4:8]=bytes((1,16,32,0xF0))
    put_le16(prefix,8,len(glyphs));prefix[10]=4
    for cp in glyphs:prefix+=bytes((cp,0))
    writer=BitWriter(prefix)
    for rows in glyphs.values():
        writer.write(0,1)
        for row in rows:
            for bit in row:writer.write(bit,1)
    put_le16(writer.data,12,len(writer.data));put_le16(writer.data,14,crc16(writer.data))
    return bytes(writer.data)


def mbuint(n):
    result=bytearray((n&127,));n>>=7
    while n:result.insert(0,(n&127)|128);n>>=7
    return result


def pbm_to_wbmp(data):
    # ImageMagick P4 is binary; consume exactly the header, never strip pixels.
    match=re.match(rb'P4\s+(?:#[^\n]*\n\s*)*(\d+)\s+(\d+)\s',data)
    if not match:raise ValueError('not a binary PBM')
    w,h=map(int,match.groups());pixels=data[match.end():]
    if len(pixels)!=(w+7)//8*h:raise ValueError('PBM length')
    pixels=bytearray(value^255 for value in pixels) # WBMP: 0 is black, PBM: 1.
    if w%8:
        for y in range(h):pixels[(y+1)*((w+7)//8)-1]&=(255<<(8-w%8))&255
    return bytes(b'\0\0'+mbuint(w)+mbuint(h)+pixels),(w,h)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--check',action='store_true')
    args=parser.parse_args()
    magick=shutil.which('magick');rsvg=shutil.which('rsvg-convert')
    if not magick or not rsvg:raise SystemExit('Requires ImageMagick and librsvg')
    atlas=load_atlases()[0][2] # Native Ark 16px, one source pixel per output pixel.
    records=[]
    def publish(path,data):
        if args.check:
            if path.read_bytes()!=data:raise ValueError(f'{path}: regenerate assets')
        else:path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
    with tempfile.TemporaryDirectory() as raw:
        temporary=Path(raw)
        for target,source in SOURCES.items():
            path=ROOT/'programs/games'/(target+'-320.wbmp')
            if source is None or source.endswith('.svg'):
                svg=pogonya(Path(target).name,atlas) if source is None else native_svg(ART/source,atlas)
                vector=temporary/'source.svg';vector.write_text(svg)
                png=temporary/'source.png'
                subprocess.run([rsvg,str(vector),'-o',str(png)],check=True)
                image_source=png
                if source is None:publish(ART/'native'/('pogonya-'+Path(target).name+'.svg'),svg.encode())
                mode='native vector geometry and native Ark 16px labels'
            else:
                image_source=ART/source
                mode='original scan, reduced only; no enlargement'
            pbm=subprocess.check_output([magick,str(image_source),'-background','white','-alpha','remove',
                '-resize','320x224>','-colorspace','Gray','-dither','FloydSteinberg','-monochrome','pbm:-'])
            wbmp,geometry=pbm_to_wbmp(pbm);publish(path,wbmp)
            records.append({'path':str(path.relative_to(ROOT)),'source':str((ART/source).relative_to(ROOT)) if source else 'new explanatory vector; see SOURCES.markdown',
                'mode':mode,'width':geometry[0],'height':geometry[1],
                'compact_sha256':hashlib.sha256((ROOT/'programs/games'/(target+'.wbmp')).read_bytes()).hexdigest(),
                'sha256':hashlib.sha256(wbmp).hexdigest(),
                'source_sha256':hashlib.sha256((ART/source).read_bytes()).hexdigest() if source else hashlib.sha256(svg.encode()).hexdigest()})
    publish(ROOT/'programs/games/Bumblebee/Bumblebee320.FMK',bee_font())
    publish(ART/'native/manifest.json',(json.dumps(records,indent=2)+'\n').encode())
    print(f'{len(records)} native illustrations and Bumblebee 16x32 font checked')


if __name__=='__main__':main()
