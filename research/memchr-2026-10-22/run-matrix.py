#!/usr/bin/env python3
"""Run the exact two old-host M4 SRAM matrix APPs and restore each namespace."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import re
import struct
import sys
import time
from types import SimpleNamespace

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sys.path.insert(0,str(HERE));sys.path.insert(0,str(ROOT/'tests'))
import matrix
from session import ClassicState,Hold,OwnedSession,scan_files,sha
from transfer import read_file,write_file
from hil_system_memory import connect,health,require_empty
from hil_multi_device_identity import parse_identity
from hil_rtc_alarm import canonical_state_reply,PROMPT
from hil_usb_disk_transaction import listing_entries

def dependencies():return matrix.dependencies(__file__)

def correlate(port):
    def command(text,timeout=5):
        port.pump(.03);start=len(port.text);port.write_line(text);deadline=time.monotonic()+timeout
        echo=re.compile(r'(?m)^(?:[^\r\n]*>\s*)?'+re.escape(text)+r'\r?$')
        while time.monotonic()<deadline:
            port.pump();data=bytes(port.text[start:]);reply=data.decode('cp1251','replace');match=echo.search(reply)
            if match and PROMPT.search(data):return reply[match.start():]
        raise TimeoutError('No correlated reply for '+repr(text))
    port.command=command

def main():
    if not __debug__:raise RuntimeError('Run without -O')
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--show-dependencies',action='store_true')
    p.add_argument('--plan',type=Path);p.add_argument('--plan-sha256');p.add_argument('--port');p.add_argument('--output',type=Path)
    a=p.parse_args()
    if a.show_dependencies:print(json.dumps(dependencies(),indent=2));return
    if not all((a.plan,a.plan_sha256,a.port,a.output)):p.error('Pass approved matrix plan/digest, port and fresh output')
    plan,lease_path,lease_sha=matrix.validate(a.plan,a.plan_sha256,a.port,__file__)
    output=a.output.resolve()
    if ROOT/'.build' not in output.parents or not output.relative_to(ROOT/'.build').parts[0].startswith('memchr-'):raise Hold('Dedicated memchr output required')
    output.mkdir(parents=True,exist_ok=False)
    def save(path,value):path.write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n')
    def leased():
        if sha(lease_path.read_bytes())!=lease_sha:raise Hold('Matrix lease changed')
    report=dict(status='RUNNING',scope='APP-only',plan_sha256=a.plan_sha256,recorded_at=datetime.now(timezone.utc).isoformat(),
        serial_closed=False,cleanup_pending=False,apps=[])
    port=None;failure=None
    try:
        leased()
        with connect(a.port,matrix.BUILD,wait=0) as port:
            correlate(port);correlated_command=port.command
            def command(text,**kwargs):leased();return correlated_command(text,**kwargs)
            port.command=command
            identity=parse_identity(port.command('identity'))
            if (identity.public,identity.usb,identity.profile,identity.build)!=(matrix.UID,matrix.SERIAL,'classic-v3-uc1609',matrix.BUILD):raise Hold('Wrong matrix device identity')
            report['initial_health']=health(port,matrix.BUILD)
            if not re.search(r'\bstatic_end=0x20005438 guard=0x2001BF00\+256\b',report['initial_health']['mpu status']):raise Hold('Guarded RAM layout differs')
            for number,row in enumerate(plan['apps']):
                target=output/str(number);target.mkdir()
                result=dict(directory=row['directory'],shared=row['shared'],status='RUNNING',groups=[],filesystem_mutation_attempted=False)
                report['apps'].append(result);save(output/'result.json',report)
                state=ClassicState(port,canonical_state_reply,require_empty)
                state.capture(lambda value:save(target/'calculator-before.json',value))
                session=OwnedSession(row['directory'],lambda:scan_files(port,read_file,listing_entries),lambda path:read_file(port,path),
                    lambda path,data:(leased(),write_file(port,path,data))[-1],lambda text:(leased(),port.command(text,timeout=30))[-1],
                    lambda ledger:save(target/'journal.json',ledger))
                original=session.capture();backups=target/'original-files';backups.mkdir()
                for path,data in original.files.items():(backups/(sha(path.encode())+'.bin')).write_bytes(data)
                save(target/'original-files.json',{path:dict(local=sha(path.encode())+'.bin',bytes=len(data),sha256=sha(data)) for path,data in original.files.items()})
                result['before_files']=original.metadata();bounded=matrix.proof(row);save(target/'bounded-relocation-proof.json',bounded)
                try:
                    result['filesystem_mutation_attempted']=True;report['cleanup_pending']=True;save(output/'result.json',report)
                    session.create();session.put('CHRBEN.APP',Path(row['app']).read_bytes())
                    corpus=SimpleNamespace(**row['corpus'],cpu='m4');cases=matrix.bench.cases(corpus);chunks=[cases[i:i+12] for i in range(0,len(cases),12)]
                    for run in range(corpus.runs):
                        for index,inputs in enumerate(chunks):
                            full=bool(corpus.full_hardware_correctness_sweep and run==index==0)
                            payload=struct.pack('<4I',0x4d434852,1,len(inputs),int(full))+b''.join(struct.pack('<6I',*values) for values in inputs)+bytes(24*(12-len(inputs)))
                            session.put('INPUT.bin',payload);admit=matrix.validator(inputs,bounded,full)
                            session.expect_result(admit,dict(run=run,index=index,inputs=inputs,full=full,pointers=bounded['pointers'],sdk_cached_target=bounded['sdk_cached_target']))
                            port.command('open "'+row['directory']+'/CHRBEN.APP"',timeout=180)
                            raw=read_file(port,row['directory']+'/RESULT.bin');(target/f'{run:02d}-{index:02d}.bin').write_bytes(raw);session.admit_result(raw)
                            group=matrix.decode(raw,inputs,bounded,full,row['shared']);group.update(run=run,index=index);result['groups'].append(group);save(output/'result.json',report)
                            print('PASS APP',number+1,'batch',index+1,'/',len(chunks),'checks',group['checks'],flush=True)
                    result['benchmark_status']='PASS'
                except BaseException as error:result.update(benchmark_status='FAIL',benchmark_failure=repr(error));failure=error
                finally:
                    try:
                        result['cleanup']=session.cleanup(state.preflight_recovery,state.recover)
                        result['status']='PASS' if result.get('benchmark_status')=='PASS' and result['cleanup']['files_preserved'] and result['cleanup']['state']['preserved'] else 'FAIL_RESTORED'
                        report['cleanup_pending']=False
                    except BaseException as error:
                        result.update(status='HOLD',cleanup_failure=repr(error));report['cleanup_pending']=True
                        if failure is None:failure=error
                    save(output/'result.json',report)
                if result['status']!='PASS':raise failure or Hold('Matrix qualification failed despite restoration')
            report['final_health']=health(port,matrix.BUILD)
            if parse_identity(port.command('identity'))!=identity:raise Hold('Final matrix identity differs')
            report['status']='PASS'
    except BaseException as error:
        report.update(status='HOLD' if report['cleanup_pending'] else 'FAIL',failure=repr(error));failure=error
    finally:
        if port is not None:(output/'transcript.bin').write_bytes(bytes(port.text))
        report['serial_closed']=port is None or port.fd<0;save(output/'result.json',report)
    if failure:raise failure

if __name__=='__main__':main()
