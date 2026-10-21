#!/usr/bin/env python3
"""macOS: verify cached Pico SD sectors remain coherent across USB MSC writes.

Uses one exact UID/build and a fresh directory, never formats a volume. The
host only replaces our test file. Safe eject precedes returning SD ownership
to firmware. Calculator state and USB Screen mode are restored in finally.
"""
import argparse
from datetime import datetime,timezone
import hashlib,json,os,plistlib,re,subprocess,time
from pathlib import Path
from hil_picocalc_software import connect,calculator,restore,raw
from hil_picocalc_hardware import healthy,field
from hil_c5_stack import read_file,write_file

def disk(*args):
    return plistlib.loads(subprocess.check_output(['diskutil',*args],timeout=30))

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',required=True);parser.add_argument('--uid',required=True)
    parser.add_argument('--firmware-directory',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    build=json.loads((args.firmware_directory/'manifest.json').read_text())
    directory='/MK61S-DMAUSB-'+datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')
    path=directory+'/cached.bin';payload=bytes((i*71+i//13)&255 for i in range(4096))
    changed=bytes(b^0xA5 for b in payload)
    report=dict(passed=False,uid=args.uid,build=build['build_id'].upper(),uf2_sha256=build['uf2_sha256'],directory=directory)
    p=connect(args.port,args.uid);before=None;created=False;whole=None;usb=False
    def eject():
        if whole is None:return
        for _ in range(3):
            result=subprocess.run(['diskutil','eject',whole],capture_output=True,text=True,timeout=30)
            if result.returncode==0:return
            p.pump(1)
        raise RuntimeError('Safe eject failed: leave USB disk active; '+result.stderr)
    try:
        initial=p.status();healthy(initial,report['build']);report['initial']=initial
        for marker in ('USB_DISK=0','SERVICE=CLOSED','M61_ACTIVE=0','DIRTY=0','RUN=0 BUSY=0'):
            assert marker in initial,(marker,initial)
        before={c:p.command(c) for c in ('reg','stk','hout','dump','pwd')}
        p.command('uscreen off')
        assert 'ERROR' not in p.command('mkdir '+directory,timeout=60);created=True
        write_file(p,path,payload);assert read_file(p,path)==payload
        report['warm_before']=p.status()
        report['existing_disks']=disk('list','-plist','external','physical')['WholeDisks']
        assert 'ERROR' not in p.command('usbdisk');usb=True
        active=p.expect('USB_DISK=1','SERVICE=USB_DISK');report['usb_started']=active
        print('USB MSC active; waiting for macOS filesystem check/mount',flush=True)
        mount=None;started=time.monotonic();deadline=started+180
        while time.monotonic()<deadline and mount is None:
            candidates=[]
            for candidate in disk('list','-plist','external','physical')['WholeDisks']:
                info=disk('info','-plist',candidate)
                if info.get('BusProtocol')=='USB' and 'PicoCalc' in info.get('MediaName',''):candidates.append(candidate)
            assert len(candidates)<=1,candidates
            if candidates:
                if whole!=candidates[0]:print('PicoCalc media '+candidates[0],flush=True)
                whole=candidates[0]
                for part in disk('list','-plist',whole)['AllDisksAndPartitions'][0].get('Partitions',[]):
                    info=disk('info','-plist',part['DeviceIdentifier'])
                    if info.get('MountPoint'):mount=Path(info['MountPoint']);break
            if mount is None:p.pump(.2)
        report['mount_wait_seconds']=time.monotonic()-started
        assert mount is not None,'PicoCalc SD did not mount'
        print('PicoCalc SD mounted after %.1f s'%report['mount_wait_seconds'],flush=True)
        target=mount/path.lstrip('/');assert target.read_bytes()==payload
        with target.open('r+b') as stream:
            stream.write(changed);stream.flush();os.fsync(stream.fileno())
        assert target.read_bytes()==changed
        streamed=p.status();report['usb_streamed']=streamed
        # Local firmware reads are suspended. Host bulk reads must bypass
        # PSRAM, while host writes may invalidate its headers.
        assert field(streamed,'READ_BYTES')==field(active,'READ_BYTES'),(active,streamed)
        eject();assert 'ERROR' not in p.command('usbdisk off');usb=False
        p.expect('USB_DISK=0','SERVICE=CLOSED','SD=OK')
        assert read_file(p,path)==changed
        after=p.status();healthy(after,report['build'])
        msc=lambda status:re.search(r'(?m)^MSC_READ=[^\r\n]*',status)[0]
        assert field(msc(after),'WRITE')>field(msc(initial),'WRITE'),after
        assert 'READ_ERROR=0 WRITE_ERROR=0' in after,after
        report.update(passed=True,disk=whole,after=after,
            original_sha256=hashlib.sha256(payload).hexdigest(),host_written_sha256=hashlib.sha256(changed).hexdigest())
    finally:
        try:
            if usb:
                eject();assert 'ERROR' not in p.command('usbdisk off');usb=False
            if before is not None:
                calculator(p)
                if created:
                    # Finder can create metadata in our otherwise empty
                    # folder. The device's ordinary listing hides dotfiles;
                    # remove only these known test-local names explicitly.
                    for name in ('.DS_Store','._cached.bin'):
                        p.command('rm "'+directory+'/'+name+'"',timeout=30)
                    assert 'ERROR' not in p.command('rm -r '+directory,timeout=60)
                cwd=re.search(r'(?m)^(/[^\r\n]*)',before['pwd'])[1]
                p.command('cd "'+cwd+'"');restore(p,before)
                ip=field(initial,'IP');assert ip<100
                raw(p,('g'+f'{ip:02d}').encode());p.expect('IP='+f'{ip:02d}','RUN=0 BUSY=0');p.commands()
                assert {c:p.command(c) for c in before}==before
                p.command('uscreen off' if 'USB_SCREEN=OFF ' in initial else 'uscreen on')
                final=p.status();healthy(final,report['build'])
                report.update(calculator_state_restored=True,temporary_directory_removed=created,final=final)
        finally:
            (args.output/'terminal.bin').write_bytes(p.text);p.__exit__(None,None,None)
            (args.output/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    assert report['passed'] and report['calculator_state_restored']
    print('PASS SD DMA/CRC/PSRAM coherence through macOS USB writes and safe eject',flush=True)

if __name__=='__main__':main()
