#!/usr/bin/env python3
"""Exercise real controller cleanup after a fault with an in-memory device."""
from pathlib import Path
import argparse,json,re,shlex,sys,tempfile
import hil
class ModelBackend:
 """Protocol fixture for the real controller; no device/OS backend imported."""
 UID='HOST-ONLY-NOT-A-DEVICE'
 CORE_COUNTERS=('ERRORS','QPI_FALLBACKS','TAIL_TIMEOUTS','CRC_ERRORS','DMA_TIMEOUTS',
  'LCD_ERRORS','SD_SPEED_FALLBACKS','SD_PROBE_FAILURES','I2C_TIMEOUTS','I2C_ABORTS',
  'SCREEN_ERRORS','BATTERY_ERRORS','PHYSICAL_KEYS','SETTINGS_WRITES','RTC_SET')
 Port=write_file=read_file=wait_pattern=None
 class Hold(Exception):pass
 @staticmethod
 def need(ok,message):
  if not ok:raise ModelBackend.Hold(message)
 @staticmethod
 def field(status,key):
  if key in ('EXPECTED','ACTUAL','IMAGE'):
   lines=re.findall(r'(?m)^FIRMWARE_CRC=[^\r\n]*',status)
   ModelBackend.need(len(lines)==1,'Ambiguous CRC line');status=lines[0]
  values=re.findall(r'(?<![A-Za-z0-9_])'+re.escape(key)+r'=([^\s]+)',status)
  ModelBackend.need(len(values)==1,'Missing/ambiguous field '+key);return values[0]
 @staticmethod
 def foreground(status):
  rows=re.findall(r'(?m)^SERVICE=([A-Z_]+)[^\r\n]* PATH=\[([^\r\n\]]*)\] RESULT=\[([^\r\n\]]*)\]',status)
  ModelBackend.need(len(rows)==1,'Ambiguous foreground');return rows[0]
 @staticmethod
 def names(report):return {line.split('\t')[-1].rstrip('/\r')for line in report.splitlines()if re.match(r'^[df]\t',line)}
base=ModelBackend();hil.base=base
before=(Path(__file__).resolve().parent/'fixtures/native_status.txt').read_text()
after=before
for key in ('I2C_TIMEOUTS','IO_I2C_RESETS'):
 after,count=re.subn(r'(?<![A-Za-z0-9_])'+key+r'=\d+',key+'=2',after)
 assert count==1
bad_keyboard,count=re.subn(r'(?<![A-Za-z0-9_])KBD=OK','KBD=FAIL',after);assert count==1

class Port:
 def __init__(self,g):
  self.g=g;self.closed=False;self.text=bytearray();self.launched=False
  self.folder=False;self.file=False;self.data=None;self.commands_seen=[];self.reads=0
  g.port=self
 def __enter__(self):return self
 def __exit__(self,*args):self.closed=True
 def status(self):return (bad_keyboard if self.g.bad_keyboard else after) if self.launched else before
 def commands(self):pass
 def command(self,line,**kwargs):
  self.commands_seen.append(line);args=shlex.split(line)
  if args==['identity']:return 'UID='+base.UID
  if args==['ls','/']:return 'd\t0\tKEEP\n'+('d\t0\t'+hil.FOLDER[1:]+'\n' if self.folder else '')
  if args==['mkdir',hil.FOLDER]:assert not self.folder;self.folder=True;return ''
  if args==['ls',hil.FOLDER]:return 'f\t1\tFASTLINK.APP\n' if self.file else ''
  if args==['rm',hil.APP]:assert self.file;self.file=False;return ''
  if args==['rmdir',hil.FOLDER]:assert self.folder and not self.file;self.folder=False;return ''
  raise AssertionError(args)
 def send(self,data):
  assert data==('open "'+hil.APP+'"\r').encode() and not self.launched
  self.launched=True;self.text.extend(b'FL FAIL code=-40 cases=9 bytes=216 uart_errors=0 resources_released=1\n')
 def pump(self,*args):pass

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,default=hil.KIT/'controller-test.json');args=ap.parse_args()
 native_frames=0
 for boundary,name in hil.NATIVE_BOUNDARIES.items():
  frame=(f'FL NATIVE_FAIL case=8 boundary={boundary} previous_boundary=1\n'
   'FL NATIVE_BEFORE at=1 timeouts=7 resets=7 aborts=0 errors=7 stage=2 result=1 pending=0 phase=1 online=1\n'
   'FL NATIVE_AFTER at=2 timeouts=8 resets=8 aborts=0 errors=8 stage=0 result=-2 pending=0 phase=0 online=0\n').encode()
  found=hil.native_observation(frame);assert found['boundary_name']==name and found['after']['result']==-2
  assert found['before']['timeouts']==7 and found['after']['timeouts']==8;native_frames+=1
 for bad in (frame.rsplit(b'FL NATIVE_AFTER',1)[0],frame+frame,frame.replace(b'boundary=9 ',b'boundary=99 ')):
  try:hil.native_observation(bad);raise AssertionError('Invalid native frame accepted')
  except base.Hold:pass
  native_frames+=1
 accepted=hil.native_health(before,closed=True)
 assert accepted==before and base.field(accepted,'BOOT_WATCHDOG')=='0' and base.field(accepted,'CRASH')=='AVAILABLE'
 admission_cases=1
 baseline={k:base.field(before,k)for k in ('BOOTS','BOOT_WATCHDOG','RESET_REASON','CRASH')}
 hil.native_health(before,baseline,closed=True);admission_cases+=1
 for key,value in (('BOOTS','18'),('BOOTS','20'),('BOOT_WATCHDOG','1'),('BOOT_WATCHDOG','2'),('RESET_REASON','00000000'),
                   ('CRASH','NONE'),('CRASH','FAULT'),('ACTUAL','00000000'),('KBD','FAIL')):
  changed,count=re.subn(r'(?<![A-Za-z0-9_])'+key+r'=[^\s]+',key+'='+value,before)
  assert count==1
  try:hil.native_health(changed,baseline,closed=True);raise AssertionError('Bad admission passed '+key)
  except base.Hold:pass
  admission_cases+=1
 originals={name:getattr(base,name)for name in ('Port','write_file','read_file','wait_pattern')}
 try:
  base.Port=Port
  def write(port,path,data):assert path==hil.APP;port.data=data;port.file=True
  def read(port,path):
   assert path==hil.APP and port.file;port.reads+=1
   return port.data+b'corrupt' if port.g.corrupt and port.reads>1 else port.data
  base.write_file=write;base.read_file=read;base.wait_pattern=lambda *args:None
  for corrupt,bad_keys in ((False,False),(True,False),(False,True)):
   with tempfile.TemporaryDirectory(prefix='cleanup-policy-') as tmp:
    hil.KIT=Path(tmp)/'kit';(hil.KIT/'app').mkdir(parents=True)
    (hil.KIT/'app/FASTLINK.APP').write_bytes(b'HOST-ONLY-SYNTHETIC-APP')
    class Gate:pass
    g=Gate();g.out=Path(tmp);g.final={};g.corrupt=corrupt;g.bad_keyboard=bad_keys
    try:hil.run(g);raise AssertionError('Faulted test was incorrectly accepted')
    except base.Hold as exc:
     assert ('Owned APP changed' if corrupt else 'RAM link probe failed') in str(exc)
    assert g.port.closed and g.final['CDC_closed'] and g.final['CLOSED']
    if corrupt:
     assert g.port.file and g.port.folder and not any(c.startswith('rm ')for c in g.port.commands_seen)
    else:
     assert not g.port.file and not g.port.folder and g.final['owned_sd_removed']
     assert ('KBD' if bad_keys else 'I2C_TIMEOUTS') in g.final['final_qualification_error']
    assert sum(c.startswith('open ')for c in g.port.commands_seen)==0 # one send, no retry/launch in cleanup
 finally:
  for key,value in originals.items():setattr(base,key,value)
 assert 'current_hil'not in sys.modules and'device_guard'not in sys.modules
 result=dict(status='PASS',physical_io=False,synthetic_status_and_APP=True,negative_cleanup_cases=3,scoped_admission_cases=admission_cases,
  archived_hardware_backend_imported=False,
  native_boundary_frame_cases=native_frames,
  original_watchdog_text_preserved=True,preexisting_crash_text_preserved=True,new_reset_rejected=True,
  counter_fault_stays_failure=True,owned_exact_cleanup_completes=True,changed_owned_file_preserved=True)
 args.output.parent.mkdir(parents=True,exist_ok=True)
 args.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':main()
