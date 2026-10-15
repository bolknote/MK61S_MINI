#!/usr/bin/env python3
"""Check real M61/framebuffer lifetimes and APP coexistence on one pinned board.

Opening a new root M61 clears program banks. This runner requires a reset,
zero calculator before any writes, records all files/state and verifies exact
preservation. It never flashes, changes RTC settings or lowers stack budgets.
"""
import argparse,json,re,time
from contextlib import ExitStack
from hil_rtc_alarm import warm_reset
from pathlib import Path
from hil_portable_apps import ScreenPort
from hil_multi_device_identity import parse_identity
from hil_packbits_firmware import fingerprint
from hil_c5_stack import read_file,write_file
APP='/LIFERAM.APP';REPORT='/LIFERPT.txt';SCRIPT='/RAMWATCH.m61'
def zero_calculator(p):
    logical={c:p.command(c,20) for c in ('reg','stk','dump','hout','pwd')}
    values=re.findall(r'(?m)^(?:R[0-9A-E]|X1|[TZYX])\s+=\s+(-?\d\.\d+)\s+(-?\d+)\r?$',logical['reg']+logical['stk'])
    assert len(values)==20 and all(float(x)==0 and not x.startswith('-') and int(e)==0 for x,e in values),'zero calculator required'
    assert 'IP: 0' in logical['reg'] and 'IP =  0' in logical['stk']
    assert not re.search(r'(?m)^\d{4} ',logical['hout']),'all program banks must be empty'
    return logical
def main():
    a=argparse.ArgumentParser(description=__doc__)
    a.add_argument('--port',required=True);a.add_argument('--public-id',required=True)
    a.add_argument('--fixture',type=Path,required=True);a.add_argument('--app',type=Path,required=True)
    a.add_argument('--keyboard-layout',type=int,choices=(0,1),required=True)
    a.add_argument('--output-dir',type=Path,required=True);args=a.parse_args()
    fixture=json.loads(args.fixture.read_text());scoped=bool(fixture['probe']['HEAD'])
    out=args.output_dir;out.mkdir(parents=True,exist_ok=True);rows=[];created=[];complete=False
    with ExitStack() as sessions:
        p=sessions.enter_context(ScreenPort(args.port,keyboard_layout=args.keyboard_layout))
        def restart():
            nonlocal p
            # A cached diagnostic APP at the top would hide the displaced-APP
            # MPU regression. Start each owner-order with a cold APP loader.
            fresh,path,_=warm_reset(p,p.path,args.public_id);fresh.close()
            p=sessions.enter_context(ScreenPort(path,keyboard_layout=args.keyboard_layout))
            p.pump(.3);p.write_line('');p.pump(.3)
            after=parse_identity(p.command('identity',15))
            assert after==identity

        p.pump(.3);p.write_line('');p.pump(.3)
        identity=parse_identity(p.command('identity',15))
        assert identity.public==args.public_id.upper() and identity.build==fixture['build']
        logical=zero_calculator(p);files=fingerprint(p)
        assert not {n.casefold() for n in (APP,REPORT,SCRIPT)}&{n.casefold() for n in files['files']}
        def measure(label,count,bytes_):
            reply=p.command(f'open "{APP}"',30);assert 'Open failed!' not in reply,reply
            raw=read_file(p,REPORT).decode('ascii');assert raw.startswith('LIFERAM1 ') and raw.endswith('\n'),raw
            words=raw[9:-1].split();assert len(words)==8 and all(re.fullmatch('[0-9A-F]{8}',v) for v in words),raw
            build,heap,end,overlay,app,live,rounded,owners=(int(v,16) for v in words)
            assert build==int(fixture['build'],16) and end==fixture['probe']['END']
            assert (live,rounded)==((count,bytes_) if scoped else (0,0)),(label,raw)
            # Independently released high buffers can leave a reusable gap
            # above the lowest live object. OVERLAY is the contiguous prefix,
            # not the sum of every hole in the pool. Idle must coalesce fully.
            gap=end-((heap+7)&~7)-overlay-app-rounded
            assert gap>=0 and (live or gap==0),(label,raw,gap)
            assert 'Removed 1 entry.' in p.command(f'rm "{REPORT}"',20)
            rows.append(dict(label=label,heap=heap,overlay=overlay,app=app,count=live,rounded=rounded,owners=owners,gap=gap))
            print(label,'live',live,'bytes',rounded,flush=True)
        try:
            write_file(p,APP,args.app.read_bytes());created.append(APP)
            write_file(p,SCRIPT,b'bind OK run :help\nret\n:help\nprint "RAM LIFETIME CALLBACK"\nret\n');created.append(SCRIPT)
            measure('idle',0,0)
            for order in (0,1):
                restart()
                if order:p.attach()
                reply=p.command(f'open "{SCRIPT}"',20);assert 'Open failed!' not in reply,reply
                measure(f'{order}-watch',1+order,2112+1536*order)
                if not order:p.attach()
                measure(f'{order}-both',2,3648)
                p.key(37 if args.keyboard_layout else 29);p.pump(.1)
                measure(f'{order}-callback',2,3648)
                if order:
                    p.send(0x13);p.attached=False;p.pump(.2)
                    measure('watch-after-detach',1,2112);p.attach()
                p.key(39);p.pump(.1)
                measure(f'{order}-screen-after-esc',1,1536)
                p.send(0x13);p.attached=False;p.pump(.2)
                measure(f'{order}-idle',0,0)
            complete=True
        finally:
            if p.attached:
                p.key(39);p.send(0x13);p.attached=False;p.pump(.2)
            else:
                # A failed assertion may leave a watcher waiting for ESC.
                # Virtual keys require an attached session.
                p.attach();p.key(39);p.send(0x13);p.attached=False;p.pump(.2)
            p.command('fsput cancel',10)
            current=fingerprint(p)
            for name in (REPORT,*reversed(created)):
                actual=next((n for n in current['files'] if n.casefold()==name.casefold()),None)
                if actual:assert 'Removed 1 entry.' in p.command(f'rm "{actual}"',20)
            assert fingerprint(p)==files,'lifetime test changed original files'
            for c,value in logical.items():assert p.command(c,20)==value,(c,'calculator state changed')
            health={c:p.command(c,20) for c in ('df','crash show','mpu status')}
            assert 'actual=0x'+fixture['build'] in health['df'] and 'FIRMWARE CRC state=valid' in health['df']
            assert 'CRASH none' in health['crash show']
            remaining=re.search(r'watermark_remaining=(\d+)',health['mpu status'])
            assert remaining and int(remaining[1])>=12288,health['mpu status']
            (out/'report.json').write_text(json.dumps(dict(status='PASS' if complete else 'INCOMPLETE',identity=identity.__dict__,scoped=scoped,samples=rows,health=health,preservation='Exact files/program/registers/stack/pwd'),indent=2)+'\n')
    print('Resident lifetimes and APP coexistence PASS',identity.public,flush=True)
if __name__=='__main__':main()
