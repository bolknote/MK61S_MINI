#!/usr/bin/env python3
"""Measure real heap/MSC lifetime across repeated disk sessions without reset.

Only a uniquely identified calculator volume selected by the existing guarded
MSC runner is touched. The qualification APP reads allocator metadata from an exact sealed ELF.
No raw block writes and no production diagnostic hooks are used.
"""
import argparse
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import re
from hil_rtc_alarm import warm_reset
from hil_portable_apps import ScreenPort
from hil_multi_device_identity import Target, parse_identity, require_unchanged
from hil_packbits_firmware import fingerprint
from hil_c5_stack import read_file
from hil_c6_system_bootstrap import write_file
import hil_usb_disk_transaction as msc
APP='/MSCRAM.APP';REPORT='/MSCRPT.txt'

class Port(ScreenPort):
    # warm_reset() can return before the last terminal echo has arrived. Use
    # the streaming reader and an empty-line handshake before a pinned ID;
    # never resend a mutating command to get past a stale response.
    def __init__(self,path):
        super().__init__(path)
        try:
            self.pump(.3);self.write_line('');self.pump(.3)
        except BaseException:
            self.close();raise

def save(path,data):path.write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n')
def remove(port,name):
    response=port.command(f'rm "{name}"',timeout=20)
    assert 'Removed 1 entry.' in response,response

def measure(target,fixture):
    with Port(target.path) as port:
        require_unchanged(target.identity,parse_identity(port.command('identity')))
        response=port.command(f'open "{APP}"',timeout=30)
        assert 'Open failed!' not in response,response
        raw=read_file(port,REPORT).decode('ascii')
        assert raw.startswith('MSCRAM1 ') and raw.endswith('\n'),raw
        words=raw[8:-1].split(' ')
        assert len(words)==9 and all(re.fullmatch(r'[0-9A-F]{8}',v) for v in words),raw
        build,heap,end,prepared,session,workspace,bulk,overlay_capacity,app_capacity=(int(v,16) for v in words)
        # The manager must actually coalesce the released region, rather than
        # merely clear the MSC pointer while leaving an auxiliary fence alive.
        assert overlay_capacity+app_capacity==end-((heap+7)&~7),(overlay_capacity,app_capacity,heap,end)
        assert build==int(fixture['build'],16) and end==fixture['probe']['END']
        assert session==fixture['probe']['SESSION'] and 0x20000000<heap<end
        remove(port,REPORT)
        missing_retained=(0 if workspace else 8192)+(0 if bulk else 8192)
        return dict(heap=heap,pool_end=end,free_above_heap=end-((heap+7)&~7),
                    guaranteed_free=end-((heap+7)&~7)-missing_retained,workspace=workspace,bulk=bulk,
                    prepared=prepared,msc_session=session,overlay_capacity=overlay_capacity,app_capacity=app_capacity)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--port',required=True);p.add_argument('--public-id',required=True)
    p.add_argument('--fixture',type=Path,required=True);p.add_argument('--app',type=Path,required=True)
    p.add_argument('--output-dir',type=Path,required=True);p.add_argument('--cycles',type=int,default=6)
    p.add_argument('--minimum-stack-remaining',type=int,default=12288)
    a=p.parse_args();assert 2<=a.cycles<=20 and a.minimum_stack_remaining>=0
    fixture=json.loads(a.fixture.read_text());app=a.app.read_bytes();out=a.output_dir.resolve();out.mkdir(parents=True)
    if msc.console_locked(msc.system_root()):raise AssertionError('Mac console is locked')
    with Port(a.port) as port:
        identity=parse_identity(port.command('identity'))
        assert identity.public==a.public_id.upper() and identity.build==fixture['build'],identity
        assert identity.profile in msc.USB_DISK_PROFILES
        original=fingerprint(port);logical={c:port.command(c,20) for c in ('reg','stk','dump','pwd')}
        reserved={APP,REPORT,f'/МСК-{identity.short[-4:]}.bin'}
        assert not ({v.casefold() for v in reserved}&{v.casefold() for v in original['files']})
        save(out/'before.json',dict(identity=asdict(identity),files=original,logical=logical))
        write_file(port,APP,app)
        assert read_file(port,APP)==app
        fresh,path,_=warm_reset(port,port.path,identity.public);fresh.close()
    target=Target(path,identity);disk='';runs=[];before=None
    try:
        # Warm APP loader, workspace and NOR read cache before measuring. No
        # MSC reset occurs between these readings and the end of the loop.
        warm=measure(target,fixture);before=measure(target,fixture)
        location=msc.find_cdc_location(msc.usb_tree(),identity)
        baseline=msc.whole_disks();name=f'МСК-{identity.short[-4:]}.bin'
        for cycle in range(a.cycles):
            payload=bytes((i*73+cycle*19)&255 for i in range(4096))
            msc.enter_usb_disk(target)
            disk,info=msc.wait_for_msc_disk(location,identity.usb,baseline,30)
            mount=msc.ensure_mounted(disk,info)
            assert (mount/APP[1:]).read_bytes()==app
            with (mount/name).open('xb') as file:
                file.write(payload);file.flush();os.fsync(file.fileno())
            assert (mount/name).read_bytes()==payload
            msc.run_text(['diskutil','eject',disk],timeout=30);disk=''
            msc.reconnect(target,30)
            with Port(target.path) as port:
                require_unchanged(identity,parse_identity(port.command('identity')))
                assert read_file(port,'/'+name)==payload
                remove(port,'/'+name)
                report=port.command('mpu status',20)
                remaining=msc.require_stack_headroom(report,a.minimum_stack_remaining)
                crash=port.command('crash show',20);assert 'CRASH none' in crash,crash
            row=measure(target,fixture);row.update(cycle=cycle,stack_remaining=remaining,payload_sha256=hashlib.sha256(payload).hexdigest())
            runs.append(row);save(out/'cycles.json',dict(warm=warm,before=before,cycles=runs))
            if fixture['probe']['SESSION']:
                assert row['prepared']==0 and row['guaranteed_free']==before['guaranteed_free'],(before,row)
            else:
                assert row['prepared'] and before['guaranteed_free']-row['guaranteed_free'] in (8264,8272),(before,row)
            print('MSC session',cycle+1,'PASS heap',hex(row['heap']),'prepared',hex(row['prepared']),flush=True)
    finally:
        if disk:msc.run_text(['diskutil','eject',disk],timeout=30);msc.reconnect(target,30)
        with Port(target.path) as port:
            require_unchanged(identity,parse_identity(port.command('identity')))
            entries=msc.listing_entries(port.command('ls /',20))
            for name in sorted(reserved):
                if any(line.casefold().endswith('\t'+name[1:].casefold()) for line in entries):remove(port,name)
            fresh,path,_=warm_reset(port,port.path,identity.public);fresh.close()
        with Port(path) as port:
            require_unchanged(identity,parse_identity(port.command('identity')))
            after=fingerprint(port);assert after==original
            for c,value in logical.items():assert port.command(c,20)==value,c
            df=port.command('df',20);assert 'FIRMWARE CRC state=valid' in df and 'actual=0x'+identity.build in df,df
            assert 'CRASH none' in port.command('crash show',20)
            save(out/'after.json',dict(files=after,df=df))
        save(out/'report.json',dict(status='PASS' if len(runs)==a.cycles else 'INCOMPLETE',fixture=fixture,
             app_sha256=hashlib.sha256(app).hexdigest(),app_bytes=len(app),before=before,cycles=runs,minimum_stack_required=a.minimum_stack_remaining,files_preserved=len(original['files']),reset_between_cycles=False))
if __name__=='__main__':main()
