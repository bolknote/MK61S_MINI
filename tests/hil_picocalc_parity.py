#!/usr/bin/env python3
"""Pico H: terminal/file protocol, linked Markdown, extended APP ABI and math.

Builds two M0+ APPs, uses one newly created SD directory, and removes it in
finally. Never formats or flashes; checks the Pico UID before any mutation.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import statistics
import struct
import subprocess
import sys
import time
from hil_portable_apps import ScreenPort
from hil_c5_stack import read_file, write_file

ROOT=Path(__file__).resolve().parents[1]
NAMES=('sin','cos','tan','asin','acos','atan','ln','log10','exp','sqrt','pow')
class PicoShell(ScreenPort):
    def command(self,command,timeout=5):
        self.pump(.02);start=len(self.text);self.write_line(command)
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            self.pump(.05)
            if re.search(rb'(?:^|[\r\n])mk61> ',self.text[start:]):
                return self.text[start:].decode('cp1251','replace')
        raise TimeoutError((command,bytes(self.text[start:])))

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--firmware-directory',type=Path,default=ROOT/'binary/picocalc-pico-h')
    parser.add_argument('--directory',default='MK61S-PARITY-'+time.strftime('%Y%m%d-%H%M%S'))
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    assert re.fullmatch(r'MK61S-PARITY-[A-Za-z0-9-]+',args.directory)
    directory='/'+args.directory
    sys.path.insert(0,str(ROOT/'tools'))
    from build_picocalc import compiler_bin
    work=ROOT/'.build/picocalc-parity-hil'/args.directory;work.mkdir(parents=True,exist_ok=True)
    apps={}
    for name,source,define,ext in (
        ('PARITY','tests/picocalc_native_parity.cpp','PICO_TEST_ROOT','.cpp'),
        ('MATHCHK','tests/fixtures/compact_math_probe_app.c','MK61_MATH_VECTOR_ROOT','.c')):
        wrapper=work/(name+ext)
        wrapper.write_text(f'#define {define} "{directory}"\n#include "{ROOT/source}"\n')
        command=[sys.executable,str(ROOT/'tools/build_portable_app.py'),'--target','picocalc-pico-h','--pico-legacy-display',
            '--name',name,'--source',str(wrapper),'--arm-toolchain-bin',str(compiler_bin(None)),
            '--output-dir',str(work/name),'--shared-runtime']
        if name=='PARITY':command+=['--handled-magic','S1']
        subprocess.run(command,check=True)
        apps[name]=(work/name/(name+'.APP')).read_bytes()
    records=[]
    fixture=ROOT/'tests/fixtures/compact_math_binary64.tsv'
    for line in fixture.read_text().splitlines():
        if not line or line.startswith('#'):continue
        op,a,b,result=line.split();records.append(struct.pack('<IIQQQ',NAMES.index(op),0,int(a,16),int(b,16),int(result,16)))
    vectors=[struct.pack('<4I',0x5641544d,len(records[i:i+127]),i,len(records))+b''.join(records[i:i+127]) for i in range(0,len(records),127)]
    cases=[];created=False;math=None
    deadline=time.monotonic()+15
    while not Path(args.port).exists() and time.monotonic()<deadline:time.sleep(.2)
    with PicoShell(args.port,keyboard_layout=0) as p:
        def status():
            start=len(p.text);os.write(p.fd,b'\x05');deadline=time.monotonic()+4
            while time.monotonic()<deadline:
                p.pump(.05)
                if b'MSC_SD_READ_US=' in p.text[start:]:break
            return bytes(p.text[start:])
        def wait_text(expected,start,timeout=15):
            deadline=time.monotonic()+timeout
            while time.monotonic()<deadline:
                p.pump(.05)
                if expected in p.text[start:]:return
                if b'APP returned an error' in p.text[start:]:break
            raise AssertionError((expected,bytes(p.text[start:])))
        def passed(text):cases.append(text);print('PASS '+text,flush=True)
        os.write(p.fd,b'\x1f');p.pump(.2)
        identity=p.command('identity');assert 'UID=E6657CD423721C35' in identity,identity
        build=json.loads((args.firmware_directory/'manifest.json').read_text())
        initial=status();assert ('PICO-H '+build['prototype_version']).encode() in initial and ('BUILD='+build['build_id'].upper()).encode() in initial and b'SERVICE=CLOSED' in initial and b'USB_DISK=0' in initial,initial
        runtime=b'owned-M0-IEEE' if build.get('arithmetic_runtime')=='owned-m0' else b'GCC-IEEE-softfloat'
        assert b'MATH=compact-binary64/'+runtime+b' MATH_TEST=OK failures=0' in initial,initial
        if b'SLEEP=1' in initial: p.command('display on')
        assert 'fsput' in p.command('help')
        p.command('reinit');p.command('kbd 15');p.pump(.2);assert b'X_RAW=[ 1.0000000  00]' in status()
        p.command('poke X 42');p.pump(.2)
        before={command:p.command(command) for command in ('reg','stk','dump','pwd')}
        listing=p.command('ls /');assert args.directory+'/' not in listing
        answer=p.command('mkdir '+directory);assert 'ERROR' not in answer,answer;created=True
        try:
            for name,data in [('fixture.txt',b'abcdef'),('mode.sheet',b'S1OK'),('Face.FMK',(ROOT/'programs/games/Turochamp/Turochamp.FMK').read_bytes()),
                ('main.md','Первая страница\n\n[Далее](вторая.md)\n\n[Ошибка](missing.md)\n'.encode()),
                ('вторая.md','Вторая страница\n\n[Назад](main.md)\n'.encode()),
                *[(name+'.APP',data) for name,data in apps.items()]]:
                write_file(p,directory+'/'+name,data)
            passed('shared STM32 command names, CP1251 paths, kbd, fsput/fsget with POSIX CRC and binary/UTF-8 readback')
            p.command('uscreen');p.attach_waiting()
            deadline=time.monotonic()+5
            while not p.frames and time.monotonic()<deadline:p.pump(.05)
            assert p.frames
            start=len(p.text);p.open(directory+'/main.md');p.pump(.3)
            os.write(p.fd,b'\xb7\r');p.pump(.5)
            assert ('PATH=['+directory+'/вторая.md]').encode() in status()
            os.write(p.fd,b'\x1b');p.pump(.3);assert ('PATH=['+directory+'/main.md]').encode() in status()
            os.write(p.fd,b'\x1b');wait_text(b'mk61> ',start)
            passed('linked Markdown: Russian relative path, opening child, Esc returns to parent then caller')
            start=len(p.text);p.open(directory+'/mode.sheet')
            wait_text(b'PICO PARITY FILE_OPEN PASS',start);wait_text(b'mk61> ',start)
            assert b'APP_FLOW_RESULT=0' in p.text[start:]
            passed('FILE_OPEN uses the document handler even when the APP also implements cooperative flow')
            start=len(p.text);p.open(directory+'/PARITY.APP');wait_text(b'PICO PARITY MENU READY',start,30)
            os.write(p.fd,b'\xb6'*9+b'\r');wait_text(b'PICO PARITY API AND FLOW PASS',start)
            wait_text(b'mk61> ',start)
            assert b'APP_FLOW_RESULT=0' in p.text[start:]
            passed('native M0+ shared runtime, 64-bit EABI quotient/remainder, UI glyphs, revision-safe resources, text fonts/setup, graphics, 10-row menu, nested/direct APP flow')
            p.send(0x13);p.attached=False;p.pump(.1);p.command('uscreen off')
            for i,data in enumerate(vectors):
                write_file(p,f'{directory}/MATH{i:02d}.bin',data)
                if i%4==0:print(f'Math vectors uploaded {i+1}/{len(vectors)}',flush=True)
            answer=p.command(f'open "{directory}/MATHCHK.APP"',timeout=120)
            assert 'APP_FLOW_RESULT=0' in answer,answer
            raw=read_file(p,directory+'/MATHOUT.bin');assert len(raw)==544
            magic,version,samples,rounds,count,failures=struct.unpack_from('<6I',raw)
            assert (magic,version,samples,rounds,count)==(0x54414d51,1,1024,9,len(records))
            worst=struct.unpack_from('<11Q',raw,24);timings=struct.unpack_from('<99I',raw,112)
            math={'oracle_cases':count,'failures':failures,'worst_ulp':dict(zip(NAMES,worst)),
                'microseconds_per_call':{n:statistics.median(timings[i*rounds:(i+1)*rounds])/samples for i,n in enumerate(NAMES)},
                'raw_batch_microseconds':dict(zip(NAMES,[list(timings[i*rounds:(i+1)*rounds]) for i in range(11)])),
                'vectors_sha256':hashlib.sha256(fixture.read_bytes()).hexdigest(),'first_failure':{
                    'index':struct.unpack_from('<I',raw,508)[0],'expected':f'{struct.unpack_from("<Q",raw,520)[0]:016X}',
                    'actual':f'{struct.unpack_from("<Q",raw,528)[0]:016X}'}}
            (args.output/'math-result.json').write_text(json.dumps(math,indent=2)+'\n')
            assert not failures,math
            passed(f'{count} independent binary64 oracle vectors and 9x1024-call timing batches on physical RP2040')
            after={command:p.command(command) for command in before}
            assert before==after,('calculator changed',before,after)
            passed('program memory, stack, registers and terminal directory unchanged by diagnostics')
        finally:
            p.command('fsput cancel')
            # Restore the calculator page after the native result viewer.
            os.write(p.fd,b'\x1e\x1b\x1b\x1f');p.pump(.3)
            if created:
                answer=p.command('rm -r '+directory,timeout=30);assert 'ERROR' not in answer,answer
            p.command('poke X 42');final=status()
            (args.output/'transcript.bin').write_bytes(p.text)
        digest=hashlib.sha256((args.firmware_directory/'mk61s-picocalc-pico-h.uf2').read_bytes()).hexdigest()
        (args.output/'result.json').write_text(json.dumps({'passed':True,'uf2_sha256':digest,'identity':identity,
            'cases':cases,'math':math,'temporary_directory_removed':True,'actual_battery_operation_verified':False,
            'initial':initial.decode(errors='replace'),'final':final.decode(errors='replace')},ensure_ascii=False,indent=2)+'\n')
    print('ALL PicoCalc parity HIL PASS',flush=True)

if __name__=='__main__':main()
