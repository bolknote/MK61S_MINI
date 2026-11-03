#!/usr/bin/env python3
"""Bounded native Explorer qualification on one explicitly leased Pico UID.

No firmware installation, formatting, math probe or existing file overwrite.
Creates one fresh SD directory, records native frames/LCD CRC, then removes only
that directory. Calculator data are checked and, on failure without physical
input, restored through the established public snapshot helper.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import time
import zlib
from hil_c5_stack import read_file, write_file
from hil_picocalc_software import connect, calculator, raw, restore, saved_numbers
from hil_portable_system_apps import png

ROOT=Path(__file__).resolve().parents[1]


def value(frame,x,y):
    return bool(frame[(y//8)*320+x]&(1<<(y&7)))


def physical(status):
    match=re.search(r'\bPHYSICAL_KEYS=(\d+)',status)
    assert match,status
    return int(match[1])


def same_snapshot(before,after):
    return all(saved_numbers(before[k],prefix)==saved_numbers(after[k],prefix)
               for k,prefix in (('reg','R'),('stk','S'))) and all(
        re.findall(pattern,before[k],re.M)==re.findall(pattern,after[k],re.M)
        for k,pattern in (('hout',r'^hin [^\r\n]+'),('pwd',r'^/[^\r\n]*')))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',required=True);parser.add_argument('--uid',required=True)
    parser.add_argument('--build-id',required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    assert re.fullmatch(r'[0-9A-F]{16}',args.uid) and re.fullmatch(r'[0-9A-Fa-f]{8}',args.build_id)
    args.output.mkdir(parents=True,exist_ok=False)
    directory='/MK61S-EXPLORER-'+datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')
    icon=(ROOT/'programs/games/Turochamp/autoexec.wbmp').read_bytes()
    assert len(icon)==132 and icon[:4]==bytes((0,0,32,32))
    menu_items=re.findall(r'^MK61_MAIN_ITEM\((\w+),',(ROOT/'code/main_menu_items.inc').read_text(),re.M)
    explorer=menu_items.index('EXPLORER')
    report=dict(passed=False,uid=args.uid,build_id=args.build_id.upper(),directory=directory,cases=[],screens={})
    p=connect(args.port,args.uid);p.native_display=True
    before=None;created=False;initial=None;unexpected_input=False
    def check():
        nonlocal unexpected_input
        status=p.status()
        if initial is not None and physical(status)!=physical(initial):
            unexpected_input=True
            raise AssertionError('Physical input changed during the exclusive Explorer test; leaving fresh user state intact')
        assert all(marker in status for marker in ('CRASH=NONE','USB_DISK=0','KBD=OK','LCD_ERRORS=0','DMA_TIMEOUTS=0')),status
        return status
    def keys(data):
        check();raw(p,data)
    def picture(name):
        p.pump(.2);start=len(p.frames);p.send(0x16)
        deadline=time.monotonic()+15
        while len(p.frames)<start+2 and time.monotonic()<deadline:p.pump(.05)
        assert len(p.frames)>=start+2,(name,p.status())
        frame=p.frames[-1];assert len(frame)==12800
        rows=bytearray(12800)
        for y in range(320):
            for x in range(320):
                if value(frame,x,y):rows[y*40+x//8]|=0x80>>(x&7)
        crc=f'{zlib.crc32(rows):08X}';deadline=time.monotonic()+8
        while time.monotonic()<deadline:
            status=check()
            if 'LCD_PENDING=0 ' in status and 'LCD_FRAME_CRC='+crc in status:break
        else:raise AssertionError(('LCD differs from complete native frame',name,crc,status))
        png(frame,args.output/(name+'.png'))
        report['screens'][name]=dict(sha256=hashlib.sha256(frame).hexdigest(),lcd_crc=crc,status=status)
        return frame
    def browse():
        calculator(p);keys(b'\t'+b'\xb5'*32+b'\xb6'*explorer+b'\r')
        p.expect('SERVICE=BROWSER');keys(b'/');p.expect('SERVICE=PROMPT')
        keys(directory.encode()+b'\r');p.expect('SERVICE=BROWSER')
    try:
        initial=p.status();report['initial']=initial
        for marker in ('BUILD='+args.build_id.upper(),'FIRMWARE_CRC=valid','CRASH=NONE','DIRTY=0','M61_ACTIVE=0','USB_DISK=0','RUN=0 BUSY=0'):
            assert marker in initial,(marker,initial)
        assert re.search(r'SERVICE=(?:CLOSED|DEVELOPMENT|BROWSER|FILE_ACTIONS)\b',initial),initial
        if 'SLEEP=1' in initial:p.command('display on')
        p.expect('SD=OK','KBD=OK','SLEEP=0')
        calculator(p);before={key:p.command(key) for key in ('reg','stk','hout','pwd')}
        (args.output/'before.json').write_text(json.dumps(before,ensure_ascii=False,indent=2)+'\n')
        assert directory[1:]+'/' not in p.command('ls /')
        assert 'ERROR' not in p.command('mkdir '+directory);created=True
        names=['00Icon','01Launcher',*[f'{i:02d}Plain' for i in range(2,9)],'09Page','10Page']
        for name in names:assert 'ERROR' not in p.command('mkdir '+directory+'/'+name)
        write_file(p,directory+'/00Icon/autoexec.wbmp',icon)
        write_file(p,directory+'/01Launcher/autoexec.m61',b'ret\n')
        assert read_file(p,directory+'/00Icon/autoexec.wbmp')==icon
        p.command('uscreen on');p.attach_waiting()
        browse();first=picture('icons-native')
        assert all(value(first,x,31) for x in range(320))
        for y in range(32):
            for x in range(32):assert value(first,44+x,52+y)==(not bool(icon[4+y*4+x//8]&(0x80>>(x&7))))
        keys(b'\xb7');second=picture('selection')
        changed=[(x,y) for y in range(320) for x in range(320) if value(first,x,y)!=value(second,x,y)]
        assert changed and all(91<=y<109 and x<211 for x,y in changed)
        report['cases'].append('exact 32x32 WBMP, 320x320 raster, name-only highlight and completed LCD source CRC')
        keys(b'\x81');p.expect('SERVICE=FILE_ACTIONS');picture('file-menu')
        keys(b'\xb6'*5+b'\r');p.expect('SERVICE=BROWSER','M61_ACTIVE=0');picture('folder-without-autoexec')
        report['cases'].append('file menu enters launcher directory without running its script')
        keys(b'\x1b');keys(b'\xb7'*9);page=picture('next-page')
        assert not any(value(page,x,y) for y in range(52,84) for x in range(244,276))
        keys(b'\x86');p.expect('SERVICE=PROMPT');keys(b'Page\r');p.expect('SERVICE=BROWSER');picture('search')
        keys(b'\x1b');keys(b'\x88');picture('list');keys(b'\x88');picture('icons-restored')
        report['cases'].append('page navigation, search and runtime icons/list switch')
        keys(b'/');p.expect('SERVICE=PROMPT');keys((directory+'/02Plain').encode()+b'\r')
        p.expect('SERVICE=BROWSER');picture('empty-folder');keys(b'\r');p.expect('SERVICE=PROMPT');keys(b'\x1b')
        report['cases'].append('empty folder opens the new-folder prompt without leaving its parent')
        report['passed']=True
    finally:
        try:
            if before and not unexpected_input:
                calculator(p);after={key:p.command(key) for key in before}
                report['data_unchanged']=same_snapshot(before,after)
                if not report['data_unchanged']:report['passed']=False;restore(p,before)
                if created:
                    assert 'ERROR' not in p.command('rm -r '+directory,timeout=30)
                    report['temporary_directory_removed']=True
                p.send(0x13);p.attached=False;p.pump(.1)
                if initial and 'USB_SCREEN=OFF ' in initial:p.command('uscreen off')
                report['final']=check()
        finally:
            report['unexpected_physical_input']=unexpected_input
            (args.output/'transcript.bin').write_bytes(p.text)
            (args.output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
            p.__exit__(None,None,None)
    assert report['passed'] and report.get('data_unchanged') and not unexpected_input,report
    print('PicoCalc native Explorer HIL PASS',flush=True)


if __name__=='__main__':main()
