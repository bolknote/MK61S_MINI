#!/usr/bin/env python3
"""Real APP: required 6 MiB, pinned windows, PSRAM frames and return cleanup."""
import argparse,hashlib,json,re,time
from datetime import datetime,timezone
from pathlib import Path
from hil_picocalc_software import connect,calculator,restore,raw
from hil_picocalc_hardware import healthy,field
from hil_c5_stack import read_file,write_file
from hil_picocalc_display import lcd_crc
from hil_portable_system_apps import png

def expected(page):
    result=bytearray(12800)
    for y in range(320):
        for x in range(320):
            lit=bool((x//16+y//8)&1) != bool(page)
            if lit:result[y//8*320+x]|=1<<(y&7)
    return bytes(result)

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ('port','uid'):ap.add_argument('--'+name,required=True)
    for name in ('firmware-directory','app','output'):ap.add_argument('--'+name,required=True,type=Path)
    args=ap.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    m=json.loads((args.firmware_directory/'manifest.json').read_text())
    assert hashlib.sha256((args.firmware_directory/'mk61s-picocalc-pico-h.uf2').read_bytes()).hexdigest()==m['uf2_sha256']
    directory='/MK61S-APPBUF-'+datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')
    report=dict(passed=False,build=m['build_id'].upper(),uf2_sha256=m['uf2_sha256'],uid=args.uid,directory=directory,frames=[])
    p=connect(args.port,args.uid);p.native_display=True;before=None;created=False
    try:
        initial=p.status();healthy(initial,report['build']);report['initial']=initial
        for marker in ('SERVICE=CLOSED','RUN=0 BUSY=0','DIRTY=0','USB_DISK=0','M61_ACTIVE=0','USB_SCREEN=OFF'):
            assert marker in initial,(marker,initial)
        before={c:p.command(c) for c in ('reg','stk','hout','dump','pwd')}
        assert 'ERROR' not in p.command('mkdir '+directory);created=True
        app=args.app.read_bytes();path=directory+'/PSRAMP.APP'
        write_file(p,path,app);assert read_file(p,path)==app
        p.command('uscreen on');p.attach_waiting();start=len(p.text);p.open(path)
        for stage in range(3):
            p.wait_text(f'PSRAM FRAME {stage} READY'.encode(),start,timeout=30)
            assert b'PSRAM SMALL IO PASS' in p.text[start:]
            wanted=expected(stage&1);crc=lcd_crc(wanted);first=len(p.frames);p.send(0x16)
            deadline=time.monotonic()+20
            while time.monotonic()<deadline:
                p.pump(.04)
                if len(p.frames)>first and p.frames[-1]==wanted:
                    status=p.status()
                    if 'LCD_PENDING=0 ' in status and 'LCD_FRAME_CRC='+crc in status:break
            else:raise AssertionError(('PSRAM frame mismatch',stage,p.status()))
            healthy(status,report['build']);assert 'IO_ERRORS=0 VALID=1' in status,status
            assert field(status,'PSRAM_USED')>=6291456+25600,status
            png(wanted,args.output/f'frame-{stage}.png')
            report['frames'].append(dict(stage=stage,sha256=hashlib.sha256(wanted).hexdigest(),lcd_crc=crc,status=status))
            raw(p,b'\r')
        p.wait_text(b'PSRAM BUFFER PASS',start);p.wait_text(b'APP_FLOW_RESULT=0',start);calculator(p)
        after=p.status();healthy(after,report['build'])
        assert 'SRAM_USED=0 ' in after and 'PINNED=0 ' in after and 'IO_ERRORS=0 VALID=1' in after,after
        assert field(after,'ACTIVE')<=2 and field(after,'EXTERNAL')<=2,after
        report.update(passed=True,after_app=after,app_sha256=hashlib.sha256(app).hexdigest(),required_bytes=6291456,frames_bytes=25600,short_writes_verified=4096)
    finally:
        try:
            if before:
                calculator(p)
                if p.attached:p.send(0x13);p.attached=False;p.pump(.1)
                p.commands();p.command('fsput cancel')
                if created:assert 'ERROR' not in p.command('rm -r '+directory,timeout=30)
                cwd=re.search(r'(?m)^(/[^\r\n]*)',before['pwd'])[1];p.command('cd "'+cwd+'"');restore(p,before)
                ip=field(initial,'IP');raw(p,('g'+f'{ip:02d}').encode());p.expect('IP='+f'{ip:02d}','RUN=0 BUSY=0');p.commands()
                assert {c:p.command(c) for c in before}==before
                p.command('uscreen off');final=p.status();healthy(final,report['build'])
                report.update(calculator_state_restored=True,temporary_files_removed=created,final=final)
        finally:
            (args.output/'terminal.bin').write_bytes(p.text);p.__exit__(None,None,None)
            (args.output/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    assert report['passed'] and report['calculator_state_restored']
    print('PASS native APP 6 MiB, window commit/pin, three exact PSRAM frames and automatic return cleanup',flush=True)
if __name__=='__main__':main()
