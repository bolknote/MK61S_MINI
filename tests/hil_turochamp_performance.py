#!/usr/bin/env python3
"""Time installed Turochamp, book off, using actual CRC-checked screen frames.

No firmware or filesystem writes. Game state/registers change; registers and
cwd are restored. Cold means an optional pinned MCU reset, warm means repeating
the same search without reset. The 24 KiB cache need not contain all modules.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import statistics
import sys
import time

from hil_c6_system_bootstrap import read_file
from hil_multi_device_identity import parse_identity
from hil_portable_apps import ScreenPort
from hil_portable_system_apps import png, registers
from hil_rtc_alarm import Port
from turochamp_package_self_test import decode_font

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from m8_codec import encode


class Font:
    def __init__(self,data):
        self.glyphs=decode_font(data)
        self.patterns={}

    def pattern(self,text):
        if text not in self.patterns:
            glyphs=[self.glyphs[c] for c in encode(text)]
            self.patterns[text]=tuple(tuple((g[y]>>(6-x))&1 for g in glyphs for x in range(7))
                                      for y in range(7))
        return self.patterns[text]

    def matches(self,frame,text,row,col):
        pattern=self.pattern(text)
        x0,y0=2+7*col,7*row
        if x0+len(pattern[0])>190 or y0+7>64:return False
        return all(((frame[(y0+y)//8*192+x0+x]>>((y0+y)%8))&1)==value
                   for y,line in enumerate(pattern) for x,value in enumerate(line))

    def find(self,frame,text):
        for row in range(9):
            for col in range(27-len(encode(text))):
                if self.matches(frame,text,row,col):return row,col
        return None

    def has(self,frame,text):return self.find(frame,text) is not None

    def number_after(self,frame,text):
        found=self.find(frame,text)
        if found is None:return None
        row,col=found;col+=len(encode(text));digits=''
        while col<26:
            digit=next((str(n) for n in range(10) if self.matches(frame,str(n),row,col)),None)
            if digit is None:break
            digits+=digit;col+=1
        return int(digits) if digits else None


class TimedScreenPort(ScreenPort):
    def __init__(self,path):
        super().__init__(path);self.frame_times=[]

    def receive_packet(self,encoded):
        count=len(self.frames)
        super().receive_packet(encoded)
        if len(self.frames)>count:self.frame_times.append(time.monotonic())


def wait_screen(port,font,*labels,timeout=10):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        port.pump(.04)
        if b'Open failed!' in port.text[port.open_text_start:]:raise AssertionError('Turochamp open failed')
        if port.frames:
            for label in labels:
                if font.has(port.frames[-1],label):return label
    raise TimeoutError('Missing Turochamp screen '+repr(labels))


def profile(report):
    frequency=re.search(r'\bclock=(\d+)',report)
    assert frequency,report
    hz=int(frequency.group(1));points={}
    for name,n,minimum,average,maximum,total,own in re.findall(
            r'^PROF (\S+) n=(\d+) min=(\d+) avg=(\d+) max=(\d+) total=(\d+)(?: self=(\d+))?',report,re.M):
        points[name]={'calls':int(n),'total_cycles':int(total),
                      'total_seconds':int(total)/hz if hz else None,
                      'maximum_cycles':int(maximum)}
        if own:
            assert int(own)<=int(total),(name,own,total)
            points[name].update(self_cycles=int(own), self_seconds=int(own)/hz if hz else None)
    cache = [{'id':int(i),'bytes':int(size),'hits':int(hits),'misses':int(misses),'name':name.rstrip('\r')}
             for i,size,hits,misses,name in re.findall(
                 r'^VMCACHE id=(\d+) bytes=(\d+) hits=(\d+) misses=(\d+) name=(.*)$',report,re.M)]
    dropped=re.search(r'^VMCACHE dropped=(\d+)',report,re.M)
    result={'clock_hz':hz,'points':points}
    if dropped:
        result.update(vm_cache=cache,vm_cache_dropped=int(dropped.group(1)))
    return result


def identify(port,args):
    report=port.command('identity');identity=parse_identity(report)
    assert identity.public==args.public_id.upper() and identity.build==args.build_id.upper(),identity
    assert identity.profile=='classic-v3-uc1609',identity
    return report


def stop_game(port):
    for _ in range(2):port.key(39);port.pump(.25)
    response=port.command('reg',timeout=10)
    assert re.search(r'^IP: 0\s*$',response,re.M),response


def completed_board(font, frame):
    # The move appears on the sixth rank while rows seven/eight are still
    # being printed. It is not a completed frame or a safe point to send ESC.
    return (font.has(frame, 'e2-e3') and font.has(frame, 'ВАШ ХОД') and
            all(font.matches(frame, str(rank), rank, 0) for rank in range(1, 9)) and
            font.has(frame, 'С/П МЕНЮ') and font.has(frame, 'ОК ВЫБОР'))


def board_pixels(frame):
    # Disk activity is asynchronous to the completed board. Ignore only its
    # documented x=176..191, y=0..15 rectangle, retaining the full raw capture.
    assert len(frame) == 1536
    pixels = bytearray(frame)
    for page in range(2):
        pixels[page * 192 + 176:(page + 1) * 192] = bytes(16)
    return bytes(pixels)


def search(port,font,args,index,out):
    port.open(args.game_dir+'/autoexec.m61')
    wait_screen(port,font,'ВЫБЕРИТЕ СТОРОНУ')
    for _ in range(4):port.key(36)
    wait_screen(port,font,'ДЕБЮТНАЯ КНИГА')
    if font.has(port.frames[-1],'КНИГА: ВКЛ'):port.key(37)
    wait_screen(port,font,'КНИГА: ВЫКЛ')
    png(port.frames[-1],out/'book-off.png')
    for _ in range(2):port.key(36) # book(4) -> White(0) -> Black(1)
    wait_screen(port,font,'ЧЁРНЫЕ')
    assert 'PROF started' in port.command('prof start')
    cursor=len(port.frames);started=time.monotonic();port.key(37)
    progress=[];seen=set();last_notice=started;finished=None
    while time.monotonic()-started<args.timeout:
        port.pump(.04)
        for frame,stamp in zip(port.frames[cursor:],port.frame_times[cursor:]):
            if font.has(frame,'ДУМАЕТ...'):
                nodes=font.number_after(frame,'ПОЗ ')
                if nodes is not None and nodes not in seen:
                    seen.add(nodes);progress.append({'nodes':nodes,'seconds':stamp-started})
                    if nodes in (0,21,210,420):png(frame,out/(f'nodes-{nodes:04d}.png'))
            elif completed_board(font,frame):
                finished=stamp;png(frame,out/'move-e2-e3.png')
                (out/'move.frame').write_bytes(frame)
                digest=hashlib.sha256(frame).hexdigest()
                board_digest=hashlib.sha256(board_pixels(frame)).hexdigest();break
        cursor=len(port.frames)
        if finished is not None:break
        if time.monotonic()-last_notice>=25:
            last=progress[-1] if progress else {'nodes':'?','seconds':time.monotonic()-started}
            print(f'{args.build_id} run {index}: {last["nodes"]} nodes, {time.monotonic()-started:.1f}s',flush=True)
            last_notice=time.monotonic()
        assert b'Open failed!' not in port.text[port.open_text_start:],port.text[-600:]
    assert finished is not None,('search timeout',progress,port.text[-900:])
    assert progress and progress[-1]['nodes']==420,progress
    counters=port.command('prof stop',timeout=15)
    (out/'prof.txt').write_text(counters)
    elapsed=finished-started
    result={'repeat':index,'temperature':'cold' if index==0 and args.reset_before else 'repeat',
            'seconds':elapsed,'nodes':420,'nodes_per_second':420/elapsed,'move':'e2e3',
            'final_frame_sha256':digest,'complete_eight_rank_board':True,
            'board_frame_sha256':board_digest,
            'progress':progress,'profile':profile(counters)}
    (out/'run.json').write_text(json.dumps(result,indent=2)+'\n')
    print(f'{args.build_id} run {index}: e2-e3 / 420 nodes in {elapsed:.3f}s PASS',flush=True)
    stop_game(port)
    return result


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--port',required=True);ap.add_argument('--public-id',required=True)
    ap.add_argument('--build-id',required=True);ap.add_argument('--output-dir',type=Path,required=True)
    ap.add_argument('--game-dir',default='/Games/Turochamp')
    ap.add_argument('--runs',type=int,default=3);ap.add_argument('--timeout',type=float,default=360)
    ap.add_argument('--reset-before',action='store_true')
    args=ap.parse_args();assert 1<=args.runs<=10
    args.output_dir.mkdir(parents=True,exist_ok=True)
    report={'result':'RUNNING','device':args.public_id,'build':args.build_id,'opening_book':False,
            'level':2,'maximum_depth':8,'runs':[],'filesystem_writes':0}
    font=Font((ROOT/'programs/games/Turochamp/Turochamp.FMK').read_bytes())
    with Port(args.port) as port:
        report['identity_before']=identify(port,args)
        saved,raw=registers(port);(args.output_dir/'registers-before.txt').write_text(raw)
        cwd=port.command('pwd').splitlines()[1].strip()
        # Reading/verifying the installed game is outside measured search time.
        for path in sorted((ROOT/'programs/games/Turochamp').iterdir()):
            if not path.is_file():continue
            payload=path.read_bytes() if path.suffix.lower()=='.fmk' else encode(path.read_text())
            read_file(port,args.game_dir+'/'+path.name,payload)
        report['verified_files']=30
        if args.reset_before:
            port.drain();port.write_line('rst now');time.sleep(.2)
    if args.reset_before:
        # Wait for the same public identity/build, not merely any CDC device.
        deadline=time.monotonic()+20
        while True:
            try:
                with Port(args.port) as port:identify(port,args)
                break
            except (OSError,TimeoutError):
                if time.monotonic()>deadline:raise
                time.sleep(.15)
    with TimedScreenPort(args.port) as port:
        identify(port,args)
        report['health_before']={c:port.command(c,timeout=15) for c in ('df','mpu status','crash show')}
        assert 'CRASH none' in report['health_before']['crash show']
        try:
            port.attach();port.pump(.2)
            for index in range(args.runs):
                out=args.output_dir/f'run-{index}';out.mkdir(exist_ok=True)
                report['runs'].append(search(port,font,args,index,out))
                (args.output_dir/'report.json').write_text(json.dumps(report,indent=2)+'\n')
            assert len({r['board_frame_sha256'] for r in report['runs']})==1
            report['median_seconds']=statistics.median(r['seconds'] for r in report['runs'])
            report['warm_median_seconds']=statistics.median(r['seconds'] for r in report['runs'][1:]) if args.runs>1 else None
            report['result']='PASS'
        except BaseException as error:
            report['result']='FAIL';report['error']=repr(error)
            try:
                if port.attached:stop_game(port)
            except (OSError,AssertionError,TimeoutError) as cleanup:report['stop_error']=repr(cleanup)
            raise
        finally:
            try:
                if port.attached:port.send(0x13);port.attached=False;port.pump(.2)
                port.command('prof stop')
                for name,value in saved.items():port.command(name+'= '+str(value))
                port.command('cd "'+cwd+'"')
                report['health_after']={c:port.command(c,timeout=15) for c in ('identity','df','mpu status','crash show')}
                assert 'state=valid' in report['health_after']['df']
                assert 'layout=ok' in report['health_after']['mpu status']
                assert 'CRASH none' in report['health_after']['crash show']
                report['registers_restored']=True
            except BaseException as cleanup:
                report['cleanup_error']=repr(cleanup);report['result']='FAIL'
            report['frames_crc_verified']=len(port.frames)
            (args.output_dir/'report.json').write_text(json.dumps(report,indent=2)+'\n')
            (args.output_dir/'terminal.txt').write_bytes(port.text)
    assert report['result']=='PASS',report
    print(json.dumps({k:report[k] for k in ('result','build','median_seconds','warm_median_seconds','frames_crc_verified')},indent=2),flush=True)


if __name__=='__main__':main()
