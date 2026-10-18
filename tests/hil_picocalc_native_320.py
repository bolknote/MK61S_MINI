#!/usr/bin/env python3
"""Native PicoCalc display and legacy APP compatibility on an exact Pico UID.

Uses a new temporary SD directory, removes its probes, and restores calculator
data. Firmware installation and the permanent APP collection are separate.
"""
import argparse
import hashlib
import json
import os
import struct
from pathlib import Path
import subprocess
import sys
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from hil_picocalc_software import connect, calculator, restore, raw
from hil_c5_stack import read_file, write_file
from hil_portable_system_apps import png

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from build_picocalc import compiler_bin


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',required=True)
    parser.add_argument('--uid',required=True)
    parser.add_argument('--firmware-directory',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    build=json.loads((args.firmware_directory/'manifest.json').read_text())
    work=ROOT/'.build/picocalc-native-320-probes';apps={}
    for name,legacy in [('NATIVE320',False),('LEGACY192',True)]:
        command=[sys.executable,str(ROOT/'tools/build_portable_app.py'),'--target','picocalc-pico-h',
            '--name',name,'--source',str(ROOT/'tests/picocalc_native_320_probe.cpp'),
            '--arm-toolchain-bin',str(compiler_bin(None)),'--output-dir',str(work/name),'--shared-runtime']
        if legacy:command+=['--pico-legacy-display']
        subprocess.run(command,check=True,stdout=subprocess.DEVNULL)
        apps[name]=(work/name/(name+'.APP')).read_bytes()
    directory='/MK61S-NATIVE320-'+time.strftime('%Y%m%d-%H%M%S')
    cases=[];screens={};created=False
    p=connect(args.port,args.uid);p.native_display=True
    def passed(value):cases.append(value);print('PASS '+value,flush=True)
    def picture(name,expected=None):
        p.pump(.4);start=len(p.frames);p.send(0x16)
        deadline=time.monotonic()+20
        while time.monotonic()<deadline:
            p.pump(.05)
            if len(p.frames)>=start+2 and (expected is None or p.frames[-1]==expected):break
        assert len(p.frames)>start,(name,p.status())
        frame=p.frames[-1]
        assert len(frame)==12800 and (expected is None or frame==expected),(name,hashlib.sha256(frame).hexdigest())
        png(frame,args.output/(name+'.png'));screens[name]=hashlib.sha256(frame).hexdigest();return frame
    before=None;initial=None
    try:
        calculator(p)
        initial=p.expect('BUILD='+build['build_id'].upper(),'FIRMWARE_CRC=valid','CRASH=NONE','SERVICE=CLOSED','USB_DISK=0')
        before={cmd:p.command(cmd) for cmd in ('reg','stk','hout','pwd')}
        assert 'ERROR' not in p.command('mkdir '+directory);created=True
        for name,data in apps.items():
            write_file(p,directory+'/'+name+'.APP',data)
            assert read_file(p,directory+'/'+name+'.APP')==data
        raw(p,b'\x0842');p.expect('BUSY=0','RUN=0');p.commands()
        now=datetime.now(ZoneInfo('Europe/Moscow'))
        p.send(0x40,b'\2'+struct.pack('<HBBBBB',now.year,now.month,now.day,now.hour,now.minute,now.second))
        p.pump(.2);p.expect('RTC_SET=1')
        p.command('uscreen on');p.attach_waiting()
        snapshot_at=time.monotonic();calculator_frame=picture('calculator')
        assert time.monotonic()-snapshot_at<5,'idle calculator must stream two native frames within five seconds'
        passed('idle calculator streams two complete native frames within five seconds')
        start=len(p.text);p.open(directory+'/NATIVE320.APP')
        p.wait_text(b'NATIVE320 TEXT READY',start);text_frame=picture('native-text-row-12')
        assert any(text_frame[20*320:]),'native text must occupy rows beyond a 192x64 screen'
        os.write(p.fd,b'\r');p.wait_text(b'NATIVE320 BITMAP READY',start)
        expected=bytearray(12800)
        for y in range(320):
            for x in range(320):
                if (x*3+y*5)%11<5:expected[y//8*320+x]|=1<<(y&7)
        picture('native-bitmap',bytes(expected))
        passed('320x320 APP geometry, borrowed 12800-byte bitmap and every physical framebuffer pixel matched an independent oracle')
        os.write(p.fd,b'\r');p.wait_text(b'NATIVE320 TEXT RESTORED',start)
        picture('native-text-restored',text_frame)
        os.write(p.fd,b'\r');p.wait_text(b'NATIVE320 PASS',start);p.wait_text(b'mk61> ',start)
        calculator(p)
        passed('native proportional text below row 64 and exact restoration after fullscreen graphics')
        start=len(p.text);p.open(directory+'/LEGACY192.APP')
        p.wait_text(b'LEGACY192 BITMAP READY',start);frame=picture('legacy-bitmap-1-to-1')
        for y in range(64):
            for x in range(192):
                actual=bool(frame[(96+y)//8*320+64+x]&(1<<((96+y)&7)))
                old=((y//8*192+x)*37+7)&255
                assert actual==bool(old&(1<<(y&7))),(x,y)
        os.write(p.fd,b'\r');p.wait_text(b'LEGACY192 PASS',start);p.wait_text(b'mk61> ',start)
        calculator(p);passed('old ABI 6 M0 APP still receives 192x64 and is displayed centred pixel-for-pixel')
        source=b'10 CLS\n20 PRINT GW;GH\n30 PSET GW-1,GH-1\n40 PAUSE\n50 END\n'
        write_file(p,directory+'/native.bas',source)
        start=len(p.text);p.open(directory+'/native.bas');p.wait_text(b'320320',start)
        frame=picture('basic-bottom-right');assert frame[-1]&128
        os.write(p.fd,b'\r');p.wait_text(b'VM_RESULT=OK',start)
        calculator(p);passed('BASIC GW/GH are 320 and PSET reaches pixel 319,319')
        source='print off\nprint "Native M61 / Ё"\nwait 60000\n'.encode()
        write_file(p,directory+'/native.m61',source)
        start=len(p.text);p.open(directory+'/native.m61');p.wait_text(b'mk61> ',start)
        p.expect('M61_ACTIVE=1','DISPLAY=1');m61_frame=picture('m61-native-text')
        assert m61_frame!=frame,'M61 screenshot must not reuse the completed BASIC snapshot'
        os.write(p.fd,b'\x1e\x1b');p.pump(.3);p.commands();p.expect('M61_ACTIVE=0');calculator(p)
        document='# Native PicoCalc\n\n'+('\n\n'.join('Строка %02u: родной шрифт 320x320.'%i for i in range(30)))+'\n'
        write_file(p,directory+'/native.md',document.encode())
        start=len(p.text);p.open(directory+'/native.md');p.expect('SERVICE=VIEWER')
        first=picture('markdown-320');os.write(p.fd,b'\xb6');second=picture('markdown-scrolled')
        assert first!=second;os.write(p.fd,b'\x1b');p.wait_text(b'mk61> ',start)
        calculator(p);passed('M61 native glyph rendering and 320x240 Markdown viewport with working scroll')
    finally:
        if before:
            calculator(p);restore(p,before)
        if created:
            p.commands();assert 'ERROR' not in p.command('rm -r '+directory,timeout=30)
        p.send(0x13);p.attached=False;p.pump(.1)
        if initial and 'USB_SCREEN=OFF ' in initial:p.command('uscreen off')
        final=p.status();(args.output/'transcript.bin').write_bytes(p.text)
        p.__exit__(None,None,None)
    assert all(token in final for token in ('CRASH=NONE','SCREEN_ERRORS=0','USB_DISK=0','SERVICE=CLOSED'))
    report={'passed':True,'version':build['prototype_version'],'build_id':build['build_id'],
        'uf2_sha256':build['uf2_sha256'],'uid':args.uid,'cases':cases,'screens':screens,
        'recorded_at_utc':datetime.now(timezone.utc).isoformat(),'temporary_directory_removed':True,
        'calculator_state_restored':True,'initial':initial,'final':final}
    (args.output/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')

if __name__=='__main__':main()
