#!/usr/bin/env python3
"""Install the complete Pico H APP collection and qualify the exact SD copies.

Requires explicit --install. Uses a new directory; --resume only reuses files
whose contents already match this collection. No formatting or flashing.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from hil_picocalc_parity import PicoShell
from hil_c5_stack import read_file, write_file
from hil_portable_system_apps import png

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from build_picocalc import compiler_bin
from build_picocalc_apps import APPS, ASSETS
from package_picocalc import verify_app


class AppsPort(PicoShell):
    def command(self,command,timeout=5):
        # Each Pico fsget block yields to an emulated MK-61 cycle. Large
        # SHEET images need more time than the STM32 helper's 15-second limit.
        if command.startswith('fsget '):timeout=max(timeout,120)
        return super().command(command,timeout)

    def commands(self):
        start=len(self.text);os.write(self.fd,b'\x1f')
        self.wait_text(b'MK61S PicoCalc terminal;',start,timeout=90)
        self.wait_text(b'mk61> ',start,timeout=90)

    def wait_text(self,expected,start,timeout=15):
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            self.pump(.05)
            if expected in self.text[start:]:return
        raise AssertionError((expected,bytes(self.text[start:])))

    def status(self):
        self.pump(.03);start=len(self.text);os.write(self.fd,b'\x05')
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            self.pump(.05)
            if re.search(rb'MSC_SD_READ_US=[^\r\n]*\r?\n',self.text[start:]):
                return self.text[start:].decode('utf-8','replace')
        raise TimeoutError(bytes(self.text[start:]))

    def expect(self,*markers,timeout=15):
        deadline=time.monotonic()+timeout;status=''
        while time.monotonic()<deadline:
            status=self.status()
            if all(marker in status for marker in markers):return status
        raise AssertionError((markers,status))

    def calculator(self):
        os.write(self.fd,b'\x1e');self.pump(.05)
        for _ in range(6):
            if 'SERVICE=CLOSED' in self.status():break
            os.write(self.fd,b'\x1b');self.pump(.15)
        else:raise AssertionError('APP did not leave the foreground')
        self.commands()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',required=True)
    parser.add_argument('--uid',required=True)
    parser.add_argument('--apps',type=Path,default=ROOT/'binary/picocalc-pico-h/apps')
    parser.add_argument('--firmware-directory',type=Path,default=ROOT/'binary/picocalc-pico-h')
    parser.add_argument('--directory',default='/MK61S-PicoCalc-0.6')
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--install',action='store_true',required=True)
    parser.add_argument('--resume',action='store_true')
    parser.add_argument('--native-display',action='store_true')
    args=parser.parse_args()
    assert re.fullmatch(r'/MK61S-PicoCalc-[A-Za-z0-9.-]+',args.directory)
    assert re.fullmatch(r'[0-9A-F]{16}',args.uid)
    args.output.mkdir(parents=True,exist_ok=True)
    records=json.loads((args.apps/'manifest.json').read_text())
    assert [r['name'] for r in records]==list(APPS)
    for record in records:verify_app(args.apps/(record['name']+'.APP'),record)
    names=[*(name+'.APP' for name in APPS),*ASSETS,'manifest.json']
    payloads={name:(args.apps/name).read_bytes() for name in names}
    hashes={name:hashlib.sha256(data).hexdigest() for name,data in payloads.items()}
    build=json.loads((args.firmware_directory/'manifest.json').read_text())
    work=ROOT/'.build/picocalc-apps-hil';work.mkdir(parents=True,exist_ok=True)
    wrapper=work/'WBMPCHK.cpp'
    wrapper.write_text(f'#define PICO_APPS_DIRECTORY "{args.directory}"\n#include "{ROOT}/tests/picocalc_wbmp_handler_probe.cpp"\n')
    subprocess.run([sys.executable,str(ROOT/'tools/build_portable_app.py'),'--target','picocalc-pico-h',
        '--name','WBMPCHK','--source',str(wrapper),'--arm-toolchain-bin',str(compiler_bin(None)),
        '--output-dir',str(work/'WBMPCHK'),'--shared-runtime'],check=True)
    probe=(work/'WBMPCHK/WBMPCHK.APP').read_bytes()
    probe_path=args.directory+'/.WBMPCHK.APP'
    cases=[];screens={};probe_written=False
    def passed(message):cases.append(message);print('PASS '+message,flush=True)
    with AppsPort(args.port,keyboard_layout=0) as p:
        p.native_display=args.native_display
        p.commands();identity=p.command('identity')
        assert f'UID={args.uid}' in identity,identity
        initial=p.expect('SERVICE=CLOSED','USB_DISK=0','RUN=0','DIRTY=0','BUILD='+build['build_id'].upper())
        assert f'PICO-H {build["prototype_version"]} ' in initial,initial
        if 'SLEEP=1' in initial:p.command('display on')
        p.pump(.2)
        before={command:p.command(command) for command in ('reg','stk','dump','pwd')}
        listing=p.command('ls /')
        exists=any(line.endswith('\t'+args.directory[1:]+'/') for line in listing.splitlines())
        if exists:
            assert args.resume,'destination already exists; use --resume to verify/reuse matching files'
        else:assert 'ERROR' not in p.command('mkdir '+args.directory)
        try:
            if exists:
                existing=p.command('ls '+args.directory)
                present={line.split('\t')[-1] for line in existing.splitlines() if line.startswith('f\t')}
                assert not any(line.startswith('d\t') for line in existing.splitlines()),existing
                assert present<=set(names)|{'INSTALL.json'},present
            else:present=set()
            for name,data in payloads.items():
                path=args.directory+'/'+name
                if name in present:assert read_file(p,path)==data,path
                else:write_file(p,path,data)
                print('Installed and read back '+name,flush=True)
            passed('all seven M0+ APPs and example assets read back byte-for-byte with POSIX CRC')
            write_file(p,args.directory+'/INSTALL.json',json.dumps({
                'profile':'picocalc-pico-h','uid':args.uid,'uf2_sha256':build['uf2_sha256'],'files':hashes,
            },indent=2).encode())
            p.command('uscreen');p.attach_waiting()

            def picture(name,start):
                # The foreground may change before its first graphics_present.
                # Request a fresh keyframe after the app's initialization, so
                # a cached Explorer frame is never accepted as its screenshot.
                p.pump(.4);start=len(p.frames);p.send(0x16)
                deadline=time.monotonic()+15
                while time.monotonic()<deadline:
                    if len(p.frames)>=start+(2 if args.native_display else 1) and any(p.frames[-1]):break
                    p.pump(.05)
                assert len(p.frames)>start and any(p.frames[-1]),name
                assert len(p.frames[-1])==(12800 if args.native_display else 1536),name
                png(p.frames[-1],args.output/(name+'.png'))
                screens[name]=hashlib.sha256(p.frames[-1]).hexdigest()

            def open_app(name,expected=None):
                start=len(p.text);frame=len(p.frames);p.open(args.directory+'/'+name)
                if expected:p.expect('RUNTIME=APP',expected)
                else:p.wait_text(b'APP_FLOW_RESULT=0',start)
                p.pump(.2);picture(name.replace('.','-'),frame)
                return start

            def returned(start):
                p.wait_text(b'APP_FLOW_RESULT=0',start);p.wait_text(b'mk61> ',start)
                response=bytes(p.text[start:])
                assert b'APP returned an error' not in response,response
                p.calculator()

            for name,text,wait in (
                ('HELLO.APP','HELLO C APP',False),
                ('HELLO_CPP.APP','HELLO APP',True),
                ('HELLO_RS.APP','HELLO, MK61S!',True),
                ('SERVICES.APP','sqrt(3^2+4^2)=5',True),
                ('WBMP.APP','Open a WBMP file',False)):
                for launch in range(2):
                    start=open_app(name,'TEXT=['+text if wait else None)
                    assert 'TEXT=['+text in p.status()
                    if wait:os.write(p.fd,b'\r')
                    returned(start)
                passed(name+': two successful launches, expected text and clean exit')
            start=open_app('ELIZA.APP','RUNTIME=APP')
            os.write(p.fd,b'\r');p.pump(.4);os.write(p.fd,b'\r');p.pump(.4)
            p.expect('RUNTIME=APP','TEXT=[>')
            os.write(p.fd,b'hello\r');reply=p.expect('TEXT=[HOW DO YOU DO.')
            picture('ELIZA-reply',0)
            os.write(p.fd,b'\x1b');returned(start)
            passed('ELIZA.APP: graphical intro, QWERTY HELLO input, expected DOCTOR reply and exit')
            for document in ('SHEET.APP','BUDGET.mks','CYCLE.mks'):
                start=open_app(document,'RUNTIME=APP');frame=p.frames[-1]
                os.write(p.fd,b'\xb7');until=time.monotonic()+5
                while time.monotonic()<until and p.frames[-1]==frame:p.pump(.05)
                assert p.frames[-1]!=frame,(document,p.status())
                os.write(p.fd,b'\x1b');returned(start)
            passed('SHEET.APP: new book, Russian/formula document, cycle document, navigation and exit')
            write_file(p,probe_path,probe);probe_written=True
            start=len(p.text);frames=len(p.frames);p.open(probe_path)
            width,height=(320,320) if args.native_display else (192,64)
            expected=bytearray(width*height//8)
            for y in range(height):
                for x in range(width):
                    if (x*3+y*5)%11<5:expected[(y//8)*width+x]|=1<<(y%8)
            p.expect_frame(bytes(expected),frames,timeout=20);picture('WBMP-file-handler',frames)
            os.write(p.fd,b'\x1b');p.wait_text(b'PICO WBMP FILE_OPEN PASS',start);returned(start)
            assert 'ERROR' not in p.command('rm '+probe_path);probe_written=False
            passed(f'installed WBMP.APP FILE_OPEN through APP_FLOW DIRECT; exact {width}x{height} pixel oracle')
            def steady_chip8_frame():
                until=time.monotonic()+20;changed=time.monotonic();last=None
                while time.monotonic()<until:
                    p.pump(.05)
                    if not p.frames:continue
                    frame=p.frames[-1]
                    if frame!=last:last=frame;changed=time.monotonic()
                    elif any(frame) and time.monotonic()-changed>.7:return frame
                raise AssertionError('CHIP-8 did not finish drawing its page')
            start=len(p.text);frames=len(p.frames);p.open(args.directory+'/ECHO8.ch8')
            p.expect('RUNTIME=CHIP8');title=steady_chip8_frame();picture('ECHO8-title',frames)
            p.key(16);until=time.monotonic()+10
            while time.monotonic()<until and p.frames[-1]==title:p.pump(.05)
            assert p.frames[-1]!=title,'CHIP-8 did not advance from its title after a key'
            assert steady_chip8_frame()!=title
            picture('ECHO8-intro',frames)
            os.write(p.fd,b'\x1b');p.wait_text(b'CHIP8_RESULT=0',start);p.wait_text(b'mk61> ',start)
            p.calculator()
            passed('installed ECHO8.ch8: physical RP2040 interpreter, title/intro raster, Fx0A key and clean Escape exit')
            after={command:p.command(command) for command in before}
            assert before==after,('calculator or terminal directory changed',before,after)
            for name,digest in hashes.items():
                assert hashlib.sha256(read_file(p,args.directory+'/'+name)).hexdigest()==digest,name
            passed('installed files unchanged after execution; registers, stack, program and terminal directory preserved')
        finally:
            p.calculator()
            p.command('fsput cancel')
            if probe_written:
                assert read_file(p,probe_path)==probe
                assert 'ERROR' not in p.command('rm '+probe_path)
            p.send(0x13);p.attached=False;p.pump(.1)
            if 'USB_SCREEN=OFF ' in initial:p.command('uscreen off')
            final=p.status();(args.output/'transcript.bin').write_bytes(p.text)
        assert 'SERVICE=CLOSED' in final and 'USB_DISK=0' in final and 'SCREEN_ERRORS=0' in final
        report={'passed':True,'recorded_at_utc':datetime.now(timezone.utc).isoformat(),
            'uid':args.uid,'uf2_sha256':build['uf2_sha256'],'directory':args.directory,
            'files':hashes,'cases':cases,'screens':screens,'initial':initial,'final':final,
            'temporary_probe_removed':True}
        (args.output/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print('ALL PicoCalc native APP install/HIL PASS',flush=True)


if __name__=='__main__':main()
