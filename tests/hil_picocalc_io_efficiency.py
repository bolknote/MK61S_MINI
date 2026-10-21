#!/usr/bin/env python3
"""Measure terminal I/O and idle-ROM work on one exact Pico UID/build.

Only a new temporary directory is written. Calculator data, cwd, IP and
the existing files remain unchanged; profiling is stopped on completion.
"""
import argparse
from datetime import datetime,timezone
import hashlib,json,re,time
from pathlib import Path
from hil_picocalc_software import connect
from hil_c5_stack import read_file,write_file

def core_stats(text):
    m=re.search(r'(?m)^core\s+calls=(\d+) total_us=(\d+) max_us=(\d+) mean_us=(\d+)',text)
    assert m,text
    return dict(zip(('calls','total_us','maximum_us','mean_us'),map(int,m.groups())))

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ('port','uid','build-id'):ap.add_argument('--'+name,required=True)
    ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--require-quiet',action='store_true')
    args=ap.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    directory='/MK61S-IO-'+datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')
    report=dict(passed=False,uid=args.uid,build=args.build_id.upper(),directory=directory,cases=[])
    p=connect(args.port,args.uid);before=None;created=False;profile=False
    def measure(name,action):
        p.command('prof reset');p.command('prof start');p.pump(.2)
        start=core_stats(p.command('prof core'));p.pump(.2)
        begin=time.monotonic();action();elapsed=time.monotonic()-begin;p.pump(.2)
        stop=core_stats(p.command('prof core'));p.command('prof stop')
        row=dict(name=name,seconds=elapsed,core_calls=stop['calls']-start['calls'],core_us=stop['total_us']-start['total_us'])
        report['cases'].append(row);print(json.dumps(row),flush=True)
        if args.require_quiet:assert row['core_calls']==0,row
    try:
        initial=p.expect('BUILD='+report['build'],'FIRMWARE_CRC=valid','CRASH=NONE','SERVICE=CLOSED','DIRTY=0','RUN=0 BUSY=0','M61_ACTIVE=0','USB_DISK=0','USB_SCREEN=OFF')
        report['initial']=initial
        assert 'PROFILE=STOPPED' in p.command('prof'),'Do not reset an active user profile'
        profile=True;before={c:p.command(c) for c in ('reg','stk','hout','dump','pwd')}
        (args.output/'snapshot.json').write_text(json.dumps(before,indent=2)+'\n')
        cwd=re.search(r'(?m)^(/[^\r\n]*)',before['pwd'])[1]
        def pwd():
            for _ in range(12):assert ('\r\n'+cwd+'\r\n') in p.command('pwd')
        measure('12 pwd commands',pwd)
        assert 'ERROR' not in p.command('mkdir '+directory,timeout=60);created=True
        path=directory+'/payload.bin';payload=bytes((i*37+(i>>8)*13)&255 for i in range(8192))
        measure('8192-byte upload and CRC readback',lambda:write_file(p,path,payload))
        def read():
            for _ in range(2):assert read_file(p,path)==payload
        measure('two warm 8192-byte reads',read)
        report.update(payload_bytes=len(payload),payload_sha256=hashlib.sha256(payload).hexdigest(),passed=True)
    finally:
        try:
            if profile:p.command('prof stop')
            p.command('fsput cancel')
            if created:assert 'ERROR' not in p.command('rm -r '+directory,timeout=60)
            if before is not None:
                assert {c:p.command(c) for c in before}==before
                final=p.expect('BUILD='+report['build'],'RUN=0 BUSY=0','CRASH=NONE','FIRMWARE_CRC=valid','DMA_TIMEOUTS=0','CRC_ERRORS=0','LCD_ERRORS=0')
                assert re.search(r'\bIP=(\d+)',final)[1]==re.search(r'\bIP=(\d+)',initial)[1]
                report.update(calculator_state_preserved=True,temporary_directory_removed=created,final=final)
        finally:
            (args.output/'terminal.bin').write_bytes(p.text);p.__exit__(None,None,None)
            (args.output/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    assert report['passed'] and report['calculator_state_preserved']
    print('PASS PicoCalc terminal I/O efficiency and state preservation',flush=True)

if __name__=='__main__':main()
