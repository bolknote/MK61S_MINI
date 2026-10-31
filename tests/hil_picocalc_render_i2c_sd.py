#!/usr/bin/env python3
"""Measure idle/menu raster work and live I2C; preserve calculator state."""
import argparse,json,re
from pathlib import Path
from datetime import datetime,timezone
from hil_picocalc_software import connect,calculator,restore,raw
from hil_picocalc_hardware import healthy,field

def restore_ip(p,ip):
    # The ROM GOTO key takes two decimal digits. Reach the final physical
    # cells through ordinary STEP keys rather than typing a third digit into X.
    first=min(ip,99)
    raw(p,('g'+f'{first:02d}').encode())
    p.expect('IP='+f'{first:02d}','RUN=0 BUSY=0')
    if ip>first:raw(p,b'fe')
    for at in range(first,ip,8):
        end=min(ip,at+8)
        raw(p,b'['*(end-at))
        p.expect('IP='+f'{end:02d}','RUN=0 BUSY=0')
    if ip>first:raw(p,b'fn');p.expect('IP='+f'{ip:02d}','RUN=0 BUSY=0')
    p.commands()

def stable_sample(start,end):
    assert field(end,'UI_SKIPS')>field(start,'UI_SKIPS')+20,end
    assert field(end,'I2C_IRQS')>field(start,'I2C_IRQS'),end
    for name in ('I2C_TIMEOUTS','I2C_ABORTS','SD_SPEED_FALLBACKS'):
        assert field(end,name)==field(start,name),(name,start,end)
    hz,safe,advertised=(field(end,name) for name in ('SD_SPI_HZ','SD_SAFE_HZ','SD_ADVERTISED_HZ'))
    assert 0<safe<=min(12500000,advertised) and safe<=hz<=min(20833333,advertised),end
    assert hz==field(start,'SD_SPI_HZ'),(start,end)

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ('port','uid'):ap.add_argument('--'+name,required=True)
    for name in ('firmware-directory','output'):ap.add_argument('--'+name,type=Path,required=True)
    ap.add_argument('--baseline',action='store_true')
    args=ap.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    m=json.loads((args.firmware_directory/'manifest.json').read_text())
    report=dict(passed=False,uid=args.uid,build=m['build_id'].upper(),uf2_sha256=m['uf2_sha256'],
        recorded_at_utc=datetime.now(timezone.utc).isoformat(),baseline=args.baseline,samples={})
    p=connect(args.port,args.uid);before=None;was_profiling=False;profiling=False
    try:
        initial=p.expect('SERVICE=CLOSED','RUN=0 BUSY=0','USB_DISK=0','DIRTY=0','USB_SCREEN=OFF')
        keyboard_errors=field(initial,'errors');healthy(initial,report['build'],keyboard_errors)
        before={c:p.command(c) for c in ('reg','stk','hout','dump','pwd')};report['initial']=initial
        previous_profile=p.command('prof');was_profiling='PROFILE=RUNNING' in previous_profile
        calculator(p);p.commands()
        for name in ('calculator','menu'):
            if name=='menu':raw(p,b'\t');p.expect('UI=MAIN');p.commands()
            p.pump(.4);start=p.status()
            p.command('prof reset');p.command('prof start');profiling=True
            p.pump(3.2);p.command('prof stop');profiling=False
            profile=p.command('prof');end=p.status();healthy(end,report['build'],keyboard_errors)
            match=re.search(r'(?m)^display\s+calls=(\d+) total_us=(\d+) max_us=(\d+)',profile);assert match,profile
            sample=dict(before=start,after=end,profile=profile,display_calls=int(match[1]),display_us=int(match[2]))
            if args.baseline:assert sample['display_calls']>20,sample
            else:
                assert sample['display_calls']<=(1 if name=='calculator' else 0),sample
                stable_sample(start,end)
            report['samples'][name]=sample
            print('PASS',name,'idle raster calls',sample['display_calls'],'raster us',sample['display_us'],flush=True)
        if not args.baseline:
            # Menu navigation and a direct terminal mutation both invalidate.
            start=p.status();raw(p,b'\xb6');p.pump(.3)
            assert field(p.status(),'UI_RENDERS')>field(start,'UI_RENDERS')
            # Y is visible in the stack pane immediately. A raw X write can
            # leave the physical MK-61 display latch unchanged until a key.
            calculator(p);p.commands();start=p.status();p.command('poke Y 42');p.pump(.3)
            assert field(p.status(),'UI_RENDERS')>field(start,'UI_RENDERS')
        report['passed']=True
    finally:
        try:
            if before is not None:
                if profiling:p.command('prof stop')
                calculator(p);restore(p,before)
                restore_ip(p,field(initial,'IP'))
                assert {c:p.command(c) for c in before}==before
                if was_profiling:p.command('prof start')
                final=p.status();healthy(final,report['build'],keyboard_errors)
                report.update(calculator_state_restored=True,final=final)
        finally:
            (args.output/'terminal.bin').write_bytes(p.text);p.__exit__(None,None,None)
            (args.output/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    assert report['passed'] and report['calculator_state_restored']
if __name__=='__main__':main()
