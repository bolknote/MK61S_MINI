#!/usr/bin/env python3
"""Check ELIZA/SHEET headroom on a verified Pico build without replacing apps."""
import argparse,hashlib,json,re,time
from pathlib import Path
from hil_picocalc_software import connect,calculator,restore,raw
from hil_picocalc_hardware import healthy,field
from hil_c5_stack import read_file
from hil_picocalc_eliza import ElizaFont
from hil_picocalc_sheet import SheetFont
from hil_picocalc_display import lcd_crc
from hil_portable_system_apps import png

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ('port','uid'):ap.add_argument('--'+name,required=True)
    ap.add_argument('--firmware-directory',type=Path,required=True)
    ap.add_argument('--directory',default='/MK61S-PicoCalc-0.8')
    ap.add_argument('--keyboard-error-baseline',type=int,default=0,
        help='Explicit existing boot counter; the APP trial must not add an I2C error.')
    ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    build=json.loads((args.firmware_directory/'manifest.json').read_text())
    assert args.keyboard_error_baseline>=0
    report=dict(passed=False,uid=args.uid,uf2_sha256=build['uf2_sha256'],build=build['build_id'].upper(),cases=[],screens={},files={},
        keyboard_error_baseline=args.keyboard_error_baseline)
    def check_health(text):healthy(text,report['build'],args.keyboard_error_baseline)
    p=connect(args.port,args.uid);p.native_display=True;before=None
    def shot(name,predicate):
        first=len(p.frames);p.send(0x16);deadline=time.monotonic()+20
        while time.monotonic()<deadline:
            p.pump(.04)
            if len(p.frames)>first and predicate(p.frames[-1]):
                frame=p.frames[-1];wanted=lcd_crc(frame);status=p.status()
                if 'LCD_PENDING=0 ' in status and 'LCD_FRAME_CRC='+wanted in status:break
        else:raise AssertionError(('Missing native APP frame',name,p.status()))
        png(frame,args.output/(name+'.png'));report['screens'][name]=hashlib.sha256(frame).hexdigest()
    def returned(start):
        p.wait_text(b'APP_FLOW_RESULT=0',start,timeout=20);calculator(p)
        check_health(p.expect('SERVICE=CLOSED','RUNTIME=NONE'))
    try:
        initial=p.expect('SERVICE=CLOSED','RUN=0 BUSY=0','M61_ACTIVE=0','USB_DISK=0');check_health(initial)
        report['initial']=initial
        before={c:p.command(c) for c in ('reg','stk','hout','dump','pwd')}
        for name in ('ELIZA','SHEET'):
            data=(args.firmware_directory/'apps'/(name+'.APP')).read_bytes()
            assert read_file(p,args.directory+'/'+name+'.APP')==data
            report['files'][name+'.APP']=hashlib.sha256(data).hexdigest()
        p.command('uscreen on');p.attach_waiting()
        face=ElizaFont();start=len(p.text);p.open(args.directory+'/ELIZA.APP');p.expect('RUNTIME=APP')
        raw(p,b'\r');raw(p,b'\r');shot('eliza-input',lambda f:face.editor(f,''))
        raw(p,b'hello\r');shot('eliza-reply',lambda f:face.page(f,face.wrap('HOW DO YOU DO. PLEASE STATE YOUR PROBLEM')))
        raw(p,b'\x1b');returned(start);report['cases'].append('ELIZA: existing matching APP, native editor and exact HELLO reply, clean return')
        sheet=SheetFont();start=len(p.text);p.open(args.directory+'/SHEET.APP');p.expect('RUNTIME=APP')
        shot('sheet-a1',lambda f:f==sheet.table({}))
        p.key(24);shot('sheet-b1',lambda f:f==sheet.table({},selected='B1'))
        raw(p,b'\x1b');returned(start);report['cases'].append('SHEET: existing matching APP, exact native empty grid, navigation and clean return')
        report['passed']=True
    finally:
        try:
            if before is not None:
                calculator(p)
                if p.attached:p.send(0x13);p.attached=False;p.pump(.1)
                p.commands();cwd=re.search(r'(?m)^(/[^\r\n]*)',before['pwd'])[1]
                p.command('cd "'+cwd+'"');restore(p,before)
                ip=field(initial,'IP');assert ip<100
                raw(p,('g'+f'{ip:02d}').encode());p.expect('IP='+f'{ip:02d}','RUN=0 BUSY=0');p.commands()
                assert {c:p.command(c) for c in before}==before
                p.command('uscreen off' if 'USB_SCREEN=OFF ' in initial else 'uscreen on')
                report.update(calculator_state_restored=True,final=p.status());check_health(report['final'])
        finally:
            (args.output/'terminal.bin').write_bytes(p.text);p.__exit__(None,None,None)
            (args.output/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    assert report['passed'] and report['calculator_state_restored']
    print('PASS ELIZA/SHEET headroom with PSRAM/DMA resident and native pixel oracles',flush=True)

if __name__=='__main__':main()
