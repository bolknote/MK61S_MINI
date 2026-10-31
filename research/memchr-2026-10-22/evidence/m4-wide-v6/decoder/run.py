#!/usr/bin/env python3
"""Physical memchr APP benchmark with exclusive access and state/file recovery."""
import argparse
from datetime import datetime,timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import statistics
import struct
import sys

if not __debug__:raise RuntimeError('Run without -O: hardware preservation checks are required')
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT/'tests'))
from transfer import read_file,write_file
from hil_system_memory import connect,health
from hil_packbits_firmware import fingerprint
from hil_multi_device_identity import parse_identity
from hil_rtc_alarm import canonical_state_reply
from hil_usb_disk_transaction import listing_entries
spec=importlib.util.spec_from_file_location('memset_runner',HERE.parent/'rp2040-memset-2026-10-21/run.py')
old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
FLASH_PATTERN=bytearray([0xa5]*4112)
for _value,_at in enumerate((0,1,3,4,7,15,16,63,64,255,256,1023,4095),0x10):FLASH_PATTERN[_at]=_value

def names(cpu):
    return ['baseline','libc','byte','own4','own16','own64','indirect']+(['swar16'] if cpu=='m4' else [])

def prefix(n,offset,value,source,mode):
    if source:
        at=FLASH_PATTERN[offset:offset+n].find(bytes([value&255]))
        return n if at<0 else at+1
    at=n if mode==0 else 0 if mode==1 else min(4,n-1) if mode==2 else n//2 if mode==3 else n-1
    return min(n,at+1)

def decode(raw,inputs,cpu):
    functions=names(cpu);h=struct.unpack_from('<64I',raw)
    assert h[:5]==(0x4D435250,3,len(functions),len(inputs),7),h[:16]
    assert not h[6],('Correctness failed',h[:32])
    assert h[5]>=len(functions)*(len(inputs)+1),'Missing correctness checks'
    assert h[14]>=(200000 if cpu=='m0' else 19200000),h[:16]
    assert h[26]==1,'Indirect column must use the private experimental table'
    assert h[13]==h[21] and h[13]&1,'Indirect and direct own64 must call the same code'
    assert h[15]==(125000000 if cpu=='m0' else 96000000)
    assert h[24]==(0x0a428502 if cpu=='m0' else 0x9f8f7ded)
    row_words=6+7*(1+len(functions));row_bytes=4*row_words
    assert len(raw)==256+row_bytes*len(inputs)
    rows=[]
    for i,values in enumerate(inputs):
        words=struct.unpack_from('<'+str(row_words)+'I',raw,256+row_bytes*i)
        assert tuple(values)==words[:6]
        control=words[6:13];timing={}
        for f,name in enumerate(functions):
            samples=words[13+7*f:20+7*f]
            cycles=[(sample-empty)*(125 if cpu=='m0' else 1)/values[3] for sample,empty in zip(samples,control)]
            timing[name]=dict(median_cycles=statistics.median(cycles),raw=list(samples),paired_cycles=cycles)
        rows.append(dict(size=values[0],offset=values[1],value=values[2],loops=values[3],source=values[4],mode=values[5],
            prefix_bytes=prefix(values[0],values[1],values[2],values[4],values[5]),
            control=list(control),timings=timing))
    return dict(checks=h[5],clock=h[15],rom_code_crc32=f'{h[24]:08X}',payload_crc32=f'{h[25]:08X}',
        indirect_table='APP-local experiment, not public runtime',indirect_target=hex(h[13]),
        rom_version_or_flash_acr=h[11],addresses={n:hex(a) for n,a in zip(functions,h[16:16+len(functions)])},rows=rows)

def cases(args):
    result=[]
    for source in args.sources:
        for n in args.sizes:
            for mode in args.modes if n and not source else [0]:
                for offset in args.alignments:
                    for value in args.values:
                        span=prefix(n,offset,value,source,mode)
                        loops=max(32 if args.cpu=='m0' else 16,(32768 if args.cpu=='m0' else 16384)//(span+16))
                        result.append((n,offset,value&0xffffffff,loops,source,mode))
    assert len(result)==len(set(result)),'Repeated case keys'
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cpu',choices=('m0','m4'),required=True)
    p.add_argument('--port',required=True)
    p.add_argument('--uid',required=True)
    p.add_argument('--build',required=True)
    p.add_argument('--app',type=Path,required=True)
    p.add_argument('--directory',required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--runs',type=int,default=3)
    p.add_argument('--sizes',type=int,nargs='+',default=[0,1,2,3,4,7,8,15,16,17,31,32,33,63,64,65,127,128,129,255,256,257,511,512,1024,4096])
    p.add_argument('--alignments',type=int,nargs='+',default=[0,1,2,3])
    p.add_argument('--values',type=lambda s:int(s,0),nargs='+',default=[0])
    p.add_argument('--sources',type=int,nargs='+',default=[0])
    p.add_argument('--modes',type=int,nargs='+',default=[0,1,2,3,4])
    p.add_argument('--quick',action='store_true',help='Skip the exhaustive hardware correctness sweep after its first recorded PASS')
    a=p.parse_args()
    assert re.fullmatch(r'/MCHR[A-Za-z0-9-]*',a.directory)
    assert re.fullmatch(r'[0-9A-F]{16}',a.uid) and re.fullmatch(r'[0-9A-F]{8}',a.build)
    assert 0<a.runs<=10 and all(0<=n<=4096 for n in a.sizes)
    assert all(0<=x<=7 for x in a.alignments) and all(s in (0,1) for s in a.sources)
    assert all(m in range(5) for m in a.modes)
    rows=cases(a);assert rows
    chunks=[rows[i:i+12] for i in range(0,len(rows),12)]
    app_bytes=a.app.read_bytes()
    manifest_path=a.app.resolve().parents[1]/'benchmark.json'
    manifest=json.loads(manifest_path.read_text())
    app_sha=hashlib.sha256(app_bytes).hexdigest()
    assert manifest['app_sha256']==app_sha and manifest['directory']==a.directory
    assert manifest['target']==('stm32' if a.cpu=='m4' else 'picocalc-pico-h')
    handoff=ROOT/'.build'/('classic-device-handoff.json' if a.cpu=='m4' else 'picocalc-device-handoff.json')
    lease=json.loads(handoff.read_text())
    assert lease['owner']=='memchr','Reserve the shared device handoff before opening serial'
    assert lease['build']==a.build,('Unexpected handoff build',lease['build'],a.build)
    a.output.mkdir(parents=True,exist_ok=False)
    report=dict(recorded_at=datetime.now(timezone.utc).isoformat(),status='INCOMPLETE',cpu=a.cpu,
        app_sha256=app_sha,build=a.build,public_memchr_runtime=False,
        app_manifest=manifest,handoff=lease,
        method='Physical CPU; TIMERAWL us at 125MHz on M0+, DWT cycles at 96MHz on M4; seven rotated batches, paired empty call; IRQs enabled; warm caches.',
        runs=a.runs,groups=[])
    created=False;failure=None
    def save():(a.output/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    with (old.BenchPort(a.port,keyboard_layout=0) if a.cpu=='m0' else connect(a.port,a.build,wait=0)) as port:
        if a.cpu=='m0':
            mode=port.status()
            for token in ('RP2040','RUN=0 BUSY=0','USB_DISK=0','RUNTIME=NONE','SERVICE=CLOSED','DIRTY=0','FIRMWARE_CRC=valid','CRASH=NONE','BUILD='+a.build):assert token in mode,(token,mode)
            port.commands();identity=port.command('identity');assert 'UID='+a.uid in identity,identity
            awake=port.status();assert 'RP2040 125 MHz' in awake and 'POWER_MODE=RUN SYS_HZ=125000000' in awake,awake
            commands=('reg','stk','hout','dump','pwd');canon=lambda x:x
            root_before=listing_entries(port.command('ls /'))
        else:
            identity=parse_identity(port.command('identity'));assert identity.public==a.uid
            mode=awake=health(port,a.build);report['files_before']=fingerprint(port)
            commands=('reg','stk','dump','pwd');canon=canonical_state_reply;root_before=None
        report.update(identity=str(identity),initial_status=mode,awake_status=awake)
        before={c:canon(port.command(c)) for c in commands}
        assert a.directory[1:] not in port.command('ls /')
        report.update(before=before,directory=a.directory,calculator_data_preserved=False,files_preserved=False,temporary_directory_removed=False)
        save()
        try:
            answer=port.command('mkdir '+a.directory);assert 'ERROR' not in answer,answer
            created=True;write_file(port,a.directory+'/CHRBEN.APP',app_bytes)
            for run in range(a.runs):
                for index,inputs in enumerate(chunks):
                    full_check=run==0 and index==0 and not a.quick
                    data=struct.pack('<4I',0x4D434852,1,len(inputs),int(full_check))
                    data+=b''.join(struct.pack('<6I',*c) for c in inputs)+bytes(24*(12-len(inputs)))
                    write_file(port,a.directory+'/INPUT.bin',data)
                    if index==0:print('Starting APP; full correctness sweep:',full_check,flush=True)
                    answer=port.command('open "'+a.directory+'/CHRBEN.APP"',timeout=180)
                    if a.cpu=='m0':assert 'APP_FLOW_RESULT=0' in answer,answer
                    raw=read_file(port,a.directory+'/RESULT.bin');(a.output/f'{run:02d}-{index:02d}.bin').write_bytes(raw)
                    group=decode(raw,inputs,a.cpu);group.update(run=run,index=index);report['groups'].append(group);save()
                    print('run',run,'chunk',index+1,'/',len(chunks),'checks',group['checks'],'last',inputs[-1],
                        {k:round(v['median_cycles'],2) for k,v in group['rows'][-1]['timings'].items()},flush=True)
            report['status']='PASS'
        except BaseException as error:
            failure=error;report.update(status='FAIL',failure=repr(error));raise
        finally:
            report['cleanup_pending']=created
            try:
                port.command('fsput cancel')
                if a.cpu=='m0':os.write(port.fd,b'\x1e\x1b\x1b\x1f');port.pump(.3)
                if created:
                    answer=port.command('rm -r '+a.directory,timeout=30);assert 'ERROR' not in answer,answer
                    report.update(temporary_directory_removed=True,cleanup_pending=False)
                after={c:canon(port.command(c)) for c in before};assert before==after,'Calculator data changed'
                if a.cpu=='m0':
                    assert sorted(root_before)==sorted(listing_entries(port.command('ls /'))),'Root listing changed'
                    final=port.status()
                    for pattern in (r'BUILD=([0-9A-F]+)',r'BOOTS=(\d+)',r'IP=(\d+)'):assert re.search(pattern,final)[1]==re.search(pattern,awake)[1]
                    for token in ('FIRMWARE_CRC=valid','CRASH=NONE','RUNTIME=NONE','SERVICE=CLOSED'):assert token in final,(token,final)
                    if 'SLEEP=1 ' in mode:port.command('display off');port.pump(.2)
                    if 'TERMINAL=COMMAND' not in mode:os.write(port.fd,b'\x1e');port.pump(.2)
                    report['final_status']=port.status()
                else:
                    report['files_after']=fingerprint(port);assert report['files_before']==report['files_after'],'Filesystem changed'
                    assert parse_identity(port.command('identity'))==identity
                    report['final_status']=health(port,a.build)
                report.update(calculator_data_preserved=True,files_preserved=True)
            except BaseException as error:
                report.update(status='FAIL',cleanup_failure=repr(error))
                if failure is None:raise
            finally:
                (a.output/'transcript.bin').write_bytes(port.text);save()

if __name__=='__main__':main()
