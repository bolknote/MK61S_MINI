"""HOST-only validation by default; one native LUT8 image and one inference run."""
from pathlib import Path
import argparse, errno, fcntl, json, os, re, runpy, signal, stat, struct, sys, time, traceback
ROOT=Path('/Users/bolk/Projects/MK61S_MINI')
BASE=Path(__file__).resolve().parent
helpers=runpy.run_path(str(ROOT/'.build/mk61ai/math-choice-20261111/run-benchmark.py'),run_name='lut8_helpers')
import hil_mk61_ai_perf as perf
ai,finish=perf.ai,perf.finish
sha,field=helpers['sha'],helpers['field']
UID=ai.UID
OLD_BUILD,OLD_CRC='7C38C634','8A17554E'
APPDIR='/Apps/MK61AI/HILV3-LUT8-20261111-002'
FOLDER='/AI/HILV3-M3-9943AE8536E2'
LEASE=ROOT/'.build/m0-libc-batch-20261107-v1/ROOT-PICO-LEASE-001.json'
PACKAGE=BASE/'HARDWARE-PACKAGE-003.json'
CFG=dict(kernel=2,arithmetic=1,cores=2,freeze=1,filter=0,mhz=270,prefill=2,decode=2,repeat=2,stress_ms=5000,control=2,constrained=0,prefetch=1)
STABLE=('BOOTS','SETTINGS_WRITES','SETTINGS_ERASES','RTC_SET','I2C_ABORTS','IO_ERRORS')
TELEMETRY=('I2C_TIMEOUTS','IO_I2C_RESETS','keyboard_errors')
original_ready,original_cleanup=ai.readiness,ai.cleanup_status
def normalize(s):return re.sub(r'\bPHYSICAL_KEYS=\d+','PHYSICAL_KEYS=0',s)
ai.readiness=lambda s,b,c:original_ready(normalize(s),b,c)
ai.cleanup_status=lambda s,p,f:original_cleanup(normalize(s),p,f)
def dynamic_uid():
 try:ai.PORT=helpers['binding']()['port']
 except (AssertionError,FileNotFoundError) as e:raise ValueError('UID not on CDC') from e
ai.usb_identity=dynamic_uid
class TracedSerial(ai.Serial):
 trace=None
 def pump(self,seconds=.01):
  before=len(self.data)
  try:return super().pump(seconds)
  finally:
   if self.trace and len(self.data)>before:
    with self.trace.open('ab') as stream:stream.write(self.data[before:])
ai.Serial=TracedSerial
def connect(end):
 while time.monotonic()<end:
  try:
   p=helpers['connect'](end-time.monotonic());return p
  except (ValueError,AssertionError,FileNotFoundError):time.sleep(.2)
  except OSError as e:
   if e.errno not in (errno.ENOENT,errno.ENXIO,errno.ENODEV,errno.EIO):raise
   time.sleep(.2)
 raise TimeoutError('UID-bound CDC deadline')
def counters(s):
 r={k:field(s,k) for k in STABLE+TELEMETRY[:-1]}
 m=re.search(r'KBD=(?:OK|WAIT) errors=(\d+)',s);assert m
 r['keyboard_errors']=m[1];return r
def check(s,b,c,awake=True):
 for token in ('BUILD='+b,'EXPECTED='+c,'ACTUAL='+c,'FIRMWARE_CRC=valid','BOOT_WATCHDOG=0',
               'MATH_TEST=OK failures=0','KBD=OK','PSRAM=OK BYTES=8388608','SD=OK','USB_DISK=0','SYS_HZ=125000000'):
  assert token in s,token
 if awake:assert field(s,'SLEEP')=='0'
def closed(s):return all(t in s for t in ('UI=CALCULATOR','SERVICE=CLOSED','RUNTIME=NONE'))
def bounds(p):
 raw=Path(p).read_bytes();assert raw and len(raw)%512==0
 for i in range(len(raw)//512):
  block=raw[512*i:512*(i+1)];h=struct.unpack_from('<8I',block)
  assert h[:3]==(0x0a324655,0x9e5d5157,0x2000) and h[3]==0x10000000+256*i
  assert h[4:7]==(256,i,len(raw)//512) and h[7]==0xe48bff56 and h[3]+h[4]<=0x101c0000
  assert struct.unpack_from('<I',block,508)[0]==0x0ab16f30
def validate():
 package=json.loads(PACKAGE.read_text())
 for p,d in package['pins'].items():assert sha(p)==d,p
 plan=json.loads((BASE/'PLAN-003.json').read_text())
 assert plan['config']==CFG and (plan['old_build'],plan['old_crc'])==(OLD_BUILD,OLD_CRC)
 m=json.loads(Path(plan['payloads']['firmware_manifest']['path']).read_text())
 assert plan['new_build']==m['build_id'].upper() and plan['new_crc']==m['firmware_integrity']['crc32'].upper()
 assert m['ai_fast_clock'] and m['ai_fast_math'] and not m['ai_psram_late_read']
 assert m['foreground_memory_budget']['heap_capacity_bytes']>=108544
 bounds(plan['payloads']['uf2']['path'])
 arm=json.loads((BASE/'native-arm.json').read_text());assert arm['status']=='NATIVE_ARM_ROM_PASS' and len(arm['cases'])==24
 assert arm['firmware_sha256']==sha(BASE/'firmware/mk61s-picocalc-pico-h.elf')
 assert '512-position KV exact' in (BASE/'tests/prefetch-hybrid.log').read_text()
 assert 'Native MKA repack PASS' in (BASE/'tests/repack-native.log').read_text()
 return plan
def ready(p,b,c,out,name,end):
 while time.monotonic()<end:
  s=p.status();(out/name).write_text(s)
  try:check(s,b,c);assert closed(s);return s
  except AssertionError:time.sleep(.2)
 raise TimeoutError('Native readiness deadline')
def execute(go_path):
 plan=validate();go=json.loads(go_path.read_text())
 assert go['coordinator_thread']==ai.COORDINATOR and go['uid']==UID and go['handoff_received'] is True
 assert go['package_sha256']==sha(PACKAGE) and go.get('romcache_verified') is True
 expected={k:str(v) for k,v in go['expected_counters'].items()};assert set(expected)==set(STABLE)
 assert all(v.isdigit() for v in expected.values())
 seconds=min(300,go['finish_before_utc_epoch']-time.time()-10);assert seconds>=180
 out=BASE/'hardware-002';out.mkdir(exist_ok=False);(out/'handoff.json').write_bytes(go_path.read_bytes())
 report=dict(status='HOLD',firmware_flashes=0,inference_runs=0,M3_writes=0,global_model_writes=0,
             reference_seconds_per_token=[.4277315,.442951],historical_baseline_rerun=False)
 lease=p=None;connection=[None];owned=[];prior={};touched=set();end=time.monotonic()+seconds
 try:
  lease=os.open(LEASE,os.O_RDONLY|os.O_NOFOLLOW);info=os.fstat(lease)
  assert info.st_ino==289244874 and info.st_nlink==1 and stat.S_ISREG(info.st_mode)
  fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB);TracedSerial.trace=out/'serial.bin'
  p=connect(end);finish.drain(p,maximum=3,quiet=.25)
  before=p.status();(out/'before.txt').write_text(before);check(before,OLD_BUILD,OLD_CRC,False)
  assert closed(before) and all(t in before for t in ('RUN=0','DIRTY=0','PHYSICAL_KEYS=0'))
  initial=counters(before);assert {k:initial[k] for k in STABLE}==expected
  report['entry_counters']=initial
  if field(before,'SLEEP')=='1':
   assert go.get('allow_wake_calculator') is True
   p.send(b'\x1e\x91');time.sleep(.3);check(p.status(),OLD_BUILD,OLD_CRC)
  assert counters(p.status())==initial
  p.commands();ai.identity(p)
  ai.create_owned(p,APPDIR,owned,out)
  command='ls "'+FOLDER+'"';listing=ai.listing_rows(p.command(command),command)
  assert b'f\t2093896 B\tMODEL.MKA' in listing,'Pinned private model missing'
  for leaf in ('PERF.CFG','PERF.REF','PERF.JSON'):
   if any(row.split(b'\t')[-1].upper()==leaf.encode() for row in listing):
    prior[leaf]=ai.download(p,FOLDER+'/'+leaf);(out/('prior-'+leaf)).write_bytes(prior[leaf])
  (out/'prior-perf-names.json').write_text(json.dumps(sorted(prior))+'\n')
  for leaf,key in [('AIHASH.APP','hashprobe'),('AIBENCH.APP','benchmark')]:
   ai.upload(p,APPDIR+'/'+leaf,Path(plan['payloads'][key]['path']).read_bytes(),out/'upload-fault.bin')
  for leaf,key in [('PERF.CFG','config'),('PERF.REF','reference')]:
   touched.add(leaf);ai.upload(p,FOLDER+'/'+leaf,Path(plan['payloads'][key]['path']).read_bytes(),out/'upload-fault.bin')
  probe=APPDIR+'/AIHASH.APP';p.data.clear();p.send(('run "'+probe+'"\r').encode())
  reply=p.wait(lambda d:ai.PROMPT.search(d),45);(out/'model-sha.txt').write_bytes(reply)
  digest=re.search(rb'AI_MODEL_SHA bytes=2093896 sha256=([0-9a-f]{64})',reply)
  assert digest and digest[1].decode() in plan['accepted_model_sha256'] and b'ERROR' not in reply
  report['model_sha256']=digest[1].decode();ai.leave_app(p)
  assert counters(p.status())==initial,'Counter delta during model identity probe'
  p.close();p=None;finish.flash_once(plan,out);report['firmware_flashes']=1
  p=connect(end);after=ready(p,plan['new_build'],plan['new_crc'],out,'after-flash.txt',min(end,time.monotonic()+30))
  own=counters(after);assert own['BOOTS']==str(int(initial['BOOTS'])+1),'Unexpected reboot count'
  assert field(after,'CRASH')==field(before,'CRASH'),'Retained crash changed'
  assert all(own[k]==initial[k] for k in ('SETTINGS_WRITES','SETTINGS_ERASES','RTC_SET','IO_ERRORS'))
  report['post_flash_counters']=own;report['ambient_post_flash_telemetry']={k:own[k] for k in TELEMETRY+('I2C_ABORTS',)}
  p.commands();ai.identity(p)
  assert counters(p.status())==own,'Counter delta before inference'
  app=APPDIR+'/AIBENCH.APP';connection[0]=p;report['inference_runs']=1
  touched.add('PERF.JSON');p,report['transport']=perf.run_perf(connection,plan,app,out)
  raw=ai.download(p,FOLDER+'/PERF.JSON');(out/'performance.json').write_bytes(raw);result=json.loads(raw)
  load=re.search(r'AI_LOAD bytes=2093896 us=(\d+) ok=1',(out/'progress.txt').read_text())
  assert load and int(load[1])==result['model_load_us'],'Stale report'
  assert result['device'] and result['ok'] and not result['cancelled'] and not report['transport']['app_error']
  assert result['actual_hz']==270000000 and result['restored_hz']==125000000 and result['clocks_restored'] and result['config']==CFG
  assert result['reference_external'] and result['tile_rows']==28 and result['psram_read_divider256']==461
  assert result['matching_tokens'] and result['matching_checksums']
  assert result['stress_before_decode'] and result['stress_elapsed_ms']>=5000 and result['stress_iterations']>0
  stress=result['stress_diagnostic'];assert stress['reason']=='none' and stress['crc_match'] and stress['busy_entered'] and stress['busy_exited']
  assert result['freeze_count']==result['thaw_count'] and not result['freeze_violations'] and not result['i2c_errors']
  rows=result['results'];assert len(rows)==2 and [r['pass'] for r in rows]==[1,2]
  for r in rows:
   assert r['prefill_tokens']==r['decode_tokens']==2 and r['next']==[0,1295,1295,1295]
   assert r['rows']==75776 and r['worker_rows']==37888 and r['worker_jobs']==3279 and r['prefetches']==2996 and not r['remote_jobs']
   assert (r['lut8_preparations'],r['lut8_reuses'],r['lut8_rows'])==(123,120,70656)
  assert result['sampled_heap_peak']<result['heap_capacity'] and result['stack_high_water']<32768
  report['seconds_per_token']=[r['decode_us']/r['decode_tokens']/1e6 for r in rows]
  report['faster_than_reference']=all(t<.4277315 for t in report['seconds_per_token'])
  after=p.status();(out/'after-app.txt').write_text(after);check(after,plan['new_build'],plan['new_crc'])
  assert counters(after)==own,'New counter delta during inference'
  ai.leave_app(p);p.commands()
  for leaf in sorted(touched):
   path=FOLDER+'/'+leaf
   if leaf in prior:ai.upload(p,path,prior[leaf],out/'restore-fault.bin')
   else:p.command('rm "'+path+'"',20)
  report['prior_perf_restored']=sorted(touched);touched.clear()
  for path in list(reversed(owned)):p.command('rm -r "'+path+'"',20);owned.remove(path)
  p.send(b'\x1e\x1b');time.sleep(.25)
  final=ready(p,plan['new_build'],plan['new_crc'],out,'final-status.txt',min(end,time.monotonic()+10))
  assert counters(final)==own
  report.update(status='PASS_RETAINED' if report['faster_than_reference'] else 'MEASURED',temporary_removed=True,counters_after=counters(final))
 except BaseException as e:
  report['error']=repr(e);(out/'error-trace.txt').write_text(traceback.format_exc())
 finally:
  for port in (p,connection[0]):
   if port:port.close()
  if lease is not None:os.close(lease)
  TracedSerial.trace=None;report['CDC_closed']=all(q is None or q.fd==-1 for q in (p,connection[0]));report['lease_closed']=True
  (out/'receipt.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2),flush=True)
 if report['status']=='HOLD':raise SystemExit(1)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--execute-after-handoff',type=Path);a=p.parse_args()
 if a.execute_after_handoff:
  signal.signal(signal.SIGALRM,lambda *args:(_ for _ in ()).throw(TimeoutError('Finite330s LUT8 controller')));signal.alarm(330)
  try:execute(a.execute_after_handoff)
  finally:signal.alarm(0)
 else:validate();print('HOST LUT8 package PASS; no physical I/O')
