"""Classic full-Flash transport for a separately approved future FW window.

Importing this module performs no device I/O. Callers must supply an immutable
lease guard and exact image hashes. APP-only runners never import or call it.
"""
from dataclasses import asdict
import errno
import json
from pathlib import Path
import subprocess
import time
from session import Hold,sha
import hil_system_memory as system_transport
from hil_system_memory import health,require_empty,valid_classic_dfu_listing
from hil_multi_device_identity import parse_identity

ROOT=Path(__file__).resolve().parents[2]
PORT='/dev/cu.usbmodem2068336B47311'
SERIAL='2068336B4731'
DFU=Path('/Users/bolk/Library/Arduino15/packages/arduino/tools/dfu-util/0.11.0-arduino5/dfu-util')
DFU_SHA='a200781d74555c0d9c4b379fc7d5872deed6e13bf3988fc9d6313210090a8f43'
FULL_SIZE=524288
ORIGINAL_SHA='412f036e278a75beb63c96d95f4ca72798b59d66d6549e43e420261cafa602d1'

def save(path,value):path.write_text(json.dumps(value,indent=2)+'\n')

def connect(path,build=None,wait=30,observe=None):
    """The normal pinned CDC admission, with raw evidence for rejected attempts.

    Keep retries limited to USB enumeration/busy and reply timeouts. An identity
    mismatch is final, and its port is closed before reporting the failure.
    """
    deadline=time.monotonic()+wait
    while True:
        port=None;failure=None;retry=False;identity=None
        try:
            port=system_transport.ExclusiveScreenPort(path)
            identity=parse_identity(port.command('identity',timeout=15))
            assert (identity.public,identity.usb,identity.profile)==(system_transport.PUBLIC,SERIAL,system_transport.PROFILE),identity
            if build:assert identity.build==build,(identity.build,build)
        except BaseException as error:
            failure=error
            if port is not None:port.close()
            retry=(isinstance(error,OSError) and error.errno in (errno.EBUSY,errno.ENOENT)) or isinstance(error,TimeoutError)
            retry=retry and time.monotonic()<deadline
        if observe is not None:
            try:
                observe(dict(port=path,requested_build=build,wait_seconds=wait,
                    status='RETRY' if retry else 'REJECTED' if failure else 'ADMITTED',
                    identity=asdict(identity) if identity is not None else None,
                    failure=repr(failure) if failure is not None else None,
                    serial_closed=port is None or port.fd<0),bytes(port.text) if port is not None else b'')
            except BaseException:
                if port is not None:port.close()
                if failure is not None:raise failure
                raise
        if failure is None:return port
        if not retry:raise failure
        time.sleep(.3)

class ClassicFlash:
    def __init__(self,lease_guard,output):
        self.lease_guard=lease_guard;self.output=Path(output).resolve()
        if ROOT/'.build' not in self.output.parents or not self.output.relative_to(ROOT/'.build').parts[0].startswith('memchr-'):raise Hold('Dedicated memchr Flash output required')
    def guard(self):
        self.lease_guard()
        if sha(DFU.read_bytes())!=DFU_SHA:raise Hold('Pinned DFU tool changed')
    def begin(self,path,**fields):
        path=Path(path).resolve()
        if self.output not in path.parents or path.exists():raise Hold('Fresh dedicated transport journal required')
        self.last_enter=None;self.last_transcript=b'';self.last_listing=None
        receipt=dict(status='PENDING',phase='before-enter',**fields)
        self.active_journal=path;self.active_receipt=receipt
        save(path,receipt)
        return path,receipt
    def capture_output(self,path,receipt,stdout,stderr):
        for name,value in (('stdout',stdout),('stderr',stderr)):
            if value is None:continue
            raw=value if isinstance(value,bytes) else value.encode()
            target=path.with_suffix('.'+name+'.bin');target.write_bytes(raw)
            receipt[name]=raw.decode('utf-8','replace')
            receipt[name+'_raw']=dict(path=str(target),bytes=len(raw),sha256=sha(raw))
    def failed(self,path,receipt,error):
        # Never replace the primary transport exception with a logging error.
        try:
            self.capture_output(path,receipt,getattr(error,'stdout',None),getattr(error,'stderr',None))
            receipt.update(status='HOLD',failure=repr(error),failure_type=type(error).__name__)
            if self.last_enter is not None:receipt['before']=self.last_enter
            if self.last_listing is not None:
                if receipt['phase']=='rom-ready':
                    listing_path=path.with_suffix('.listing-'+str(self.last_listing['index']).zfill(3)+'.json')
                    self.capture_output(listing_path,self.last_listing,getattr(error,'stdout',None),getattr(error,'stderr',None))
                    self.last_listing.update(failure=repr(error),status='HOLD')
                receipt['listing']=self.last_listing
            serial=path.with_suffix('.serial.bin')
            if self.last_transcript or not serial.exists():serial.write_bytes(self.last_transcript)
            save(path,receipt)
        except BaseException as logging_error:
            receipt['logging_failure']=repr(logging_error)
            try:save(path,receipt)
            except BaseException:pass
    def transfer(self,command,path,receipt):
        self.guard();receipt.update(phase='subprocess',command=command);save(path,receipt)
        result=subprocess.run(command,capture_output=True,timeout=180)
        self.capture_output(path,receipt,result.stdout,result.stderr)
        receipt['returncode']=result.returncode;save(path,receipt)
        return result
    def observe_cdc(self,event,raw):
        attempts=self.active_receipt.setdefault('cdc_attempts',[])
        event=dict(event,index=len(attempts))
        target=self.active_journal.with_suffix('.cdc-'+str(event['index']).zfill(3)+'.serial.bin')
        target.write_bytes(raw);event['raw']=dict(path=str(target),bytes=len(raw),sha256=sha(raw))
        attempts.append(event);save(self.active_journal,self.active_receipt)
    def recovery_health(self,port):
        value={'qualification_skipped_for_original_recovery':True}
        for command in ('df','crash show','mpu status'):
            try:value[command]=port.command(command,timeout=3)
            except Exception as error:value[command]={'failure':repr(error)}
        return value
    def enter(self,build,empty=True,recovery=False):
        self.guard()
        # The candidate may have an invalid CRC, a retained crash record or an
        # unreadable build footer. Recovery relies on the physical device
        # identity checked by connect(), not on candidate health/build.
        port=None;self.last_enter=dict(recovery=recovery,requested_build=build)
        try:
            with connect(PORT,None if recovery else build,wait=30,observe=self.observe_cdc if hasattr(self,'active_journal') else None) as port:
                self.last_enter['identity']=asdict(parse_identity(port.command('identity')))
                status=self.recovery_health(port) if recovery else health(port,build)
                self.last_enter['health']=status
                if empty and not recovery:require_empty(status)
                self.guard();port.drain()
                self.last_enter.update(dfu_request_attempted=True,dfu_request_issued=False)
                try:
                    port.write_line('dfu');self.last_enter['dfu_request_issued']=True
                    port.pump(.2)
                except OSError as error:
                    if error.errno not in (errno.ENXIO,errno.EIO,errno.ENODEV):raise
                    # USB may disappear before the CDC pump returns. This is
                    # not a ROM admission: ready() must still prove the exact
                    # pinned descriptor/serial before any upload or download.
                    self.last_enter['dfu_usb_disconnect']=dict(errno=error.errno,failure=repr(error))
        finally:
            if port is not None:
                self.last_transcript=bytes(port.text);self.last_enter['serial_closed']=port.fd<0
        return self.last_enter,self.last_transcript
    def ready(self):
        deadline=time.monotonic()+15
        while True:
            self.guard()
            listings=self.active_receipt.setdefault('listings',[])
            command=[str(DFU),'-d','0483:df11','-S',SERIAL,'-l']
            self.last_listing=dict(index=len(listings),command=command,status='PENDING')
            listings.append(self.last_listing);self.active_receipt['listing']=self.last_listing;save(self.active_journal,self.active_receipt)
            listing=subprocess.run(command,capture_output=True,timeout=8)
            self.last_listing['returncode']=listing.returncode
            self.capture_output(self.active_journal.with_suffix('.listing-'+str(self.last_listing['index']).zfill(3)+'.json'),self.last_listing,listing.stdout,listing.stderr)
            valid=valid_classic_dfu_listing(self.last_listing['stdout'],self.last_listing['stderr'],listing.returncode)
            self.last_listing['status']='VALID' if valid else 'REJECTED';save(self.active_journal,self.active_receipt)
            if valid:return self.last_listing
            if time.monotonic()>=deadline:raise Hold('Exact Classic ROM DFU descriptor is absent; no write allowed')
            time.sleep(.2)
    def upload(self,build,destination,expected_sha,recovery=False,already_in_dfu=False):
        destination=Path(destination).resolve()
        if self.output not in destination.parents or destination.exists():raise Hold('Fresh full-Flash backup path required')
        if recovery and expected_sha!=ORIGINAL_SHA:raise Hold('Recovery readback is restricted to the exact original image')
        if already_in_dfu and not recovery:raise Hold('ROM-only readback is restricted to original-image recovery')
        command=[str(DFU),'-d','0483:df11','-S',SERIAL,'-a','0','-s','0x08000000:524288:leave','-U',str(destination)]
        path,receipt=self.begin(destination.with_suffix('.transfer.json'),operation='read-full-and-leave-without-download',command=command,expected_sha256=expected_sha,recovery=recovery)
        try:
            if already_in_dfu:receipt['before'],transcript=dict(source='exact pinned ROM DFU',serial_closed=True),b''
            else:receipt['before'],transcript=self.enter(build,empty=not recovery,recovery=recovery)
            path.with_suffix('.serial.bin').write_bytes(transcript)
            receipt['phase']='rom-ready';save(path,receipt);receipt['listing']=self.ready()
            result=self.transfer(command,path,receipt)
            if destination.exists():
                raw=destination.read_bytes();receipt.update(bytes=len(raw),sha256=sha(raw));save(path,receipt)
            if result.returncode or 'Upload done.' not in receipt['stdout'] or 'Submitting leave request' not in receipt['stdout']:raise Hold('Full Flash upload/leave failed')
            raw=destination.read_bytes()
            if len(raw)!=FULL_SIZE or sha(raw)!=expected_sha:raise Hold('Independent full Flash readback differs')
            if recovery:
                # A complete byte comparison is independent of the restored
                # firmware's ability to boot or its retained crash record.
                # The controller performs CDC/state/health qualification later.
                receipt.update(status='PASS',phase='full-image-verified-health-deferred',serial_closed=True,health_qualification_deferred=True)
                save(path,receipt);return raw
            self.guard();receipt['phase']='post-read-identity' if recovery else 'post-read-health';save(path,receipt)
            with connect(PORT,None if recovery else build,wait=30,observe=self.observe_cdc) as port:
                receipt['identity']=asdict(parse_identity(port.command('identity')))
                receipt['health']=self.recovery_health(port) if recovery else health(port,build)
            receipt.update(status='PASS',serial_closed=port.fd<0);save(path,receipt)
            return raw
        except BaseException as error:
            if destination.exists():
                try:raw=destination.read_bytes();receipt.update(bytes=len(raw),sha256=sha(raw))
                except OSError:pass
            self.failed(path,receipt,error);raise
    def download(self,current_build,image,expected_sha,receipt_path,recovery=False,already_in_dfu=False):
        image=Path(image).resolve();raw=image.read_bytes()
        if len(raw)!=FULL_SIZE or sha(raw)!=expected_sha:raise Hold('Exact full candidate/restore image required')
        if recovery and expected_sha!=ORIGINAL_SHA:raise Hold('Recovery can only restore the pinned original image')
        if already_in_dfu and not recovery:raise Hold('ROM-only download is restricted to original-image recovery')
        # Original recovery stays in ROM until an independent full upload has
        # verified the final write; that upload then requests :leave.
        address='0x08000000' if recovery else '0x08000000:leave'
        command=[str(DFU),'-d','0483:df11','-S',SERIAL,'-a','0','-s',address,'-D',str(image)]
        path,receipt=self.begin(receipt_path,operation='download-full-image',command=command,sha256=expected_sha,recovery=recovery,leaves_rom=not recovery)
        try:
            if already_in_dfu:receipt['before'],transcript=dict(source='exact pinned ROM DFU',serial_closed=True),b''
            else:receipt['before'],transcript=self.enter(current_build,empty=not recovery,recovery=recovery)
            path.with_suffix('.serial.bin').write_bytes(transcript)
            receipt['phase']='rom-ready';save(path,receipt);receipt['listing']=self.ready()
            self.guard()
            if sha(image.read_bytes())!=expected_sha:raise Hold('Full image changed immediately before download')
            result=self.transfer(command,path,receipt)
            if result.returncode:raise Hold('Full Flash download failed; verified restoration remains pending')
            receipt.update(status='READBACK_REQUIRED');save(path,receipt)
            # A write is not a verification receipt. The caller must upload
            # after the final write and compare every original Flash byte.
            return receipt
        except BaseException as error:self.failed(path,receipt,error);raise
