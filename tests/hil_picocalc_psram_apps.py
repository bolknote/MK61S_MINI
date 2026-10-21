#!/usr/bin/env python3
"""Qualify real WBMP/SHEET/ELIZA APP storage on one explicit PicoCalc.

Uses fresh temporary files and restores calculator data and the working folder.
WBMP pixels and ELIZA text are checked against independent reference layouts.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from hil_c5_stack import read_file, write_file
from hil_picocalc_software import connect, calculator, restore, raw
from hil_picocalc_hardware import healthy, field
from hil_picocalc_eliza import ElizaFont
from hil_portable_system_apps import png

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from build_picocalc import compiler_bin

def wbmp_image():
    # Terminal fsput has a 65535-byte limit. This 32-KiB source already
    # exceeds the old APP's 16-KiB SRAM image and exercises both-axis panning.
    return b'\0\0\x84\0\x84\0'+bytes((x*73+y*11)&255 for y in range(512) for x in range(64))

def wbmp_frame(left,top):
    frame=bytearray(12800)
    for y in range(320):
        for x in range(320):
            sx,sy=left+x,top+y
            if not (((sx//8)*73+sy*11)&(0x80>>(sx%8))):frame[y//8*320+x]|=1<<(y%8)
    return bytes(frame)

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ('port','uid'):ap.add_argument('--'+name,required=True)
    for name in ('firmware-directory','apps','output'):ap.add_argument('--'+name,type=Path,required=True)
    args=ap.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    manifest=json.loads((args.firmware_directory/'manifest.json').read_text())
    directory='/MK61S-PSRAMAPPS-'+datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')
    wrapper=args.output/'WBMPCHK.cpp'
    wrapper.write_text('#define PICO_APPS_DIRECTORY "'+directory+'"\n#include "'+str(ROOT/'tests/picocalc_wbmp_handler_probe.cpp')+'"\n')
    subprocess.run([sys.executable,str(ROOT/'tools/build_portable_app.py'),'--target','picocalc-pico-h',
        '--name','WBMPCHK','--source',str(wrapper),'--arm-toolchain-bin',str(compiler_bin(None)),
        '--output-dir',str(args.output/'probe'),'--shared-runtime'],check=True)
    payloads={name+'.APP':(args.apps/(name+'.APP')).read_bytes() for name in ('WBMP','SHEET','ELIZA')}
    payloads.update({'WBMPCHK.APP':(args.output/'probe/WBMPCHK.APP').read_bytes(),'PATTERN.wbmp':wbmp_image()})
    report=dict(passed=False,uid=args.uid,build=manifest['build_id'].upper(),directory=directory,
        uf2_sha256=manifest['uf2_sha256'],files={n:hashlib.sha256(b).hexdigest() for n,b in payloads.items()},cases=[],frames=[])
    p=connect(args.port,args.uid);p.native_display=True;before=None;created=False
    def picture(name,predicate):
        first=len(p.frames);p.send(0x16);deadline=time.monotonic()+20
        while time.monotonic()<deadline:
            p.pump(.04)
            if len(p.frames)>first and predicate(p.frames[-1]):
                frame=p.frames[-1];png(frame,args.output/(name+'.png'))
                report['frames'].append(dict(name=name,sha256=hashlib.sha256(frame).hexdigest()))
                return frame
        raise AssertionError(('Missing frame',name,p.status()))
    def storage(size):
        status=p.status();healthy(status,report['build'])
        assert field(status,'APP_BUFFERS')==(1 if size else 0),status
        assert field(status,'APP_EXTERNAL_BYTES')==size,status
        assert field(status,'APP_WINDOWS')==0 and 'IO_ERRORS=0 VALID=1' in status,status
        report['cases'].append(dict(external_bytes=size,status=status))
    def returned(start):
        p.wait_text(b'APP_FLOW_RESULT=0',start,timeout=30);calculator(p);storage(0)
    try:
        initial=p.status();healthy(initial,report['build']);report['initial']=initial
        for marker in ('SERVICE=CLOSED','RUN=0 BUSY=0','DIRTY=0','USB_DISK=0','M61_ACTIVE=0','USB_SCREEN=OFF'):
            assert marker in initial,(marker,initial)
        before={c:p.command(c) for c in ('reg','stk','hout','dump','pwd')}
        (args.output/'snapshot.json').write_text(json.dumps(before,indent=2)+'\n')
        assert 'ERROR' not in p.command('mkdir '+directory);created=True
        for name,data in payloads.items():
            write_file(p,directory+'/'+name,data);assert read_file(p,directory+'/'+name)==data,name
        p.command('uscreen on');p.attach_waiting()
        start=len(p.text);p.open(directory+'/WBMPCHK.APP')
        for name,left,top,key in [('wbmp-start',0,0,None),('wbmp-right',8,0,b'\xb7'),('wbmp-down',8,192,b'\xb6')]:
            if key:raw(p,key)
            expected=wbmp_frame(left,top);picture(name,lambda f:f==expected);storage(len(payloads['PATTERN.wbmp']))
        raw(p,b'\x1b');p.wait_text(b'PICO WBMP FILE_OPEN PASS',start);returned(start)
        print('PASS WBMP: 32-KiB PSRAM image, exact initial/right/down frames and release',flush=True)

        start=len(p.text);p.open(directory+'/SHEET.APP');p.expect('RUNTIME=APP')
        p.pump(.3);empty=picture('sheet-empty',lambda f:any(f));storage(256*1024)
        raw(p,b'1\r');p.pump(.3);one=picture('sheet-one',lambda f:f!=empty)
        raw(p,b'2\r');p.pump(.3);picture('sheet-two',lambda f:f!=one)
        raw(p,b'\t\r');picture('sheet-undo-one',lambda f:f==one)
        raw(p,b'\t\r');picture('sheet-undo-empty',lambda f:f==empty)
        storage(256*1024);raw(p,b'\x1b');returned(start)
        print('PASS SHEET: PSRAM undo history, two exact reverse edits and release',flush=True)

        font=ElizaFont();start=len(p.text);p.open(directory+'/ELIZA.APP');p.expect('RUNTIME=APP')
        raw(p,b'\r');p.pump(.3);raw(p,b'\r')
        picture('eliza-input',lambda f:font.editor(f,''));storage(256*1024)
        transcript=[('my memory ends here','YOUR MEMORY ENDS HERE'),
            ('zqxv','I AM NOT SURE I UNDERSTAND YOU FULLY'),
            ('zqxv','DOES THAT HAVE ANYTHING TO DO WITH THE FACT THAT YOUR MEMORY ENDS HERE')]
        for index,(text,reply) in enumerate(transcript):
            raw(p,(text+'\r').encode())
            picture('eliza-reply-'+str(index),lambda f:font.page(f,font.wrap(reply)))
            if index+1<len(transcript):
                raw(p,b'\r');picture('eliza-editor-'+str(index),lambda f:font.editor(f,''))
        storage(256*1024);raw(p,b'\x1b');returned(start)
        report['eliza_reference']='Accepted pre-change engine: MY MEMORY ENDS HERE, ZQXV, ZQXV'
        print('PASS ELIZA: 256-KiB PSRAM memory, exact replies and recalled FIFO record, release',flush=True)
        report['passed']=True
    finally:
        try:
            if before is not None:
                calculator(p)
                if p.attached:p.send(0x13);p.attached=False;p.pump(.1)
                p.commands();p.command('fsput cancel')
                cwd=re.search(r'(?m)^(/[^\r\n]*)',before['pwd'])[1];p.command('cd "'+cwd+'"')
                if created:assert 'ERROR' not in p.command('rm -r '+directory,timeout=30)
                restore(p,before);raw(p,('g'+f'{field(initial,"IP"):02d}').encode())
                p.expect('IP='+f'{field(initial,"IP"):02d}','RUN=0 BUSY=0');p.commands()
                after={c:p.command(c) for c in before}
                # Raw calculator notifications can arrive beside a command
                # response. Compare every stored value/opcode, not prompt noise.
                patterns={'reg':r'(?m)^R[0-9A-E] = [^\r\n]+','stk':r'(?m)^S[0-4] = [^\r\n]+',
                    'hout':r'(?m)^hin [^\r\n]+','dump':r'(?m)^\d{4} [0-9A-Fa-f]{2}\r?$',
                    'pwd':r'(?m)^/[^\r\n]*'}
                for command,pattern in patterns.items():
                    assert re.findall(pattern,after[command])==re.findall(pattern,before[command]),(command,before[command],after[command])
                report['after']=after
                p.command('uscreen off');final=p.status();healthy(final,report['build'])
                report.update(calculator_state_restored=True,temporary_files_removed=True,final=final)
        finally:
            (args.output/'terminal.bin').write_bytes(p.text);p.__exit__(None,None,None)
            (args.output/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    assert report['passed'] and report['calculator_state_restored']
    print('PASS real PSRAM APPs with calculator data preserved',flush=True)
if __name__=='__main__':main()
