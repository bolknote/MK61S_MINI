#!/usr/bin/env python3
"""One separately leased Classic shadow FW/Flash experiment with full rollback."""
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

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sys.path.insert(0,str(HERE));sys.path.insert(0,str(ROOT/'tests'))
import wide
from firmware import ClassicFlash,ORIGINAL_SHA,PORT,FULL_SIZE
from session import ClassicState,Files,Hold,OwnedSession,scan_files,sha
from transfer import read_file,write_file
from hil_system_memory import connect,health,require_empty
from hil_multi_device_identity import parse_identity
from hil_rtc_alarm import canonical_state_reply,PROMPT
from hil_usb_disk_transaction import listing_entries

THREAD='01a15d77-6fe3-74d3-a025-dbf484687484'
UID='AEB505B6E0067623';SERIAL='2068336B4731';ORIGINAL_BUILD='3AB3DD45'
SCOPE='firmware-and-payload'

def dependencies():return wide.dependencies(__file__)
def grant(plan,digest):
    return dict(scope=SCOPE,cpu='m4',uid=UID,usb_serial=SERIAL,original_build=ORIGINAL_BUILD,candidate_build=wide.BUILD,
        plan_sha256=digest,runner_sha256=sha(Path(__file__).read_bytes()),original_sha256=ORIGINAL_SHA,candidate_sha256=wide.FULL_SHA,
        apps=[dict(directory=r['directory'],app_sha256=r['app_sha256']) for r in plan['apps']])

def validate_metadata(path,plan,digest):
    packet=path.parent.resolve();seal=json.loads((packet/'sha256.json').read_text())
    files={str(p.relative_to(packet)):p for p in packet.rglob('*') if p.is_file() and p!=packet/'sha256.json'}
    if set(seal)!=set(files):raise Hold('Packet seal does not cover every file exactly')
    for name,expected in seal.items():
        file=files[name]
        if packet not in file.resolve().parents or sha(file.read_bytes())!=expected:raise Hold('Packet sealed file differs: '+name)
    binding=json.loads((packet/'requested-lease-binding.json').read_text())
    if binding!=grant(plan,digest):raise Hold('Requested lease binding is not derived from this plan/runner')

def validate(path,digest,port,lease_path=None):
    if sha(path.read_bytes())!=digest:raise Hold('Wide FW plan changed')
    plan=json.loads(path.read_text())
    if (plan.get('scope'),plan.get('cpu'),plan.get('uid'),plan.get('usb_serial'),plan.get('original_build'),plan.get('candidate_build'))!=(SCOPE,'m4',UID,SERIAL,ORIGINAL_BUILD,wide.BUILD) or os.path.realpath(port)!=PORT:raise Hold('Wrong wide FW scope/device')
    validate_metadata(path,plan,digest)
    if plan['dependencies']!=dependencies():raise Hold('Wide FW dependency changed')
    for name,item in plan['artifacts'].items():
        data=Path(name).read_bytes()
        if len(data)!=item['bytes'] or sha(data)!=item['sha256']:raise Hold('Wide FW artifact differs: '+name)
    for key in ('original_reference','sealed_prefix','resident_elf','candidate','payload','payload_elf','payload_layout','runtime_proof'):
        if plan[key] not in plan['artifacts']:raise Hold('Unpinned wide FW input: '+key)
    if tuple((r['directory'],r['app_sha256'],r['shared'],r['placement']) for r in plan['apps'])!=wide.APPS:raise Hold('Wide FW APP set differs')
    for row in plan['apps']:
        for key in ('app','elf','raw_image','manifest','kernel_layout'):
            if row[key] not in plan['artifacts']:raise Hold('Unpinned APP proof input')
        if sha(Path(row['app']).read_bytes())!=row['app_sha256']:raise Hold('Wide FW APP changed')
        wide.proof(plan,row)
    wide.verify_images(plan)
    lease_path=lease_path or ROOT/'.build/classic-device-handoff.json'
    raw=lease_path.read_bytes();lease=json.loads(raw)
    if (lease.get('owner'),lease.get('owner_thread'),lease.get('state'))!=('memchr',THREAD,'reserved_firmware'):raise Hold('No exclusive FW/rollback lease')
    if lease.get('memchr_approval')!=grant(plan,digest):raise Hold('Wide FW lease binding differs')
    return plan,lease_path,sha(raw)

def correlate(port,leased):
    def command(text,timeout=5):
        leased();port.pump(.03);start=len(port.text);port.write_line(text);deadline=time.monotonic()+timeout
        echo=re.compile(r'(?m)^(?:[^\r\n]*>\s*)?'+re.escape(text)+r'\r?$')
        while time.monotonic()<deadline:
            port.pump();data=bytes(port.text[start:]);reply=data.decode('cp1251','replace');match=echo.search(reply)
            if match and PROMPT.search(data):return reply[match.start():]
        raise TimeoutError('No correlated reply: '+repr(text))
    port.command=command

def main():
    if not __debug__:raise RuntimeError('Run without -O')
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--show-dependencies',action='store_true')
    p.add_argument('--plan',type=Path);p.add_argument('--plan-sha256');p.add_argument('--port');p.add_argument('--output',type=Path)
    a=p.parse_args()
    if a.show_dependencies:print(json.dumps(dependencies(),indent=2));return
    if not all((a.plan,a.plan_sha256,a.port,a.output)):p.error('Pass approved FW plan/digest, exact port, fresh output')
    plan,lease_path,lease_sha=validate(a.plan,a.plan_sha256,a.port)
    output=a.output.resolve()
    if ROOT/'.build' not in output.parents or not output.relative_to(ROOT/'.build').parts[0].startswith('memchr-'):raise Hold('Dedicated memchr output required')
    output.mkdir(parents=True,exist_ok=False)
    def save(name,value):(output/name).write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n')
    report=dict(status='RUNNING',scope=SCOPE,recorded_at=datetime.now(timezone.utc).isoformat(),plan_sha256=a.plan_sha256,
        flash_mutation_attempted=False,firmware_restore_pending=False,cleanup_pending=False,serial_closed=True,apps=[])
    def checkpoint():save('result.json',report)
    def leased():
        if sha(lease_path.read_bytes())!=lease_sha:raise Hold('Wide FW lease changed')
    def known_identity(port,build):
        value=parse_identity(port.command('identity'))
        if (value.public,value.usb,value.profile,value.build)!=(UID,SERIAL,'classic-v3-uc1609',build):raise Hold('Wide FW identity differs')
        return value
    def snapshot(port):return scan_files(port,read_file,listing_entries)
    transcripts=[];original=None;before_state=None;pending_session=None;failure=None;port=None
    flasher=ClassicFlash(leased,output)
    try:
        leased()
        with connect(PORT,ORIGINAL_BUILD,wait=0) as port:
            correlate(port,leased);known_identity(port,ORIGINAL_BUILD);report['initial_health']=health(port,ORIGINAL_BUILD)
            state=ClassicState(port,canonical_state_reply,require_empty);before_state=state.capture(lambda v:save('calculator-before.json',v))
            original=snapshot(port);save('original-files.json',original.metadata())
            if any(directory.casefold() in {p.casefold() for p in [*original.files,*original.directories]} for directory,_,_,_ in wide.APPS):raise Hold('Reserved wide namespace exists')
            backups=output/'original-files';backups.mkdir()
            for path,data in original.files.items():(backups/(sha(path.encode())+'.bin')).write_bytes(data)
            transcripts.append(bytes(port.text))
        checkpoint()
        print('Reading two complete original Flash backups',flush=True)
        backup_a=flasher.upload(ORIGINAL_BUILD,output/'original-a.bin',ORIGINAL_SHA)
        backup_b=flasher.upload(ORIGINAL_BUILD,output/'original-b.bin',ORIGINAL_SHA)
        if backup_a!=backup_b:raise Hold('Fresh full Flash backups disagree')
        report['double_backup_verified']=True;checkpoint()
        # Initial state is already captured and durably backed up before any
        # destructive operation. Recovery permission includes this original.
        report.update(flash_mutation_attempted=True,firmware_restore_pending=True);checkpoint()
        print('Installing and independently reading back exact shadow image',flush=True)
        flasher.download(ORIGINAL_BUILD,plan['candidate'],wide.FULL_SHA,output/'candidate-download.json')
        flasher.upload(wide.BUILD,output/'candidate-readback.bin',wide.FULL_SHA)
        report['candidate_full_readback_verified']=True;checkpoint()
        with connect(PORT,wide.BUILD) as port:
            correlate(port,leased);known_identity(port,wide.BUILD);report['candidate_health']=health(port,wide.BUILD)
            if not re.search(r'\bstatic_end=0x200053F8 guard=0x2001BF00\+256\b',report['candidate_health']['mpu status'],re.I):raise Hold('Shadow RAM geometry differs')
            state=ClassicState(port,canonical_state_reply,require_empty);state.before=before_state
            now=state.preflight_recovery()
            if any(now[k]!=before_state[k] for k in ('reg','stk','dump','hout','pwd')) or snapshot(port)!=original:raise Hold('Shadow boot changed original user state')
            for number,row in enumerate(plan['apps']):
                target=output/('app-'+str(number));target.mkdir()
                result=dict(directory=row['directory'],shared=row['shared'],placement=row['placement'],status='RUNNING',groups=[])
                report['apps'].append(result);checkpoint()
                session=OwnedSession(row['directory'],lambda:snapshot(port),lambda path:read_file(port,path),
                    lambda path,data:(leased(),write_file(port,path,data))[-1],lambda text:port.command(text,timeout=30),
                    lambda ledger:(target/'journal.json').write_text(json.dumps(ledger,indent=2)+'\n'))
                session.capture();pending_session=session;bounded=wide.proof(plan,row)
                (target/'proof.json').write_text(json.dumps(bounded,indent=2)+'\n')
                try:
                    report['cleanup_pending']=True;checkpoint();session.create();session.put('CHRBEN.APP',Path(row['app']).read_bytes())
                    corpus=SimpleNamespace(**row['corpus'],cpu='m4');cases=wide.cases(corpus);chunks=[cases[i:i+7] for i in range(0,len(cases),7)]
                    for index,inputs in enumerate(chunks):
                        full=bool(corpus.full_hardware_correctness_sweep and index==0)
                        data=struct.pack('<4I',0x4d434852,1,len(inputs),int(full))+b''.join(struct.pack('<6I',*r) for r in inputs)+bytes(24*(7-len(inputs)))
                        session.put('INPUT.bin',data);session.expect_result(wide.validator(inputs,bounded,full),dict(index=index,inputs=inputs,full=full))
                        port.command('open "'+row['directory']+'/CHRBEN.APP"',timeout=180)
                        raw=read_file(port,row['directory']+'/RESULT.bin');(target/f'{index:03d}.bin').write_bytes(raw);session.admit_result(raw)
                        group=wide.decode(raw,inputs,bounded,full);group['index']=index;result['groups'].append(group);checkpoint()
                        print('PASS shadow APP',number+1,'batch',index+1,'/',len(chunks),'checks',group['checks'],flush=True)
                    result['benchmark_status']='PASS'
                except BaseException as error:result.update(benchmark_status='FAIL',benchmark_failure=repr(error));failure=error
                finally:
                    try:
                        result['cleanup']=session.cleanup(state.preflight_recovery,state.recover)
                        result['status']='PASS' if result.get('benchmark_status')=='PASS' and result['cleanup']['files_preserved'] and result['cleanup']['state']['preserved'] else 'FAIL_RESTORED'
                        pending_session=None;report['cleanup_pending']=False
                    except BaseException as error:
                        result.update(status='HOLD',cleanup_failure=repr(error));report['cleanup_pending']=True
                        if failure is None:failure=error
                    checkpoint()
                if result['status']!='PASS':raise failure or Hold('Wide benchmark qualification failed')
            transcripts.append(bytes(port.text));report['benchmark_status']='PASS'
    except BaseException as error:
        report.update(status='ROLLBACK_REQUIRED' if report['flash_mutation_attempted'] else 'FAIL',benchmark_status='FAIL',failure=repr(error));failure=error
        # Save the primary failure and active CDC bytes before any rollback
        # can time out, lose the port or report a separate recovery failure.
        try:
            if port is not None:transcripts.append(bytes(port.text))
            (output/'failure-before-rollback-transcript.bin').write_bytes(b'\n'.join(transcripts));checkpoint()
        except BaseException as evidence_error:
            report['failure_evidence_error']=repr(evidence_error)
            try:checkpoint()
            except BaseException:pass
    finally:
        if port is not None:transcripts.append(bytes(port.text))
        if report['flash_mutation_attempted']:
            try:
                print('Restoring and independently reading back all original Flash',flush=True)
                try:
                    with connect(PORT,wait=3) as current:
                        correlate(current,leased);identity=parse_identity(current.command('identity'));current_build=identity.build
                        # connect() pins UID/USB/profile. A corrupt candidate
                        # footer must not block restoration of the saved image.
                    in_dfu=False
                except (OSError,TimeoutError):current_build=None;in_dfu=True
                try:
                    flasher.download(current_build,output/'original-a.bin',ORIGINAL_SHA,output/'restore-download.json',recovery=True,already_in_dfu=in_dfu)
                except BaseException as write_error:
                    report['restore_write_failure']=repr(write_error);checkpoint()
                    if failure is None:failure=write_error
                # Even an ambiguous/failed original write gets a read-only
                # attempt to prove its actual bytes through the pinned ROM.
                flasher.upload(ORIGINAL_BUILD,output/'restored-full.bin',ORIGINAL_SHA,recovery=True,already_in_dfu=True)
                report.update(firmware_restore_pending=False,full_original_flash_verified=True)
            except BaseException as error:
                report.update(status='HOLD',firmware_restore_pending=True,restore_failure=repr(error))
                if failure is None:failure=error
        if original is not None and before_state is not None and not report['firmware_restore_pending']:
            try:
                with connect(PORT,ORIGINAL_BUILD) as port:
                    correlate(port,leased);known_identity(port,ORIGINAL_BUILD)
                    report['final_health_evidence']=flasher.recovery_health(port);checkpoint()
                    state=ClassicState(port,canonical_state_reply,require_empty);state.before=before_state
                    if pending_session is not None:
                        pending_session.scan=lambda:snapshot(port);pending_session.read=lambda path:read_file(port,path)
                        pending_session.write=lambda path,data:(leased(),write_file(port,path,data))[-1]
                        pending_session.command=lambda text:port.command(text,timeout=30)
                        report['pending_namespace_recovery']=pending_session.cleanup(state.preflight_recovery,state.recover)
                        pending_session=None
                    recovery=OwnedSession('/MCHR-ROLLBACK',lambda:snapshot(port),lambda path:read_file(port,path),
                        lambda path,data:(leased(),write_file(port,path,data))[-1],lambda text:port.command(text,timeout=30),
                        lambda ledger:save('final-recovery-journal.json',ledger))
                    recovery.before=original
                    report['restoration']=recovery.cleanup(state.preflight_recovery,state.recover)
                    report['final_health']=health(port,ORIGINAL_BUILD)
                    report['cleanup_pending']=False;transcripts.append(bytes(port.text))
                    preserved=report['restoration']['files_preserved'] and report['restoration']['state']['preserved']
                    report['status']='PASS' if failure is None and report.get('benchmark_status')=='PASS' and preserved else 'FAIL_RESTORED'
            except BaseException as error:
                report.update(status='HOLD',cleanup_pending=True,state_restore_failure=repr(error))
                if failure is None:failure=error
        elif report['status']=='RUNNING':report['status']='FAIL'
        if port is not None:transcripts.append(bytes(port.text))
        report['serial_closed']=port is None or port.fd<0
        (output/'transcript.bin').write_bytes(b'\n'.join(transcripts));checkpoint()
    if failure:raise failure
    if report['status']!='PASS':raise Hold('Wide transaction did not qualify')

if __name__=='__main__':main()
