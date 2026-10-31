"""Owned APP-only filesystem transaction and conservative Classic recovery."""
from dataclasses import dataclass
from datetime import datetime,timedelta
import hashlib
import json
from pathlib import Path
import re
import time

class Hold(RuntimeError):pass
def sha(data):return hashlib.sha256(data).hexdigest()
def clean_reply(reply):
    if re.search(r'(?im)^(?:ERROR\b|@MKC:(?:ERROR|FAIL)\b|(?:mkdir|rmdir|rm|cd|fsput):|Usage:)',reply):
        raise Hold('Command reported failure: '+reply)
    return reply

@dataclass
class Files:
    files:dict
    directories:set
    def validate(self):
        paths=[*self.files,*self.directories]
        if len({p.casefold() for p in paths})!=len(paths):raise Hold('Ambiguous case-folded namespace')
        for p in paths:
            if not p.startswith('/') or any(x in ('','.', '..') for x in p[1:].split('/')) or '"' in p:
                raise Hold('Unsafe filesystem path: '+repr(p))
        return self
    def metadata(self):
        return dict(files={p:dict(bytes=len(b),sha256=sha(b)) for p,b in sorted(self.files.items())},directories=sorted(self.directories))

class OwnedSession:
    """All cleanup is planned and classified before its first mutation."""
    def __init__(self,directory,scan,read,write,command,save):
        self.directory=directory;self.scan=scan;self.read=read;self.write=write
        self.command=command;self.save=save;self.before=None;self.created=False
        self.mkdir_intent=False;self.versions={};self.result_tests=[];self.ledger={}
    def record(self):
        self.ledger.update(directory=self.directory,mkdir_intent=self.mkdir_intent,created=self.created,
            versions={p:[dict(bytes=len(b),sha256=sha(b)) for b in versions] for p,versions in self.versions.items()})
        self.save(self.ledger)
    def capture(self):
        self.before=self.scan().validate()
        if self.directory.casefold() in {p.casefold() for p in [*self.before.files,*self.before.directories]}:
            raise Hold('Reserved directory already exists, including case variants')
        self.ledger['before']=self.before.metadata();self.record()
        return self.before
    def create(self):
        self.mkdir_intent=True;self.record();lost=None
        try:clean_reply(self.command('mkdir '+self.directory))
        except (OSError,TimeoutError) as error:lost=repr(error)
        after=self.scan().validate()
        if after.files!=self.before.files or after.directories!=self.before.directories|{self.directory}:
            raise Hold('mkdir ownership could not be proved; preserve the namespace')
        self.created=True;self.ledger['mkdir_ack_lost']=lost;self.record()
    def put(self,name,data):
        if not self.created or name not in ('CHRBEN.APP','INPUT.bin'):raise Hold('Unowned write')
        path=self.directory+'/'+name
        self.versions.setdefault(path,[]).append(data);self.record()
        self.write(path,data)
        if self.read(path)!=data:raise Hold('Write/readback mismatch: '+path)
    def expect_result(self,validator,metadata=None):
        self.result_tests.append(validator);self.ledger.setdefault('result_intents',[]).append(metadata);self.record()
    def admit_result(self,data):
        if not any(test(data) for test in self.result_tests):raise Hold('Unrecognized APP result')
        self.versions.setdefault(self.directory+'/RESULT.bin',[]).append(data);self.record()
    def plan_cleanup(self):
        current=self.scan().validate()
        allowed=set(self.versions)
        if self.result_tests:allowed.add(self.directory+'/RESULT.bin')
        # C9 preserves the basename but canonicalizes APP extensions to .app.
        # Only known temporary names may match case-insensitively; exact bytes
        # still establish ownership, and Files.validate rejects collisions.
        allowed_by_fold={p.casefold():p for p in allowed}
        if len(allowed_by_fold)!=len(allowed):raise Hold('Ambiguous owned namespace')
        extra_files={p for p in current.files if p not in self.before.files and p.casefold() not in allowed_by_fold}
        extra_dirs=current.directories-self.before.directories-({self.directory} if self.created else set())
        if extra_files or extra_dirs:raise Hold('Unknown files/directories preserved: '+repr((sorted(extra_files),sorted(extra_dirs))))
        owned={}
        for p in sorted(set(current.files)-set(self.before.files)):
            data=current.files[p]
            known=allowed_by_fold[p.casefold()]
            recognized=data in self.versions.get(known,[])
            if known.casefold()==(self.directory+'/RESULT.bin').casefold():recognized=recognized or any(test(data) for test in self.result_tests)
            if not self.created or not recognized:raise Hold('Unknown content preserved: '+p)
            owned[p]=data
        # A new ancestor, directory replacement, or case variant must never be
        # reclassified as an original file or an owned temporary file.
        if any(p.casefold() in {d.casefold() for d in current.directories} for p in self.before.files):
            raise Hold('Original file replaced by a directory')
        restore={p:b for p,b in self.before.files.items() if current.files.get(p)!=b}
        self.ledger['cleanup_plan']=dict(remove={p:sha(b) for p,b in owned.items()},restore={p:sha(b) for p,b in restore.items()},
            missing_original_directories=sorted(self.before.directories-current.directories))
        self.record();return current,owned,restore
    def cleanup(self,state_check=None,state_restore=None):
        current,owned,restore=self.plan_cleanup() # read-only, before cancel/rm/restore
        state_before_cleanup=state_check() if state_check else None
        clean_reply(self.command('fsput cancel'))
        # Point operations only; never recursively remove a directory.
        for path,data in owned.items():
            if self.read(path)!=data:raise Hold('File changed after cleanup planning: '+path)
            clean_reply(self.command('rm "'+path+'"'))
            if path in self.scan().files:raise Hold('Owned file still present: '+path)
        for directory in sorted(self.before.directories-current.directories,key=lambda p:p.count('/')):
            clean_reply(self.command('mkdir "'+directory+'"'))
        for path,data in restore.items():
            self.write(path,data)
            if self.read(path)!=data:raise Hold('Original file recovery readback failed: '+path)
        if self.created:
            now=self.scan().validate()
            if any(p.startswith(self.directory+'/') for p in [*now.files,*now.directories]):raise Hold('Temporary directory is not empty')
            clean_reply(self.command('rmdir "'+self.directory+'"'))
        final=self.scan().validate()
        if final.files!=self.before.files or final.directories!=self.before.directories:raise Hold('Filesystem restoration mismatch')
        state_result=state_restore(state_before_cleanup) if state_restore else None
        repaired=bool(restore or self.before.directories-current.directories)
        self.created=False;self.ledger.update(cleanup_status='PASS',state_recovery=state_result,files_restored=repaired);self.record()
        return dict(status='PASS',files_preserved=not repaired,files_restored=repaired,state=state_result)

def scan_files(port,read_file,listing_entries):
    files={};directories=set();pending=['/']
    while pending:
        parent=pending.pop()
        answer=port.command('ls "'+parent+'"',timeout=30);clean_reply(answer)
        for entry in listing_entries(answer):
            kind,name=entry[0],entry.split('\t')[-1].rstrip('/')
            if not name or name in ('.','..') or '/' in name or '"' in name:raise Hold('Invalid directory entry')
            path=parent.rstrip('/')+'/'+name
            if path in files or path in directories:raise Hold('Duplicate directory entry')
            if kind=='d':
                if path in directories:raise Hold('Directory cycle')
                directories.add(path);pending.append(path)
            else:files[path]=read_file(port,path)
    return Files(files,directories).validate()

class ClassicState:
    """First window accepts only the exact empty/IP0 Classic state.

    Replay only captured zero program bytes; recovery cannot reset firmware,
    erase storage, clear an arbitrary calculator, or silently accept a failure.
    """
    def __init__(self,port,canon,require_empty):self.port=port;self.canon=canon;self.require_empty=require_empty;self.before=None
    def read(self):
        values={c:self.canon(self.port.command('hout 0 105' if c=='hout' else c,timeout=15)) for c in ('reg','stk','dump','hout','pwd')}
        values['rtc']=self.rtc();return values
    @staticmethod
    def replay(text):
        commands=[];program=bytearray()
        for line in text.splitlines():
            if not line.startswith('hin'):continue
            match=re.fullmatch(r'hin ([0-9]{4}) ([0-9A-Fa-f]{2,48})',line)
            if not match or len(match[2])%2 or int(match[1],10)!=len(program):raise Hold('Malformed/gapped program replay backup')
            program.extend(bytes.fromhex(match[2]));commands.append(line)
        if bytes(program)!=bytes(105):raise Hold('Explicit hout 0 105 must capture all 105 original zero bytes')
        return commands
    def rtc(self):
        date=self.port.command('date ms');alarm=self.port.command('alarm')
        if not all('RTC ALARM '+s+' off' in alarm for s in ('A','B')):raise Hold('RTC alarms must be idle')
        match=re.search(r'(?m)^(20\d\d-\d\d-\d\d \d\d:\d\d:\d\d)(?:\.(\d{3}))?\r?$',date)
        calendar=match[1]+'.'+(match[2] or '000') if match else None
        unset='Set the date.' in date
        if not calendar and not unset:raise Hold('Unrecognized RTC state')
        return dict(raw=date,alarm=alarm,calendar=calendar,unset=unset,wall_utc=time.time())
    def capture(self,save=None):
        self.before=self.read()
        if save:save(self.before)
        self.require_empty(self.before)
        if not re.search(r'(?m)^IP: 0\r?$',self.before['reg']):raise Hold('First Classic plan requires IP0')
        self.replay(self.before['hout'])
        return self.before
    def trajectory(self,now):
        old=self.before['rtc']
        if old['unset']!=now['unset']:return False
        # An unset backup-domain flag may accompany a ticking 2001 calendar.
        # Preserve both facts; unset does not mean calendar=None.
        if old['calendar'] is None:return now['calendar'] is None
        if not now['calendar']:return False
        rtc_elapsed=(datetime.fromisoformat(now['calendar'])-datetime.fromisoformat(old['calendar'])).total_seconds()
        elapsed=now['wall_utc']-old['wall_utc']
        return abs(rtc_elapsed-elapsed)<=max(4,elapsed*.03)
    def preflight_recovery(self):
        now=self.read()
        if self.before['rtc']['unset'] and not self.trajectory(now['rtc']):
            raise Hold('Original unset RTC flag/trajectory changed; no public command can safely restore the unset flag')
        return now
    def recover(self,now):
        if self.before['rtc']['unset'] and not self.trajectory(now['rtc']):
            raise Hold('Original unset RTC flag/trajectory changed; preserve it without any date write')
        changed=any(now[c]!=self.before[c] for c in ('reg','stk','dump','hout','pwd'))
        actions=[]
        if changed:
            # These commands are authorized only by the captured empty/IP0
            # precondition; nothing resembling clear/reset/format is sent.
            for command in ('poke Y 0','poke X 0','kbd 0B',*[f'R{i:X}= 0' for i in range(15)],
                'poke X 0','poke Y 0','poke Z 0','poke T 0',
                *self.replay(self.before['hout']),
                'kbd 00','kbd 15','kbd 04','kbd 04','cd /'):
                clean_reply(self.port.command(command));actions.append(command)
        if not self.before['rtc']['unset'] and not self.trajectory(now['rtc']):
            old=self.before['rtc'];target=datetime.fromisoformat(old['calendar'])+timedelta(seconds=time.time()-old['wall_utc'])
            command='date '+target.strftime('%Y-%m-%d %H:%M:%S');clean_reply(self.port.command(command));actions.append(command)
        after=self.read()
        if any(after[c]!=self.before[c] for c in ('reg','stk','dump','hout','pwd')) or not self.trajectory(after['rtc']):
            raise Hold('Calculator/IP/RTC recovery did not verify; saved state remains pending')
        return dict(status='PASS',preserved=not changed and not actions,restored=bool(actions),actions=actions,after=after)
