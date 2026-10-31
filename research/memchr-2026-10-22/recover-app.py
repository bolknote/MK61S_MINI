#!/usr/bin/env python3
"""Recover the exact held Classic V4 APP transaction; never execute an APP."""
import argparse
import copy
from datetime import datetime,timezone
import importlib.util
import json
import os
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(HERE));sys.path.insert(0,str(ROOT/'tests'))
spec=importlib.util.spec_from_file_location('memchr_run_app',HERE/'run-app.py')
app=importlib.util.module_from_spec(spec);spec.loader.exec_module(app)
from session import ClassicState,Files,Hold,OwnedSession,scan_files,sha
from transfer import read_file,write_file
from hil_system_memory import connect,health,require_empty
from hil_multi_device_identity import parse_identity
from hil_rtc_alarm import canonical_state_reply
from hil_usb_disk_transaction import listing_entries

V4_PLAN='e14f1099d3e408caf606e044d5ace5d2473ce86d79b502e37ed1a2f22f00c421'
V4_RUNNER='08503c8cbd1d402ada065545828b0fb08e36bc858a7fcaed2cdf97f664702653'
RAW_SHA='b3a28fc0a8949eb2cdf881606eea749f31f8920262b022a40e177b22d576d996'

def dependencies():
    paths={Path(__file__).resolve(),Path(app.__file__).resolve(),Path(app.bench.old.__file__).resolve()}
    for module in list(sys.modules.values()):
        value=getattr(module,'__file__',None)
        if value:
            path=Path(value).resolve()
            if path.suffix=='.py' and ROOT in path.parents:paths.add(path)
    return {str(path.relative_to(ROOT)):sha(path.read_bytes()) for path in sorted(paths)}

def validate(path,digest,port,lease_path=None):
    raw=path.read_bytes()
    if sha(raw)!=digest:raise Hold('Recovery plan differs')
    plan=json.loads(raw)
    pins=dict(scope='recovery-only',cpu='m4',uid=app.UID,usb_serial=app.SERIAL,build=app.BUILD,directory=app.DIRECTORY,
        app_sha256=app.APP_SHA,raw_sha256=RAW_SHA,parent_plan_sha256=V4_PLAN,parent_runner_sha256=V4_RUNNER)
    if any(plan.get(k)!=v for k,v in pins.items()):raise Hold('Recovery identity/scope pin differs')
    if os.path.realpath(port)!=os.path.realpath(plan['port']):raise Hold('Wrong Classic port')
    if sha(Path(app.__file__).read_bytes())!=V4_RUNNER:raise Hold('Held V4 helper changed')
    if plan['dependencies']!=dependencies():raise Hold('Recovery code dependency changed')
    for name,metadata in plan['artifacts'].items():
        data=(path.parent/name).read_bytes()
        if len(data)!=metadata['bytes'] or sha(data)!=metadata['sha256']:raise Hold('Recovery artifact differs: '+name)
    lease_path=lease_path or ROOT/'.build/classic-device-handoff.json'
    lease_raw=lease_path.read_bytes();lease=json.loads(lease_raw)
    original=dict(plan_sha256=V4_PLAN,runner_sha256=V4_RUNNER,app_sha256=app.APP_SHA,
        cpu='m4',uid=app.UID,usb_serial=app.SERIAL,build=app.BUILD,directory=app.DIRECTORY,scope='APP-only')
    grant=dict(plan_sha256=digest,runner_sha256=sha(Path(__file__).read_bytes()),**pins)
    if lease.get('owner')!='memchr' or lease.get('owner_thread')!=app.THREAD or lease.get('state')!='reserved_app_only':raise Hold('No held owner lease')
    if lease.get('build')!=app.BUILD or lease.get('memchr_approval')!=original or lease.get('memchr_recovery_approval')!=grant:raise Hold('Recovery lease binding differs')
    return plan,lease_path,sha(lease_raw)

def restore_inputs(packet):
    journal=json.loads((packet/'prior/journal.json').read_text())
    saved=json.loads((packet/'prior/original-files.json').read_text())
    files={p:(packet/'prior/original-files'/m['local']).read_bytes() for p,m in saved.items()}
    before=Files(files,set(journal['before']['directories'])).validate()
    if before.metadata()!=journal['before'] or not journal['created'] or journal['directory']!=app.DIRECTORY:raise Hold('Original transaction ownership proof differs')
    state=json.loads((packet/'prior/calculator-before.json').read_text())
    require_empty(state);ClassicState.replay(state['hout'])
    owned={app.DIRECTORY+'/CHRBEN.APP':(packet/'CHRBEN.APP').read_bytes(),
        app.DIRECTORY+'/INPUT.bin':(packet/'INPUT.bin').read_bytes(),
        app.DIRECTORY+'/RESULT.bin':(packet/'prior/00-00.bin').read_bytes()}
    if sha(owned[app.DIRECTORY+'/CHRBEN.APP'])!=app.APP_SHA or sha(owned[app.DIRECTORY+'/RESULT.bin'])!=RAW_SHA:raise Hold('Owned APP/result bytes differ')
    for name in ('CHRBEN.APP','INPUT.bin'):
        data=owned[app.DIRECTORY+'/'+name]
        if dict(bytes=len(data),sha256=sha(data)) not in journal['versions'][app.DIRECTORY+'/'+name]:raise Hold('Known write intent differs')
    return before,state,owned,journal

def main():
    if not __debug__:raise RuntimeError('Run without -O')
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--show-dependencies',action='store_true')
    p.add_argument('--plan',type=Path);p.add_argument('--plan-sha256');p.add_argument('--port');p.add_argument('--output',type=Path)
    a=p.parse_args()
    if a.show_dependencies:print(json.dumps(dependencies(),indent=2));return
    if not all((a.plan,a.plan_sha256,a.port,a.output)):p.error('Pass frozen recovery plan, digest, port, fresh output')
    plan,lease_path,lease_sha=validate(a.plan,a.plan_sha256,a.port)
    before,before_state,owned,journal=restore_inputs(a.plan.parent)
    output=a.output.resolve()
    if ROOT/'.build' not in output.parents or not output.relative_to(ROOT/'.build').parts[0].startswith('memchr-'):raise Hold('Dedicated memchr output required')
    output.mkdir(parents=True,exist_ok=False)
    def save(name,value):(output/name).write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n')
    def leased():
        if sha(lease_path.read_bytes())!=lease_sha:raise Hold('Recovery lease changed')
    report=dict(status='RUNNING',scope='recovery-only',plan_sha256=a.plan_sha256,recorded_at=datetime.now(timezone.utc).isoformat(),
        serial_closed=False,cleanup_pending=True,filesystem_mutation_attempted=False)
    port=None;failure=None
    try:
        leased()
        with connect(a.port,app.BUILD,wait=0) as port:
            app.correlate(port)
            correlated_command=port.command
            def command(text,**kwargs):
                leased();return correlated_command(text,**kwargs)
            port.command=command
            identity=parse_identity(port.command('identity'))
            if (identity.public,identity.usb,identity.profile,identity.build)!=(app.UID,app.SERIAL,'classic-v3-uc1609',app.BUILD):raise Hold('Wrong Classic identity')
            report['initial_health']=health(port,app.BUILD)
            state=ClassicState(port,canonical_state_reply,require_empty);state.before=before_state
            current=scan_files(port,read_file,listing_entries);save('current-files.json',current.metadata())
            # Recovery-only allows exactly the three captured objects, in the
            # original directory, with exact content. It cannot claim a fresh
            # unknown object or admit a new report through a weaker oracle.
            expected={**before.files,**owned}
            if {p.casefold():b for p,b in current.files.items()}!={p.casefold():b for p,b in expected.items()} or current.directories!=before.directories|{app.DIRECTORY}:
                raise Hold('Current files differ from exact original plus three captured objects')
            session=OwnedSession(app.DIRECTORY,lambda:scan_files(port,read_file,listing_entries),lambda path:read_file(port,path),
                lambda path,data:(leased(),write_file(port,path,data))[-1],
                lambda command:(leased(),port.command(command,timeout=30))[-1],lambda ledger:save('recovery-journal.json',ledger))
            session.before=before;session.created=True;session.mkdir_intent=True;session.versions={p:[b] for p,b in owned.items()}
            session.ledger=copy.deepcopy(journal);session.ledger['recovery_parent_plan']=V4_PLAN;session.record()
            current_state=state.preflight_recovery();save('calculator-current.json',current_state)
            report['filesystem_mutation_attempted']=True;save('result.json',report)
            report['cleanup']=session.cleanup(state.preflight_recovery,state.recover)
            report['final_health']=health(port,app.BUILD)
            if parse_identity(port.command('identity'))!=identity:raise Hold('Final identity differs')
            report.update(status='PASS_RESTORED',cleanup_pending=False)
    except BaseException as error:report.update(status='HOLD',failure=repr(error));failure=error
    finally:
        if port is not None:(output/'transcript.bin').write_bytes(bytes(port.text))
        report['serial_closed']=port is None or port.fd<0;save('result.json',report)
    if failure:raise failure

if __name__=='__main__':main()
