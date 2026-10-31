#!/usr/bin/env python3
"""Return only the pending original RTC; no ROM, firmware or matrix entry."""
import argparse
from datetime import datetime,timedelta
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sys.path[:0]=[str(HERE),str(ROOT/'tests'),str(ROOT/'tools')]
from session import Hold,sha
from transfer import read_file,write_file

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec)
    sys.modules[name]=m;spec.loader.exec_module(m);return m
ctx=load('memchr_return_context',HERE/'pico-lab-context.py')
envelope=load('memchr_return_envelope',HERE/'pico-envelope.py')
stage=load('memchr_return_stage',HERE/'pico-lab-matrix.py')
SCOPE='MEMCHR_M0_ORIGINAL_CLOCK_RETURN_ONLY'
UID='E6657CD423721C35';THREAD='01a15d77-6fe3-74d3-a025-dbf484687484'
LEASE=ROOT/'.build/picocalc-device-handoff.json'
FAILED=ROOT/'.build/memchr-20261023/m0-hardware-v1'
RTC=ROOT/'.build/picocalc-cold-current-20261023/hardware-v2/rtc-set0'
ORIGINAL=ROOT/'.build/memchr-20261023/m0-lab-packet-v1/original/mk61s-picocalc-pico-h.bin'


class CorrelatedPort(ctx.MatrixPort):
    def command(self,command,timeout=8):
        reply=ctx.RawPort.command(self,command,timeout)
        result,prefix=envelope.correlated(command,reply)
        if prefix:
            ctx.transport.exclusive_bytes(self.evidence/f'async-prefix-{self.command_count:06d}.bin',prefix.encode('cp1251'))
        return result


def binding():
    manifest=RTC/'manifest.json';codec=RTC/'host_codec.py';m=json.loads(manifest.read_text())
    return dict(scope=SCOPE,runner_sha256=sha(Path(__file__).read_bytes()),
        envelope_sha256=sha((HERE/'pico-envelope.py').read_bytes()),
        failed_result_sha256=sha((FAILED/'result.json').read_bytes()),
        fresh_before_sha256=sha((FAILED/'fresh-original-before.json').read_bytes()),
        full_original_sha256=sha((FAILED/'restored-full.bin').read_bytes()),
        rtc_manifest_sha256=sha(manifest.read_bytes()),rtc_codec_sha256=sha(codec.read_bytes()),
        rtc_app_sha256=sha(Path(m['app']['path']).read_bytes()))


def main():
    if not __debug__:raise Hold('Assertions required')
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path);p.add_argument('--lease-sha256')
    p.add_argument('--show-binding',action='store_true');p.add_argument('--execute',action='store_true')
    a=p.parse_args();expected=binding()
    if a.show_binding:print(json.dumps(expected,indent=2));return
    if not a.execute or not a.output or not a.lease_sha256:p.error('Explicit output/active lease/execute required')
    def guard():
        raw=LEASE.read_bytes()
        if sha(raw)!=a.lease_sha256:raise Hold('Recovery lease changed')
        value=json.loads(raw)
        if (value.get('owner'),value.get('owner_thread'),value.get('enabled'),value.get('hardware_window_granted'))!=('memchr',THREAD,True,True):
            raise Hold('No exclusive original-return owner')
        if value.get('memchr_clock_return_approval')!=expected:raise Hold('Wrong exact original-return approval')
    guard()
    failed=json.loads((FAILED/'result.json').read_text());before=json.loads((FAILED/'fresh-original-before.json').read_text())
    sha_original='695c7bcfe4b6c767bc31a34a83f5be7c25fb1935051778cbbd5e0aff5b6bc454'
    if not failed['full_original_return_verified'] or expected['full_original_sha256']!=sha_original:
        raise Hold('No exact current original full readback')
    full=(FAILED/'restored-full.bin').read_bytes();prefix=ORIGINAL.read_bytes()
    if len(full)!=2097152 or full!=(FAILED/'original-a.bin').read_bytes() or full[:len(prefix)]!=prefix:
        raise Hold('Original readback/backup/prefix differs')
    if expected['rtc_manifest_sha256']!='22633189edcd185bf187b1689ae32e9d306dd35c66714fcb9f267ec576625132' or expected['rtc_codec_sha256']!='ad56838ebb3d747a85687b2e4fcfc6b1c1ef95c1af24b8dc02880c024d34bd14' or expected['rtc_app_sha256']!='a47cda18b84bab34aee21f3604b756fe76af196f3444f58200ea524fd700800a':
        raise Hold('Qualified one-purpose RTC inputs differ')
    codec=load('qualified_current_rtc_codec',RTC/'host_codec.py')
    manifest=json.loads((RTC/'manifest.json').read_text());app=Path(manifest['app']['path']).read_bytes()
    output=a.output.resolve();os.umask(0o077)
    if ROOT/'.build' not in output.parents or not output.relative_to(ROOT/'.build').parts[0].startswith('memchr-'):raise Hold('Wrong recovery output')
    output.mkdir(exist_ok=False)
    report=dict(status='RUNNING',scope=SCOPE,pid=os.getpid(),binding=expected,
        reset_requested=False,Flash_write=False,namespace_created=False,RTC_write_attempted=False,serial_closed=True)
    def save():(output/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    save();port=None;error=None
    value=json.loads(LEASE.read_text());folder=output/'cdc';folder.mkdir()
    try:
        guard();ctx.physical_usb(folder,value['port'],value.get('location_id',18022400))
        context=ctx.Context('A7483AE6','C0A51996',754344,guard,before['settings'])
        port=CorrelatedPort(value['port'],folder,context);report['serial_closed']=False;save()
        first=port.status()
        ctx.assert_health(first,'A7483AE6','C0A51996',754344)
        for token in ('TERMINAL=COMMAND','SERVICE=CLOSED','RUN=0 BUSY=0','RUNTIME=NONE','USB_DISK=0','USB_SCREEN=OFF','M61_ACTIVE=0 SUSPENDED=0'):
            if token not in first:raise Hold('Current original foreground changed')
        if ctx.field(first,'BOOTS')!=3 or ctx.field(first,'RESET_REASON',16)!=0x10001:raise Hold('Unexpected reset since verified return')
        identity=port.command('identity')
        if re.findall(r'\bUID=([0-9A-F]{16})\b',identity)!=[UID]:raise Hold('Wrong physical original UID')
        if ctx.canonical('crash show',port.command('crash show'))!='CRASH=NONE':raise Hold('Current original has a fault')
        context.health(port.status())
        current=context.capture(port,'current-before-clock',output)
        for field in ('reg','stk','hout','pwd','alarm','settings'):
            if current[field]!=before[field]:raise Hold('Current original logical/settings changed: '+field)
        roots=context.listing(port,'/');directory='/PCCUR-RTC0';app_path=directory+'/RTC0.APP';request_path=directory+'/request.bin'
        if any(r['path'].casefold()==directory.casefold() for r in roots):raise Hold('RTC0 namespace exists')
        # A748 has no profile-heap command. Its native loader checks calloc
        # before decoding or calling this qualified RTC-only APP.
        context.directory=directory;context.app_path=app_path
        context.state=dict(install_reserved=True,backup_helper_created=False,cleanup_authorized=False,backup_helper_expected={app_path:sha(app)})
        stage.clean(port.command('mkdir "'+directory+'"'));context.state['backup_helper_created']=True
        report.update(namespace_created=True,cleanup_pending=True);save()
        write_file(port,app_path,app)
        origin=before['clock'];ppm=before['settings']['RTC_PPM'];mid=(origin['monotonic_before_ns']+origin['monotonic_after_ns'])/2
        elapsed=(time.monotonic_ns()-mid)/1e9
        if elapsed<0:raise Hold('Host monotonic origin changed')
        rate=46875/((46875*(1000000-ppm)+500000)//1000000)
        calendar=(datetime.fromisoformat(origin['rtc'])+timedelta(seconds=elapsed*rate)).isoformat(sep=' ',timespec='seconds')
        epochs=[codec.epoch(re.fullmatch(r'ALARM [AB] OFF ONCE (20\d\d-\d\d-\d\d \d\d:\d\d:\d\d)',line)[1]) for line in before['alarm'].split('\r\n')]
        session=codec.session_binding(UID,FAILED/'restored-full.bin',sha_original,ORIGINAL,output.name)
        request,nonce=codec.request(calendar,ppm,epochs,1,session)
        context.state['backup_helper_expected'][request_path]=sha(request)
        (output/'request.bin').write_bytes(request);write_file(port,request_path,request)
        report.update(target_calendar=calendar,RTC_write_attempted=True);save()
        port.open(app_path);port.wait_text(b'APP_FLOW_RESULT=',port.app_start,30);port.wait_text(b'mk61> ',port.app_start,10)
        raw=bytes(port.text[port.app_start:]);(output/'provider-raw.bin').write_bytes(raw)
        decoded=codec.decode(raw,nonce,session,1,require_success=True)
        (output/'provider-result.json').write_text(json.dumps(decoded,indent=2)+'\n')
        # Only the qualified successful owned return uses the existing guarded
        # VIEWER exit. There are no initial Escape/reset/normalization keys.
        port.calculator()
        context.state['cleanup_authorized']=True
        for path,data in ((request_path,request),(app_path,app)):
            if read_file(port,path)!=data:raise Hold('RTC0 owned file changed')
            stage.clean(port.command('rm "'+path+'"'))
        if context.listing(port,directory):raise Hold('Unknown RTC0 child retained')
        stage.clean(port.command('rmdir "'+directory+'"'));report['cleanup_pending']=False;save()
        if context.listing(port,'/')!=roots:raise Hold('RTC0 visible root changed')
        after=context.capture(port,'current-after-clock',output);context.compare(before,after)
        report['original_current_data_and_clock_verified']=True
    except BaseException as failure:
        error=failure;report['failure']=repr(failure);save()
    finally:
        if port is not None:
            try:port.close();report['serial_closed']=True
            except BaseException as failure:report['close_failure']=repr(failure);error=error or failure
        holder=subprocess.run(['/usr/sbin/lsof','-nP','-t','--',value['port']],capture_output=True)
        report['holders_after_close']=dict(returncode=holder.returncode,stdout=holder.stdout.decode(errors='replace'),stderr=holder.stderr.decode(errors='replace'))
        report['no_holder']=holder.returncode==1 and not holder.stdout and not holder.stderr
        report['status']='PASS' if error is None and report.get('original_current_data_and_clock_verified') and not report.get('cleanup_pending') and report['serial_closed'] and report['no_holder'] else 'HOLD'
        save()
    print(json.dumps(dict(status=report['status'],output=str(output))),flush=True)
    if error is not None:raise error
    if report['status']!='PASS':raise Hold('Original clock return remains pending')

if __name__=='__main__':main()
