"""Exact-UID ROM-only full Flash transport for a future leased Pico session.

Importing this module opens nothing. The caller owns CDC admission, original
state/SD capture and ROM entry. Every ROM operation checks the lease and pinned
tool again. A recovery write accepts only the newly captured original hash;
candidate health/build never participates in that recovery path.
"""
import json
from pathlib import Path
import re
import subprocess
import time
from session import Hold,sha

UID='E6657CD423721C35'
BASE=0x10000000
FLASH_BYTES=2097152


def exact_rom(stdout,stderr,returncode):
    """The pinned picotool's device-only output must identify one 2-MiB RP2040."""
    if returncode or stderr.strip():return False
    try:text=stdout.decode('utf-8','strict')
    except UnicodeError:return False
    values={}
    for line in text.splitlines():
        match=re.fullmatch(r' (type|flash size|flash id):\s+(.+)',line)
        if match:
            if match[1] in values:return False
            values[match[1]]=match[2]
    return (text.count('Device Information')==1 and values==
        {'type':'RP2040','flash size':'2048K','flash id':'0x'+UID})


class PicoRomFlash:
    def __init__(self,output,tool,tool_sha256,original_sha256,lease_guard):
        self.output=Path(output).resolve();self.tool=Path(tool).resolve()
        self.tool_sha256=tool_sha256;self.original_sha256=original_sha256
        self.lease_guard=lease_guard;self.last_read=None;self.last_write=None
        if not self.output.is_dir() or not re.fullmatch('[0-9a-f]{64}',original_sha256):
            raise Hold('Fresh dedicated output and exact current original hash required')

    def guard(self):
        self.lease_guard()
        if sha(self.tool.read_bytes())!=self.tool_sha256:raise Hold('Pinned Pico ROM tool changed')

    def begin(self,label,operation,**fields):
        if not re.fullmatch('[a-z0-9-]+',label):raise Hold('Invalid Pico transport label')
        path=self.output/(label+'.json')
        if path.exists():raise Hold('Pico transport journal already exists')
        receipt=dict(status='PENDING',operation=operation,**fields)
        self.save(path,receipt);return path,receipt

    @staticmethod
    def save(path,receipt):
        temporary=path.with_suffix('.new')
        temporary.write_text(json.dumps(receipt,indent=2)+'\n');temporary.replace(path)

    def execute(self,path,receipt,arguments,timeout=120):
        self.guard();command=[str(self.tool),*map(str,arguments),'--ser',UID]
        receipt['command']=command;self.save(path,receipt)
        try:
            result=subprocess.run(command,capture_output=True,timeout=timeout)
            receipt['returncode']=result.returncode
            self.capture(path,receipt,result.stdout,result.stderr);self.save(path,receipt)
            return result
        except BaseException as error:
            self.capture(path,receipt,getattr(error,'stdout',None),getattr(error,'stderr',None))
            receipt.update(status='HOLD',failure=repr(error));self.save(path,receipt);raise

    @staticmethod
    def capture(path,receipt,stdout,stderr):
        for name,value in (('stdout',stdout),('stderr',stderr)):
            if value is None:continue
            raw=value if isinstance(value,bytes) else value.encode()
            target=path.with_suffix('.'+name+'.bin');target.write_bytes(raw)
            receipt[name]=dict(path=str(target),bytes=len(raw),sha256=sha(raw))

    def ready(self,label):
        path,receipt=self.begin(label,'read-only exact ROM identity')
        deadline=time.monotonic()+25;receipt['attempts']=[]
        while True:
            attempt,row=self.begin(label+'-attempt-'+str(len(receipt['attempts'])).zfill(3),'ROM enumeration')
            receipt['attempts'].append(str(attempt));self.save(path,receipt)
            try:result=self.execute(attempt,row,['info','-d'],timeout=10)
            except BaseException as error:
                receipt.update(status='HOLD',failure=repr(error));self.save(path,receipt);raise
            admitted=exact_rom(result.stdout,result.stderr,result.returncode)
            row['status']='PASS' if admitted else 'REJECTED';self.save(attempt,row)
            if admitted:
                receipt['status']='PASS';self.save(path,receipt);return
            # Retry only the pinned tool's exact absent-UID message. A wrong
            # UID/type/size, malformed success or permission error is final.
            absent=('No accessible RP-series devices in BOOTSEL mode were found found with serial number '+UID+'.')
            output=b' '.join((result.stdout+b' '+result.stderr).split()).decode('utf-8','replace')
            retry=bool(result.returncode and output==absent and time.monotonic()<deadline)
            if not retry:
                receipt['status']='HOLD';self.save(path,receipt)
                raise Hold('Exact Pico ROM identity is absent; no transfer allowed')
            time.sleep(.25)

    def read_full(self,label,destination,expected_sha256,recovery=False):
        destination=Path(destination).resolve()
        if self.output not in destination.parents or destination.exists():raise Hold('Fresh dedicated Pico backup required')
        if not re.fullmatch('[0-9a-f]{64}',expected_sha256):raise Hold('Exact Pico readback hash required')
        if recovery and expected_sha256!=self.original_sha256:raise Hold('Recovery readback must be the original image')
        path,receipt=self.begin(label,'independent full Flash readback',expected_sha256=expected_sha256,recovery=recovery)
        self.last_read=None
        try:
            self.ready(label+'-rom')
            result=self.execute(path,receipt,['save','-a','-v',destination,'-t','bin'])
            if destination.exists():
                raw=destination.read_bytes();receipt.update(bytes=len(raw),sha256=sha(raw));self.save(path,receipt)
            if result.returncode or not destination.exists() or len(raw)!=FLASH_BYTES or sha(raw)!=expected_sha256:
                raise Hold('Independent full Pico Flash readback differs')
            self.last_read=expected_sha256;receipt['status']='PASS';self.save(path,receipt);return raw
        except BaseException as error:
            receipt.update(status='HOLD',failure=repr(error));self.save(path,receipt);raise

    def write_full(self,label,source,expected_sha256,recovery=False):
        source=Path(source).resolve()
        if self.output not in source.parents:raise Hold('Dedicated Pico full-image input required')
        raw=source.read_bytes()
        if len(raw)!=FLASH_BYTES or sha(raw)!=expected_sha256:raise Hold('Pico complete write image differs')
        if recovery and expected_sha256!=self.original_sha256:raise Hold('Recovery can write only the exact original image')
        path,receipt=self.begin(label,'full Flash write staying in ROM',expected_sha256=expected_sha256,recovery=recovery)
        self.last_read=None;self.last_write=expected_sha256
        try:
            self.ready(label+'-rom')
            result=self.execute(path,receipt,['load','-u','-v',source,'-t','bin','-o',hex(BASE)])
            if result.returncode:raise Hold('Pico full Flash write failed; independent readback still required')
            receipt.update(status='WRITE_COMPLETE_READBACK_REQUIRED',reboot_requested=False);self.save(path,receipt)
        except BaseException as error:
            receipt.update(status='HOLD',failure=repr(error));self.save(path,receipt);raise

    def reboot_verified(self,label,expected_sha256):
        if self.last_read!=expected_sha256 or (self.last_write is not None and self.last_write!=expected_sha256):
            raise Hold('Pico reboot requires independent full matching readback')
        path,receipt=self.begin(label,'boot independently verified image',expected_sha256=expected_sha256)
        try:
            self.ready(label+'-rom')
            result=self.execute(path,receipt,['reboot'])
            if result.returncode:raise Hold('Pico ROM reboot command failed')
            self.last_read=None;self.last_write=None;receipt['status']='PASS';self.save(path,receipt)
        except BaseException as error:
            receipt.update(status='HOLD',failure=repr(error));self.save(path,receipt);raise
