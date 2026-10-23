#!/usr/bin/env python3
"""Qualify PicoCalc PSRAM, SD DMA/CRC/cache, RTC IRQs and idle waits.

Uses one explicit UID/build and a new temporary SD directory. The full PSRAM
test destroys only volatile caches. Calculator data and unused test alarms
are restored; no formatting, firmware installation or user-file replacement.
"""
import argparse
from datetime import datetime,timezone
import hashlib,json,re,time
from pathlib import Path
from hil_picocalc_software import connect,calculator,restore,raw
from hil_c5_stack import read_file,write_file

def field(text,name):
    found=re.search(r'\b'+name+r'=(\d+)',text)
    assert found,(name,text)
    return int(found[1])

def healthy(text,build,keyboard_errors=0):
    for marker in ('BUILD='+build,'FIRMWARE_CRC=valid','CRASH=NONE','KBD=OK errors='+str(keyboard_errors)+' ',
                   'SD=OK','PSRAM=OK BYTES=8388608','EXT_CACHE=PSRAM','SD_DMA=1',
                   'CRC_ERRORS=0','DMA_TIMEOUTS=0','LCD_ERRORS=0'):
        assert marker in text,(marker,text)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',required=True);parser.add_argument('--uid',required=True)
    parser.add_argument('--firmware-directory',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    build=json.loads((args.firmware_directory/'manifest.json').read_text())
    directory='/MK61S-HARDWARE-'+datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')
    report=dict(passed=False,uid=args.uid,build=build['build_id'].upper(),uf2_sha256=build['uf2_sha256'],
                directory=directory,cases=[])
    p=connect(args.port,args.uid);before=None;created=False;alarm_backup=[]
    def passed(text):report['cases'].append(text);print('PASS '+text,flush=True)
    try:
        initial=p.status();healthy(initial,report['build'])
        for marker in ('SERVICE=CLOSED','DIRTY=0','M61_ACTIVE=0','USB_DISK=0','RUN=0 BUSY=0','USB_SCREEN=OFF'):
            assert marker in initial,(marker,initial)
        report['initial']=initial
        before={c:p.command(c) for c in ('reg','stk','hout','dump','pwd')}
        assert abs(field(initial,'UART_BAUD')-115200)<500,initial
        (args.output/'snapshot.json').write_text(json.dumps(before,indent=2)+'\n')
        full=p.command('display test',timeout=120);report['full_psram']=full
        assert 'HARDWARE_TEST=PASS PSRAM_BYTES=8388608' in full and 'CRC32=CBF43926' in full,full
        healthy(p.status(),report['build'])
        passed('full 8 MiB PSRAM write-then-read/address pattern on real PIO/DMA; hardware CRC32 known vector')
        idle_before=p.status();p.pump(1.2);idle_after=p.status()
        report['idle']={'before':idle_before,'after':idle_after}
        assert field(idle_after,'IDLE_WAITS')>field(idle_before,'IDLE_WAITS'),idle_after
        assert field(idle_after,'IDLE_MS')-field(idle_before,'IDLE_MS')>=500,idle_after
        passed('settled foreground waits for events while USB/status and keypad remain responsive')
        assert 'ERROR' not in p.command('mkdir '+directory,timeout=60);created=True
        path=directory+'/dma-cache.bin'
        payload=bytes((i*73+(i>>8)*19)&255 for i in range(16384))
        write_file(p,path,payload)
        assert read_file(p,path)==payload
        cold=p.status();assert read_file(p,path)==payload;warm=p.status()
        report['sd_cache']={'cold':cold,'warm':warm}
        assert field(warm,'READS')==field(cold,'READS'),(cold,warm)
        external_line=lambda status:re.search(r'(?m)^EXT_CACHE=[^\r\n]*',status)[0]
        assert field(external_line(warm),'SD_HIT')>=field(external_line(cold),'SD_HIT')+32,(cold,warm)
        changed=bytearray(payload);changed[17]^=0x5A;changed[8191]^=0xA5
        write_file(p,path,bytes(changed));assert read_file(p,path)==changed
        healthy(p.status(),report['build'])
        passed('SD DMA+CRC16 read/write; warm PSRAM sector hits avoid physical reads; overwrite invalidates cached sectors')
        alarms=p.command('alarm')
        saved=re.findall(r'(?m)^ALARM ([AB]) (ON|OFF) (DAILY|ONCE) (\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)\r?$',alarms)
        # Use only disabled one-shot slots; active user alarms remain intact.
        alarm_backup=[a for a in saved if a[1:3]==('OFF','ONCE')]
        assert alarm_backup,('No unused one-shot RTC slot for this test',alarms)
        before_irq=field(p.status(),'RTC_IRQS')
        for slot,*_ in alarm_backup:assert 'ALARM OK' in p.command('alarm '+slot+' in 4')
        start=len(p.text);assert 'ERROR' not in p.command('display off')
        began=time.monotonic();sleeping=p.expect('SLEEP=1',timeout=3)
        diagnostic_seconds=time.monotonic()-began
        healthy(sleeping,report['build'])
        assert 'POWER_MODE=SLEEP_USB SYS_HZ=48000000' in sleeping,sleeping
        usb_console='CONSOLE=USB ' in sleeping
        if usb_console:
            # A second USB reply must neither enqueue UART bytes nor flush
            # that transport. Clock/sleep boundaries still explicitly drain it.
            independent=p.status();healthy(independent,report['build'])
            assert 'CONSOLE=USB ' in independent
            for name in ('UART_BYTES','UART_WAIT_US','UART_FLUSH_US','UART_FLUSHES','UART_SLEEP_HOLDS'):
                assert field(independent,name)==field(sleeping,name),(name,sleeping,independent)
            report['usb_uart_independent']=dict(before=sleeping,after=independent)
        else:assert field(sleeping,'UART_SLEEP_HOLDS')>0,sleeping
        assert abs(field(sleeping,'UART_BAUD')-115200)<500,sleeping
        # A status reply must finish while the device is still asleep. Its
        # temporary UART/DMA/SRAM clock lease must already be released.
        mask=lambda text,name:int(re.search(r'\b'+name+r'=([0-9A-F]{8})',text)[1],16)
        assert not mask(sleeping,'SLEEP_CLOCK0')&0xF0000030,sleeping
        assert not mask(sleeping,'SLEEP_CLOCK1')&0x3C0,sleeping
        report['sleep_uart']=dict(status_seconds=diagnostic_seconds,status=sleeping,
            temporary_clock_lease_restored=True)
        passed('USB replies are independent of UART in 48 MHz sleep' if usb_console else
               'UART diagnostics finish in 48 MHz sleep; temporary DMA/UART/SRAM clock lease restores the sleep mask')
        end=time.monotonic()+10
        while time.monotonic()<end:
            p.pump(.1)
            if all(('RTC_ALARM='+a[0]).encode() in p.text[start:] for a in alarm_backup):break
        else:raise AssertionError(('RTC alarm IRQ did not wake',bytes(p.text[start:])))
        awake=p.expect('SLEEP=0','LCD_BKL=240',timeout=5)
        assert abs(field(awake,'UART_BAUD')-115200)<500,awake
        assert field(awake,'RTC_IRQS')>before_irq,awake
        assert field(awake,'RTC_IRQS')-before_irq<=len(alarm_backup)+1,awake
        report['rtc']={'original':alarms,'after':awake}
        passed('hardware RTC alarm IRQ wakes clock-gated sleep and delivers all due slots')
        report['passed']=True
    finally:
        try:
            if before is not None:
                calculator(p)
                for slot,_,_,date in alarm_backup:
                    assert 'ALARM OK' in p.command('alarm '+slot+' at '+date)
                    assert 'ALARM OK' in p.command('alarm '+slot+' off')
                if created:assert 'ERROR' not in p.command('rm -r '+directory,timeout=30)
                cwd=re.search(r'(?m)^(/[^\r\n]*)',before['pwd'])[1]
                p.command('cd "'+cwd+'"');restore(p,before)
                original_ip=field(initial,'IP')
                assert original_ip<100,original_ip
                raw(p,('g'+f'{original_ip:02d}').encode())
                p.expect('IP='+f'{original_ip:02d}','RUN=0 BUSY=0')
                p.commands()
                after={c:p.command(c) for c in before};assert after==before,(before,after)
                final=p.status();healthy(final,report['build'])
                report.update(calculator_state_restored=True,temporary_directory_removed=created,final=final)
        finally:
            (args.output/'terminal.bin').write_bytes(p.text);p.__exit__(None,None,None)
            (args.output/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    assert report['passed'] and report['calculator_state_restored']
    print('PASS PicoCalc hardware resources HIL',flush=True)

if __name__=='__main__':main()
