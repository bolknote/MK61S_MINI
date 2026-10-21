#!/usr/bin/env python3
"""Cross settings-sector rollover with live LCD/I2C/UART, preserving settings."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from hil_picocalc_software import connect, calculator, font, restore, raw
from hil_picocalc_hardware import healthy, field

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ('port','uid'):ap.add_argument('--'+name,required=True)
    for name in ('firmware-directory','output'):ap.add_argument('--'+name,type=Path,required=True)
    ap.add_argument('--saves',type=int,default=32)
    args=ap.parse_args();assert args.saves>=32;args.output.mkdir(parents=True,exist_ok=False)
    m=json.loads((args.firmware_directory/'manifest.json').read_text())
    report=dict(passed=False,uid=args.uid,build=m['build_id'].upper(),uf2_sha256=m['uf2_sha256'],
        recorded_at_utc=datetime.now(timezone.utc).isoformat(),samples=[])
    p=connect(args.port,args.uid);before=None
    try:
        initial=p.expect('SERVICE=CLOSED','RUN=0 BUSY=0','USB_DISK=0','DIRTY=0','USB_SCREEN=OFF')
        healthy(initial,report['build']);report['initial']=initial
        family=field(initial,'UI_FONT_FAMILY');size=field(initial,'UI_FONT_SIZE')
        key=re.search(r'\bUI_FONT_KEY=([0-9A-F]{8})',initial)[1]
        before={c:p.command(c) for c in ('reg','stk','hout','dump','pwd')}
        first=field(initial,'SETTINGS_WRITES');first_erase=field(initial,'SETTINGS_ERASES')
        last_size=size
        for index in range(args.saves):
            wanted=12 if last_size!=12 else 16;last_size=wanted
            font(p,1,wanted);calculator(p);status=p.status();healthy(status,report['build'])
            assert field(status,'UI_FONT_FAMILY')==1 and field(status,'UI_FONT_SIZE')==wanted
            assert field(status,'SETTINGS_WRITES')>=first+index+1,status
            report['samples'].append(dict(index=index,status=status))
            print('PASS settings write',index+1,'erases',field(status,'SETTINGS_ERASES')-first_erase,flush=True)
        status=p.status()
        assert field(status,'SETTINGS_ERASES')-first_erase>=2,status
        assert field(status,'I2C_TRANSACTIONS')>field(initial,'I2C_TRANSACTIONS')+100,status
        assert field(status,'FRAMES')>field(initial,'FRAMES'),status
        report.update(passed=True,verified_writes=field(status,'SETTINGS_WRITES')-first,
            verified_sector_erases=field(status,'SETTINGS_ERASES')-first_erase)
    finally:
        try:
            if before is not None:
                font(p,family,size,key if family==3 else None);calculator(p);restore(p,before)
                raw(p,('g'+f'{field(initial,"IP"):02d}').encode());p.expect('IP='+f'{field(initial,"IP"):02d}','RUN=0 BUSY=0');p.commands()
                final=p.status();healthy(final,report['build'])
                assert field(final,'UI_FONT_FAMILY')==family and field(final,'UI_FONT_SIZE')==size
                report.update(calculator_state_restored=True,settings_restored=True,final=final)
        finally:
            (args.output/'terminal.bin').write_bytes(p.text);p.__exit__(None,None,None)
            (args.output/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    assert report['passed'] and report['settings_restored']
    print('PASS settings journal sector erases with live LCD/I2C/UART and no I2C timeout',flush=True)
if __name__=='__main__':main()
