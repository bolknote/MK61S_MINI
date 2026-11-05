#!/usr/bin/env python3
"""Original, integer-pixel 32x32 Explorer artwork and distribution copies.

WBMP uses 0 for black; Explorer turns those black pixels into foreground ink.
Generation and packaging use the standard library only. Pillow is optional for
the review sheet; neither firmware nor the build needs it.
"""

import argparse
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
ARTWORK=ROOT/'doc/explorer-icons'
PROGRAM_FOLDERS={
    'CHIP8':'chip8', 'Fonts':'fonts', 'app':'applications', 'examples':'examples',
    'games':'games', 'library':'library', 'sheets':'sheets', 'spectrum':'games',
    'games/Bumblebee':'bumblebee', 'games/Bumblebee Fly':'bee-flight',
    'games/Chase HQ':'chase', 'games/ELITE':'elite', 'games/Fox Hunting':'fox',
    'games/High Noon':'cowboy', 'games/Infinity Story':'story',
    'games/Lunolet 1':'rocket', 'games/Mult Lunolet':'lander',
    'games/Naval Battle':'ship', 'games/Pogonya':'pursuit', 'games/RACE':'race',
    'games/Runner':'runner', 'games/Samurai':'samurai',
    'games/Turochamp':'knight', 'games/Wumpus':'wumpus',
    'urq':'games', 'urq/house_that_jack_built':'games',
    'urq/trapped_in_time_ru':'games',
}
# These directories are produced by builders rather than copied from programs/.
BUNDLE_FOLDERS={**PROGRAM_FOLDERS, 'apps':'applications', 'System':'system',
    'urq':'games','apps/URQ':'games',
    'Games/URQ':'games','licenses/ryu':'license','licenses/urq':'license',
    'System/VMCache':'cache', 'licenses':'license', 'licenses/ui-fonts':'font-license'}
for _urq_game in ('house_that_jack_built', 'trapped_in_time_ru'):
    for _urq_prefix in ('apps/URQ', 'Games/URQ'):
        BUNDLE_FOLDERS[_urq_prefix + '/' + _urq_game] = 'games'
    BUNDLE_FOLDERS['licenses/urq/' + _urq_game] = 'license'

# Preserve the three already reviewed drawings exactly, including their pixels.
ORIGINALS={
    'knight': 'ffffffffffffffffffffffffffefdfffffe78fffffe207ffffc003ffffc003ffffc011ffff8008ffff18087ffc18047ff800043ff800023ff000023ff7c0023fe000021ff000011ff800011ffdc0011fffc0013fff80023fff80023fff80043fff00041ffe00000ffc000007f8000007f8000007f8000007ffffffffffffffff',
    'cowboy': 'fffffffffffffffffffffffffffffffffffdf7ffffe0e0ffffe000ffffe000ffffe000ffffe000ffffc0007fffc0007ffbcfff77f0000003f0000003e0000001f0000003f800000ffc00001fffc000ffffce0effffc000ffffc000fffff7f7ffffe1c3ffffc000ffffe001fffff003fffff807ffffffffffffffffffffffffff',
    'runner': 'ffffffffffffffffffffffffffffc3ffffffc3ffffffc3ffffffc3fffffffffffffefffffe0003fffc0003fff80001fff07001ffe0f000ffc1e000fff1e02003fbc03003ffc07803ff807c03ff00ffffff003ffffe000ffffe0003fffc1c03fff81f83fff83f83fff07f83fff07fc3ffe0ffc3ffffffc3ffffffffffffffffff',
}


class Canvas:
    def __init__(self):self.ink=bytearray(32*32)
    def point(self,x,y,ink=True):
        if 0<=x<32 and 0<=y<32:self.ink[y*32+x]=bool(ink)
    def rect(self,x0,y0,x1,y1,fill=False,ink=True,width=1):
        for y in range(y0,y1+1):
            for x in range(x0,x1+1):
                if fill or min(x-x0,x1-x,y-y0,y1-y)<width:self.point(x,y,ink)
    def line(self,x0,y0,x1,y1,width=1,ink=True):
        dx=abs(x1-x0);sx=1 if x0<x1 else -1
        dy=-abs(y1-y0);sy=1 if y0<y1 else -1;error=dx+dy
        while True:
            self.rect(x0,y0,x0+width-1,y0+width-1,True,ink)
            if x0==x1 and y0==y1:break
            twice=2*error
            if twice>=dy:error+=dy;x0+=sx
            if twice<=dx:error+=dx;y0+=sy
    def path(self,points,width=1,closed=False):
        points=list(points)
        for a,b in zip(points,points[1:]+([points[0]] if closed else [])):
            self.line(*a,*b,width)
    def polygon(self,points):
        # Integer ray crossings, sampled at pixel centres.
        for y in range(min(p[1] for p in points),max(p[1] for p in points)+1):
            for x in range(min(p[0] for p in points),max(p[0] for p in points)+1):
                inside=False
                for (ax,ay),(bx,by) in zip(points,points[1:]+points[:1]):
                    if (2*ay>2*y+1)!=(2*by>2*y+1):
                        left=(2*x+1-2*ax)*(by-ay)
                        right=(bx-ax)*(2*y+1-2*ay)
                        if (left<right) if by>ay else (left>right):inside=not inside
                if inside:self.point(x,y)
        self.path(points,closed=True)
    def ellipse(self,x0,y0,x1,y1,fill=False,ink=True,width=1):
        def inside(x,y,a,b,c,d):
            rx=c-a;ry=d-b
            return rx>0 and ry>0 and (2*x-a-c)**2*ry**2+(2*y-b-d)**2*rx**2<=rx**2*ry**2
        for y in range(y0,y1+1):
            for x in range(x0,x1+1):
                if inside(x,y,x0,y0,x1,y1) and (fill or not inside(x,y,x0+width,y0+width,x1-width,y1-width)):
                    self.point(x,y,ink)
    def wbmp(self):
        return b'\0\0\x20\x20'+bytes(
            sum((0x80>>bit) for bit in range(8) if not self.ink[y*32+x+bit])
            for y in range(32) for x in range(0,32,8))


def chip(c):
    c.rect(7,6,25,26,width=2)
    for at in (10,16,22):
        c.line(3,at,6,at,2);c.line(26,at,29,at,2)
        c.line(at,2,at,5,2);c.line(at,27,at,29,2)


def page(c):
    c.path([(6,3),(20,3),(27,10),(27,28),(6,28)],2,True)
    c.path([(20,3),(20,10),(27,10)])


def bee(c,flight=False):
    c.ellipse(6,5,16,15,width=2);c.ellipse(14,3,24,15,width=2)
    c.ellipse(5,12,25,24,True)
    c.rect(10,12,12,24,True,False);c.rect(17,12,19,24,True,False)
    c.ellipse(22,11,29,20,True);c.point(26,14,False)
    c.line(24,11,25,6);c.line(27,11,29,8);c.line(2,17,5,17,2)
    if flight:c.path([(3,28),(27,28),(24,25)]);c.line(27,28,24,30)


def draw(name):
    if name in ORIGINALS:return b'\0\0\x20\x20'+bytes.fromhex(ORIGINALS[name])
    c=Canvas()
    if name=='applications':
        c.rect(3,4,23,22,width=2);c.line(5,9,21,9)
        c.rect(10,12,29,28,True,False);c.rect(10,12,29,28,width=2)
        c.line(12,17,27,17);c.path([(14,21),(17,23),(14,25)])
        c.line(21,25,25,25)
    elif name=='chip8':
        chip(c);c.rect(12,10,20,22,width=2);c.line(13,16,19,16,2)
    elif name=='fonts':
        c.path([(3,26),(11,5),(19,26)],2);c.line(7,18,16,18,2)
        c.path([(22,17),(27,17),(28,26),(23,26),(22,22),(28,21)],2)
        c.line(3,29,29,29)
    elif name=='examples':
        c.path([(11,4),(21,4),(21,7),(19,7),(19,13),(28,26),(27,28),(5,28),(4,26),(13,13),(13,7),(11,7)],2,True)
        c.line(10,20,23,20);c.rect(13,23,14,24,True);c.point(19,25)
    elif name=='games':
        c.rect(4,22,28,28,width=2);c.rect(14,12,17,23,True)
        c.ellipse(11,4,21,14,True);c.ellipse(22,18,27,23,True)
        c.line(8,25,11,25)
    elif name=='library':
        for x,y in ((4,8),(12,4),(20,6)):
            c.rect(x,y,x+6,27,width=2);c.line(x+2,y+5,x+4,y+5)
        c.line(3,29,28,29)
    elif name=='sheets':
        c.rect(4,4,28,28,width=2);c.rect(6,6,26,10,True)
        for x in (12,20):c.line(x,11,x,26)
        for y in (16,22):c.line(6,y,26,y)
        c.rect(14,18,18,20,True)
    elif name=='bumblebee':bee(c)
    elif name=='bee-flight':bee(c,True)
    elif name=='chase':
        c.line(2,28,8,5,2);c.line(29,28,24,5,2);c.line(16,3,16,7,2)
        c.rect(8,13,24,26,True);c.path([(8,13),(11,10),(21,10),(24,13)])
        c.rect(10,15,22,19,True,False);c.rect(13,8,19,10,True)
        c.rect(10,23,12,24,True,False);c.rect(20,23,22,24,True,False)
    elif name=='elite':
        c.path([(2,17),(10,10),(21,10),(29,17),(20,24),(11,24)],2,True)
        c.path([(2,17),(16,19),(29,17)]);c.line(10,10,16,19);c.line(21,10,16,19)
        c.line(16,19,11,24);c.line(16,19,20,24)
        c.path([(4,4),(4,8)]);c.line(2,6,6,6);c.point(26,5);c.point(25,28)
    elif name=='fox':
        c.path([(3,4),(11,10),(21,10),(29,4),(26,20),(16,28),(6,20)],2,True)
        c.path([(6,15),(12,20),(16,26),(20,20),(27,15)])
        c.rect(9,15,12,16,True);c.rect(20,15,23,16,True)
        c.polygon([(13,22),(19,22),(16,25)])
    elif name=='story':
        c.path([(4,9),(13,7),(16,9),(19,7),(28,9),(28,27),(19,25),(16,27),(13,25),(4,27)],2,True)
        c.line(16,10,16,26)
        for y in (13,17,21):c.line(7,y,12,y-1);c.line(21,y-1,25,y)
        c.line(23,1,23,5);c.line(21,3,25,3);c.point(9,3)
    elif name=='rocket':
        c.ellipse(22,2,29,10,True);c.ellipse(25,1,30,7,True,False)
        c.path([(15,4),(21,13),(21,22),(9,22),(9,13)],2,True)
        c.ellipse(12,12,18,18,width=2)
        c.polygon([(9,15),(5,24),(9,22)]);c.polygon([(21,15),(25,24),(21,22)])
        c.line(12,25,12,29,2);c.line(18,25,18,29,2)
    elif name=='lander':
        c.path([(13,7),(19,7),(23,15),(9,15)],2,True)
        c.rect(13,10,19,13);c.line(16,3,16,6);c.point(15,2)
        c.path([(10,16),(6,24),(11,24)],2);c.path([(22,16),(26,24),(21,24)],2)
        c.line(2,28,29,28);c.ellipse(3,27,11,30);c.ellipse(23,2,29,8)
    elif name=='ship':
        c.polygon([(3,20),(29,20),(24,26),(8,26)])
        c.rect(7,12,14,19,width=2);c.line(16,5,16,19,2)
        c.polygon([(18,5),(25,7),(18,9)]);c.path([(19,17),(19,14),(25,14)],2)
        for x in (2,13,24):c.line(x,29,x+6,29)
    elif name=='pursuit':
        for x,y in ((3,3),(21,3),(3,21)):
            c.rect(x,y,x+7,y+7,width=2);c.point(x+3,y+3)
        c.path([(3,16),(16,16),(16,24),(20,24)],2)
        c.path([(18,21),(21,24),(18,27)])
        c.ellipse(23,20,29,28,width=2)
    elif name=='race':
        c.line(6,4,6,29,2);c.rect(8,5,28,20)
        for y in range(6,20):
            for x in range(9,28):
                if ((x-9)//4+(y-6)//4)%2==0:c.point(x,y)
        c.line(3,29,11,29)
    elif name=='samurai':
        c.ellipse(8,8,24,27,True)
        c.polygon([(3,3),(13,8),(14,14),(7,12)])
        c.polygon([(29,3),(19,8),(18,14),(25,12)])
        c.rect(10,17,22,20,True,False);c.line(16,15,16,21,2)
        c.line(13,24,19,24,1,False);c.line(11,28,21,28,2)
    elif name=='wumpus':
        c.ellipse(6,9,26,29,width=2)
        c.path([(7,13),(4,3),(13,10)],2);c.path([(25,13),(28,3),(19,10)],2)
        c.ellipse(10,14,14,19,True);c.ellipse(19,14,23,19,True)
        c.line(11,23,22,23,2);c.line(13,23,13,26);c.line(20,23,20,26)
    elif name=='system':
        for x0,y0,x1,y1 in ((13,2,19,8),(13,24,19,30),(2,13,8,19),(24,13,30,19)):
            c.rect(x0,y0,x1,y1,True)
        for points in ([(5,5),(10,5),(13,10),(9,13),(5,10)],[(22,5),(27,5),(27,10),(23,13),(20,10)],
                       [(5,22),(10,20),(13,23),(10,27),(5,27)],[(22,20),(27,22),(27,27),(22,27),(20,23)]):c.polygon(points)
        c.ellipse(6,6,26,26,True);c.ellipse(11,11,21,21,True,False)
    elif name=='cache':
        chip(c);c.polygon([(16,9),(21,9),(17,16),(22,16),(12,24),(14,18),(10,18)])
    elif name=='license':
        page(c);c.path([(11,19),(15,23),(23,15)],2)
    elif name=='font-license':
        page(c);c.path([(10,23),(16,12),(22,23)],2);c.line(13,19,19,19,2)
    else:raise ValueError('Unknown icon: '+name)
    return c.wbmp()


def validate(data):
    if len(data)!=132 or data[:4]!=b'\0\0\x20\x20' or data[4:] in (b'\0'*128,b'\xff'*128):
        raise ValueError('Expected nonempty 32x32 Type 0 WBMP')
    return data


def copy_icon(role,destination):
    destination=Path(destination)
    destination.write_bytes(validate((ARTWORK/(role+'.wbmp')).read_bytes()))
    return destination


def install_bundle_icons(directory,folders=None):
    directory=Path(directory)
    roles={path.casefold():role for path,role in BUNDLE_FOLDERS.items()}
    allowed=None if folders is None else {path.casefold() for path in folders}
    result=[]
    # Use the spelling of actual directories (Apps on STM32, apps on Pico).
    for folder in sorted(path for path in directory.rglob('*') if path.is_dir()):
        relative=folder.relative_to(directory).as_posix().casefold()
        if allowed is not None and relative not in allowed:continue
        role=roles.get(relative)
        if role:result.append(copy_icon(role,folder/'autoexec.wbmp'))
    return result


def generate(check=False):
    outputs={ARTWORK/(role+'.wbmp'):validate(draw(role)) for role in set(BUNDLE_FOLDERS.values())}
    outputs.update({ROOT/'programs'/folder/'autoexec.wbmp':draw(role) for folder,role in PROGRAM_FOLDERS.items()})
    for path,data in sorted(outputs.items()):
        if check:
            if not path.is_file() or path.read_bytes()!=data:raise ValueError(f'{path}: regenerate Explorer icons')
        else:
            path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
    folders={p.relative_to(ROOT/'programs').as_posix() for p in (ROOT/'programs').rglob('*') if p.is_dir()}
    if folders!=set(PROGRAM_FOLDERS):raise ValueError(f'Unreviewed program folders: {sorted(folders^set(PROGRAM_FOLDERS))}')
    print(f'Explorer icons: {len(set(BUNDLE_FOLDERS.values()))} drawings, {len(PROGRAM_FOLDERS)} program folders')


def preview(destination):
    from PIL import Image,ImageDraw,ImageFont
    entries=list(PROGRAM_FOLDERS.items())+[(folder,role) for folder,role in BUNDLE_FOLDERS.items()
        if folder not in PROGRAM_FOLDERS and folder!='apps']
    width=800;cell_width=160;cell_height=116
    sheet=Image.new('RGB',(width,((len(entries)+4)//5)*cell_height),(23,23,23))
    painter=ImageDraw.Draw(sheet)
    font=None
    for candidate in ('DejaVuSans.ttf','/System/Library/Fonts/Supplemental/Arial.ttf'):
        try:font=ImageFont.truetype(candidate,13);break
        except OSError:pass
    if font is None:font=ImageFont.load_default()
    for i,(folder,role) in enumerate(entries):
        data=validate(draw(role));tile=Image.new('RGB',(32,32),(23,23,23))
        for y in range(32):
            for x in range(32):
                if not data[4+y*4+x//8]&(0x80>>(x%8)):tile.putpixel((x,y),(245,245,245))
        x=i%5*cell_width;y=i//5*cell_height
        sheet.paste(tile.resize((64,64),Image.Resampling.NEAREST),(x+48,y+8))
        label=folder.removeprefix('games/')
        painter.text((x+80,y+84),label,font=font,fill=(245,245,245),anchor='mt')
    Path(destination).parent.mkdir(parents=True,exist_ok=True);sheet.save(destination)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    action=parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--generate',action='store_true');action.add_argument('--check',action='store_true')
    action.add_argument('--bundle',type=Path,help='add stock icons only to directories already present in a local bundle')
    action.add_argument('--preview',type=Path,help='render a review sheet (requires Pillow)')
    args=parser.parse_args()
    if args.bundle is not None:
        for path in install_bundle_icons(args.bundle):print(path)
    elif args.preview is not None:preview(args.preview)
    else:generate(args.check)


if __name__=='__main__':main()
