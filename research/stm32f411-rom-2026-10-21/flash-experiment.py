#!/usr/bin/env python3
"""Pinned-device Flash experiment, with double backup and unconditional recovery."""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import time
import zlib

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT/'tests'))
from hil_c5_stack import read_file,write_file
from hil_multi_device_identity import parse_identity
from hil_packbits_firmware import firmware_info,fingerprint
from hil_rtc_alarm import canonical_state_reply
from hil_system_memory import connect,health,require_empty,valid_classic_dfu_listing,flash,SERIAL

BUILD='3AB3DD45'
ORIGINAL_SHA='0acbf033ecf553eed89f33220c5ba04c052394f98577090efbc4b90932c2e635'
IMAGE_BYTES=370064
FLASH_BYTES=524288
REMOTES=('/FLBEN.APP','/FLREAD.APP','/FLCRC.bin','/FLBN0.bin','/FLBN1.bin','/FLBN2.bin')
STATE=('reg','stk','dump','pwd')

def state(port):
    return {c:canonical_state_reply(port.command(c,15)) for c in STATE}

def decode(raw,page,layout):
    h=struct.unpack_from('<20I',raw)
    assert h[:3]==(0x31424C46,1,page)
    assert h[3:8]==(64 if page<2 else 24,152,8,128,9)
    assert h[9]==layout['crc32'] and h[11]==0
    assert list(h[12:])==[e['address'] for e in layout['entries']]
    assert len(raw)==80+h[3]*44
    rows=[]
    for i in range(h[3]):
        n,a,v,*b=struct.unpack_from('<HBB10I',raw,80+i*44)
        control,before,after,*candidates=b
        baseline=((before+after)/2-control)/128
        rows.append({'bytes':n,'alignment':a,'value':v,'baseline_cycles':baseline,
            'before_cycles':(before-control)/128,'after_cycles':(after-control)/128,
            'cycles':{e['name']:(c-control)/128 for e,c in zip(layout['entries'][1:],candidates)},
            'raw_batch_cycles':b})
    return {'page':page,'correctness_checks':h[8],'flash_acr':h[10],'rows':rows}

def remove_temporary(port):
    port.command('fsput cancel')
    current=fingerprint(port)
    for name in REMOTES:
        actual=next((p for p in current['files'] if p.casefold()==name.casefold()),None)
        if actual:
            assert 'Removed 1 entry.' in port.command('rm "'+actual+'"',30)

def proof(port,expected):
    raw=read_file(port,'/FLCRC.bin')
    assert struct.unpack('<3I',raw)==(0x31435246,FLASH_BYTES,zlib.crc32(expected))
    return {'bytes':FLASH_BYTES,'crc32':f'{zlib.crc32(expected):08X}','status':'PASS'}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--port',default='/dev/cu.usbmodem2068336B47311')
    p.add_argument('--dfu-util',type=Path,default=Path('/Users/bolk/Library/Arduino15/packages/STMicroelectronics/tools/STM32Tools/2.4.0/macosx/dfu-util'))
    p.add_argument('--output',type=Path,default=HERE/'flash-hil')
    p.add_argument('--resident-candidate',type=Path,help='Verified prepare-resident.py manifest')
    a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=False)
    build=ROOT/'.build/stm32f411-rom-20261021'
    layout=json.loads((build/'flash-experiment/layout.json').read_text())
    payload=(build/'flash-experiment/payload.bin').read_bytes()
    assert hashlib.sha256(payload).hexdigest()==layout['sha256']
    validation=json.loads((HERE/'flash-validation.json').read_text())
    assert validation['payload_sha256']==layout['sha256'] and len(validation['results'])==8
    assert all(r['status']=='PASS' for r in validation['results'])
    app=(build/'flash-benchmark/FLBEN.APP').read_bytes()
    checker=(build/'flash-check/FLREAD.APP').read_bytes()
    report={'status':'RUNNING','layout':layout,'runs':[],
        'app_sha256':hashlib.sha256(app).hexdigest(),
        'method':'Actual internal Flash and factory ROM; identical short helpers; full dispatcher on every call; 9-round medians of 128 calls minus common empty-call baseline; candidate order rotated; original A/B/A; interrupts enabled; three complete runs.'}
    def save(): (a.output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    backup=None
    entered_dfu=False
    failure=None
    with connect(a.port,BUILD) as port:
        report['identity_before']=asdict(parse_identity(port.command('identity')))
        before_health=health(port,BUILD);require_empty(before_health)
        original_state=state(port);original_files=fingerprint(port)
        assert not any(p.casefold() in {r.casefold() for r in REMOTES} for p in original_files['files'])
        report['files_before']=original_files
        report['state_before']=original_state
        report['health_before']=before_health
        save()
    try:
        print('Preflight PASS; entering pinned ROM DFU for two full Flash reads',flush=True)
        with connect(a.port,BUILD) as port:
            port.drain();port.write_line('dfu');entered_dfu=True;time.sleep(.2)
        deadline=time.monotonic()+20
        while True:
            listing=subprocess.run([str(a.dfu_util),'-l'],capture_output=True,text=True,timeout=8)
            if valid_classic_dfu_listing(listing.stdout,listing.stderr,listing.returncode):break
            if time.monotonic()>=deadline:raise TimeoutError('Pinned complete Classic DFU descriptor absent')
            time.sleep(.3)
        report['dfu_listing']=listing.stdout;save()
        reads=[]
        for name in ('a','b'):
            path=a.output/f'flash-original-{name}.bin'
            result=subprocess.run([str(a.dfu_util),'-d','0483:df11','-S',SERIAL,'-a','0',
                '-s',f'0x08000000:{FLASH_BYTES}','-U',str(path)],capture_output=True,text=True,timeout=120)
            (a.output/f'upload-{name}.txt').write_text(result.stdout+result.stderr)
            assert result.returncode==0,(result.returncode,result.stdout,result.stderr)
            raw=path.read_bytes();assert len(raw)==FLASH_BYTES
            assert hashlib.sha256(raw[:IMAGE_BYTES]).hexdigest()==ORIGINAL_SHA
            reads.append(raw)
            print('Flash backup',name,len(raw),'bytes',hashlib.sha256(raw).hexdigest(),flush=True)
        assert reads[0]==reads[1],'Flash backups differ'
        backup=reads[0]
        original=a.output/'resident-original.bin';original.write_bytes(backup[:IMAGE_BYTES])
        info=firmware_info(original);assert info['build']==BUILD
        report['original_firmware']=info
        report['backup_sha256']=hashlib.sha256(backup).hexdigest()
        offset=layout['base']-0x08000000
        assert offset>=IMAGE_BYTES and backup[offset:offset+len(payload)]==b'\xff'*len(payload),'Extension area is occupied'
        candidate=bytearray(backup);candidate[offset:offset+len(payload)]=payload
        assert candidate[:IMAGE_BYTES]==backup[:IMAGE_BYTES]
        assert candidate[:offset]==backup[:offset] and candidate[offset+len(payload):]==backup[offset+len(payload):]
        target_build=BUILD
        if a.resident_candidate:
            spec=json.loads(a.resident_candidate.read_text())
            proposed=Path(spec['path']).read_bytes()
            assert len(proposed)==FLASH_BYTES and hashlib.sha256(proposed).hexdigest()==spec['full_sha256']
            sealed=firmware_info(Path(spec['resident']['path']))
            assert sealed['build']==spec['build'] and proposed[:IMAGE_BYTES]==Path(sealed['path']).read_bytes()
            changed=[i for i,(x,y) in enumerate(zip(candidate,proposed)) if x!=y]
            assert changed and all(0x8934<=i<0x898C or info['footer']+20<=i<info['footer']+28 for i in changed)
            candidate=bytearray(proposed);target_build=sealed['build']
            report['resident_candidate']=spec
        test_path=a.output/'flash-test.bin';test_path.write_bytes(candidate)
        report['test_sha256']=hashlib.sha256(candidate).hexdigest();save()
        print('Double backup verified; installing experiment, resident build',target_build,flush=True)
        flash(a,{'path':str(test_path),'build':target_build},a.output/'install.json')
        with connect(a.port,target_build) as port:
            assert state(port)==original_state
            write_file(port,REMOTES[0],app)
            assert read_file(port,REMOTES[0])==app
            for run in range(3):
                print('Measuring full Flash memset variants, run',run+1,flush=True)
                launched=port.command('open "'+REMOTES[0]+'"',timeout=180)
                run_dir=a.output/f'run-{run+1}';run_dir.mkdir()
                pages=[]
                for page in range(3):
                    raw=read_file(port,f'/FLBN{page}.bin')
                    (run_dir/f'page-{page}.bin').write_bytes(raw)
                    pages.append(decode(raw,page,layout))
                assert pages[-1]['correctness_checks']==18112
                assert len({(r['bytes'],r['alignment']) for p in pages for r in p['rows']})==152
                report['runs'].append({'launch':launched,'full_flash_readback':proof(port,candidate),'pages':pages})
                save();print('Run',run+1,'PASS: 18112 correctness checks; 152 timing cases',flush=True)
            report['health_experiment']=health(port,target_build)
            (a.output/'terminal.txt').write_bytes(port.text)
    except BaseException as error:
        failure=error;report['error']=repr(error);save()
    finally:
        if entered_dfu and backup is not None:
            print('Restoring the complete original 512 KiB Flash',flush=True)
            try:
                flash(a,{'path':str(a.output/'flash-original-a.bin'),'build':BUILD},a.output/'restore.json')
                with connect(a.port,BUILD) as port:
                    remove_temporary(port)
                    write_file(port,'/FLREAD.APP',checker)
                    report['restore_check_launch']=port.command('open "/FLREAD.APP"',timeout=90)
                    report['full_flash_restored']=proof(port,backup)
                    remove_temporary(port)
                    report['health_after']=health(port,BUILD)
                    report['identity_after']=asdict(parse_identity(port.command('identity')))
                    report['files_unchanged']=fingerprint(port)==original_files
                    report['state_unchanged']=state(port)==original_state
                    assert report['files_unchanged'] and report['state_unchanged']
                    assert report['identity_after']==report['identity_before']
                    assert 'enabled=1 layout=ok' in report['health_after']['mpu status']
                    (a.output/'restore-terminal.txt').write_bytes(port.text)
                print('Full Flash CRC, original files, calculator state, identity and health restored',flush=True)
            except BaseException as error:
                report['recovery_error']=repr(error)
                if failure is None:failure=error
        elif entered_dfu:
            report['recovery_error']='No certified double backup; Flash was not written. Device may remain in ROM DFU.'
        report['status']='PASS' if failure is None and len(report['runs'])==3 and report.get('full_flash_restored',{}).get('status')=='PASS' else 'FAIL'
        save()
    if failure is not None:raise failure
    assert report['status']=='PASS'

if __name__=='__main__':main()
