#!/usr/bin/env python3
"""Check mutating CLI commands resume a parked Pico ROM; restore all data."""
import argparse,json,re
from pathlib import Path
from hil_picocalc_software import connect,calculator,restore,raw
from hil_picocalc_io_efficiency import core_stats

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ('port','uid','build-id'):ap.add_argument('--'+name,required=True)
    ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    p=connect(args.port,args.uid);before=None;profiling=False
    report=dict(passed=False,uid=args.uid,build=args.build_id.upper(),cases=[])
    try:
        initial=p.expect('BUILD='+report['build'],'FIRMWARE_CRC=valid','CRASH=NONE','SERVICE=CLOSED','RUN=0 BUSY=0','M61_ACTIVE=0','USB_DISK=0')
        before={c:p.command(c) for c in ('reg','stk','hout','dump','pwd')}
        (args.output/'snapshot.json').write_text(json.dumps(before,indent=2)+'\n')
        assert 'PROFILE=STOPPED' in p.command('prof')
        p.command('prof reset');p.command('prof start');profiling=True
        assert 'ERROR' not in p.command('asm 0 clr 1 push 2 add hlt')
        assert 'ERROR' not in p.command('run 0')
        p.expect('RUN=0 BUSY=0','X_RAW=[ 3.0000000  00]','CORE_PARKED=1',timeout=30)
        stats=core_stats(p.command('prof core'));assert stats['calls']>0,stats
        report['program_core']=stats;report['cases'].append('assemble/run/stop: ROM advances, 1 ENTER 2 + = 3, then parks')
        assert 'ERROR' not in p.command('R1= 7')
        assert re.search(r'(?m)^R1 =  7\.0000000  00\r?$',p.command('reg'))
        assert 'ERROR' not in p.command('if R1 == 7 poke X 42')
        p.expect('X_RAW=[ 4.2000000  01]','CORE_PARKED=1','RUN=0 BUSY=0')
        report['cases'].append('register assignment and conditional nested POKE resume and settle correctly')
        p.command('prof reset');p.command('prof start')
        p.expect('CORE_PARKED=1','RUN=0 BUSY=0')
        assert 'confirm Y/y' in p.command('clr')
        # The next terminal line answers the confirmation; inspect only after
        # cancelling it, otherwise "prof core" would itself cancel the prompt.
        assert 'ERROR' not in p.command('n')
        assert core_stats(p.command('prof core'))['calls']==0
        assert 'confirm Y/y' in p.command('clr')
        assert 'ERROR' not in p.command('y')
        p.expect('CORE_PARKED=1','RUN=0 BUSY=0')
        assert core_stats(p.command('prof core'))['calls']>0
        dump=p.command('dump');codes=re.findall(r'(?m)^\d{4} ([0-9A-F]{2})\r?$',dump)
        assert len(codes)>=105 and set(codes)=={'00'},dump
        report['cases'].append('clear confirmation stays parked; confirmed clear wakes and clears the full code page')
        report['passed']=True
    finally:
        try:
            if profiling:p.command('prof stop')
            if before is not None:
                if 'RUN=1' in p.status():raw(p,b'r');p.expect('RUN=0')
                calculator(p);cwd=re.search(r'(?m)^(/[^\r\n]*)',before['pwd'])[1]
                p.command('cd "'+cwd+'"');restore(p,before)
                ip=int(re.search(r'\bIP=(\d+)',initial)[1]);assert ip<100
                raw(p,('g'+f'{ip:02d}').encode());p.expect('IP='+f'{ip:02d}','RUN=0 BUSY=0');p.commands()
                assert {c:p.command(c) for c in before}==before
                final=p.expect('BUILD='+report['build'],'FIRMWARE_CRC=valid','CRASH=NONE','CORE_PARKED=1')
                report.update(calculator_state_restored=True,final=final)
        finally:
            (args.output/'terminal.bin').write_bytes(p.text);p.__exit__(None,None,None)
            (args.output/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    assert report['passed'] and report['calculator_state_restored']
    print('PASS PicoCalc selective ROM wake: actual program execution, nested POKE, confirmed clear and complete state restoration',flush=True)

if __name__=='__main__':main()
