#!/usr/bin/env python3
"""Execute one frozen, owner-approved, APP-only Classic memchr plan."""
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import re
import struct
import sys
import time
from types import SimpleNamespace

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(HERE));sys.path.insert(0,str(ROOT/'tests'))
import run as bench
from session import ClassicState,Files,Hold,OwnedSession,scan_files,sha
from transfer import read_file,write_file
from hil_system_memory import connect,health,require_empty
from hil_multi_device_identity import parse_identity
from hil_rtc_alarm import canonical_state_reply
from hil_usb_disk_transaction import listing_entries
from check_stm32_vectors import ElfImage
from hil_rtc_alarm import PROMPT

THREAD='01a15d77-6fe3-74d3-a025-dbf484687484'
UID='AEB505B6E0067623'
SERIAL='2068336B4731'
BUILD='3AB3DD45'
DIRECTORY='/MCHR-M01'
APP_SHA='e322183988519bbac254773f9e73b32c03cc930b191d61e7031bc68e25aa2e1a'

def correlate(port):
    # A late prompt from a timed-out command must never acknowledge the next
    # mutation. Send once, require the exact echo, then its following prompt.
    def command(text,timeout=5):
        port.pump(.03);start=len(port.text);port.write_line(text)
        deadline=time.monotonic()+timeout
        echo=re.compile(r'(?m)^(?:[^\r\n]*>\s*)?'+re.escape(text)+r'\r?$')
        while time.monotonic()<deadline:
            port.pump()
            data=bytes(port.text[start:]);reply=data.decode('cp1251','replace')
            match=echo.search(reply)
            if match and PROMPT.search(data):return reply[match.start():]
        raise TimeoutError('No correlated reply for '+repr(text))
    port.command=command

def dependencies():
    paths={Path(__file__).resolve(),Path(bench.old.__file__).resolve()}
    for module in list(sys.modules.values()):
        value=getattr(module,'__file__',None)
        if value:
            path=Path(value).resolve()
            if path.suffix=='.py' and ROOT in path.parents:paths.add(path)
    return {str(path.relative_to(ROOT)):sha(path.read_bytes()) for path in sorted(paths)}

def validate(plan_path,expected_plan_sha,port,lease_path=None):
    raw=plan_path.read_bytes()
    if sha(raw)!=expected_plan_sha:raise Hold('Plan SHA differs from the approved packet')
    plan=json.loads(raw)
    expected=dict(cpu='m4',uid=UID,usb_serial=SERIAL,build=BUILD,directory=DIRECTORY,app_sha256=APP_SHA)
    for key,value in expected.items():
        if plan.get(key)!=value:raise Hold('Plan pin differs: '+key)
    if plan.get('scope')!='APP-only' or os.path.realpath(port)!=os.path.realpath(plan['port']):raise Hold('Wrong operation scope/port')
    if plan['dependencies']!=dependencies():raise Hold('Runner dependency changed since plan freeze')
    app=Path(plan['app']);data=app.read_bytes()
    if sha(data)!=APP_SHA or sha(Path(plan['elf']).read_bytes())!=plan['elf_sha256']:raise Hold('APP or ELF changed')
    manifest=json.loads(Path(plan['manifest']).read_text())
    if manifest['app_sha256']!=APP_SHA or manifest['directory']!=DIRECTORY:raise Hold('APP manifest differs')
    lease_path=lease_path or ROOT/'.build/classic-device-handoff.json'
    lease_raw=lease_path.read_bytes();lease=json.loads(lease_raw)
    grant=dict(plan_sha256=expected_plan_sha,runner_sha256=sha(Path(__file__).read_bytes()),app_sha256=APP_SHA,
        cpu='m4',uid=UID,usb_serial=SERIAL,build=BUILD,directory=DIRECTORY,scope='APP-only')
    if lease.get('owner')!='memchr' or lease.get('owner_thread')!=THREAD or lease.get('state')!='reserved_app_only':raise Hold('No exclusive APP-only lease')
    if lease.get('build')!=BUILD or lease.get('memchr_approval')!=grant:raise Hold('Lease is not bound to the exact approved packet')
    return plan,data,lease_path,sha(lease_raw)

def result_validator(inputs,addresses):
    expected=tuple(tuple(c) for c in inputs);row_words=6+7*9;length=256+4*row_words*len(inputs)
    def recognized(raw):
        if len(raw)!=length:return False
        h=struct.unpack_from('<64I',raw)
        if h[:5]!=(0x4d435250,3,8,len(inputs),7) or h[26]!=1 or h[15]!=96000000 or h[24]!=0x9f8f7ded:return False
        if tuple(h[16:24])!=tuple(addresses) or h[13]!=addresses[5]:return False
        if h[6] and h[14]==0 and not any(raw[256:]):return h[7]<8 and h[8]<=4096 and h[9]<=7
        return all(struct.unpack_from('<6I',raw,256+i*row_words*4)==values for i,values in enumerate(expected))
    return recognized

def main():
    if not __debug__:raise RuntimeError('Run without -O')
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--show-dependencies',action='store_true')
    p.add_argument('--plan',type=Path);p.add_argument('--plan-sha256');p.add_argument('--port');p.add_argument('--output',type=Path)
    a=p.parse_args()
    if a.show_dependencies:print(json.dumps(dependencies(),indent=2));return
    if not all((a.plan,a.plan_sha256,a.port,a.output)):p.error('Pass the approved plan/SHA, port and fresh output directory')
    plan,app,lease_path,lease_sha=validate(a.plan,a.plan_sha256,a.port)
    output=a.output.resolve()
    if ROOT/'.build' not in output.parents or not output.relative_to(ROOT/'.build').parts[0].startswith('memchr-'):
        raise Hold('Use a dedicated memchr output directory')
    output.mkdir(parents=True,exist_ok=False)
    def save(name,value):(output/name).write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n')
    def leased():
        if sha(lease_path.read_bytes())!=lease_sha:raise Hold('Device lease changed during the window')
    report=dict(status='RUNNING',scope='APP-only',recorded_at=datetime.now(timezone.utc).isoformat(),
        plan_sha256=a.plan_sha256,app_sha256=APP_SHA,benchmark_status='INCOMPLETE',groups=[],serial_closed=False,
        filesystem_mutation_attempted=False,cleanup_pending=False,stage='read-only-preflight')
    session=None;failure=None;port=None
    try:
        leased()
        with connect(a.port,BUILD,wait=0) as port:
            correlate(port)
            identity=parse_identity(port.command('identity'))
            if (identity.public,identity.usb,identity.profile,identity.build)!=(UID,SERIAL,'classic-v3-uc1609',BUILD):raise Hold('Device identity differs')
            report['initial_health']=health(port,BUILD)
            state=ClassicState(port,canonical_state_reply,require_empty)
            before_state=state.capture(lambda before:save('calculator-before.json',before))
            session=OwnedSession(DIRECTORY,lambda:scan_files(port,read_file,listing_entries),
                lambda path:read_file(port,path),lambda path,data:(leased(),write_file(port,path,data))[-1],
                lambda command:(leased(),port.command(command,timeout=30))[-1],lambda ledger:save('journal.json',ledger))
            original=session.capture()
            backups=output/'original-files';backups.mkdir()
            for path,data in original.files.items():(backups/(sha(path.encode())+'.bin')).write_bytes(data)
            save('original-files.json',{path:dict(local=sha(path.encode())+'.bin',bytes=len(data),sha256=sha(data)) for path,data in original.files.items()})
            report['before_files']=original.metadata();save('result.json',report)
            try:
                report.update(filesystem_mutation_attempted=True,stage='owned-namespace');save('result.json',report)
                session.create();session.put('CHRBEN.APP',app)
                corpus=SimpleNamespace(**plan['corpus'],cpu='m4')
                rows=bench.cases(corpus);chunks=[rows[i:i+12] for i in range(0,len(rows),12)]
                elf=ElfImage(Path(plan['elf']))
                addresses=[elf.symbols[n]|1 for n in ('baseline','libc_search','byte_search','own4','own16','own64','indirect_search','swar16')]
                for run in range(corpus.runs):
                    for index,inputs in enumerate(chunks):
                        full=bool(corpus.full_hardware_correctness_sweep and run==index==0)
                        data=struct.pack('<4I',0x4d434852,1,len(inputs),int(full))+b''.join(struct.pack('<6I',*row) for row in inputs)+bytes(24*(12-len(inputs)))
                        session.put('INPUT.bin',data)
                        validator=result_validator(inputs,addresses)
                        session.expect_result(validator,dict(run=run,index=index,inputs=inputs,addresses=addresses))
                        leased();port.command('open "'+DIRECTORY+'/CHRBEN.APP"',timeout=180)
                        raw=read_file(port,DIRECTORY+'/RESULT.bin');(output/f'{run:02d}-{index:02d}.bin').write_bytes(raw)
                        session.admit_result(raw)
                        group=bench.decode(raw,inputs,'m4');group.update(run=run,index=index);report['groups'].append(group);save('result.json',report)
                        print('PASS batch',index+1,'/',len(chunks),'checks',group['checks'],flush=True)
                report['benchmark_status']='PASS'
            except BaseException as error:
                failure=error;report.update(benchmark_status='FAIL',benchmark_failure=repr(error))
            finally:
                try:
                    report['cleanup']=session.cleanup(state.preflight_recovery,state.recover)
                    report['final_health']=health(port,BUILD)
                    if parse_identity(port.command('identity'))!=identity:raise Hold('Final identity differs')
                    if report['benchmark_status']=='PASS' and report['cleanup']['files_preserved'] and report['cleanup']['state']['preserved']:
                        report['status']='PASS'
                    else:report['status']='FAIL_RESTORED'
                    report['cleanup_pending']=False
                except BaseException as error:
                    report.update(status='HOLD',cleanup_pending=True,cleanup_failure=repr(error))
                    if failure is None:failure=error
                finally:
                    (output/'transcript.bin').write_bytes(bytes(port.text));save('result.json',report)
    except BaseException as error:
        report.update(status='HOLD',failure=repr(error))
        if failure is None:failure=error
    finally:
        if port is not None:(output/'transcript.bin').write_bytes(bytes(port.text))
        report['serial_closed']=port is None or port.fd<0;save('result.json',report)
    if failure:raise failure
    if report['status']!='PASS':raise Hold('Qualification restored but did not pass; inspect its receipt')

if __name__=='__main__':main()
