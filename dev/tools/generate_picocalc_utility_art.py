#!/usr/bin/env python3
"""Native 1-bit USB/UF2 artwork. Integer pixels, deterministic ZX0, no resampling."""
from pathlib import Path
import argparse,hashlib,json,subprocess,tempfile

ROOT=Path(__file__).resolve().parents[2]

# A small, purpose-drawn block alphabet for these banners. The two-pixel
# strokes are deliberate native pixel art, baked into the 320-wide assets;
# no font or framebuffer is resized by the device.
BANNER={
 'A':['0011100','0100010','1000001','1000001','1111111','1000001','1000001','1000001','1000001'],
 'B':['1111110','1000001','1000001','1000001','1111110','1000001','1000001','1000001','1111110'],
 'C':['0111110','1000001','1000000','1000000','1000000','1000000','1000000','1000001','0111110'],
 'D':['1111100','1000010','1000001','1000001','1000001','1000001','1000001','1000010','1111100'],
 'E':['1111111','1000000','1000000','1000000','1111110','1000000','1000000','1000000','1111111'],
 'F':['1111111','1000000','1000000','1000000','1111110','1000000','1000000','1000000','1000000'],
 'I':['0111110','0001000','0001000','0001000','0001000','0001000','0001000','0001000','0111110'],
 'J':['0001111','0000001','0000001','0000001','0000001','1000001','1000001','1000001','0111110'],
 'K':['1000001','1000010','1000100','1001000','1110000','1001000','1000100','1000010','1000001'],
 'L':['1000000','1000000','1000000','1000000','1000000','1000000','1000000','1000000','1111111'],
 'M':['1000001','1100011','1010101','1001001','1000001','1000001','1000001','1000001','1000001'],
 'O':['0111110','1000001','1000001','1000001','1000001','1000001','1000001','1000001','0111110'],
 'P':['1111110','1000001','1000001','1000001','1111110','1000000','1000000','1000000','1000000'],
 'R':['1111110','1000001','1000001','1000001','1111110','1001000','1000100','1000010','1000001'],
 'S':['0111111','1000000','1000000','1000000','0111110','0000001','0000001','0000001','1111110'],
 'T':['1111111','0001000','0001000','0001000','0001000','0001000','0001000','0001000','0001000'],
 'U':['1000001','1000001','1000001','1000001','1000001','1000001','1000001','1000001','0111110'],
 'W':['1000001','1000001','1000001','1000001','1000001','1001001','1010101','1100011','1000001'],
 'H':['1000001','1000001','1000001','1000001','1111111','1000001','1000001','1000001','1000001'],
 'Y':['1000001','1000001','0100010','0010100','0001000','0010000','0100000','1000000','1000000'],
 '2':['0111110','1000001','0000001','0000010','0000100','0001000','0010000','0100000','1111111'],
 '1':['0001000','0011000','0101000','0001000','0001000','0001000','0001000','0001000','0111110'],
 '6':['0011110','0100000','1000000','1000000','1111110','1000001','1000001','1000001','0111110'],
 '-':['0000000','0000000','0000000','0000000','0111110','0000000','0000000','0000000','0000000'],
 'Д':['0001110','0010010','0010010','0010010','0100010','0100010','1111111','1000001','1000001'],
 'З':['1111110','0000001','0000001','0000010','0011100','0000010','0000001','0000001','1111110'],
 'И':['1000001','1000001','1000011','1000101','1001001','1010001','1100001','1000001','1000001'],
 'Л':['0001111','0010001','0010001','0010001','0010001','0100001','0100001','1000001','1000001'],
 'П':['1111111','1000001','1000001','1000001','1000001','1000001','1000001','1000001','1000001'],
 'Ш':['1001001','1001001','1001001','1001001','1001001','1001001','1001001','1001001','1111111'],
 'Ч':['1000001','1000001','1000001','1000001','0111111','0000001','0000001','0000001','0000001'],
 'Г':['1111111','1000000','1000000','1000000','1000000','1000000','1000000','1000000','1000000']}
for original,latin in zip('АВЕКМНОРСТУ','ABEKMHOPCTY'):BANNER[original]=BANNER[latin]
TITLES={'usb':('USB-ДИСК','USB DISK'),'ejected':('КАРТА ИЗВЛЕЧЕНА','CARD EJECTED'),
        'uf2':('ПРОШИВКА UF2','UF2 FIRMWARE'),'ready':('ЗАГРУЗЧИК UF2','UF2 LOADER')}
LABELS={'title_'+state+'_'+language:title for state,labels in TITLES.items()
        for language,title in zip(('ru','en'),labels)}
LABELS['brand']='MK61S'

class Bitmap:
    def __init__(self,w,h):
        self.w,self.h=w,h
        self.data=bytearray((w//8)*h)
    def rect(self,x,y,w,h,on=True):
        for py in range(y,y+h):
            for px in range(x,x+w):
                assert 0<=px<self.w and 0<=py<self.h
                at=py*(self.w//8)+px//8;mask=128>>(px&7)
                if on:self.data[at]|=mask
                else:self.data[at]&=255^mask
    def path(self,points,thickness=3,on=True):
        for (x,y),(xx,yy) in zip(points,points[1:]):
            assert x==xx or y==yy
            self.rect(min(x,xx),min(y,yy),abs(x-xx)+thickness,abs(y-yy)+thickness,on)
    def box(self,x,y,w,h,t=3):
        self.rect(x,y,w,h);self.rect(x+t,y+t,w-2*t,h-2*t,False)
    def label(self,text,x,y,scale=1):
        glyphs={
            'U':['101','101','101','101','111'],
            'F':['111','100','110','100','100'],
            '2':['111','001','111','100','111'],
            'S':['111','100','111','001','111'],
            'D':['110','101','101','101','110']}
        for ch in text:
            for row,bits in enumerate(glyphs[ch]):
                for col,bit in enumerate(bits):
                    if bit=='1':self.rect(x+col*scale,y+row*scale,scale,scale)
            x+=4*scale
    def letters(self,text,x,y,advance=20,space=10,on=True):
        for ch in text:
            if ch==' ':x+=space;continue
            for row,bits in enumerate(BANNER[ch]):
                for col,bit in enumerate(bits):
                    if bit=='1':self.rect(x+2*col,y+2*row,3,3,on)
            x+=advance
        return x
    def micro(self,x,y):
        glyphs={'m':['00000','11010','10101','10101','10101','10101','10101'],
                'i':['010','000','110','010','010','010','111'],
                'c':['00000','01110','10001','10000','10000','10001','01110'],
                'r':['00000','10110','11001','10000','10000','10000','10000'],
                'o':['00000','01110','10001','10001','10001','10001','01110']}
        for ch in 'micro':
            for row,bits in enumerate(glyphs[ch]):
                for col,bit in enumerate(bits):
                    if bit=='1':self.rect(x+2*col,y+2*row,2,2)
            x+=2*(len(glyphs[ch][0])+1)
    def smile(self,x,y):
        for eye in (x,x+38):
            for dx,dy,w in [(0,6,3),(3,3,3),(6,0,4),(10,3,3),(13,6,3)]:self.rect(eye+dx,y+dy,w,3)
        self.rect(x+18,y+20,18,3);self.rect(x+21,y+23,12,3);self.rect(x+24,y+26,6,2)

def artwork():
    # Scenes occupy native rows 64..223. Black space is part of the bitmap;
    # ZX0 expands these rows straight into the retained 320-wide LCD buffer.
    usb=Bitmap(320,160)
    # Solid white case and a deep, stepped bezel, as in the approved drawing.
    # The animated eyes/mouth are the only parts not baked into this scene.
    usb.rect(34,23,88,82);usb.rect(30,27,96,74);usb.rect(27,32,102,64)
    usb.rect(36,33,84,63,False);usb.box(40,37,76,55,2)
    usb.rect(47,43,3,3);usb.rect(44,46,3,3);usb.rect(43,49,3,3)
    usb.rect(69,105,20,10);usb.rect(51,115,56,4)
    usb.rect(27,121,101,25);usb.rect(24,125,107,21)
    for row in range(4):
        for col in range(8):
            if (row+col)%2==0:usb.rect(31+col*3,127+row*3,3,3,False)
    usb.rect(91,130,26,7,False);usb.rect(95,133,18,1)
    # The card is a full-sized second character, rather than a tiny SD logo.
    usb.path([(220,37),(260,37),(260,41),(264,41),(264,45),(268,45),(268,49),
              (272,49),(272,53),(278,53),(278,117),(216,117),(216,113),(212,113),
              (212,45),(216,45),(216,41),(220,41),(220,37)],4)
    usb.micro(219,55);usb.letters('SD',229,77,advance=19)
    for x in range(221,273,9):usb.rect(x,103,5,14)
    usb.rect(240,121,13,7)
    usb.rect(136,108,21,18)
    # A small black USB trident inside the white plug.
    usb.path([(143,120),(143,112),(147,112)],2,False)
    usb.rect(147,110,3,5,False);usb.rect(139,115,3,3,False);usb.rect(147,117,4,3,False)
    usb.path([(128,129),(136,129),(136,120)],4)
    usb.path([(157,116),(169,116),(169,139),(246,139),(246,128)],5)
    usb.rect(258,10,4,11);usb.rect(272,12,4,7);usb.rect(269,19,4,6)
    usb.rect(282,25,4,4);usb.rect(279,29,4,4)
    chip=Bitmap(320,160)
    chip.path([(115,90),(203,90),(203,94),(207,94),(207,142),(203,142),
               (203,146),(115,146),(115,142),(111,142),(111,94),(115,94),(115,90)],4)
    for x in range(122,201,19):
        # Leave the insertion lane open instead of merging the arrow into a pin.
        if x!=160:chip.rect(x,82,8,8)
        chip.rect(x,150,8,10)
    for y in (100,118,136):
        chip.rect(98,y,13,7);chip.rect(211,y,13,7)
    chip.smile(132,110)
    for x,y in [(92,68),(222,72)]:
        chip.rect(x,y+3,10,3);chip.rect(x+3,y,3,10)
    chip.rect(104,33,4,5);chip.rect(108,38,4,4)
    chip.rect(218,28,4,7);chip.rect(215,35,4,4)
    card=Bitmap(80,72)
    card.path([(6,1),(56,1),(56,5),(60,5),(60,9),(64,9),(64,13),(68,13),
               (68,17),(76,17),(76,64),(72,64),(72,68),(6,68),(6,64),(2,64),
               (2,7),(6,7),(6,1)],3)
    for x in range(14,52,8):card.rect(x,7,4,12)
    card.rect(10,24,62,29);card.letters('UF2',16,29,advance=16,on=False)
    for y in range(2):
        for x in range(13):
            if (x+y)%2==0:card.rect(12+x*4,58+y*4,4,4)
    result={'usb':usb,'chip':chip,'cartridge':card}
    for state,labels in TITLES.items():
        for language,title in zip(('ru','en'),labels):
            banner=Bitmap(320,24);x=banner.letters(title,12,0)
            assert x<=312,title
            result['title_'+state+'_'+language]=banner
    brand=Bitmap(320,22);brand.letters('MK61S',12,0,advance=16);result['brand']=brand
    return result

BRIDGE=r'''
#include "zx0.hpp"
#include <iostream>
#include <iterator>
#include <vector>
int main(){
 std::vector<u8> in((std::istreambuf_iterator<char>(std::cin)),{}),out;
 std::vector<u8> work(4*(in.size()+1)+1024);zx0::EncodeResult result{};
 if(!zx0::encode(in.data(),in.size(),work.data(),work.size(),
   {&out,[](void*p,u8 b){((std::vector<u8>*)p)->push_back(b);return true;}},result))return 1;
 std::cout.write((const char*)out.data(),out.size());
}
'''

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--check',action='store_true');args=parser.parse_args()
    records={};lines=['// Generated by dev/tools/generate_picocalc_utility_art.py; do not edit.',
        '#ifndef MK61_PICOCALC_UTILITY_ART_HPP','#define MK61_PICOCALC_UTILITY_ART_HPP',
        '#include "rust_types.h"','namespace picocalc { namespace utility_art {']
    with tempfile.TemporaryDirectory(prefix='pico-utility-art-') as tmp:
        tmp=Path(tmp);(tmp/'pack.cpp').write_text(BRIDGE)
        subprocess.run(['clang++','-std=c++17','-O2','-I'+str(ROOT/'code'),str(tmp/'pack.cpp'),str(ROOT/'code/zx0_encode.cpp'),'-o',str(tmp/'pack')],check=True)
        def emit(name,data):
            lines.append('inline constexpr u8 '+name+'[] = {')
            for i in range(0,len(data),16):lines.append('    '+','.join(f'0x{v:02x}'for v in data[i:i+16])+',')
            lines.append('};')
        # Shared stroke shapes, not eight duplicate full-width title rasters.
        # The bitmap reference hashes below still prove exact native pixels.
        shapes=[];indices={}
        for ch in sorted(set(''.join(LABELS.values()))-{' '}):
            shape=tuple(int(row,2)for row in BANNER[ch])
            if shape not in shapes:shapes.append(shape)
            indices[ch]=shapes.index(shape)
        glyphs=bytes(value for shape in shapes for value in shape)
        packed=subprocess.check_output([str(tmp/'pack')],input=glyphs)
        emit('glyphs',packed);lines.append(f'inline constexpr unsigned GLYPH_BYTES={len(glyphs)}, GLYPH_COUNT={len(shapes)};')
        records['glyphs']={'width':7,'height':9,'raw_bytes':len(glyphs),'packed_bytes':len(packed),
            'packing':'zx0-stroke-table','raw_sha256':hashlib.sha256(glyphs).hexdigest(),'packed_sha256':hashlib.sha256(packed).hexdigest()}
        for name,b in artwork().items():
            raw=bytes(b.data)
            packed=bytes(255 if ch==' ' else indices[ch] for ch in LABELS[name]) if name in LABELS else subprocess.check_output([str(tmp/'pack')],input=raw)
            records[name]={'width':b.w,'height':b.h,'raw_bytes':len(raw),'packed_bytes':len(packed),
                'packing':'shared-stroke-glyphs' if name in LABELS else 'zx0',
                'raw_sha256':hashlib.sha256(raw).hexdigest(),'packed_sha256':hashlib.sha256(packed).hexdigest()}
            emit(name,packed)
    lines+=['} }','#endif','']
    outputs={ROOT/'ports/picocalc/utility_art.hpp':'\n'.join(lines),
             ROOT/'doc/picocalc-utility/manifest.json':json.dumps(records,indent=2)+'\n'}
    for path,data in outputs.items():
        if args.check:
            if not path.exists() or path.read_text()!=data:raise SystemExit('Stale artwork: '+str(path))
        else:path.parent.mkdir(parents=True,exist_ok=True);path.write_text(data)
    raw=sum(r['raw_bytes']for name,r in records.items()if name!='glyphs');packed=sum(r['packed_bytes']for r in records.values())
    print(f'Pico utility art: {raw} -> {packed} bytes ZX0/shared glyphs ({100*packed/raw:.1f}%), exact native pixels')

if __name__=='__main__':main()
