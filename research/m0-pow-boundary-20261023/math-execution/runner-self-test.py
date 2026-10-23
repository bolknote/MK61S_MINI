"""Offline orchestration checks. Mock ports, never a physical device."""
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys

WORK=Path(__file__).resolve().parent
OUT=WORK/'runner-self-test'
OUT.mkdir(exist_ok=True)
spec=importlib.util.spec_from_file_location('v138_math_runner',WORK/'run-math.py')
runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
_,cfg=runner.verify_package()
uid='E6657CD423721C35'
image=bytearray(b'\xff'*(2*1024*1024));base=Path(cfg['firmware_elf']).with_suffix('.bin').read_bytes()
image[:len(base)]=base;addon=(WORK/'reference/reference-sectors.bin').read_bytes();at=cfg['reference_address']-0x10000000
image[at:at+len(addon)]=addon
flash=OUT/'MOCK-postinstall-readback.bin';flash.write_bytes(image)


class MockPort:
    def __init__(self,stop=None,fail=False):
        self.text=bytearray();self.files={};self.directories=set();self.calls=[];self.opens=0;self.stop=stop;self.fail=fail
    def pump(self,*args):pass
    def status(self):
        return 'BUILD=83CF4AC4 RP2040 125 MHz MATH_TEST=OK FIRMWARE_CRC=valid CRASH=NONE RUN=0 BUSY=0 USB_DISK=0 RUNTIME=NONE SERVICE=CLOSED DIRTY=0 TERMINAL=COMMAND SLEEP=0 IP=24\n'
    def command(self,text,timeout=5):
        self.calls.append(text)
        if text=='identity':return 'UID='+uid+'\r\nmk61> '
        if text=='crash show':return 'CRASH none\r\nmk61> '
        if text in ('reg','stk','hout','dump','pwd'):return text+'\r\npreserved\r\nmk61> '
        if text=='ls /':
            return 'ls /\r\n'+''.join('d\t'+d[1:]+'/\r\n' for d in sorted(self.directories))+str(len(self.directories))+' entries.\r\nmk61> '
        if text.startswith('mkdir '):self.directories.add(text[6:]);return 'mk61> '
        if text.startswith('rm -r '):self.directories.remove(text[6:]);return 'mk61> '
        assert text=='open "'+cfg['directory']+'/TIMING.APP"',text
        self.opens+=1
        data=self.files[cfg['directory']+'/INPUT.bin'];h=struct.unpack_from('<8I',data);cases=h[4]
        results=[]
        for index,(_,_,want) in enumerate(struct.iter_unpack('<3Q',data[32:])):
            results.append((want^(1 if self.fail and index==0 else 0),want))
        raw=struct.pack('<10I',0x4d305250,4,h[2],h[3],cases,h[5],12,0,0xffffffff,1000000)
        raw+=struct.pack('<48I',*([200]*12+[210]*12+[100]*24))
        raw+=struct.pack('<96I',*([100]*24+[110]*24+[10]*24+[20]*24))
        raw+=b''.join(struct.pack('<2Q',*pair) for pair in results)
        self.files[cfg['directory']+'/RESULT.bin']=raw
        self.files[cfg['directory']+'/GUARD.bin']=struct.pack('<8I',0x56313338,1,cfg['runtime_table_address'],26,
            cfg['reference_fnv'],125000000,125000000,cfg['footer_crc'])
        if self.stop:self.stop.touch()
        return 'APP_FLOW_RESULT=0\r\nmk61> '


runner.write_file=lambda port,path,data:port.files.__setitem__(path,data)
runner.read_file=lambda port,path:port.files[path]
checks=[]
with (OUT/'progress.log').open('w') as log,contextlib.redirect_stdout(log):
    # The primary matrix and explicit supplementary canary are separate stages.
    for phase,launches in [('matrix',119),('canary',1)]:
        destination=OUT/('complete-'+phase)
        if destination.exists():shutil.rmtree(destination)
        port=MockPort();result=runner.run(port,uid=uid,output=destination,verified_flash=flash,phase=phase,settle_ms=0)
        assert result['status']=='PASS' and port.opens==launches and result['temporary_directory_removed']
        assert result['completed_chunks']==launches and not port.directories
        assert len(result['groups'])==(117 if phase=='matrix' else 0)
        checks.append('complete_'+phase)
    destination=OUT/'resume';stop=OUT/'STOP'
    if destination.exists():shutil.rmtree(destination)
    stop.unlink(missing_ok=True)
    port=MockPort(stop=stop);result=runner.run(port,uid=uid,output=destination,verified_flash=flash,
        stop_file=stop,phase='matrix',settle_ms=0)
    assert result['status']=='PARTIAL_STOPPED' and port.opens==1 and not port.directories
    stop.unlink();port=MockPort()
    result=runner.run(port,uid=uid,output=destination,verified_flash=flash,resume=True,phase='matrix',settle_ms=0)
    assert result['status']=='PASS' and port.opens==118 and result['completed_chunks']==119
    checks.append('cooperative_stop_and_hash_checked_resume')
    destination=OUT/'failure'
    if destination.exists():shutil.rmtree(destination)
    port=MockPort(fail=True);result=runner.run(port,uid=uid,output=destination,verified_flash=flash,phase='canary',settle_ms=0)
    assert result['status']=='FAIL' and port.opens==1 and port.directories
    assert not any(c.startswith('rm ') for c in port.calls)
    assert port.calls[-2:]==['crash show','identity']
    checks.append('failure_saves_evidence_without_cleanup_retry_or_reset')

directory=cfg['directory']
for name in [directory[1:],directory[1:].lower()]:
    for row in ['d\t'+name+'/','f\t0 B\t'+name]:
        try:runner.require_absent_directory(row+'\r\n1 entries.\r\nmk61> ',directory)
        except AssertionError:pass
        else:raise AssertionError('FAT collision accepted')
for bad in ['/','.','..','/../'+directory[1:],directory+'/',directory+'/..',directory+'"',directory+'/child']:
    try:runner.mutation_directory(bad)
    except AssertionError:pass
    else:raise AssertionError(('unsafe mutation directory',bad))
for listing in ['d\t../\r\n1 entries.','d\t./\r\n1 entries.','d\tname/\r\n0 entries.','d\tname/',
                'f\t0 B\tNAME\r\nd\tname/\r\n2 entries.']:
    try:runner.parse_listing(listing)
    except AssertionError:pass
    else:raise AssertionError(('bad listing accepted',listing))
checks.append('structured_FAT_collision_root_dot_dotdot_and_mutation_path_guards')

# A malicious helper cannot run before the pinned byte check, even from a
# different CWD and without the canonical project on the import path.
tamper=OUT/'tamper';tamper.mkdir(exist_ok=True)
shutil.copyfile(WORK/'run-math.py',tamper/'run-math.py')
sentinel=tamper/'SHOULD-NOT-EXIST';sentinel.unlink(missing_ok=True)
(tamper/'frozen_helpers.py').write_text('from pathlib import Path\nPath('+repr(str(sentinel))+').touch()\n')
manifest={'artifacts':[dict(path=str(tamper/'frozen_helpers.py'),sha256=runner.sha(WORK/'frozen_helpers.py'))]}
(tamper/'execution-manifest.json').write_text(json.dumps(manifest))
reply=subprocess.run([sys.executable,str(tamper/'run-math.py')],cwd='/private/tmp',capture_output=True,text=True)
assert reply.returncode!=0 and 'Frozen helper closure changed' in reply.stderr and not sentinel.exists()
checks.append('tampered_project_helper_rejected_before_import')
reply=subprocess.run([sys.executable,str(WORK/'run-math.py')],cwd='/private/tmp',capture_output=True,text=True)
assert reply.returncode==0 and 'PASS_OFFLINE_PACKAGE' in reply.stdout
checks.append('independent_CWD_no_canonical_project_imports')
report=dict(status='PASS_OFFLINE_ORCHESTRATION',checks=checks,runner_sha256=runner.sha(WORK/'run-math.py'),
    helper_sha256=runner.sha(WORK/'frozen_helpers.py'),tested_manifest_sha256=runner.sha(WORK/'execution-manifest.json'),
    mock_APP_launches=240,physical_device_accessed=False,
    scope='Mock transport/results exercise sequencing, cancellation/resume, failure evidence, explicit canary execution, FAT guards and pre-import helper authentication. Actual ARM numerical/APP evidence is separate.')
(OUT/'result.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
