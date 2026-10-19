#!/usr/bin/env python3
"""Qualify LCD windows/DMA and complete BASIC frames on one explicit Pico UID.

Uses a fresh temporary SD directory, leaves existing files intact, and restores
registers, all five stack cells, program and working directory in finally.
The LCD CRC describes the DMA source snapshot, not optical panel readback.
"""
import argparse
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
import zlib
from hil_c5_stack import read_file,write_file
from hil_picocalc_software import connect,calculator,restore
from hil_turochamp_performance import Font
from hil_portable_system_apps import png

ROOT=Path(__file__).resolve().parents[1]

def pattern(stage):
    frame=bytearray(12800)
    for y in range(320):
        for x in range(320):
            lit=(x//16+y//16)%2==1 if stage==0 or stage>=6 else False
            if 2<=stage<=4:
                left=8 if stage==2 else 16
                lit=(left<=x<left+24 and 40<=y<64) or (272<=x<296 and 256<=y<280)
                if stage==4:lit|=(x==0 and y==0) or (x==319 and y==319)
            if stage==5:lit=True
            if lit:frame[y//8*320+x]|=1<<(y%8)
    return bytes(frame)

def lcd_crc(frame):
    rows=bytearray(12800)
    for y in range(320):
        for x in range(320):
            if frame[y//8*320+x]&(1<<(y%8)):rows[y*40+x//8]|=0x80>>(x%8)
    return f'{zlib.crc32(rows):08X}'

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',required=True);parser.add_argument('--uid',required=True)
    parser.add_argument('--build-id',required=True);parser.add_argument('--app',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--require-fast',action='store_true')
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    directory='/MK61S-DISPLAY-'+datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')
    font_path=ROOT/'programs/games/Turochamp/Turochamp320.FMK'
    face=Font(font_path.read_bytes(),width=12,height=24,left=4,top=40,columns=26,rows=10,frame_width=320)
    report=dict(passed=False,uid=args.uid,build=args.build_id.upper(),directory=directory,
                recorded_at_utc=datetime.now(timezone.utc).isoformat(),stages=[])
    p=connect(args.port,args.uid);before=None;created=False
    try:
        initial=p.status();report['initial']=initial
        for marker in ('BUILD='+args.build_id.upper(),'CRASH=NONE','SERVICE=CLOSED','DIRTY=0','M61_ACTIVE=0','USB_DISK=0','SD=OK','RUN=0 BUSY=0'):
            assert marker in initial,(marker,initial)
        before={c:p.command(c) for c in ('reg','stk','hout','pwd')}
        (args.output/'snapshot.json').write_text(json.dumps(before,indent=2)+'\n')
        assert directory[1:]+'/' not in p.command('ls /')
        assert 'ERROR' not in p.command('mkdir '+directory);created=True
        for name,data in (('LCDPROBE.APP',args.app.read_bytes()),('Turochamp320.FMK',font_path.read_bytes()),
             ('ready.tbi',b'10 CLS\n20 PRINT "FRAME A"\n30 A=INPUT()\n40 CLS\n50 PRINT "FRAME B"\n60 FOR I=1 TO 100000\n70 NEXT I\n80 PRINT "DONE"\n90 B=INPUT()\n100 END\n'),
             ('ready.m61',b'loadfont Turochamp320\nopen ready.tbi\nret\n')):
            write_file(p,directory+'/'+name,data)
            assert read_file(p,directory+'/'+name)==data
        p.command('uscreen off');start=len(p.text);p.open(directory+'/LCDPROBE.APP')
        changed=time.monotonic()
        for stage in range(8):
            p.wait_text(f'LCDPROBE STAGE={stage} READY'.encode(),start,timeout=30)
            wanted=lcd_crc(pattern(stage));deadline=time.monotonic()+10
            while time.monotonic()<deadline:
                status=p.status()
                assert 'CRASH=NONE' in status and 'KBD=OK errors=0' in status,status
                if 'LCD_PENDING=0 ' in status and 'LCD_FRAME_CRC='+wanted in status:break
            else:raise AssertionError(('LCD snapshot mismatch',stage,wanted,status))
            record=dict(stage=stage,host_settle_seconds=time.monotonic()-changed,lcd_crc=wanted,status=status)
            for label,name in (('LCD_BYTES','bytes'),('LCD_RECTS','rectangles'),('LCD_US','microseconds'),('LCD_FULL_FRAMES','full_frames'),('FRAMES','frames')):
                match=re.search(r'\b'+label+r'=(\d+)',status)
                if match:record[name]=int(match[1])
            if args.require_fast:
                assert 'LCD_DMA=1 ' in status,status
                if stage==2:assert record['bytes']==2304 and record['rectangles']==2,record
                if stage==3:assert record['bytes']==768 and record['rectangles']==2,record
                if stage==4:assert record['bytes']==256 and record['rectangles']==2,record
                if stage in (0,1,6):assert record['bytes']==204800,record
                if stage==5:assert record['bytes']==202496,record  # Existing white squares need no transfer.
                if stage==7:assert record['frames']==report['stages'][-1]['frames'],record
            report['stages'].append(record)
            print(f'LCD stage {stage}: host {record["host_settle_seconds"]:.3f}s, bytes={record.get("bytes","full")}, us={record.get("microseconds","unavailable")}',flush=True)
            if stage<7:
                changed=time.monotonic();os.write(p.fd,b'\x1e\r')
        os.write(p.fd,b'\r');p.wait_text(b'APP_FLOW_RESULT=0',start,timeout=15);p.commands()
        p.command('uscreen on');p.native_display=True;p.attach_waiting()
        start=len(p.text);p.open(directory+'/ready.m61');p.wait_text(b'FRAME A',start,timeout=30)
        deadline=time.monotonic()+15
        while time.monotonic()<deadline:
            p.pump(.05)
            if p.frames and face.has(p.frames[-1],'FRAME A'):break
        else:raise AssertionError('Missing initial complete BASIC frame')
        png(p.frames[-1],args.output/'ready-a.png')
        first=len(p.frames);p.key(29)
        p.wait_text(b'FRAME B',start,timeout=15)
        p.wait_text(b'DONE',start,timeout=30)
        deadline=time.monotonic()+10
        while time.monotonic()<deadline:
            p.pump(.05)
            if p.frames and face.has(p.frames[-1],'FRAME B') and face.has(p.frames[-1],'DONE'):break
        else:raise AssertionError('Missing final complete BASIC frame')
        frames=p.frames[first:]
        incomplete=[i for i,frame in enumerate(frames) if face.has(frame,'FRAME B') and not face.has(frame,'DONE')]
        retained=sum(face.has(frame,'FRAME A') for frame in frames)
        report['basic']=dict(frames=len(frames),incomplete_frames=len(incomplete),retained_frames=retained)
        png(p.frames[-1],args.output/'ready-b.png')
        for i in incomplete[:1]:png(frames[i],args.output/'incomplete-baseline.png')
        if args.require_fast:assert not incomplete and retained>0,report['basic']
        print('BASIC ready frame: '+json.dumps(report['basic']),flush=True)
        p.key(29);p.pump(.3)
        os.write(p.fd,b'\x1e\x1b');p.pump(.3);p.commands()
        report['passed']=True
    finally:
        try:
            if before is not None:
                calculator(p)
                if p.attached:p.send(0x13);p.attached=False;p.pump(.15)
                p.commands()
                pwd=re.search(r'(?m)^(/[^\r\n]*)',before['pwd'])[1]
                assert 'ERROR' not in p.command('cd "'+pwd+'"')
                if created:assert 'ERROR' not in p.command('rm -r '+directory,timeout=30)
                restore(p,before)
                p.command('uscreen on' if 'USB_SCREEN=ON ' in report['initial'] else 'uscreen off')
                report.update(calculator_state_restored=True,temporary_directory_removed=created,final=p.status())
        finally:
            (args.output/'terminal.bin').write_bytes(p.text);p.__exit__(None,None,None)
            (args.output/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    assert report['passed'] and report['calculator_state_restored']
    print('PASS PicoCalc display HIL',flush=True)

if __name__=='__main__':main()
