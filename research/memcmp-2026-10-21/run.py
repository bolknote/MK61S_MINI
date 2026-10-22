#!/usr/bin/env python3
"""Physical memcmp benchmarks; exclusive serial lock, state/file preservation."""
import argparse
from datetime import datetime,timezone
import hashlib,importlib.util,json,os,re,statistics,struct,sys
from pathlib import Path
if not __debug__:raise RuntimeError("Run without -O: hardware preservation checks are required")
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
NAMES=['baseline','resident','runtime','own4','own16','own64','sdk','byte']
def decode(raw,inputs,cpu):
    h=struct.unpack_from('<64I',raw)
    assert h[:5]==(0x4D435250,2,len(NAMES),len(inputs),7),h[:16]
    assert not h[6],('Correctness failed',h[:16])
    assert h[14]>=(200000 if cpu=='m0' else 19200000),h[:16]
    row_words=6+7*(1+len(NAMES));row_bytes=4*row_words
    assert len(raw)==256+row_bytes*len(inputs)
    rows=[]
    for i,values in enumerate(inputs):
        words=struct.unpack_from('<'+str(row_words)+'I',raw,256+row_bytes*i)
        assert tuple(values)==words[:6]
        control=words[6:13];timing={}
        for f,name in enumerate(NAMES):
            samples=words[13+7*f:20+7*f]
            cycles=[(a-b)*(125 if cpu=='m0' else 1)/values[3] for a,b in zip(samples,control)]
            # Interrupts may hit an empty batch: retain raw data and negative
            # paired outliers, use the median over seven rotated rounds.
            timing[name]=dict(median_cycles=statistics.median(cycles),raw=list(samples),paired_cycles=cycles)
        rows.append(dict(size=values[0],left_offset=values[1],right_offset=values[2],loops=values[3],source=values[4],mode=values[5],control=list(control),timings=timing))
    return dict(checks=h[5],clock=h[15],rom_code_crc32=hex(h[24]),payload_crc32=hex(h[25]),selected_runtime=bool(h[26]),selected_address=hex(h[27]),placement=bool(h[28]),rom_version_or_flash_acr=h[11],rom_memcmp_available=False,resident_address=hex(h[13]),resident_code=raw[128:192].hex(),
        addresses={n:hex(a) for n,a in zip(NAMES,h[16:16+len(NAMES)])},rows=rows)
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cpu',choices=('m0','m4'),required=True)
    p.add_argument('--port',required=True);p.add_argument('--uid',default='E6657CD423721C35')
    p.add_argument('--app',type=Path,required=True);p.add_argument('--directory',required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--runs',type=int,default=3)
    p.add_argument('--sizes',type=int,nargs='+',default=[0,1,2,3,4,7,8,15,16,17,31,32,33,63,64,65,127,128,129,255,256,257,511,512,1024,4096])
    p.add_argument('--alignments',type=int,nargs='+',default=[0,1,2,3])
    p.add_argument('--sources',type=int,nargs='+',default=[0])
    p.add_argument('--modes',type=int,nargs='+',default=[0,1,2,3,4,5])
    p.add_argument('--extra-flash',action='store_true')
    p.add_argument('--selected-runtime',action='store_true')
    p.add_argument('--placement',action='store_true')
    p.add_argument('--quick',action='store_true',help='Only per-case correctness; full sweep already checked in a prior run')
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    if a.cpu=='m4':NAMES[-1]='own_low64'
    if a.placement:
        assert a.cpu=='m0'
        NAMES[-1]='sram'
    if a.selected_runtime:NAMES[4]='selected_runtime';NAMES[5]='selected_body'
    assert re.fullmatch(r'/MCMP[A-Za-z0-9-]*',a.directory)
    assert re.fullmatch(r'[0-9A-F]{16}',a.uid) and 0<a.runs<=10
    def one(n,left,right,source,mode):
        at=n if mode==0 else 0 if mode in (1,5) else min(4,max(0,n-1)) if mode==2 else n//2 if mode==3 else max(0,n-1)
        prefix=0 if mode==5 else n if mode==0 else min(n,at+1)
        loops=max(32 if a.cpu=='m0' else 16,(32768 if a.cpu=='m0' else 16384)//(prefix+16))
        return (n,left,right,loops,source,mode)
    cases=[one(n,left,right,source,mode) for source in a.sources for n in a.sizes for mode in a.modes
           if n or mode in (0,5) for left in a.alignments for right in ([0] if mode==5 else a.alignments)]
    if a.extra_flash:
        cases += [one(n,left,right,source,mode) for source in (1,2) for n in (16,64,4096)
                  for mode in (0,4) for left in a.alignments for right in a.alignments]
    assert len(cases)==len(set(cases)), 'Repeated case keys'
    assert all(0<=n<=4096 and 0<=left<=7 and 0<=right<=7 and source in (0,1,2) and mode in range(6)
               for n,left,right,_,source,mode in cases)
    chunks=[cases[i:i+12] for i in range(0,len(cases),12)]
    report=dict(recorded_at=datetime.now(timezone.utc).isoformat(),status='INCOMPLETE',cpu=a.cpu,app_sha256=hashlib.sha256(a.app.read_bytes()).hexdigest(),
        method='Physical CPU; TIMERAWL us at 125 MHz on M0+, DWT cycles at 96 MHz on M4; 7 rotating-order batches, paired empty call; Loop count based on compared prefix; IRQs enabled; warm caches; instructions in SRAM except real resident or explicit Flash payload.',runs=a.runs,groups=[])
    created=False;failure=None
    def save():
        (a.output/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    with (old.BenchPort(a.port,keyboard_layout=0) if a.cpu=='m0' else connect(a.port,wait=0)) as port:
        if a.cpu=='m0':
            mode=port.status()
            for token in ('RP2040','RUN=0 BUSY=0','USB_DISK=0','RUNTIME=NONE','SERVICE=CLOSED','DIRTY=0','FIRMWARE_CRC=valid','CRASH=NONE'):assert token in mode,(token,mode)
            port.commands();identity=port.command('identity');assert 'UID='+a.uid in identity,identity
            awake=port.status();assert 'RP2040 125 MHz' in awake and 'POWER_MODE=RUN SYS_HZ=125000000' in awake,awake
            commands=('reg','stk','hout','dump','pwd')
            canon=lambda x:x
            root_before=listing_entries(port.command('ls /'))
        else:
            identity=parse_identity(port.command('identity'))
            mode=awake=health(port,identity.build)
            report['files_before']=fingerprint(port)
            commands=('reg','stk','dump','pwd');canon=canonical_state_reply
            root_before=None
        report.update(identity=str(identity),initial_status=mode,awake_status=awake)
        before={c:canon(port.command(c)) for c in commands}
        assert a.directory[1:] not in port.command('ls /')
        # A disconnect can also break cleanup. Persist recovery inputs before
        # the first SD write; the publisher excludes this private device state.
        report.update(before=before,directory=a.directory,calculator_data_preserved=False,
                      files_preserved=False,temporary_directory_removed=False)
        save()
        try:
            answer=port.command('mkdir '+a.directory);assert 'ERROR' not in answer,answer
            created=True;print('State saved; installing benchmark APP',flush=True);write_file(port,a.directory+'/CMPBEN.APP',a.app.read_bytes())
            for run in range(a.runs):
                for index,rows in enumerate(chunks):
                    full_check=run==0 and index==0 and not a.quick
                    data=struct.pack('<4I',0x4D434D50,1,len(rows),int(full_check))
                    data+=b''.join(struct.pack('<6I',*c) for c in rows)+bytes(24*(12-len(rows)))
                    write_file(port,a.directory+'/INPUT.bin',data)
                    if index==0:print('Starting APP; full correctness sweep:',full_check,flush=True)
                    answer=port.command('open "'+a.directory+'/CMPBEN.APP"',timeout=180)
                    if a.cpu=='m0':assert 'APP_FLOW_RESULT=0' in answer,answer
                    raw=read_file(port,a.directory+'/RESULT.bin')
                    (a.output/f'{run:02d}-{index:02d}.bin').write_bytes(raw)
                    group=decode(raw,rows,a.cpu);assert group['selected_runtime']==a.selected_runtime
                    assert group['placement']==a.placement
                    group.update(run=run,index=index);report['groups'].append(group)
                    (a.output/'result.json').write_text(json.dumps(report,indent=2)+'\n')
                    print('run',run,'chunk',index+1,'/',len(chunks),'checks',group['checks'],'last',rows[-1],{k:round(v['median_cycles'],2) for k,v in group['rows'][-1]['timings'].items()},flush=True)
            report['status']='PASS'
        except BaseException as error:
            failure=error
            report['status']='FAIL';report['failure']=repr(error);raise
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
                    report['final_status']=health(port,identity.build)
                report.update(calculator_data_preserved=True,files_preserved=True)
            except BaseException as error:
                report.update(status='FAIL',cleanup_failure=repr(error))
                if failure is None:raise
            finally:
                (a.output/'transcript.bin').write_bytes(port.text)
                save()
if __name__=='__main__':main()
