#!/usr/bin/env python3
"""Qualify Pico software parity on its exact UID, using a new temporary SD directory.

Installs only absent/matching bundled UI fonts. --fault-tests explicitly runs
private UDF and watchdog APP probes; no fault command is added to the firmware.
No formatting or firmware flashing. Calculator data and settings are restored.
"""
import argparse
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo
import re
import subprocess
import sys
import time
from hil_picocalc_apps import AppsPort
from hil_c5_stack import read_file,write_file
from hil_portable_system_apps import png

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from build_picocalc import compiler_bin


def raw(p,keys):
    os.write(p.fd,b'\x1e'+keys);p.pump(.2)


def calculator(p):
    p.calculator()
    if 'UI=CALCULATOR' not in p.status():raw(p,b'\t');p.commands()


def font(p,family,size,key=None):
    calculator(p)
    raw(p,b'\t'+b'\xb5'*20+b'\xb6'*2+b'\r'+b'\xb5'*20+b'\xb6'*6+b'\r'+b'\xb5'*20+b'\xb6')
    p.expect('UI=FONTS')
    for _ in range(64):
        status=p.status()
        if (f'UI_FONT_FAMILY={family} ' in status and f'UI_FONT_SIZE={size} ' in status and
            (key is None or f'UI_FONT_KEY={key}' in status)):break
        raw(p,b'\xb7')
    else:raise AssertionError(('UI font not found',status))
    p.pump(1.3)
    deadline=time.monotonic()+15
    while time.monotonic()<deadline:
        status=p.status()
        if 'SETTINGS=SAVED' in status or 'SETTINGS=LOADED' in status:break
    else:raise AssertionError(('font settings did not settle',status))
    return p.status()


def connect(path,uid):
    deadline=time.monotonic()+30;error=None
    while time.monotonic()<deadline:
        p=None
        try:
            p=AppsPort(path,keyboard_layout=0);p.__enter__();p.commands()
            identity=p.command('identity')
            assert f'UID={uid}' in identity,identity
            return p
        except (OSError,TimeoutError) as failure:
            error=failure
            if p is not None:p.__exit__(None,None,None)
            time.sleep(.3)
    raise TimeoutError(('Pico did not reconnect',error))


def saved_numbers(text,prefix):
    return re.findall(r'(?m)^('+prefix+r'[0-9A-F]) = (.{14})\r?$',text)


def number(raw_value):
    return raw_value[:10].replace(' ','')+'e'+raw_value[11:14].replace(' ','')


def restore(p,before):
    calculator(p)
    values=dict(saved_numbers(before['stk'],'S'))
    # LAST X is updated through an ordinary binary operation before restoring
    # X/Y/Z/T, so watchdog/reset tests also preserve the fifth stack register.
    assert 'ERROR' not in p.command('poke Y 0')
    assert 'ERROR' not in p.command('poke X '+number(values['S4']))
    raw(p,b'+');p.pump(.3);p.expect('BUSY=0','RUN=0');p.commands()
    for line in re.findall(r'(?m)^hin [^\r\n]+',before['hout']):
        assert 'ERROR' not in p.command(line)
    for name,value in saved_numbers(before['reg'],'R'):
        assert 'ERROR' not in p.command(name+'= '+number(value))
    for i,name in enumerate(('X','Y','Z','T')):
        assert 'ERROR' not in p.command('poke '+name+' '+number(values['S'+str(i)]))
    for command in ('reg','stk','hout','pwd'):
        current=p.command(command)
        if command in ('reg','stk'):
            prefix='R' if command=='reg' else 'S'
            old,new=saved_numbers(before[command],prefix),saved_numbers(current,prefix)
        else:
            pattern=r'(?m)^hin [^\r\n]+' if command=='hout' else r'(?m)^/[^\r\n]*'
            old,new=re.findall(pattern,before[command]),re.findall(pattern,current)
        assert old and old==new,(command,before[command],current)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',required=True);parser.add_argument('--uid',required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--firmware-directory',type=Path,default=ROOT/'binary/picocalc-pico-h')
    parser.add_argument('--directory',default='/MK61S-SOFTWARE-'+time.strftime('%Y%m%d-%H%M%S'))
    parser.add_argument('--fault-tests',action='store_true')
    args=parser.parse_args()
    assert re.fullmatch(r'/MK61S-SOFTWARE-[A-Za-z0-9-]+',args.directory)
    assert re.fullmatch(r'[0-9A-F]{16}',args.uid)
    args.output.mkdir(parents=True,exist_ok=True)
    build=json.loads((args.firmware_directory/'manifest.json').read_text())
    toolchain=compiler_bin(None);work=ROOT/'.build/picocalc-software-hil';work.mkdir(exist_ok=True)
    transcripts=[];cases=[];screens={};installed_fonts={};created=False;fault_reports={}
    before=None;initial=None
    def passed(message):cases.append(message);print('PASS '+message,flush=True)
    def build_app(name,source,defines=(),extra=()):
        wrapper=work/(name+Path(source).suffix)
        wrapper.write_text('\n'.join(defines)+f'\n#include "{ROOT/source}"\n')
        command=[sys.executable,str(ROOT/'tools/build_portable_app.py'),'--target','picocalc-pico-h','--pico-legacy-display',
            '--name',name,'--arm-toolchain-bin',str(toolchain),'--shared-runtime','--source',str(wrapper),
            '--output-dir',str(work/name)]
        for path in extra:command+=['--source',str(ROOT/path)]
        subprocess.run(command,check=True,stdout=subprocess.DEVNULL)
        return (work/name/(name+'.APP')).read_bytes()
    p=connect(args.port,args.uid)
    def screenshot(name,predicate=lambda frame:True):
        if not p.attached:p.command('uscreen on');p.attach_waiting()
        p.pump(.2)
        start=len(p.frames);p.send(0x16);deadline=time.monotonic()+10
        while time.monotonic()<deadline:
            p.pump(.05)
            if len(p.frames)>start and predicate(p.frames[-1]):break
        assert len(p.frames)>start and predicate(p.frames[-1]),name
        png(p.frames[-1],args.output/(name+'.png'))
        screens[name]=hashlib.sha256(p.frames[-1]).hexdigest();return p.frames[-1]
    def reconnect():
        nonlocal p
        transcripts.append(bytes(p.text));p.__exit__(None,None,None)
        time.sleep(.8);p=connect(args.port,args.uid)
        p.expect('SERVICE=CLOSED','USB_DISK=0','RUN=0')
    try:
        calculator(p);initial=p.expect('PICO-H '+build['prototype_version'],'BUILD='+build['build_id'].upper(),'SERVICE=CLOSED','DIRTY=0','USB_DISK=0','RUN=0')
        original_font=re.search(r'UI_FONT_FAMILY=(\d+) UI_FONT_SIZE=(\d+) UI_FONT_KEY=([0-9A-F]+)',initial).groups()
        before={cmd:p.command(cmd) for cmd in ('reg','stk','hout','pwd')}
        root=p.command('ls /');assert args.directory[1:]+'/' not in root
        assert 'ERROR' not in p.command('mkdir '+args.directory);created=True
        if not re.search(r'(?im)\tFonts/\r?$',root):assert 'ERROR' not in p.command('mkdir /Fonts')
        listing=p.command('ls /Fonts');font_name=None
        font_names={name.casefold():name for name in re.findall(r'(?m)^f\t\d+(?: B)?\t([^\r\n]+)',listing)}
        for source in sorted((ROOT/'programs/Fonts').glob('*.FMK')):
            name=source.name;data=source.read_bytes()
            name=font_names.get(name.casefold(),name)
            if name.casefold() in font_names and read_file(p,'/Fonts/'+name)!=data:
                name='MK61S-'+name
                name=font_names.get(name.casefold(),name)
            if name.casefold() in font_names:
                assert read_file(p,'/Fonts/'+name)==data,('font name collision',name)
            else:
                write_file(p,'/Fonts/'+name,data);font_names[name.casefold()]=name
            installed_fonts['/Fonts/'+name]=hashlib.sha256(data).hexdigest()
            if source.stem=='DejaVu-12':font_name=Path(name).stem
        assert font_name
        probe=build_app('SOFTCHK','tests/picocalc_software_probe.cpp',
            [f'#define PICO_SOFTWARE_ROOT "{args.directory}"',f'#define PICO_SOFTWARE_FONT_ITEM "{font_name}"'],
            ['code/fmk_prepare.cpp','code/fmk_font.cpp','code/prepared_font.cpp'])
        fixtures={'stamp.txt':b'abcdef','SOFTCHK.APP':probe,
            'image.wbmp':bytes((0,0,8,8,0xAA,0x55,0xFF,0,0x81,0x42,0x24,0x18)),
            'image.md':b'![diagnostic](image.wbmp)\n',
            'styles.md':b'# Heading\n\n**bold** *italic* ~~strike~~ `code`\n\n> quote\n\n- [x] item\n\n[image](image.md)\n'}
        for name,data in fixtures.items():write_file(p,args.directory+'/'+name,data)
        p.command('prof reset');p.command('prof start')
        result=p.command('open "'+args.directory+'/SOFTCHK.APP"',timeout=60)
        assert 'PICO SOFTWARE APP PASS' in result and 'APP_FLOW_RESULT=0' in result,result
        calculator(p);passed('native ARMv6-M resource stamps, stale reads, UI font catalog/glyphs, prepared-font CRC and restoration')
        p.command('uscreen on');p.attach_waiting()
        assert 'ERROR' not in p.command('date 2026-10-17 12:34:00')
        columns=((0,0x42,0x7F,0x40,0),(0x72,0x49,0x49,0x49,0x46),
            (0x21,0x41,0x49,0x4D,0x33),(0x18,0x14,0x12,0x7F,0x10))
        rows=[0]*7
        for left,digit in zip((0,6,14,20),columns):
            for x,bits in enumerate(digit):
                for y in range(7):
                    if bits&(1<<y):rows[y]|=1<<(left+x)
        rows[2]|=1<<12;rows[4]|=1<<12
        def clock_matches(frame):
            return all(bool(frame[((y+18)//8)*192+165+x]&(1<<((y+18)%8)))==bool(rows[y]&(1<<x))
                for y in range(7) for x in range(25))
        screenshot('idle-clock',clock_matches)
        p.command('date '+datetime.now(ZoneInfo('Europe/Moscow')).strftime('%Y-%m-%d %H:%M:%S'))
        passed('idle clock HH:MM: exact calculator and USB Screen raster; RTC restored to current local time')
        start=len(p.text);frames=len(p.frames);p.open(args.directory+'/image.md')
        p.expect('SERVICE=VIEWER','PATH=['+args.directory+'/image.md]')
        expected=bytearray(1536)
        for y,value in enumerate(fixtures['image.wbmp'][4:]):
            for x in range(8):
                if not value&(0x80>>x):expected[((y+2)//8)*192+92+x]|=1<<((y+2)%8)
        p.expect_frame(bytes(expected),frames,timeout=10);screenshot('Markdown-inline-WBMP')
        os.write(p.fd,b'\x1b');p.wait_text(b'mk61> ',start);calculator(p)
        start=len(p.text);p.open(args.directory+'/styles.md');p.expect('SERVICE=VIEWER','PATH=['+args.directory+'/styles.md]')
        first=screenshot('Markdown-styles');os.write(p.fd,b'\xd7');p.pump(.2)
        assert screenshot('Markdown-scrolled')!=first
        frames=len(p.frames);os.write(p.fd,b'\xb7\r');p.expect('PATH=['+args.directory+'/image.md]')
        p.expect_frame(bytes(expected),frames,timeout=10)
        os.write(p.fd,b'\x1b');p.expect('PATH=['+args.directory+'/styles.md]')
        os.write(p.fd,b'\x1b');p.wait_text(b'mk61> ',start);calculator(p)
        passed('graphical Markdown styles, inline WBMP pixel oracle, paging, links and back history')
        # The same image must work through the normal terminal file-open route.
        start=len(p.text);frames=len(p.frames);p.open(args.directory+'/image.wbmp')
        p.expect('SERVICE=VIEWER','PATH=['+args.directory+'/image.wbmp]')
        expected=bytearray(1536)
        for y,value in enumerate(fixtures['image.wbmp'][4:]):
            for x in range(8):
                if not value&(0x80>>x):expected[(y//8)*192+x]|=1<<(y%8)
        p.expect_frame(bytes(expected),frames,timeout=10);os.write(p.fd,b'\x1b');p.wait_text(b'mk61> ',start);calculator(p)
        passed('WBMP direct file opening uses the image viewer')
        for kind,value in (('m61',61),('tbi',17)):
            directory=args.directory+'/'+kind
            assert 'ERROR' not in p.command('mkdir '+directory)
            data=(f'poke X {value}\n' if kind=='m61' else f'10 .X={value}\n20 END\n').encode()
            write_file(p,directory+'/autoexec.'+kind,data)
            calculator(p)
            raw(p,b'\t'+b'\xb5'*20+b'\xb6'*3+b'\r')
            p.expect('SERVICE=BROWSER');raw(p,b'/'+directory.encode()+b'\r')
            p.expect(f'X_RAW=[ {value/10:.7f}  01]')
            calculator(p)
        passed('Explorer entering directories executes autoexec.m61 and autoexec.tbi')
        p.send(0x13);p.attached=False;p.command('uscreen off')
        profile=p.command('prof stop');assert 'core' in profile and 'storage' in profile
        assert re.search(r'core\s+calls=[1-9]',profile) and re.search(r'app\s+calls=[1-9]',profile),profile
        assert 'ERROR' not in p.command('prof save '+args.directory+'/profile.txt')
        assert read_file(p,args.directory+'/profile.txt').startswith(b'PROFILE=STOPPED')
        assert 'WATCHDOG=ON' in p.command('wdog status')
        passed('real timer profiles, saved profile and watchdog telemetry')
        chosen_font=font(p,3,12)
        chosen_key=re.search(r'UI_FONT_KEY=([0-9A-F]+)',chosen_font)[1]
        p.commands();p.write_line('rst now')
        reconnect();p.expect('UI_FONT_FAMILY=3','UI_FONT_SIZE=12','UI_FONT_KEY='+chosen_key)
        passed('external UI font selection and settings survive a real warm reset')
        if args.fault_tests:
            assert 'CRASH=NONE' in p.command('crash show'),'existing crash must be reviewed before injecting another'
            old_crashes=set(re.findall(r'(?m)^f\t\d+(?: B)?\t(crash-picocalc-[^\r\n]+)',p.command('ls /')))
            for name,hang in (('FAULT',False),('HANG',True)):
                binary=build_app(name,'tests/picocalc_fault_probe.c',
                    ['#define PICO_SOFTWARE_HANG '+str(int(hang))])
                path=args.directory+'/'+name+'.APP';write_file(p,path,binary)
                p.open(path);p.wait_text(('INTENTIONAL WATCHDOG' if hang else 'INTENTIONAL HARDFAULT').encode(),p.open_text_start)
                time.sleep(9 if hang else 1);reconnect()
                status=p.status();fault_reports[name]={'status':status,'crash':p.command('crash show')}
                if hang:
                    assert 'BOOT_WATCHDOG=1' in status and 'PREVIOUS_VALID=1' in status,status
                else:
                    crash=fault_reports[name]['crash']
                    assert 'EXCEPTION=HardFault' in crash and 'CRC=OK' in crash and 'R4=0000002C' in crash,crash
                    assert 'ERROR' not in p.command('crash save '+args.directory+'/fault.txt')
                    assert b'EXCEPTION=HardFault' in read_file(p,args.directory+'/fault.txt')
                    new_crashes=set(re.findall(r'(?m)^f\t\d+(?: B)?\t(crash-picocalc-[^\r\n]+)',p.command('ls /')))-old_crashes
                    assert len(new_crashes)==1,('automatic SD crash report missing',new_crashes)
                    auto_path='/'+new_crashes.pop();auto_report=read_file(p,auto_path)
                    assert b'EXCEPTION=HardFault' in auto_report and b'CRC=OK' in auto_report
                    fault_reports[name]['automatic_sd_path']=auto_path
                    fault_reports[name]['automatic_sd_sha256']=hashlib.sha256(auto_report).hexdigest()
                    assert 'ERROR' not in p.command('crash clear')
            passed('intentional ARM HardFault capture, emergency stack, RAM retention, automatic SD report and watchdog hang recovery')
        restore(p,before)
        passed('program memory, five stack values, registers and terminal directory restored')
    finally:
        try:
            calculator(p);p.command('fsput cancel')
            if initial:
                family,size,key=original_font
                font(p,int(family),int(size),key if int(family)==3 else None);calculator(p)
            if before:restore(p,before)
            if created:assert 'ERROR' not in p.command('rm -r '+args.directory,timeout=30)
            p.send(0x13);p.attached=False;p.command('uscreen off')
            final=p.status();transcripts.append(bytes(p.text))
            (args.output/'transcript.bin').write_bytes(b'\n=== RECONNECT ===\n'.join(transcripts))
        finally:p.__exit__(None,None,None)
    report={'passed':True,'recorded_at_utc':datetime.now(timezone.utc).isoformat(),
        'uid':args.uid,'uf2_sha256':build['uf2_sha256'],'cases':cases,'screens':screens,
        'fonts':installed_fonts,'fault_tests':fault_reports,'initial':initial,'final':final,
        'temporary_directory_removed':True,'battery_operation_tested':False}
    (args.output/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print('ALL PicoCalc software parity HIL PASS',flush=True)


if __name__=='__main__':main()
