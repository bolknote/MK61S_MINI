#!/usr/bin/env python3
"""Qualify the remaining native text/graphics paths on one exact Pico UID/build.

Temporary files are read back and removed. Registers, stack, program, cwd,
font selection and USB Screen mode are restored, including on failure.
LCD CRC checks the DMA source; it is not optical panel readback.
"""
import argparse
from datetime import datetime,timezone
import hashlib,json,os,re,subprocess,sys,time
from pathlib import Path
from hil_picocalc_software import connect,calculator,restore,raw,font
from hil_c5_stack import read_file,write_file
from hil_picocalc_display import lcd_crc
from hil_portable_system_apps import png
from hil_turochamp_performance import Font

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from build_picocalc import compiler_bin
from generate_ui_fonts import load_atlases


class Ark:
    def __init__(self):self.face=load_atlases()[0][2]
    @staticmethod
    def pixel(frame,x,y,value=True):
        if 0<=x<320 and 0<=y<320:
            at=y//8*320+x;mask=1<<(y%8)
            if value:frame[at]|=mask
            else:frame[at]&=~mask
    def width(self,text):return sum(self.face['by_codepoint'][ord(c)]['advance'] for c in text)
    def text(self,frame,text,x,y,cell=0):
        for char in text:
            g=self.face['by_codepoint'][ord(char)];left=x+(cell-g['advance'])//2 if cell else x
            for dy,row in enumerate(g['rows']):
                for dx,bit in enumerate(row):
                    if bit=='1':self.pixel(frame,left+g['safe_bearing_x']+dx,y+self.face['ascent']-g['bearing_y']+dy)
            x+=cell or g['advance']


def wbmp(width,height):
    def mb(n):return bytes((128|(n>>7),n&127)) if n>=128 else bytes((n,))
    data=bytearray(b'\0\0'+mb(width)+mb(height))
    for y in range(height):
        for x in range(0,width,8):
            data.append(sum(128>>bit for bit in range(8) if x+bit<width and ((x+bit)*3+y*5)%11>=5))
    return bytes(data)


def image_frame(data,*,y_offset=0):
    assert data[:2]==b'\0\0';at=2
    def mb():
        nonlocal at
        value=0
        while True:
            byte=data[at];at+=1;value=(value<<7)|(byte&127)
            if not byte&128:return value
    width,height=mb(),mb();stride=(width+7)//8;out=bytearray(12800)
    for y in range(min(320,height-y_offset)):
        for x in range(min(320,width)):
            if not data[at+(y+y_offset)*stride+x//8]&(128>>(x%8)):Ark.pixel(out,x,y)
    return bytes(out)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',required=True);parser.add_argument('--uid',required=True)
    parser.add_argument('--firmware-directory',type=Path,required=True)
    parser.add_argument('--wbmp-app',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    build=json.loads((args.firmware_directory/'manifest.json').read_text())
    directory='/MK61S-NATIVETEXT-'+datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')
    work=args.output/'build';work.mkdir();toolchain=compiler_bin(None)
    probes={}
    for name,source in (('TEXTCHK',ROOT/'tests/picocalc_native_text_probe.cpp'),('LEGACY',ROOT/'tests/picocalc_native_text_probe.cpp'),('WBMPCHK',work/'wbmp.cpp')):
        if name=='WBMPCHK':source.write_text(f'#define PICO_APPS_DIRECTORY "{directory}"\n#include "{ROOT}/tests/picocalc_wbmp_handler_probe.cpp"\n')
        subprocess.run([sys.executable,str(ROOT/'tools/build_portable_app.py'),'--target','picocalc-pico-h','--name',name,
            '--source',str(source),'--shared-runtime','--arm-toolchain-bin',str(toolchain),'--output-dir',str(work/name),
            *(['--pico-legacy-display'] if name=='LEGACY' else [])],
            check=True,stdout=subprocess.DEVNULL)
        probes[name+'.APP']=(work/name/(name+'.APP')).read_bytes()
    probes['WBMP.APP']=args.wbmp_app.read_bytes();probes['PATTERN.wbmp']=wbmp(320,360)
    probes['wide.txt']=('ЖЩЮ←\n'+'Щ'*30).encode()
    probes['native.m61']='print off\nprint "ЖЩЮ←"\nwait 60000\n'.encode()
    probes['native.bas']='10 CLS\n20 PRINT AT 8,100;"ЖЩЮ←"\n30 SHOW\n40 PAUSE\n50 END\n'.encode()
    probes['native.foc']='1.10 CLS; PRINT AT 8,100,"ЖЩЮ←"\n1.20 SHOW; ASK; EXIT\n'.encode()
    probes['image.wbmp']=wbmp(16,8)
    probes['image-320.wbmp']=(ROOT/'programs/games/Pogonya/map-320.wbmp').read_bytes()
    probes['image.md']=b'![Native image](image.wbmp)\n'
    probes['Bumblebee320.FMK']=(ROOT/'programs/games/Bumblebee/Bumblebee320.FMK').read_bytes()
    probes['bee.m61']=b'loadfont Bumblebee320\nprint off\nprint "'+br'\x1B[5;1H-0008'+b'"\nwait 60000\n'
    for asset in (ROOT/'programs/games/Bumblebee').iterdir():
        if asset.is_file():probes['Bumblebee/'+asset.name]=asset.read_bytes()
    ark=Ark();report=dict(passed=False,uid=args.uid,build=build['build_id'].upper(),uf2_sha256=build['uf2_sha256'],
        recorded_at_utc=datetime.now(timezone.utc).isoformat(),directory=directory,cases=[],screens={})
    p=connect(args.port,args.uid);p.native_display=True;before=None;created=False;initial=None;prompt_ru_toggled=False
    def passed(label):report['cases'].append(label);print('PASS '+label,flush=True)
    def picture(name,expected=None):
        p.pump(.25);start=len(p.frames);p.send(0x16);deadline=time.monotonic()+20
        while time.monotonic()<deadline:
            p.pump(.04)
            if len(p.frames)<=start or (expected is not None and p.frames[-1]!=expected):continue
            frame=p.frames[-1];wanted=lcd_crc(frame);status=p.status()
            if 'LCD_PENDING=0 ' in status and 'LCD_FRAME_CRC='+wanted in status:break
        else:
            if p.frames:png(p.frames[-1],args.output/(name+'-actual.png'))
            if expected is not None:png(expected,args.output/(name+'-expected.png'))
            raise AssertionError((name,'frame mismatch',p.status()))
        assert len(frame)==12800
        png(frame,args.output/(name+'.png'));report['screens'][name]=dict(frame_sha256=hashlib.sha256(frame).hexdigest(),lcd_crc=wanted)
        return frame
    def band(frame,expected,top,bottom):
        assert all(bool(frame[y//8*320+x]&(1<<(y%8)))==bool(expected[y//8*320+x]&(1<<(y%8)))
            for y in range(top,bottom) for x in range(320)),('band mismatch',top,bottom)
    def stop():
        raw(p,b'\x1b');p.commands();calculator(p);p.expect('M61_ACTIVE=0','SERVICE=CLOSED')
    def indicator_font(value):
        font(p,1,16);raw(p,b'\xb5'*20)
        current=int(re.search(r'\bFONT=(\d+)/',p.status())[1])
        if current!=value:raw(p,b'\xb7')
        calculator(p);p.pump(1.3)
    try:
        initial=p.status();report['initial']=initial
        for marker in ('BUILD='+build['build_id'].upper(),'CRASH=NONE','FIRMWARE_CRC=valid','SD=OK','KBD=OK','SERVICE=CLOSED','DIRTY=0','RUN=0 BUSY=0'):
            assert marker in initial,(marker,initial)
        before={c:p.command(c) for c in ('reg','stk','hout','dump','pwd')}
        (args.output/'snapshot.json').write_text(json.dumps(before,indent=2)+'\n')
        selected=re.search(r'UI_FONT_FAMILY=(\d+) UI_FONT_SIZE=(\d+) UI_FONT_KEY=([0-9A-F]+)',initial).groups()
        report['font_before']=selected
        report['indicator_font_before']=int(re.search(r'\bFONT=(\d+)/',initial)[1])
        if selected[:2]!=('1','16'):font(p,1,16);calculator(p)
        assert 'ERROR' not in p.command('mkdir '+directory);created=True
        assert 'ERROR' not in p.command('mkdir '+directory+'/Bumblebee')
        for name,data in probes.items():
            write_file(p,directory+'/'+name,data);assert read_file(p,directory+'/'+name)==data
            print('Installed probe '+name,flush=True)
        p.command('uscreen on');p.attach_waiting()
        if 'RTC_SET=1' in initial:
            frame=picture('clock-native')
            hh,mm=re.search(r'RTC=\d+-\d+-\d+T(\d+):(\d+)',p.status()).groups()
            expected=bytearray(12800);value=hh+':'+mm;ark.text(expected,value,310-ark.width(value),9)
            assert all(bool(frame[y//8*320+x]&(1<<(y%8)))==bool(expected[y//8*320+x]&(1<<(y%8)))
                for y in range(32) for x in range(240,320))
            passed('idle clock uses the exact native Ark strike, right aligned in the title row')
        assert 'ERROR' not in p.command('poke X 12345')
        indicator_font(1);frame=picture('indicator-native-font')
        shown=re.search(r'\bX=\[([^\]]+)\]',p.status())[1];expected=bytearray(12800);slot=0
        for char in shown:
            if char in '.,':
                for dy in range(2):
                    for dx in range(2):ark.pixel(expected,9+(slot-1)*26+18+dx,114+dy)
            elif slot<12:
                ark.text(expected,'O' if char=='0' else char,9+slot*26,100,16);slot+=1
        band(frame,expected,91,126);indicator_font(report['indicator_font_before'])
        font(p,4,16);calculator(p);frame=picture('interface-native-mono')
        expected=bytearray(12800);ark.text(expected,'MK61S',10,9,16)
        assert all(bool(frame[y//8*320+x]&(1<<(y%8)))==bool(expected[y//8*320+x]&(1<<(y%8)))
            for y in range(32) for x in range(8,112))
        start=len(p.text);p.open(directory+'/LEGACY.APP');p.wait_text(b'LEGACY TEXT READY',start)
        glyph=bytes.fromhex(re.search(rb'LEGACY GLYPH=([0-9A-F]{64})',p.text[start:])[1].decode())
        frame=picture('legacy-font-and-geometry');expected=bytearray(12800)
        for y in range(16):
            for x in range(10):
                if glyph[y*2+x//8]&(128>>(x%8)):ark.pixel(expected,64+x,96+y)
        assert all(bool(frame[(96+y)//8*320+64+x]&(1<<((96+y)%8)))==bool(expected[(96+y)//8*320+64+x]&(1<<((96+y)%8)))
            for y in range(64) for x in range(192))
        raw(p,b'\r');p.wait_text(b'LEGACY TEXT PASS',start);p.commands();calculator(p)
        passed('real legacy M0 APP: 192x64, four 16px rows, 10x16 glyph/12px advance and public font service agree pixel-for-pixel')
        font(p,1,16);calculator(p)
        passed('alternate calculator digits and Ark Mono interface use native strikes; selected indicator font restored')
        # Ordinary native APP cells must fit the widest MK8 navigation glyph.
        start=len(p.text);p.open(directory+'/TEXTCHK.APP');p.wait_text(b'NATIVE TEXT MONO READY',start)
        report['angle_before']=int(re.search(rb'ANGLE=([012])',p.text[start:])[1])
        expected=bytearray(12800);ark.text(expected,'ЖЩЮ←',2,0,16);picture('app-mono-wide',bytes(expected))
        raw(p,b'\r');p.wait_text(b'NATIVE TEXT EDITOR READY',start)
        expected=bytearray(12800);ark.text(expected,'>',2,0,16);ark.text(expected,'Щ'*17,18,0,16)
        for x in range(2+18*16,2+19*16):ark.pixel(expected,x,17)
        picture('app-editor-cursor',bytes(expected))
        raw(p,b'\r');p.wait_text(b'NATIVE TEXT UI READY',start)
        expected=bytearray(12800);ark.text(expected,'ЖЩЮ←',2,12*19);picture('app-ui-row-12',bytes(expected))
        raw(p,b'\r');p.wait_text(b'NATIVE TEXT PASS',start);p.commands();calculator(p)
        passed('native APP: wide Cyrillic/arrows, 19-column fixed cells, editor horizontal scroll/cursor, proportional row 12; exact pixels and DMA CRC')
        # The default M61 grid is native 20x10; no 9px overlap remains.
        start=len(p.text);p.open(directory+'/native.m61');p.wait_text(b'mk61> ',start)
        p.expect('M61_ACTIVE=1','COLS=20 ROWS=10')
        expected=bytearray(12800);ark.text(expected,'ЖЩЮ←',0,20,16);picture('m61-wide',bytes(expected));stop()
        passed('M61 default native 20x10 geometry, centred Ark strike and intact wide glyphs')
        for suffix in ('bas','foc'):
            start=len(p.text);p.open(directory+'/native.'+suffix);p.expect('SERVICE=CONSOLE')
            expected=bytearray(12800);ark.text(expected,'ЖЩЮ←',8,100);picture(suffix+'-print-at',bytes(expected))
            raw(p,b'\r');p.wait_text(b'VM_RESULT=OK',start);calculator(p)
        passed('BASIC and FOCAL PRINT AT: identical full native glyphs at pixel coordinates, independent Ark oracle')
        # Real built-in source editor and save-name prompt, through BIOS codes.
        raw(p,b'\t'+b'\xb5'*20+b'\xb6'*3+b'\r');p.expect('SERVICE=BROWSER')
        raw(p,b'/'+directory.encode()+b'/wide.txt\r');p.expect('SERVICE=EDITOR')
        frame=picture('source-editor-wide');expected=bytearray(12800);ark.text(expected,'ЖЩЮ←',8,42)
        for x in range(8,15):ark.pixel(expected,x,57)
        band(frame,expected,42,59)
        raw(p,b'\xb6\xd5');frame=picture('source-editor-scroll')
        visible=30
        while ark.width('Щ'*visible)+8>304:visible-=1
        expected=bytearray(12800);ark.text(expected,'Щ'*visible,8,59)
        for x in range(8+ark.width('Щ'*visible),15+ark.width('Щ'*visible)):ark.pixel(expected,x,74)
        band(frame,expected,59,76)
        raw(p,b'\x81'+b'\x08'*256+b'\x88'+b'O'*30);p.expect('SERVICE=PROMPT')
        prompt_ru_toggled=True
        frame=picture('save-name-prompt');expected=bytearray(12800);ark.text(expected,'Щ'*visible,8,76)
        for x in range(8+ark.width('Щ'*visible),15+ark.width('Щ'*visible)):ark.pixel(expected,x,91)
        band(frame,expected,76,93);raw(p,b'\x88\x1b');prompt_ru_toggled=False;calculator(p)
        passed('built-in editor and UTF-8 filename prompt: full wide glyphs, pixel-based horizontal scrolling and visible insertion cursor')
        # Native artwork remains 1:1 even when a Markdown paragraph has margins.
        start=len(p.text);p.open(directory+'/image.md');p.expect('SERVICE=VIEWER')
        frame=picture('markdown-native-art');source=image_frame(probes['image-320.wbmp']);expected=bytearray(12800)
        for y in range(208):
            for x in range(320):
                if source[y//8*320+x]&(1<<(y%8)):ark.pixel(expected,x,42+y)
        band(frame,expected,42,250);raw(p,b'\x1b');calculator(p)
        start=len(p.text);p.open(directory+'/image.wbmp');p.expect('SERVICE=VIEWER')
        picture('explorer-native-art',source);raw(p,b'\x1b');calculator(p)
        passed('Markdown and Explorer automatically select native WBMP sibling, all 320 columns preserved pixel-for-pixel')
        # Exercise the installed WBMP handler using physical Pico up/down codes.
        start=len(p.text);p.open(directory+'/WBMPCHK.APP');picture('wbmp-top',image_frame(probes['PATTERN.wbmp']))
        raw(p,b'\xb6');picture('wbmp-bottom',image_frame(probes['PATTERN.wbmp'],y_offset=40))
        raw(p,b'\xb6');picture('wbmp-bottom-clamped',image_frame(probes['PATTERN.wbmp'],y_offset=40))
        raw(p,b'\xb5');picture('wbmp-top-restored',image_frame(probes['PATTERN.wbmp']))
        raw(p,b'\x1b');p.wait_text(b'PICO WBMP FILE_OPEN PASS',start);p.commands();calculator(p)
        passed('real WBMP.APP FILE_OPEN: Pico Down/Up page scrolling, bottom clamp and byte-exact return to first page')
        # The bee sprite uses hand-drawn native ellipses; verify its FMK too.
        start=len(p.text);p.open(directory+'/bee.m61');p.wait_text(b'mk61> ',start);p.expect('COLS=20 ROWS=10 FONT=1')
        frame=picture('bumblebee-native-sprite')
        bee=Font(probes['Bumblebee320.FMK'],width=16,height=32,left=0,top=0,columns=20,rows=10,frame_width=320)
        assert bee.matches(frame,'-0008',4,0)
        assert not any(frame[:16*320]) and not any(frame[20*320:]);stop()
        passed('Bumblebee native 16x32 FMK, sprite at middle row with exact glyph pixels')
        start=len(p.text);first=len(p.frames);p.open(directory+'/Bumblebee/autoexec.m61');p.expect('SERVICE=VIEWER')
        raw(p,b'\x1b');p.expect('M61_ACTIVE=1','COLS=20 ROWS=10 FONT=1')
        deadline=time.monotonic()+20
        while time.monotonic()<deadline:
            p.pump(.04)
            if len(p.frames)>first and any(bee.has(p.frames[-1],sprite) for sprite in ('-0008','8000-')):break
        else:raise AssertionError(('real Bumblebee animation missing',p.status()))
        png(p.frames[-1],args.output/'bumblebee-game.png');stop()
        passed('actual Bumblebee autoexec: manual, optional BASIC geometry bootstrap, native trap handlers and live ROM-driven animation')
        report['passed']=True
    finally:
        try:
            if before is not None:
                if prompt_ru_toggled:raw(p,b'\x88')
                calculator(p)
                if p.attached:p.send(0x13);p.attached=False;p.pump(.1)
                p.commands();p.command('fsput cancel')
                pwd=re.search(r'(?m)^(/[^\r\n]*)',before['pwd'])[1]
                assert 'ERROR' not in p.command('cd "'+pwd+'"')
                if created:assert 'ERROR' not in p.command('rm -r '+directory,timeout=30)
                restore(p,before)
                if 'angle_before' in report:
                    raw(p,(b'a',b'd',b't')[report['angle_before']]);p.commands()
                assert {c:p.command(c) for c in before}==before
                family,size,key=report['font_before']
                indicator_font(report['indicator_font_before'])
                if (family,size)!=('1','16'):font(p,int(family),int(size),key if family=='3' else None);calculator(p)
                p.command('uscreen on' if 'USB_SCREEN=ON ' in initial else 'uscreen off')
                report.update(calculator_state_restored=True,temporary_directory_removed=True,final=p.status())
        finally:
            (args.output/'terminal.bin').write_bytes(p.text);p.__exit__(None,None,None)
            (args.output/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    assert report['passed'] and report['calculator_state_restored'];print('PASS native completion HIL',flush=True)


if __name__=='__main__':main()
