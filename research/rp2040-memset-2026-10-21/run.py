#!/usr/bin/env python3
"""Time the SRAM memset APP on the identified, idle PicoCalc; preserve state."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import re
import statistics
import struct
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tests'))
from hil_picocalc_apps import AppsPort
from hil_c5_stack import read_file,write_file
from hil_usb_disk_transaction import listing_entries

NAMES=['byte','rom','resident','runtime_old','runtime_r3','rom_cached','rom_sram','own16','own64']
class BenchPort(AppsPort):
    def commands(self):
        for _ in range(4):
            if 'TERMINAL=COMMAND' in self.status():return
            os.write(self.fd,b'\x1f');self.pump(.3)
        raise AssertionError('Cannot enter command mode')
    def command(self,command,timeout=5):
        if command.startswith('fsget '):timeout=max(timeout,120)
        self.pump(.002);start=len(self.text);self.write_line(command)
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            self.pump(.002)
            if re.search(rb'(?:^|[\r\n])mk61> ',self.text[start:]):
                return self.text[start:].decode('cp1251','replace')
        raise TimeoutError((command,bytes(self.text[start:])))

def decode(raw,inputs):
    h=struct.unpack_from('<64I',raw)
    assert h[:5]==(0x4D535250,1,len(NAMES),len(inputs),7),h[:16]
    assert not h[6],('Correctness failed',h[:16])
    assert h[14]>=1000000,h[:16]
    assert raw[128:248]==(Path(__file__).parent/'capture/bootrom.bin').read_bytes()[0x26B8:0x2730]
    row_words=4+7*(1+len(NAMES));row_bytes=4*row_words
    assert len(raw)==256+row_bytes*len(inputs)
    rows=[]
    for i,values in enumerate(inputs):
        words=struct.unpack_from('<'+str(row_words)+'I',raw,256+row_bytes*i)
        assert tuple(values)==words[:4]
        control=words[4:11];timing={}
        for f,name in enumerate(NAMES):
            samples=words[11+7*f:18+7*f]
            ns=[(a-b)*1000/values[3] for a,b in zip(samples,control)]
            assert min(ns)>=0,(values,name,ns)
            timing[name]=dict(median_ns=statistics.median(ns),min_ns=min(ns),max_ns=max(ns),
                             raw_batch_us=list(samples),paired_ns=ns)
        rows.append(dict(size=values[0],offset=values[1],value=values[2],loops=values[3],
            control_batch_us=list(control),timings=timing))
    return dict(checks=h[5],rom_version=h[11],rom_address=hex(h[12]),resident_address=hex(h[13]),
        addresses={n:hex(a) for n,a in zip(NAMES,h[16:16+len(NAMES)])},rows=rows)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--port',required=True);p.add_argument('--uid',required=True)
    p.add_argument('--app',type=Path,required=True);p.add_argument('--directory',required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--runs',type=int,default=3)
    p.add_argument('--candidate',choices=('own16','own_fast','sdk'),default='own_fast')
    p.add_argument('--sizes',type=int,nargs='+',default=list(range(18))+[23,24,31,32,33,47,48,63,64,65,95,96,127,128,129,255,256,257,511,512,1024,4096])
    p.add_argument('--alignments',type=int,nargs='+',default=[0,1,2,3])
    p.add_argument('--values',type=lambda s:int(s,0),nargs='+',default=[0,0xA5])
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    NAMES[7]=a.candidate
    assert re.fullmatch(r'/MK61S-MEMSET-[A-Za-z0-9-]+',a.directory)
    assert re.fullmatch(r'[0-9A-F]{16}',a.uid) and 0<a.runs<=10
    cases=[(n,align,value,max(32,131072//(n+16))) for value in a.values for n in a.sizes for align in a.alignments]
    assert all(0<=n<=8192 and 0<=align<=7 and 0<=value<=0xffffffff for n,align,value,_ in cases)
    chunks=[cases[i:i+12] for i in range(0,len(cases),12)]
    report=dict(recorded_at=datetime.now(timezone.utc).isoformat(),status='INCOMPLETE',
        app_sha256=hashlib.sha256(a.app.read_bytes()).hexdigest(),
        method='Physical RP2040 TIMERAWL, 7 rotating-order batches, paired empty call subtraction; IRQs enabled; RAM APP, real resident and ROM; no firmware or clock writes.',
        runs=a.runs,groups=[])
    created=False;failure=None
    with BenchPort(a.port,keyboard_layout=0) as port:
        mode=port.status()
        for token in ('RP2040','RUN=0 BUSY=0','USB_DISK=0','RUNTIME=NONE','SERVICE=CLOSED','DIRTY=0','FIRMWARE_CRC=valid','CRASH=NONE'):
            assert token in mode,(token,mode)
        port.commands();identity=port.command('identity')
        assert 'UID='+a.uid in identity,identity
        awake=port.status()
        assert 'RP2040 125 MHz' in awake and 'POWER_MODE=RUN SYS_HZ=125000000' in awake,awake
        report.update(identity=identity,initial_status=mode,awake_status=awake)
        before={c:port.command(c) for c in ('reg','stk','hout','pwd')}
        root_before=listing_entries(port.command('ls /'))
        assert a.directory[1:]+'/' not in port.command('ls /')
        try:
            answer=port.command('mkdir '+a.directory);assert 'ERROR' not in answer,answer
            created=True;write_file(port,a.directory+'/MEMBENCH.APP',a.app.read_bytes())
            for run in range(a.runs):
                for index,rows in enumerate(chunks):
                    data=struct.pack('<4I',0x4D534554,1,len(rows),int(index==0))
                    data+=b''.join(struct.pack('<4I',*c) for c in rows)+bytes(16*(12-len(rows)))
                    write_file(port,a.directory+'/INPUT.bin',data)
                    answer=port.command('open "'+a.directory+'/MEMBENCH.APP"',timeout=120)
                    assert 'APP_FLOW_RESULT=0' in answer,answer
                    raw=read_file(port,a.directory+'/RESULT.bin')
                    (a.output/f'{run:02d}-{index:02d}.bin').write_bytes(raw)
                    group=decode(raw,rows);group.update(run=run,index=index);report['groups'].append(group)
                    (a.output/'result.json').write_text(json.dumps(report,indent=2)+'\n')
                    print('run',run,'chunk',index+1,'/',len(chunks),'checks',group['checks'],
                        'last',rows[-1][:3],{k:round(v['median_ns'],1) for k,v in group['rows'][-1]['timings'].items()},flush=True)
            report['status']='PASS'
        except BaseException as error:
            failure=repr(error);report['status']='FAIL';report['failure']=failure;raise
        finally:
            port.command('fsput cancel')
            # APP completion leaves its result viewer open until Escape.
            os.write(port.fd,b'\x1e\x1b\x1b\x1f');port.pump(.3)
            if created:
                answer=port.command('rm -r '+a.directory,timeout=30);assert 'ERROR' not in answer,answer
            after={c:port.command(c) for c in before}
            root_after=listing_entries(port.command('ls /'))
            assert before==after,'Calculator data changed'
            assert sorted(root_before)==sorted(root_after),'Root listing changed'
            final=port.status()
            assert re.search(r'BUILD=([0-9A-F]+)',final)[1]==re.search(r'BUILD=([0-9A-F]+)',awake)[1],'Firmware changed'
            assert re.search(r'BOOTS=(\d+)',final)[1]==re.search(r'BOOTS=(\d+)',awake)[1],'Device reset'
            for token in ('FIRMWARE_CRC=valid','CRASH=NONE','RUNTIME=NONE','SERVICE=CLOSED'):
                assert token in final,(token,final)
            if 'SLEEP=1 ' in mode:
                port.command('display off');port.pump(.2)
            if 'TERMINAL=COMMAND' not in mode:
                os.write(port.fd,b'\x1e');port.pump(.2)
            restored=port.status()
            assert re.search(r'TERMINAL=(\w+)',restored)[1]==re.search(r'TERMINAL=(\w+)',mode)[1]
            report.update(final_status=restored,validation_status=final,calculator_data_preserved=True,root_listing_preserved=True,
                temporary_directory_removed=created,terminal_mode_restored=True)
            (a.output/'transcript.bin').write_bytes(port.text)
            (a.output/'result.json').write_text(json.dumps(report,indent=2)+'\n')

if __name__=='__main__':main()
