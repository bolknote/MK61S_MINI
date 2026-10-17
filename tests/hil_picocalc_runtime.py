#!/usr/bin/env python3
"""Pico H HIL: CHIP-8, native APP, USB Screen v2, RTC and suspend.

Writes only a new, uniquely named microSD test directory. Does not format
the card or touch any STM32. Uses the production keyboard/Explorer routes.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import subprocess
import time
from hil_portable_apps import ScreenPort
from hil_portable_system_apps import png

ROOT=Path(__file__).resolve().parents[1]

def disk(*args):
    return plistlib.loads(subprocess.check_output(['diskutil',*args],timeout=30))

class Pico(ScreenPort):
    def __init__(self,path):
        super().__init__(path,keyboard_layout=0)
    def close(self):
        if hasattr(self,'log_output') and hasattr(self,'text'):
            (self.log_output/'transcript.txt').write_bytes(self.text)
        super().close()
    def raw(self,keys):
        os.write(self.fd,keys)
    def status(self):
        start=len(self.text);self.raw(b'\x05');self.pump(.25)
        return self.text[start:].decode('utf-8','replace')
    def expect(self,*expected,timeout=20):
        deadline=time.monotonic()+timeout;status=''
        while time.monotonic()<deadline:
            status=self.status()
            if all(value in status for value in expected): return status
        raise AssertionError(f'Expected {expected}:\n{status}\n{bytes(self.text[-2000:])!r}')
    def step(self,keys,*expected,timeout=20):
        self.raw(keys);self.pump(.15)
        return self.expect(*expected,timeout=timeout)
    def menu(self,index):
        self.step(b'\t'+bytes([0xB5])*6+bytes([0xB6])*index+b'\r',
                  'UI=SYSTEM' if index==5 else 'SERVICE=USB_DISK' if index==1 else 'SERVICE=BROWSER')
    def system(self,index,*expected):
        self.menu(5)
        return self.step(bytes([0xB5])*8+bytes([0xB6])*index+b'\r',*expected)
    def open_file(self,path,*expected):
        self.menu(3);self.step(b'/','SERVICE=PROMPT')
        return self.step(path.encode()+b'\r',*expected,timeout=30)
    def back_to_calc(self):
        self.step(b'\x1b','SERVICE=BROWSER')
        # Back from root Explorer, then hide the still-open main menu.
        self.step(b'\x1b','SERVICE=CLOSED')
        self.step(b'\t','UI=CALCULATOR')

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--directory',help='Resume with this existing test directory from this session')
    parser.add_argument('--write-test-files',action='store_true',required=True)
    args=parser.parse_args();out=args.output;out.mkdir(parents=True,exist_ok=True)
    name=args.directory or 'MK61S-RUNTIME-'+time.strftime('%Y%m%d-%H%M%S')
    assert name.startswith('MK61S-RUNTIME-') and '/' not in name
    cases=[]
    stm32=ROOT/'.build/picocalc-native/STM32/HELLO.APP'
    def passed(text):
        cases.append(text);print('PASS '+text,flush=True)
    with Pico(args.port) as p:
        p.log_output=out
        initial=p.expect('PICO-H 0.4.','SERVICE=CLOSED','USB_DISK=0','RUN=0')
        if 'SLEEP=1' in initial: p.step(b' ','SLEEP=0')
        if not args.directory:
            before=set(disk('list','-plist','external','physical')['WholeDisks'])
            p.menu(1);mount=None;whole=None;deadline=time.monotonic()+60
            while time.monotonic()<deadline and mount is None:
                for candidate in set(disk('list','-plist','external','physical')['WholeDisks'])-before:
                    info=disk('info','-plist',candidate)
                    if info.get('BusProtocol')!='USB' or 'PicoCalc microSD' not in info.get('MediaName',''): continue
                    whole=candidate
                    for part in disk('list','-plist',whole)['AllDisksAndPartitions'][0].get('Partitions',[]):
                        volume=disk('info','-plist',part['DeviceIdentifier'])
                        if volume.get('MountPoint'): mount=Path(volume['MountPoint']);break
                if mount is None: p.pump(.5)
            if mount is None: raise RuntimeError('PicoCalc SD did not mount')
            directory=mount/name;directory.mkdir()
            for app in ('HELLO','SERVICES','CHECK','PROBE','ELIZA','SHEET'):
                shutil.copy2(ROOT/f'.build/picocalc-native/{app}/{app}.APP',directory/f'{app}.APP')
            # Same SDK source, built for STM32, must fail before execution.
            stm32=ROOT/'.build/picocalc-native/STM32/HELLO.APP'
            if stm32.exists(): shutil.copy2(stm32,directory/'M4.APP')
            (directory/'keys.ch8').write_bytes(bytes.fromhex('00e0f00af02961006200d125120c'))
            subprocess.run(['python3',str(ROOT/'examples/chip8/ECHO-8/assemble.py'),
                            str(ROOT/'examples/chip8/ECHO-8/echo8.asm'),str(directory/'ECHO8.ch8')],check=True)
            (directory/'native.m61').write_text('open HELLO.APP\nopen PROBE.APP\nprint off\nprint "PICO APP M61 RETURN"\nret\n')
            for attempt in range(3):
                result=subprocess.run(['diskutil','eject',whole],timeout=30)
                if result.returncode==0: break
                p.pump(2)
            if result.returncode: raise RuntimeError('Safe SD eject failed; leave USB disk active')
            p.step(b'\r','SERVICE=CLOSED');p.step(b'\t','UI=CALCULATOR')
            passed('microSD USB round trip; uniquely named ROM/APP fixtures')
        if 'USB_SCREEN=OFF ' in initial: p.system(5,'USB_SCREEN=OFFER','UI=CALCULATOR')
        p.attach_waiting();p.pump(.7)
        assert p.frames and any(p.frames[-1]);passed('USB Screen v2 attach, PackBits, atomic CRC frames')
        p.step(b'\x08','X_RAW=[ 0.0000000  00]');p.key(21);p.expect('X_RAW=[ 1.0000000  00]');passed('USB Screen MINI virtual key and release')
        for launch in range(2):
            start=len(p.frames);p.open_file('/'+name+'/CHECK.APP','RUNTIME=APP')
            expected=bytes(((i*17+i//16)^0xA5)&255 for i in range(1536))
            p.expect_frame(expected,start,timeout=10);png(expected,out/f'native-check-{launch}.png')
            p.raw(b'\x1b');p.expect('RUNTIME=NONE','SERVICE=VIEWER');p.back_to_calc()
        passed('native ARMv6-M execution, relocation, fresh .data/.bss on repeat launch, graphics')
        start=len(p.text);p.open_file('/'+name+'/PROBE.APP','SERVICE=VIEWER','RTC_SET=1')
        assert b'PICO NATIVE API PASS' in p.text[start:] and b'APP_RESULT=0' in p.text[start:]
        p.back_to_calc();passed('native API math, number I/O, memory leases, fonts, registers, ticking RTC')
        if stm32.exists():
            start=len(p.text);p.open_file('/'+name+'/M4.APP','SERVICE=MESSAGE','requires ABI 6 / Pico H')
            assert b'APP_RESULT=' not in p.text[start:];p.back_to_calc();passed('STM32/M4 APP rejected before execution')
        start=len(p.frames);p.open_file('/'+name+'/keys.ch8','RUNTIME=CHIP8');p.key(21);p.pump(.8)
        assert len(p.frames)>start and any(p.frames[-1]);png(p.frames[-1],out/'chip8-key.png')
        p.raw(b'\x1b');p.expect('SERVICE=BROWSER','RUNTIME=NONE');p.step(b'\x1b','SERVICE=CLOSED');p.step(b'\t','UI=CALCULATOR')
        passed('CHIP-8 SD ROM, Fx0A virtual key, display, Escape exit')
        for app in ('ELIZA','SHEET'):
            start=len(p.frames);p.open_file('/'+name+'/'+app+'.APP','RUNTIME=APP');p.pump(1)
            assert len(p.frames)>start and any(p.frames[-1]);png(p.frames[-1],out/(app.lower()+'.png'))
            if app=='ELIZA':
                p.raw(b'\r');p.pump(.3);p.raw(b'\r');p.pump(.3);p.raw(b'\r');p.pump(.3);p.raw(b'hello\r');p.pump(.8);png(p.frames[-1],out/'eliza-reply.png')
            p.raw(b'\x1b');p.expect('RUNTIME=NONE',timeout=15);p.back_to_calc()
        passed('unmodified ELIZA and SHEET sources rebuilt for Pico H and run on device')
        p.open_file('/'+name+'/native.m61','SERVICE=EDITOR');p.raw(b'\x83');p.expect('M61_ACTIVE=0','SERVICE=CLOSED',timeout=30)
        assert b'PICO NATIVE API PASS' in p.text[-5000:];passed('M61 opens native APP and resumes the shared scenario')
        # Stop the heartbeat and let the device drop/release the screen session.
        p.attached=False;p.pump(3.5);p.expect('USB_SCREEN=OFFER');passed('USB Screen heartbeat timeout returns control')
        before_sleep=p.system(7,'SLEEP=1')
        p.pump(.3);asleep=p.expect('SLEEP=1','LCD_BKL=0','KBD_BKL=0')
        p.step(b' ','SLEEP=0','LCD_BKL=240','KBD_BKL=40');passed('sleep blanks LCD/keyboard and wake restores settings and RAM')
        final=p.status();assert 'SCREEN_ERRORS=0' in final and 'READ_ERROR=0 WRITE_ERROR=0' in final
        (out/'transcript.txt').write_bytes(p.text)
        (out/'result.json').write_text(json.dumps({'firmware_sha256':hashlib.sha256((ROOT/'binary/picocalc-pico-h/mk61s-picocalc-pico-h.uf2').read_bytes()).hexdigest(),
            'directory':'/'+name,'cases':cases,'initial':initial,'asleep':asleep,'final':final},ensure_ascii=False,indent=2)+'\n')
        print('ALL PASS '+str(out),flush=True)

if __name__=='__main__': main()
