#!/usr/bin/env python3
"""Qualify the public Pico APP contract and Explorer search/move on its exact UID.

Creates and removes a new microSD directory. Never formats or flashes. Uses
binary press/release events and the reviewed font atlas as an independent oracle.
"""
import argparse
from datetime import datetime,timezone
import hashlib,json,os,re,subprocess,sys,time
from pathlib import Path
from hil_picocalc_software import connect,calculator,raw,restore,font
from hil_c5_stack import read_file,write_file,posix_cksum
from hil_portable_system_apps import png
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from build_picocalc import compiler_bin


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',required=True);parser.add_argument('--uid',required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--firmware-directory',type=Path,default=ROOT/'binary/picocalc-pico-h')
    args=parser.parse_args();assert re.fullmatch(r'[0-9A-F]{16}',args.uid)
    build=json.loads((args.firmware_directory/'manifest.json').read_text())
    assert hashlib.sha256((args.firmware_directory/'mk61s-picocalc-pico-h.uf2').read_bytes()).hexdigest()==build['uf2_sha256']
    args.output.mkdir(parents=True,exist_ok=True)
    directory='/MK61S-CONTRACT-'+time.strftime('%Y%m%d-%H%M%S');work=ROOT/'.build/picocalc-contract-hil';work.mkdir(exist_ok=True)
    wrapper=work/'CONTRACT.cpp';wrapper.write_text(f'#define PICO_CONTRACT_ROOT "{directory}"\n#include "{ROOT}/tests/picocalc_contract_probe.cpp"\n')
    subprocess.run([sys.executable,str(ROOT/'tools/build_portable_app.py'),'--target','picocalc-pico-h','--pico-legacy-display','--name','CONTRACT',
        '--source',str(wrapper),'--shared-runtime','--arm-toolchain-bin',str(compiler_bin(None)),'--output-dir',str(work/'APP')],check=True)
    failure=work/'FAIL.cpp';failure.write_text('int main() { return 42; }\n')
    subprocess.run([sys.executable,str(ROOT/'tools/build_portable_app.py'),'--target','picocalc-pico-h','--pico-legacy-display','--name','FAIL',
        '--source',str(failure),'--shared-runtime','--arm-toolchain-bin',str(compiler_bin(None)),'--output-dir',str(work/'FAIL')],check=True)
    cases=[];screens={};created=False;before=None;original=None;initial=None
    p=connect(args.port,args.uid)
    def passed(text):cases.append(text);print('PASS '+text,flush=True)
    def wait(marker,start,timeout=20):
        p.wait_text(marker.encode(),start,timeout)
        assert b'CONTRACT FAIL' not in p.text[start:],bytes(p.text[start:])
    def picture(name,expected=None):
        if 'USB_SCREEN=ATTACHED' not in p.status():p.attached=False;p.attach_waiting()
        p.pump(.3);start=len(p.frames);p.send(0x16)
        if expected is not None:p.expect_frame(expected,start,timeout=15)
        else:
            deadline=time.monotonic()+10
            while len(p.frames)==start and time.monotonic()<deadline:p.pump(.05)
            assert len(p.frames)>start
        frame=p.frames[-1];png(frame,args.output/(name+'.png'));screens[name]=hashlib.sha256(frame).hexdigest();return frame
    try:
        calculator(p);initial=p.expect('PICO-H '+build['prototype_version'],'BUILD='+build['build_id'].upper(),'SERVICE=CLOSED','DIRTY=0','USB_DISK=0','RUN=0')
        before={cmd:p.command(cmd) for cmd in ('reg','stk','hout','pwd')}
        original=re.search(r'UI_FONT_FAMILY=(\d+) UI_FONT_SIZE=(\d+) UI_FONT_KEY=([0-9A-F]+)',initial).groups()
        assert 'ERROR' not in p.command('mkdir '+directory);created=True
        for name,data in {'input.txt':'Привет, ёж!\n'.encode(),
                          'CONTRACT.APP':(work/'APP/CONTRACT.APP').read_bytes(),
                          'FAIL.APP':(work/'FAIL/FAIL.APP').read_bytes(),
                          'Find07.txt':b'ORIGINAL'}.items():write_file(p,directory+'/'+name,data)
        assert 'ERROR' not in p.command('mkdir '+directory+'/destination')
        logical=bytes((0xC6,))*65534;crc=posix_cksum(logical)
        assert '@MKC:READY 65534' in p.command(f'fsput begin "{directory}/large.txt" 65534 {crc} m8')
        for offset in range(0,len(logical),96):
            n=min(96,len(logical)-offset)
            assert f'@MKC:ACK {offset+n}' in p.command(f'fsput data {offset} '+logical[offset:offset+n].hex())
        assert f'@MKC:DONE 65534 {crc}' in p.command('fsput end',timeout=30)
        p.command('uscreen');p.attach_waiting()
        start=len(p.text);p.open(directory+'/CONTRACT.APP');wait('CONTRACT UI16 READY',start)
        atlas=json.loads((ROOT/'tools/.fmk-font/ui-atlases/pixel-16.json').read_text())
        glyph=next(g for g in atlas['glyphs'] if g['codepoint']==ord('A'))
        expected=bytearray(1536)
        for y,row in enumerate(glyph['rows']):
            for x,value in enumerate(row):
                if value=='1':
                    px=2+glyph['safe_bearing_x']+x;py=4+atlas['ascent']-glyph['bearing_y']+y
                    expected[(py//8)*192+px]|=1<<(py%8)
        baseline=picture('native-UI16',bytes(expected))
        p.key(29);wait('CONTRACT KEYS READY',start)
        assert picture('native-cursor')!=baseline
        p.send(0x30,bytes((23,1)));wait('CONTRACT KEY HELD',start)
        p.send(0x30,bytes((16,1)));p.pump(.1);p.send(0x30,bytes((16,0)))
        wait('CONTRACT OTHER KEY PRESERVED',start)
        p.send(0x30,bytes((23,0)));wait('CONTRACT UI5X8 READY',start)
        mono=picture('native-UI5X8');assert any(mono) and mono!=baseline
        p.key(29);wait('CONTRACT FILENAME READY',start)
        os.write(p.fd,b'\x08\x08\x88Ghbdtn\x88.txt\r')
        wait('CONTRACT API PASS',start);p.wait_text(b'mk61> ',start)
        assert b'APP_FLOW_RESULT=0' in p.text[start:]
        assert read_file(p,directory+'/output.txt')=='Привет, ёж!\n'.encode()
        passed('real ARMv6-M APP: M8/UTF-8 read/write, checked resource offsets, invalid file errors, shared editor INSERT hook and Escape')
        passed('shared native UI renderer: exact reviewed Ark Pixel 16 raster with three rows, cursor, 5x8 and settings restoration')
        passed('binary KEY_EVENT: real down/held/up, immediate latch, causal handoff and preserved unrelated key/release')
        assert b'CONTRACT PWM MASTER/PERCENT/DURATION PASS' in p.text[start:]
        assert b'CONTRACT ASYNC LED PASS' in p.text[start:]
        assert b'CONTRACT LARGE TEXT/EXHAUSTED MEMORY RECOVERY PASS' in p.text[start:]
        pressure=int(re.search(rb'CONTRACT PRESSURE_BYTES=(\d+)',p.text[start:])[1]);assert pressure>=8192
        passed(f'bounded M8 text I/O at 65534 characters while a {pressure//1024}-KiB APP lease is active; exhausted allocation returns and recovers')
        passed('hardware register readback: PWM master/percentage volume, silent notes, duration, asynchronous LED and invalid request rejection')
        passed('native filename prompt: M8 initial name, Cyrillic QWERTY entry and whole-codepoint UTF-8 backspace')
        calculator(p);start=len(p.text);p.open(directory+'/FAIL.APP');p.wait_text(b'mk61> ',start)
        p.expect('SERVICE=MESSAGE','RESULT=[APP returned an error]');raw(p,b'\x1b')
        p.expect('SERVICE=BROWSER');calculator(p);p.expect('SERVICE=CLOSED')
        passed('nonzero APP return: error page releases VIEWER state; Esc returns to Explorer and calculator')
        calculator(p);raw(p,b'\t'+b'\xb5'*20+b'\xb6'*3+b'\r');p.expect('SERVICE=BROWSER')
        raw(p,b'/'+directory.encode()+b'\r');p.expect('SERVICE=BROWSER')
        raw(p,b'\x86find07\r');p.expect('SERVICE=BROWSER')
        picture('explorer-search')
        raw(p,b'\xb6\x87');p.expect('SERVICE=PROMPT')
        raw(p,b'\x08'*256+directory.encode()+b'/destination\r');p.expect('SERVICE=BROWSER')
        p.commands()
        assert read_file(p,directory+'/destination/Find07.txt')==b'ORIGINAL'
        assert 'Find07.txt' not in p.command('ls '+directory)
        passed('Explorer control path: F6 case-insensitive search, F7 destination prompt and FAT move with byte-exact readback')
        raw(p,b'\x1b\x84'+b'\x08'*256+b'\x88`;\x08;\r');p.expect('SERVICE=BROWSER')
        p.commands();assert '\tёж/' in p.command('ls '+directory)
        raw(p,b'\x86~:\r');p.expect('SERVICE=BROWSER');picture('explorer-RU-search')
        raw(p,b'\x1b\x82'+b'\x08'*256+b'\x88russian.txt\r');p.expect('SERVICE=EDITOR')
        raw(p,b'\x88Ghbdtn\x88\x82');p.expect('SERVICE=EDITOR','DIRTY=0')
        p.commands();assert read_file(p,directory+'/russian.txt')=='Привет'.encode()
        passed('Russian QWERTY: F8 layout, Cyrillic mkdir/search and UTF-8 editor save/readback')
        calculator(p);raw(p,b'\t'+b'\xb5'*20+b'\xb6'*3+b'\r');p.expect('SERVICE=BROWSER')
        raw(p,b'/'+directory.encode()+b'/large.txt\r')
        p.expect('SERVICE=EDITOR','SOURCE=65534 DIRTY=0')
        raw(p,b'\x82');p.expect('SERVICE=EDITOR','SOURCE=65534 DIRTY=0')
        p.commands();assert read_file(p,directory+'/large.txt',m8=True)==logical
        assert re.search(r'(?m)^f\t131068(?: B)?\tlarge\.txt\r?$',p.command('ls '+directory))
        calculator(p);raw(p,b'\t'+b'\xb5'*20+b'\xb6'*3+b'\r');p.expect('SERVICE=BROWSER')
        raw(p,b'/'+directory.encode()+b'/input.txt\r');p.expect('SERVICE=EDITOR','SOURCE=12 DIRTY=0')
        passed('maximum-size editor: opens and saves 65534 M8 characters / 131068 UTF-8 bytes in real RP2040 memory')
        restore(p,before)
    finally:
        try:
            for scan in (23,16,29,39):p.send(0x30,bytes((scan,0)))
            calculator(p);p.command('fsput cancel')
            if original:
                family,size,key=original;font(p,int(family),int(size),key if int(family)==3 else None);calculator(p)
            if before:restore(p,before)
            if created:assert 'ERROR' not in p.command('rm -r '+directory,timeout=30)
            p.send(0x13);p.attached=False;p.command('uscreen off');final=p.status()
            (args.output/'transcript.bin').write_bytes(p.text)
        finally:
            (args.output/'transcript.bin').write_bytes(p.text)
            p.__exit__(None,None,None)
    report={'passed':True,'recorded_at_utc':datetime.now(timezone.utc).isoformat(),'uid':args.uid,
        'uf2_sha256':build['uf2_sha256'],'cases':cases,'screens':screens,'initial':initial,'final':final,
        'temporary_directory_removed':True,'calculator_state_restored':True}
    (args.output/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print('ALL PicoCalc public contract HIL PASS',flush=True)


if __name__=='__main__':main()
