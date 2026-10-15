#!/usr/bin/env python3
'''A/B/A of actual resident Flash ZX0 prepare+emit; exact recovery and files.'''
import argparse
import base64
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import shutil
import statistics
import subprocess
import sys
import time
import traceback
import hil_system_memory as system
import hil_zx0_prototypes as native
from hil_packbits_firmware import firmware_info,fingerprint
from hil_multi_device_identity import parse_identity
from hil_c5_stack import read_file
from hil_usb_disk_transaction import listing_entries

ROOT=Path(__file__).resolve().parents[1]
REMOTE='/ZX0FLASH.APP'

def save(path,value):path.write_text(json.dumps(value,indent=2)+'\n')

def default_dfu_util():
    candidates=[shutil.which('dfu-util'),
        str(Path.home()/'Library/Arduino15/packages/arduino/tools/dfu-util/0.11.0-arduino5/dfu-util'),
        str(Path.home()/'Library/Arduino15/packages/STMicroelectronics/tools/STM32Tools/2.4.0/macosx/dfu-util')]
    return next((Path(p) for p in candidates if p and Path(p).is_file() and os.access(p,os.X_OK)),None)

def flash(args,target,output):
    old=None
    try:
        with native.connect(args.port,wait=0) as port:
            old=asdict(parse_identity(port.command('identity')))
            port.drain();port.write_line('dfu');time.sleep(.2)
    except FileNotFoundError:
        pass
    deadline=time.monotonic()+20
    while True:
        # Filtering by the pinned USB serial permits independent Mini DFU work.
        listing=subprocess.run([str(args.dfu_util),'-d','0483:df11','-S',native.SERIAL,'-l'],
            capture_output=True,text=True,timeout=8)
        if system.valid_classic_dfu_listing(listing.stdout,listing.stderr,listing.returncode):break
        if time.monotonic()>=deadline:raise RuntimeError('pinned healthy Classic ROM DFU absent; no write issued')
        time.sleep(.2)
    command=[str(args.dfu_util),'-d','0483:df11','-S',native.SERIAL,'-a','0',
        '-s','0x08000000:leave','-D',target['path']]
    try:
        done=subprocess.run(command,capture_output=True,text=True,timeout=180)
        transfer=dict(returncode=done.returncode,stdout=done.stdout,stderr=done.stderr,timed_out=False)
    except subprocess.TimeoutExpired as error:
        transfer=dict(timed_out=True,stdout=(error.stdout or b'').decode(errors='replace'),
            stderr=(error.stderr or b'').decode(errors='replace'))
    result=dict(status='VERIFYING',old=old,firmware=target,transfer=transfer,
        dfu_listing=dict(stdout=listing.stdout,stderr=listing.stderr))
    save(output,result)
    with native.connect(args.port,target['build']) as port:
        result['identity']=asdict(parse_identity(port.command('identity')))
        result['health']=native.health(port,target['build'])
    result['status']='PASS';save(output,result)
    print('Resident Flash CRC verified',target['build'],flush=True)

def state(port,build):
    result=native.health(port,build)
    result['hout']=port.command('hout',timeout=15)
    result['alarm']=port.command('alarm',timeout=15)
    assert 'RTC ALARM A off' in result['alarm'] and 'RTC ALARM B off' in result['alarm']
    native.require_empty(result)
    assert 'enabled=1 layout=ok' in result['mpu status']
    return result

def summarize(phases):
    values={}
    for name,phase in phases.items():
        groups={}
        for run in phase['results']['ZX0FLASH']['runs']:
            for case in run:
                for row in case['rows']:
                    key=tuple(row[k] for k in ('size','parameter','pattern','alignment'))
                    groups.setdefault(key,[]).append(row['median_cycles'])
        values[name]=groups
    result=[]
    for n,mode,pattern in sorted({k[:3] for k in values['control1']}):
        gains=[];drift=[];cycles=[]
        for align in range(4):
            key=(n,mode,pattern,align)
            first=statistics.median(values['control1'][key]);last=statistics.median(values['control2'][key])
            control=statistics.median(values['control1'][key]+values['control2'][key])
            candidate=statistics.median(values['candidate'][key])
            gains.append(control/candidate);drift.append(last/first)
            cycles.append(dict(control=control,candidate=candidate))
        result.append(dict(size=n,mode=mode,pattern=pattern,aligned_cycles=cycles[0],
            candidate_speedup_range=[min(gains),max(gains)],control2_vs_control1_range=[min(drift),max(drift)]))
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--port',required=True);p.add_argument('--manifest',type=Path,required=True)
    p.add_argument('--recovery-bin',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True)
    p.add_argument('--dfu-util',type=Path,default=default_dfu_util())
    p.add_argument('--runs',type=int,default=3);p.add_argument('--cleanup-only',action='store_true')
    p.add_argument('--phase',action='append',choices=('control1','candidate','control2'),help='run only these explicitly selected phases in order')
    a=p.parse_args();assert 1<=a.runs<=10
    assert a.dfu_util and a.dfu_util.is_file() and os.access(a.dfu_util,os.X_OK),'dfu-util executable required before any device transition'
    requested=a.phase or ['control1','candidate','control2'];assert len(set(requested))==len(requested)
    fixture=json.loads(a.manifest.read_text());recovery=firmware_info(a.recovery_bin)
    app=Path(fixture['app']).read_bytes();assert hashlib.sha256(app).hexdigest()==fixture['app_sha256']
    for profile in fixture['profiles']:
        current=firmware_info(Path(profile['path']))
        assert all(current[k]==profile[k] for k in current),profile['variant']
    out=a.output_dir.resolve()
    if a.cleanup_only:
        before=json.loads((out/'snapshot.json').read_text());assert before['recovery']==recovery
    else:
        out.mkdir(parents=True)
        with native.connect(a.port,recovery['build']) as port:
            identity=asdict(parse_identity(port.command('identity')))
            before=dict(identity=identity,health=state(port,recovery['build']),files=fingerprint(port),recovery=recovery)
        reserved={REMOTE,native.CONTROL}|native.REPORTS
        assert not ({s.casefold() for s in reserved}&{s.casefold() for s in before['files']['files']})
        save(out/'snapshot.json',before)
    phases={};failure=None
    try:
        if not a.cleanup_only:
            for name in requested:
                variant='candidate' if name=='candidate' else 'control'
                folder=out/name;folder.mkdir()
                target=next(x for x in fixture['profiles'] if x['variant']==variant)
                flash(a,target,folder/'flash.json')
                job=dict(fixture['job'],resident_crc=target['build'])
                manifest=dict(jobs=[job],scope=fixture['scope'])
                save(folder/'manifest.json',manifest)
                command=[sys.executable,ROOT/'tests/hil_zx0_prototypes.py','--port',a.port,
                    '--manifest',str(folder/'manifest.json'),'--output-dir',str(folder/'hil'),'--runs',str(a.runs)]
                with (folder/'measurement.log').open('w') as log:subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True)
                report=json.loads((folder/'hil/report.json').read_text());assert report['status']=='PASS'
                assert report['identity']['build']==target['build']
                phases[name]=report
                print(name,target['build'],a.runs,'runs PASS',flush=True)
    except BaseException as error:
        failure=error;traceback.print_exc()
    finally:
        flash(a,recovery,out/'restore-flash.json')
        with native.connect(a.port,recovery['build']) as port:
            entries=listing_entries(port.command('ls /',timeout=20))
            present={'/'+line.split('\t')[-1] for line in entries if line.startswith('f\t')}
            names={name.casefold():name for name in present}
            for remote in sorted(native.REPORTS|{REMOTE,native.CONTROL}):
                actual=names.get(remote.casefold())
                if not actual:continue
                payload=read_file(port,actual)
                if remote==REMOTE:assert payload==app
                elif remote==native.CONTROL:assert len(payload)==1 and b'A'<=payload<=b'Z'
                else:assert len(payload)==512 and base64.b64decode(payload,validate=True)[:4]==b'ZX01'
                response=port.command(f'rm "{actual}"',timeout=20);assert 'Removed 1 entry.' in response,response
            after=dict(health=state(port,recovery['build']),files=fingerprint(port))
            assert after['files']==before['files']
            for command in (*native.STATE_COMMANDS,'hout'):assert after['health'][command].rstrip()==before['health'][command].rstrip(),command
        save(out/'final-restoration.json',dict(status='PASS',**after,recovery=recovery,cdc_closed=True))
        print('EXACT RESTORE PASS / CDC CLOSED',recovery['build'],flush=True)
    if failure:raise failure
    result=dict(status='RESTORED' if a.cleanup_only else 'PASS',fixture=fixture,before=before,after=after,phases=phases,
        summary=summarize(phases) if set(phases)=={'control1','candidate','control2'} else [],complete_matrix=set(phases)=={'control1','candidate','control2'},resident_flash=True,firmware_restored=True,cdc_closed=True)
    save(out/'report.json',result)
if __name__=='__main__':main()
