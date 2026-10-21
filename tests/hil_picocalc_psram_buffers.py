#!/usr/bin/env python3
"""Qualify shared PSRAM buffers and compare explicit SPI/QPI firmware builds.

Requires the exact device UID/build. Uses only volatile buffers/caches; no SD
file is created. Full PSRAM testing refuses active applications or user buffers.
"""
import argparse,hashlib,json,re,time
from datetime import datetime
from pathlib import Path
from hil_picocalc_software import connect,restore,raw

def field(text,name):
    m=re.search(r'\b'+name+r'=(\d+)',text);assert m,(name,text);return int(m[1])

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',required=True);parser.add_argument('--uid',required=True)
    parser.add_argument('--firmware-directory',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    manifest=json.loads((args.firmware_directory/'manifest.json').read_text())
    uf2=args.firmware_directory/'mk61s-picocalc-pico-h.uf2'
    assert hashlib.sha256(uf2.read_bytes()).hexdigest()==manifest['uf2_sha256']
    mode='SPI' if manifest['psram_bus']=='spi' else 'QPI'
    result=dict(passed=False,build=manifest['build_id'].upper(),uid=args.uid,mode=mode,
                uf2_sha256=manifest['uf2_sha256'],samples=[])
    p=connect(args.port,args.uid);before=None;initial_ip=None
    def healthy(status):
        for s in ('BUILD='+result['build'],'FIRMWARE_CRC=valid','CRASH=NONE',
                  'KBD=OK errors=0 ','SD=OK','PANEL_INIT=1','PSRAM=OK BYTES=8388608',
                  'MODE='+mode,'QPI_FALLBACKS=0','DMA_TIMEOUTS=0','CRC_ERRORS=0','LCD_ERRORS=0',
                  'BUFFERS=shared','IO_ERRORS=0','VALID=1'):
            assert s in status,(s,status)
    try:
        initial=p.status();healthy(initial)
        for s in ('SERVICE=CLOSED','DIRTY=0','M61_ACTIVE=0','USB_DISK=0','USB_SCREEN=OFF','RUN=0 BUSY=0'):
            assert s in initial,(s,initial)
        initial_ip=field(initial,'IP');assert initial_ip<100
        before={c:p.command(c) for c in ('reg','stk','hout','dump','pwd')}
        result['initial']=initial
        date=p.command('date');clock_start=time.monotonic()
        clock=re.search(r'(?m)^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)\r?$',date)
        assert clock,date
        for i in range(3):
            text=p.command('display buffers',timeout=180)
            assert 'BUFFER_TEST=PASS' in text and 'MODE='+mode in text,text
            sample={k:field(text,k) for k in ('BYTES','ALLOCATED','WRITE_US','READ_US')}
            assert sample['BYTES']==1048576 and sample['ALLOCATED']==6291456
            result['samples'].append(sample)
            healthy(p.status())
            print(f"PASS {mode} sample {i+1}: write {sample['WRITE_US']/1e6:.3f}s, read {sample['READ_US']/1e6:.3f}s / 1 MiB",flush=True)
        status=p.status();result['after_buffers']=status
        assert field(status,'RECLAIMS')>=2 and field(status,'PINNED')==0,status
        full=p.command('display test',timeout=240);result['full_psram']=full
        assert 'HARDWARE_TEST=PASS PSRAM_BYTES=8388608' in full and 'CRC32=CBF43926' in full,full
        healthy(p.status());print('PASS complete 8 MiB write/read, hardware CRC32 and shared cache rebuild',flush=True)
        elapsed=time.monotonic()-clock_start
        after_date=p.command('date')
        after_clock=re.search(r'(?m)^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)\r?$',after_date)
        assert after_clock,after_date
        rtc=(datetime.fromisoformat(after_clock[1])-datetime.fromisoformat(clock[1])).total_seconds()
        assert abs(rtc-elapsed)<3,(rtc,elapsed)
        result['rtc_elapsed']=dict(rtc_seconds=rtc,host_seconds=elapsed)
        result['passed']=True
    finally:
        try:
            if before is not None:
                after={c:p.command(c) for c in before}
                if after!=before:restore(p,before)
                if field(p.status(),'IP')!=initial_ip:
                    raw(p,('g'+f'{initial_ip:02d}').encode());p.commands()
                final=p.expect('IP='+f'{initial_ip:02d}','RUN=0 BUSY=0')
                healthy(final)
                after={c:p.command(c) for c in before};assert after==before,(before,after)
                result.update(calculator_state_restored=True,final=final)
        finally:
            (args.output/'terminal.bin').write_bytes(p.text);p.__exit__(None,None,None)
            (args.output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    assert result['passed'] and result['calculator_state_restored']
    print('PASS PicoCalc PSRAM shared buffers '+mode,flush=True)
if __name__=='__main__':main()
