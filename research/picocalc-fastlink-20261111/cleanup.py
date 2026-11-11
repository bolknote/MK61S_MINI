#!/usr/bin/env python3
"""Finite cleanup only: exact owned SD file, native status, no APP launches."""
from pathlib import Path
import argparse,fcntl,json,os,sys,time
import hil as experiment
base=experiment.base;ROOT=experiment.ROOT;WORK=experiment.WORK;EXPECTED=experiment.EXPECTED
PROOF=WORK/'CLEANUP-PACKAGE-001.json';PHASE=WORK/'CLEANUP-PHASE-001.json'
FOLDER='/FLTEST14';APP=FOLDER+'/FASTLINK.APP';PAYLOAD=WORK/'kit-004/app/FASTLINK.APP'
OLD=WORK/'hardware-004/receipt.json'
def save(p,j):experiment.save(p,j)
def prepare():
 pins={}
 for module in sys.modules.values():
  p=Path(getattr(module,'__file__','')).resolve()
  if p.is_file() and p.is_relative_to(ROOT):pins[str(p)]=experiment.sha(p)
 for p in (Path(__file__).resolve(),PAYLOAD,OLD,WORK/'hardware-004/cdc-00-rx.bin',WORK/'hardware-004/wire.txt'):
  pins[str(p)]=experiment.sha(p)
 save(PHASE,dict(uid=base.UID,action='admit',pins=pins,deadline_seconds=300,sd_scope=FOLDER))
 save(PROOF,dict(status='HOST_CLEANUP_ONLY_REVIEW_READY',uid=base.UID,phase_sha256=experiment.sha(PHASE),pins=pins,
  expected=EXPECTED,owned_sd_file=APP,owned_file_sha256=experiment.sha(PAYLOAD),root_lease_inode=289244874,
  allowed=['native status/identity/listing/readback','normal leave of already finished owned UI','exact owned-file removal','empty owned-directory removal','CDC/lease closure'],
  forbidden=['APP launch','S3M commands','GPIO/MMIO actions','cases/retries','reset/Flash/ROM mode','counter reset or old receipt rewrite'],
  interpretation=dict(hardware_004_status='HOLD',UART_cases_passed=7,SOFT1_cases_passed=2,
   failing_SOFT1_case=9,M3_error=10,pico_capture_error=-36,UART_errors=0,
   observed_native_counter_deltas={'I2C_TIMEOUTS':2,'IO_I2C_RESETS':2},
   last_saved_foreground='CALCULATOR/CLOSED/NONE',last_saved_KBD='OK',last_saved_crash='NONE',
   CDC_session_closed=True,lease_closed=True,owned_sd_cleanup_incomplete=True)))
 print(json.dumps(dict(proof=str(PROOF),sha256=experiment.sha(PROOF),phase_sha256=experiment.sha(PHASE))))
def main():
 global base
 ap=argparse.ArgumentParser();ap.add_argument('--prepare',action='store_true');ap.add_argument('--go',type=Path);ap.add_argument('--output',type=Path)
 a=ap.parse_args()
 experiment.load_backend();base=experiment.base
 if a.prepare:prepare();return
 if not a.go or not a.output:ap.error('--go and unique --output required')
 proof=json.loads(PROOF.read_text());go=json.loads(a.go.read_text());now=time.time()
 base.need(go['status']=='COORDINATOR_EXPLICIT_HARDWARE_GO' and go['uid']==base.UID and
  go['package_proof_sha256']==experiment.sha(PROOF),'No exact cleanup GO')
 base.need(go['not_before_utc_epoch']<=now<go['start_before_utc_epoch']<go['finish_before_utc_epoch'] and
  10<go['finish_before_utc_epoch']-now<=900,'Outside cleanup GO')
 base.need(proof['phase_sha256']==experiment.sha(PHASE),'Cleanup phase changed')
 for p,digest in proof['pins'].items():base.need(experiment.sha(p)==digest,'Cleanup input changed '+p)
 out=a.output.resolve();base.need(out.is_relative_to(WORK) and not out.exists(),'Use a fresh owned result directory')
 grant=WORK/(out.name+'-grant.json')
 save(grant,dict(status='ROOT_EXPLICIT_PHASE_GO',uid=base.UID,phase_sha256=experiment.sha(PHASE),source_pins=proof['pins'],
  not_before_utc_epoch=go['not_before_utc_epoch'],start_before_utc_epoch=go['start_before_utc_epoch'],
  finish_before_utc_epoch=min(go['finish_before_utc_epoch'],now+300)))
 fd=os.open(experiment.LEASE,os.O_RDONLY|os.O_NOFOLLOW)
 base.need(os.fstat(fd).st_ino==289244874,'Root lease inode changed');fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
 g=None;ok=False;error=None
 try:
  g=base.Gate(PHASE,grant,out);g.final.update(APP_launches=0,S3M_commands=0,MMIO_actions=0,Flash_writes=0,reset_commands=0)
  p=base.Port(g)
  with p:
   status=p.status()
   service,path,result=base.foreground(status)
   base.need(base.field(status,'RUNTIME')=='NONE','Active runtime; no code cancellation in cleanup-only window')
   if service!='CLOSED':status=base.return_owned(p,EXPECTED,None,{APP})
   base.health(status,EXPECTED,closed=True);g.final['before']=status
   before={k:base.field(status,k) for k in (*base.CORE_COUNTERS,'BOOTS','IO_I2C_RESETS')};g.final['observed_before_counters']=before
   p.commands();base.need(base.field(p.command('identity'),'UID')==base.UID,'Wrong cleanup identity')
   roots=base.names(p.command('ls "/"'))
   if FOLDER[1:] in roots:
    base.need(base.names(p.command('ls "'+FOLDER+'"'))=={'FASTLINK.APP'},'Owned folder contains unexpected files')
    data=base.read_file(p,APP);base.need(data==PAYLOAD.read_bytes(),'Owned file differs; refusing removal')
    g.final['owned_file_readback_sha256']=__import__('hashlib').sha256(data).hexdigest()
    p.command('rm "'+APP+'"');base.need(not base.names(p.command('ls "'+FOLDER+'"')),'Owned folder is not empty')
    p.command('rmdir "'+FOLDER+'"')
    base.need(base.names(p.command('ls "/"'))==roots-{FOLDER[1:]},'Root names differ after cleanup')
   else:g.final['owned_folder_already_absent']=True
   status=base.health(p.status(),EXPECTED,before,closed=True)
   g.final.update(final=status,CLOSED=True,owned_sd_removed=True,counters_preserved=True)
  g.final['CDC_closed']=p.closed;ok=True
 except BaseException as exc:error=repr(exc)
 finally:
  os.close(fd)
  if g is not None:g.final['lease_closed']=True;g.finish(ok,error)
 print(json.dumps(dict(status='PASS' if ok else 'HOLD',output=str(out),error=error)),flush=True)
 if not ok:raise SystemExit(1)
if __name__=='__main__':main()
