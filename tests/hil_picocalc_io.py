#!/usr/bin/env python3
"""Qualify core 1 peripheral ownership across settings flash and a real reset.

Only the selected UI font is temporarily changed. Restore font, calculator
registers, all stack cells, program, directory and USB Screen mode in finally.
"""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import re
import time
from zoneinfo import ZoneInfo
from hil_picocalc_software import connect,font,restore
from hil_picocalc_turochamp import healthy

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',required=True)
    parser.add_argument('--uid',required=True)
    parser.add_argument('--firmware-directory',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    manifest=json.loads((args.firmware_directory/'manifest.json').read_text())
    build=manifest['build_id'].upper()
    report=dict(passed=False,build=build,uf2_sha256=manifest['uf2_sha256'],
        uid=args.uid,recorded_at_utc=datetime.now(timezone.utc).isoformat())
    p=None;before=None;original=None;transcripts=[]
    def check():
        status=p.status();healthy(status,build)
        assert 'IO_CORE=1 ' in status and 'KBD=OK errors=0' in status,status
        return status
    try:
        p=connect(args.port,args.uid);initial=check()
        for marker in ('SERVICE=CLOSED','DIRTY=0','M61_ACTIVE=0','RUN=0 BUSY=0','USB_DISK=0'):
            assert marker in initial,initial
        report['initial']=initial
        before={cmd:p.command(cmd) for cmd in ('reg','stk','hout','pwd')}
        (args.output/'snapshot.json').write_text(json.dumps(before,indent=2)+'\n')
        match=re.search(r'UI_FONT_FAMILY=(\d+) UI_FONT_SIZE=(\d+) UI_FONT_KEY=([0-9A-F]+)',initial)
        original=(int(match[1]),int(match[2]),match[3])
        target=14 if original[:2]!=(1,14) else 16
        report['saved']=font(p,1,target)
        check()
        p.commands()
        p.write_line('rst now')
        try:p.pump(.3)
        except OSError:pass
        transcripts.append(bytes(p.text));p.__exit__(None,None,None);p=None
        p=connect(args.port,args.uid);restarted=check()
        assert f'UI_FONT_FAMILY=1 UI_FONT_SIZE={target} ' in restarted and 'SETTINGS=LOADED' in restarted,restarted
        report['restarted']=restarted
        report['passed']=True
    finally:
        if p is not None and before is not None:
            if original is not None:report['restored_font']=font(p,*original)
            p.calculator()
            pwd=re.search(r'(?m)^(/[^\r\n]*)',before['pwd'])[1]
            assert 'ERROR' not in p.command('cd "'+pwd+'"')
            restore(p,before)
            now=datetime.now(ZoneInfo('Europe/Moscow'))
            p.command('date '+now.strftime('%Y-%m-%d %H:%M:%S'))
            p.command('uscreen off' if 'USB_SCREEN=OFF ' in report['initial'] else 'uscreen on')
            report.update(calculator_state_restored=True,final=check())
        if p is not None:
            transcripts.append(bytes(p.text));p.__exit__(None,None,None)
        (args.output/'terminal.bin').write_bytes(b''.join(transcripts))
        (args.output/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    assert report['passed'] and report['calculator_state_restored']
    print('PASS core 1 I/O, live settings flash, persistence after reset and full restoration',flush=True)

if __name__=='__main__':main()
