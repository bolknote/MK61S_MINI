#!/usr/bin/env python3
"""One exact memchr M0 laboratory run; requires the coordinator's active grant."""
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
from session import Hold,sha,ClassicState
from transfer import read_file,write_file

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);sys.modules[name]=module
    spec.loader.exec_module(module);return module

ctx=load('memchr_lab_context',HERE/'pico-lab-context.py')
envelope=load('memchr_lab_envelope',HERE/'pico-envelope.py')
matrix=load('memchr_lab_matrix',HERE/'pico-lab-matrix.py')
oracle=load('memchr_pico_oracle',HERE/'pico-wide.py')
native=load('memchr_pico_native',HERE/'pico-native-proof.py')
images=load('memchr_pico_images',HERE/'pico-image.py')
rom=load('memchr_pico_rom',HERE/'pico-transport.py')
THREAD='01a15d77-6fe3-74d3-a025-dbf484687484'
UID='E6657CD423721C35'
LEASE=ROOT/'.build/picocalc-device-handoff.json'
SCOPE='MEMCHR_M0_LAB_MATRIX_AND_EXACT_RETURN'


class DiagnosticContext(ctx.Context):
    def heap(self,port):
        command='prof heap'
        body=ctx.canonical(command,port.command(command))
        keys=('HEAP_BYTES','HEAP_USED','HEAP_FREE','HEAP_ARENA','HEAP_FREE_BLOCKS','HEAP_TOP')
        return {name:ctx.field(body,name) for name in keys}


class OriginalReturnContext(ctx.Context):
    """Only an independently verified original return can use this context."""
    captured_incident=False

    def health(self,status,candidate=False,service='CLOSED'):
        validation=status
        if self.captured_incident:
            # The actual record/status stay intact. Only this trusted-original
            # recovery admission treats the captured retained record as history.
            validation=re.sub(r'\bCRASH=AVAILABLE\b','CRASH=NONE',status)
        return super().health(validation,candidate,service)


class CorrelatedPort(ctx.MatrixPort):
    def allowed_command(self,command):
        if command=='prof heap':
            self.t.guard()
            ctx.require(not self.app_inflight,'Command into running APP')
            return
        return super().allowed_command(command)

    def command(self,command,timeout=8):
        reply=ctx.RawPort.command(self,command,timeout)
        result,prefix=envelope.correlated(command,reply)
        if prefix:
            ctx.transport.exclusive_bytes(self.evidence/f'async-prefix-{self.command_count:06d}.bin',prefix.encode('cp1251'))
        return result


class OriginalReturnPort(CorrelatedPort):
    def status(self,timeout=8):
        start=len(self.text);self.send_bytes(b'\x05','read-original-return-status')
        deadline=time.monotonic()+timeout
        while True:
            wire=bytes(self.text[start:]);frame=ctx.status_frames.first_complete_frame(wire)
            if frame is not None:
                self.count+=1
                ctx.transport.exclusive_bytes(self.evidence/f'status-{self.count:06d}.txt',frame.encode())
                if self.first_status is None:
                    self.first_status=frame;self.t.observe_status(frame)
                ctx.status_frames.assert_observed_status_faults(wire,captured_restore_crash=True)
                return frame
            if time.monotonic()>=deadline:raise Hold('Incomplete original-return status')
            self.pump(.03)


def cleanup_known(port,context,ledger,guarded):
    """Point cleanup of this run's exact APP versions, independent of RTC."""
    directory=ledger['directory']
    names=('RTC0.APP','request.bin') if directory=='/PCCUR-RTC0' else ('CHRBEN.APP','INPUT.bin','RESULT.bin')
    if directory not in ('/MCHR-Q01','/MCHR-Q02','/MCHR-Q03','/PCCUR-RTC0') or not ledger.get('created'):
        raise Hold('No proven newly created memchr/RTC0 directory')
    if port.app_inflight:raise Hold('Cleanup held: owned APP return has not been qualified')
    context.health(port.status())
    context.directory=directory;context.app_path=directory+'/'+names[0]
    context.state=dict(install_reserved=False,backup_helper_created=True,cleanup_authorized=False,
                       backup_helper_expected={directory+'/'+name:None for name in names})
    owned={};unknown=[]
    for item in context.listing(port,directory):
        path=item['path']
        if item['kind']!='file' or path not in context.state['backup_helper_expected'] or not 0<=item['bytes']<=65534:
            unknown.append(path);continue
        data=read_file(port,path)
        if not any(len(data)==v['bytes'] and sha(data)==v['sha256'] for v in ledger['known_files'].get(path,[])):
            unknown.append(path);continue
        owned[path]=data
    context.state['backup_helper_expected']={path:sha(data) for path,data in owned.items()}
    context.state['cleanup_authorized']=True
    removed=[]
    for path,data in owned.items():
        guarded()
        if read_file(port,path)!=data:raise Hold('Known return-cleanup file changed: '+path)
        matrix.clean(port.command('rm "'+path+'"'));removed.append(path)
    if unknown:return dict(status='HOLD',removed=removed,unknown_preserved=unknown,directory_retained=True)
    if context.listing(port,directory):raise Hold('Unknown child retained after point cleanup')
    guarded();matrix.clean(port.command('rmdir "'+directory+'"'))
    return dict(status='PASS',removed=removed,directory_removed=True)


def main():
    if not __debug__:raise Hold('Python assertions are required')
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--packet',type=Path,required=True);p.add_argument('--packet-sha256',required=True)
    p.add_argument('--rtc-manifest',type=Path,required=True);p.add_argument('--rtc-manifest-sha256',required=True)
    p.add_argument('--rtc-codec',type=Path,required=True);p.add_argument('--rtc-codec-sha256',required=True)
    p.add_argument('--lease-sha256',required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--execute',action='store_true',required=True)
    a=p.parse_args();packet=a.packet.resolve()
    index=packet/'sha256.json'
    if sha(index.read_bytes())!=a.packet_sha256:raise Hold('Pico lab packet seal differs')
    seal=json.loads(index.read_text())
    files={str(f.relative_to(packet)):f for f in packet.rglob('*') if f.is_file() and f!=index}
    if set(files)!=set(seal):raise Hold('Pico lab packet file set differs')
    for name,f in files.items():
        if f.is_symlink() or sha(f.read_bytes())!=seal[name]:raise Hold('Pico lab packet changed: '+name)
    for name,digest in json.loads((packet/'workspace-dependencies.json').read_text()).items():
        if sha(Path(name).read_bytes())!=digest:raise Hold('Pico lab dependency changed: '+name)
    plan_path=packet/'plan.json';plan=json.loads(plan_path.read_text());plan_sha=sha(plan_path.read_bytes())
    if (plan['scope'],plan['uid'],plan['cpu'],plan['total_rows'])!=(SCOPE,UID,'m0',6528):
        raise Hold('Different Pico lab scope')
    for path,digest in ((a.rtc_manifest,a.rtc_manifest_sha256),(a.rtc_codec,a.rtc_codec_sha256)):
        if path.is_symlink() or sha(path.read_bytes())!=digest:raise Hold('Qualified RTC0 input changed')
    rtc_manifest=json.loads(a.rtc_manifest.read_text())
    rtc_app=Path(rtc_manifest['app']['path']);rtc_bytes=rtc_app.read_bytes()
    if sha(rtc_bytes)!=rtc_manifest['app']['sha256']:raise Hold('Qualified RTC0 APP changed')
    codec=load('memchr_qualified_rtc_codec',a.rtc_codec)
    approval=dict(scope=SCOPE,plan_sha256=plan_sha,packet_sha256=a.packet_sha256,
        runner_sha256=sha(Path(__file__).read_bytes()),envelope_sha256=sha((HERE/'pico-envelope.py').read_bytes()),
        rtc_manifest_sha256=a.rtc_manifest_sha256,
        rtc_codec_sha256=a.rtc_codec_sha256,rtc_app_sha256=sha(rtc_bytes))
    lease=json.loads(LEASE.read_text())
    def guarded():
        if sha(LEASE.read_bytes())!=a.lease_sha256:raise Hold('Exclusive Pico lab lease changed')
        if (lease.get('owner'),lease.get('owner_thread'),lease.get('enabled'),lease.get('hardware_window_granted'))!=('memchr',THREAD,True,True):
            raise Hold('No active Pico lab owner grant')
        if lease.get('memchr_approval')!=approval or lease.get('uid')!=UID:raise Hold('Pico lab approval binding differs')
    guarded()
    proofs={}
    for campaign in plan['campaigns']:
        actual=native.verify(campaign['elf'],campaign['prefix'],plan['payload_layout'])
        expected=json.loads(Path(campaign['native_proof']).read_text())
        keys=('build','firmware_crc32','provider','static_end','heap_limit','heap_reserve','prefix_sha256','elf_sha256')
        if any(actual[k]!=expected[k] for k in keys):raise Hold('Pico native proof differs')
        proofs[campaign['native']]=actual
    output=a.output.resolve()
    if ROOT/'.build' not in output.parents or not output.relative_to(ROOT/'.build').parts[0].startswith('memchr-'):
        raise Hold('Dedicated memchr output required')
    os.umask(0o077);output.mkdir(exist_ok=False)
    report=dict(status='RUNNING',scope=SCOPE,plan_sha256=plan_sha,approval=approval,pid=os.getpid(),
        serial_closed=True,rom_entry_attempted=False,candidate_write_attempted=False,
        original_full_verified=False,return_pending=False,rtc_return_pending=False,campaigns=[])
    report['booted_builds']=[]
    def save():(output/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    save();(output/'active-lease.byteexact.json').write_bytes(LEASE.read_bytes())
    port=None;port_count=0;before=None;initial_root=None;original=None;original_sha=None;failure=None
    tool=ROOT/'.build/picocalc-picotool/picotool'
    tool_sha=json.loads((packet/'rom-commands.json').read_text())['tool_sha256']
    flash=rom.PicoRomFlash(output,tool,tool_sha,'0'*64,guarded)

    def connect(build,crc,image,*,entry=False,original_return=False):
        nonlocal port,port_count,failure
        if original_return:
            readback=output/'restored-full.bin'
            if (build,crc,image)!=('A7483AE6','C0A51996',754344) or not report.get('full_original_return_verified') or original_sha is None or sha(readback.read_bytes())!=original_sha:
                raise Hold('Incident-tolerant admission requires exact full original readback first')
        guarded();folder=output/('cdc-'+str(port_count).zfill(2));port_count+=1;folder.mkdir()
        deadline=time.monotonic()+25
        while not Path(lease['port']).exists():
            if time.monotonic()>=deadline:raise Hold('Pico CDC did not enumerate')
            time.sleep(.2)
        ctx.physical_usb(folder,lease['port'],lease.get('location_id',18022400))
        Context=OriginalReturnContext if original_return else DiagnosticContext
        Port=OriginalReturnPort if original_return else CorrelatedPort
        context=Context(build,crc,image,guarded,before['settings'] if before else None)
        port=Port(lease['port'],folder,context)
        report['serial_closed']=False;save()
        first=port.status()  # Raw/first frame are durable before commands.
        if (ctx.field(first,'BUILD',16)!=int(build,16) or ctx.field(first,'IMAGE')!=image or
            re.search(r'\bACTUAL='+crc+r'\b',first) is None):
            raise Hold('First Pico frame has a different native identity')
        # status05 deliberately does not wake a sleeping Pico. Ordinary
        # identity/crash reads below wake its source-defined48MHz USB sleep.
        # Preserve that first frame, then use a new actual125MHz observation.
        if not (('POWER_MODE=RUN SYS_HZ=125000000 ' in first) or
                ('POWER_MODE=SLEEP_USB SYS_HZ=48000000 ' in first)):
            raise Hold('Unknown first Pico power/clock state')
        if entry and 'TERMINAL=COMMAND' not in first:raise Hold('Original is no longer in command mode')
        if 'TERMINAL=RAW' in first:
            for token in ('RUN=0 BUSY=0','SERVICE=CLOSED','RUNTIME=NONE','USB_DISK=0','USB_SCREEN=OFF'):
                if token not in first:raise Hold('Unknown startup foreground')
            start=len(port.text);port.send_bytes(b'\x1f','command-mode-after-observed-startup')
            port.wait_text(b'mk61> ',start,8)
        elif 'TERMINAL=COMMAND' not in first:raise Hold('Unknown Pico terminal mode')
        identity=port.command('identity')
        if re.findall(r'\bUID=([0-9A-F]{16})\b',identity)!=[UID]:raise Hold('Wrong Pico identity')
        crash=port.command('crash show')
        incident=ctx.canonical('crash show',crash)!='CRASH=NONE'
        if incident and not original_return:raise Hold('Retained crash; no clear')
        if entry:report['initial_original_crash_none']=not incident;save()
        if incident:
            records=re.findall(r'(?m)^BUILD=([0-9A-F]{8}) CURRENT_BUILD=([0-9A-F]{8})\b',crash)
            if (not report.get('initial_original_crash_none') or
                not re.search(r'\bCRASH=AVAILABLE\b',first) or 'CRC=OK' not in crash or
                len(records)!=1 or records[0][1]!='A7483AE6' or records[0][0] not in report['booted_builds']):
                raise Hold('Retained fault is not bound to this exclusively owned transaction')
            context.captured_incident=True
            report['original_return_incident']=dict(status=first,crash=crash,uid=UID,cleared=False)
            if failure is None:
                failure=Hold('Owned retained incident on original return')
                report['return_incident_failure']=repr(failure)
            save()
        status=port.status();deadline=time.monotonic()+10
        while not ctx.status_frames.startup_frame_ready(status,first,context.health,crash,captured_restore_crash=original_return and incident):
            if time.monotonic()>=deadline:raise Hold('Pico startup did not finish')
            port.pump(.05);status=port.status()
        context.health(status)
        return port,context,folder

    def cleanup_matrix_ledgers(context):
        nonlocal failure
        report.setdefault('return_cleanup',[])
        for folder in sorted([*output.glob('sram-app-*'),*output.glob('flash-app-*')]):
            path=folder/'result.json'
            if not path.exists():continue
            ledger=json.loads(path.read_text())
            if not ledger.get('created') or not ledger.get('cleanup_pending'):continue
            result=dict(directory=ledger['directory'],ledger=str(path))
            try:
                result.update(cleanup_known(port,context,ledger,guarded))
                ledger['return_cleanup']=result
                if result['status']=='PASS':ledger['cleanup_pending']=False
                else:failure=failure or Hold('Unknown owned-namespace version retained')
            except BaseException as error:
                result.update(status='HOLD',failure=repr(error));failure=failure or error
                ledger['return_cleanup']=result
            path.write_text(json.dumps(ledger,indent=2)+'\n')
            report['return_cleanup'].append(result);save()

    def enter_rom(recovery=False):
        nonlocal port
        guarded();report.update(rom_entry_attempted=True,return_pending=True,rtc_return_pending=True);save()
        if port is not None:
            try:
                # Existing one-purpose recovery transition; candidate CRC is
                # not a veto after its first failure has been preserved.
                if recovery:
                    start=len(port.text);port.send_bytes(b'\x1f','owned-failure-recovery-command-mode')
                    try:port.wait_text(b'mk61> ',start,2)
                    except BaseException:pass
                port.send_bytes(b'dfu\r','exact-owned-device-ROM-entry')
                try:port.pump(.3)
                except (OSError,RuntimeError):pass
            finally:
                port.close();port=None;report['serial_closed']=True;save()
        flash.ready('rom-admission-'+str(len(list(output.glob('rom-admission-*.json')))))

    def rtc_return(context,readback):
        directory='/PCCUR-RTC0';app_path=directory+'/RTC0.APP';request_path=directory+'/request.bin'
        roots=context.listing(port,'/')
        if directory.casefold() in {r['path'].casefold() for r in roots}:raise Hold('RTC0 namespace already exists')
        context.directory=directory;context.app_path=app_path
        context.state=dict(install_reserved=True,backup_helper_created=False,cleanup_authorized=False,
                           backup_helper_expected={app_path:sha(rtc_bytes)})
        matrix.clean(port.command('mkdir "'+directory+'"'));context.state['backup_helper_created']=True
        report['rtc_namespace_pending']=True
        report['rtc_ledger']=dict(directory=directory,created=True,known_files={
            app_path:[dict(bytes=len(rtc_bytes),sha256=sha(rtc_bytes))]})
        save()
        write_file(port,app_path,rtc_bytes)
        origin=before['clock'];ppm=before['settings']['RTC_PPM']
        rate=46875/((46875*(1000000-ppm)+500000)//1000000)
        midpoint=(origin['monotonic_before_ns']+origin['monotonic_after_ns'])/2
        elapsed=(time.monotonic_ns()-midpoint)/1e9*rate
        calendar=(datetime.fromisoformat(origin['rtc'])+timedelta(seconds=elapsed)).isoformat(sep=' ',timespec='seconds')
        epochs=[]
        for line in before['alarm'].split('\r\n'):
            match=re.fullmatch(r'ALARM [AB] OFF ONCE (20\d\d-\d\d-\d\d \d\d:\d\d:\d\d)',line)
            if not match:raise Hold('Unsupported original alarm')
            epochs.append(codec.epoch(match[1]))
        session=codec.session_binding(UID,readback,original_sha,plan['original']['prefix'],output.name)
        request,nonce=codec.request(calendar,ppm,epochs,1,session)
        context.state['backup_helper_expected'][request_path]=sha(request)
        report['rtc_ledger']['known_files'][request_path]=[dict(bytes=len(request),sha256=sha(request))]
        save()
        (output/'rtc-request.bin').write_bytes(request);write_file(port,request_path,request)
        port.open(app_path);port.wait_text(b'APP_FLOW_RESULT=',port.app_start,timeout=30)
        port.wait_text(b'mk61> ',port.app_start,10)
        raw=bytes(port.text[port.app_start:]);(output/'rtc-provider-raw.bin').write_bytes(raw)
        decoded=codec.decode(raw,nonce,session,1,require_success=True)
        (output/'rtc-provider-result.json').write_text(json.dumps(decoded,indent=2)+'\n')
        port.calculator()
        context.state['cleanup_authorized']=True
        for path,data in ((request_path,request),(app_path,rtc_bytes)):
            if read_file(port,path)!=data:raise Hold('RTC0 owned file changed')
            matrix.clean(port.command('rm "'+path+'"'))
        if context.listing(port,directory):raise Hold('Unknown RTC0 child retained')
        matrix.clean(port.command('rmdir "'+directory+'"'))
        if context.listing(port,'/')!=roots:raise Hold('RTC0 visible root changed')
        report.update(rtc_namespace_pending=False,rtc_return_pending=False);save()

    try:
        port,context,folder=connect('A7483AE6','C0A51996',754344,entry=True)
        before=context.capture(port,'fresh-original-before',output);initial_root=context.listing(port,'/')
        if before['pwd']!='/' or before['settings']['RTC_SET']!=0:raise Hold('Unsupported fresh original state')
        numbers=re.findall(r'=\s*([+\-]?\d+\.\d+)\s+([+\-]?\d+)',before['reg']+before['stk'])
        if len(numbers)!=20 or any(float(n)!=0 for n,_ in numbers):
            raise Hold('Current calculator differs from the empty handoff; no reset')
        ClassicState.replay(before['hout'])
        # Coordinator's current idle ticket is empty/IP0. A different user
        # calculation requires a new factual handoff, not a historical replay.
        if ctx.field(port.status(),'IP')!=0:raise Hold('Fresh original IP differs from current handoff')
        enter_rom()
        first_path=output/'original-a.bin';journal,value=flash.begin('original-first','first fresh complete Flash read')
        result=flash.execute(journal,value,['save','-a','-v',first_path,'-t','bin'])
        if result.returncode or not first_path.exists():raise Hold('First full original read failed')
        original=first_path.read_bytes()
        prefix=Path(plan['original']['prefix']).read_bytes()
        if len(original)!=2097152 or original[:len(prefix)]!=prefix:raise Hold('Fresh full original/prefix differs')
        original_sha=sha(original);flash.original_sha256=original_sha
        value.update(status='PASS',bytes=len(original),sha256=original_sha);flash.save(journal,value)
        second=flash.read_full('original-second',output/'original-b.bin',original_sha)
        if second!=original:raise Hold('Fresh full Flash reads disagree')
        report.update(original_full_verified=True,original_sha256=original_sha);save()
        for number,campaign in enumerate(plan['campaigns']):
            proof=proofs[campaign['native']]
            candidate=images.compose(original,second,prefix,Path(campaign['prefix']).read_bytes(),
                Path(plan['payload']).read_bytes(),json.loads(Path(plan['payload_layout']).read_text()),
                original_sha256=original_sha,baseline_sha256=plan['original']['prefix_sha256'],
                native_sha256=proof['prefix_sha256'])
            destination=output/('candidate-'+campaign['native']+'-full.bin');destination.write_bytes(candidate)
            digest=sha(candidate)
            if number:enter_rom()
            report['candidate_write_attempted']=True;save()
            flash.write_full('install-'+campaign['native'],destination,digest)
            flash.read_full('readback-'+campaign['native'],output/('readback-'+campaign['native']+'.bin'),digest)
            flash.reboot_verified('boot-'+campaign['native'],digest)
            report['booted_builds'].append(campaign['build']);save()
            port,context,folder=connect(campaign['build'],campaign['firmware_crc32'],proof['prefix_bytes'])
            current=dict(native=campaign['native'],build=campaign['build'],firmware_crc32=campaign['firmware_crc32'],apps=[])
            report['campaigns'].append(current);save()
            for index,row in enumerate(campaign['apps']):
                bounded=oracle.prepare(row,plan['payload_elf'],plan['payload_layout'],
                    proof['static_end'],proof['heap_limit'],proof['provider'])
                item=matrix.run_app(port,context,row,bounded,oracle,output/(campaign['native']+'-app-'+str(index)),guarded)
                current['apps'].append(dict(directory=row['directory'],status=item['status'],groups=len(item['groups'])));save()
        report['benchmark_status']='PASS'
    except BaseException as error:
        failure=error;report.update(benchmark_status='FAIL',failure=repr(error));save()
    finally:
        if report['rom_entry_attempted'] and original_sha is not None:
            try:
                enter_rom(recovery=failure is not None)
                if not report['original_full_verified']:
                    # A failed second acquisition cannot permit a candidate.
                    # A separate read-only return proof can still qualify the
                    # internally verified first original for recovery only.
                    flash.read_full('original-recovery-check',output/'original-recovery-check.bin',original_sha,recovery=True)
                    report['original_full_verified']=True;save()
                try:flash.write_full('return-original',output/'original-a.bin',original_sha,recovery=True)
                except BaseException as error:
                    report['original_write_failure']=repr(error);save()
                    if failure is None:failure=error
                readback=output/'restored-full.bin'
                flash.read_full('original-return-readback',readback,original_sha,recovery=True)
                report['full_original_return_verified']=True;save()
                flash.reboot_verified('boot-original',original_sha)
                report['booted_builds'].append('A7483AE6');save()
                port,context,folder=connect('A7483AE6','C0A51996',754344,original_return=True)
                # This cannot suppress the independent RTC return below.
                cleanup_matrix_ledgers(context)
                rtc_return(context,readback)
                after=context.capture(port,'original-after-return',output)
                context.compare(before,after)
                if context.listing(port,'/')!=initial_root:raise Hold('Original visible root was not returned')
                report.update(return_pending=False,restoration_complete=True)
            except BaseException as error:
                report.update(return_failure=repr(error),restoration_complete=False)
                if failure is None:failure=error
                save()
        if report.get('rtc_namespace_pending') and port is not None:
            try:
                result=cleanup_known(port,port.t,report['rtc_ledger'],guarded)
                report['rtc_return_cleanup']=result
                if result['status']=='PASS':report['rtc_namespace_pending']=False
            except BaseException as error:
                report['rtc_return_cleanup']=dict(status='HOLD',failure=repr(error))
            save()
        if port is not None:
            try:port.close();report['serial_closed']=True
            except BaseException as error:report['close_failure']=repr(error);failure=failure or error
        result=subprocess.run(['/usr/sbin/lsof','-nP','-t','--',lease['port']],capture_output=True)
        report['lsof_after_close']=dict(returncode=result.returncode,stdout=result.stdout.decode(errors='replace'),stderr=result.stderr.decode(errors='replace'))
        report['no_cdc_holder_after_close']=result.returncode==1 and not result.stdout and not result.stderr
        report['status']='PASS' if failure is None and report.get('benchmark_status')=='PASS' and report.get('restoration_complete') and report['serial_closed'] and report['no_cdc_holder_after_close'] else 'HOLD'
        save()
    print(json.dumps(dict(status=report['status'],output=str(output),restoration_complete=report.get('restoration_complete',False))),flush=True)
    if failure is not None:raise failure
    if report['status']!='PASS':raise Hold('Pico lab completion did not qualify')

if __name__=='__main__':main()
