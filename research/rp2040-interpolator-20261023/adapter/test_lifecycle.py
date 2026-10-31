#!/usr/bin/env python3
"""Wire-level hardware fakes, actual accepted framing/CRC/put/get and lifecycle."""
import argparse
import copy
from datetime import datetime,timezone
import importlib.util
import json
from pathlib import Path
import re
import sys
from lifecycle import Accepted,Wire,Lifecycle,FULL_FIELDS,ROOT,UID,BUILD,DIRECTORY,PACKET,PACKET_SHA,REFERENCE_SHA,sha,hardware_requirements,verified_apps

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True);args=ap.parse_args()
 output=args.output.resolve();output.mkdir(parents=True,exist_ok=False)
 a=Accepted();modules=a.cdc_modules()
 from hil_usb_disk_transaction import posix_cksum
 fixture=a.library/'review/status-fixtures/completion-fresh-status.txt'
 expected=json.loads((a.library/'pins.json').read_text())[str(fixture.relative_to(a.library))]
 assert sha(fixture.read_bytes())==expected
 good=fixture.read_bytes();a.core.assert_idle(good.decode(),BUILD);a.core.assert_health(good.decode(),BUILD,'C0A51996',754344)
 spec=importlib.util.spec_from_file_location('_interp_frozen_v2_decode',PACKET/'source/decode.py');decoder=importlib.util.module_from_spec(spec);spec.loader.exec_module(decoder)
 apps=verified_apps()

 class FakePort:
  def __init__(self,fault):
   self.fault=fault;self.text=bytearray();self.commands=[];self.closed=False;self.apps=0;self.stage='initial';self.put=None
   self.app_running=False;self.wait_calls=0;self.commands_at_app_entry=None
   self.dirs={'/','/Original'};self.files={'/Original/Hidden.bin':b'private\x00bytes','/Original/Large.bin':bytes(range(256))*300}
   self.original_files=copy.deepcopy(self.files);self.original_dirs=set(self.dirs)
   self.attributes={'/':0x10,'/Original':0x10,'/Original/Hidden.bin':0x22,'/Original/Large.bin':0x20}
   self.calc={k:['nondefault',i,17] for i,k in enumerate(sorted(FULL_FIELDS))};self.calc['return_stack']=[77,33,91];self.calc['bank_map']=[2,0,1]
   self.calc_before=copy.deepcopy(self.calc)
   self.env=dict(rtc='2026-10-23T12:00:00',rtc_set=0,settings={'font':'custom','layout':2,'speed':1},alarms={'A':'OFF','B':'ONCE'},cwd='/Original')
   self.env_before=copy.deepcopy(self.env);self.restore_attempted=False;self.environment_attempted=False
   if fault=='collision':self.dirs.add('/intrp01');self.original_dirs.add('/intrp01')
  def canonical(self,path):
   candidates=[p for p in [*self.files,*self.dirs] if p.casefold()==path.casefold()]
   assert len(candidates)<=1,candidates
   return candidates[0] if candidates else None
  def status(self):
   assert not self.app_running,'Status query sent into a running APP'
   frame=good
   if self.stage=='initial' and self.fault=='bad_first_good_later':frame=good.replace(b'CRASH=NONE',b'CRASH=HARDFAULT')+good
   elif self.stage=='initial' and self.fault=='truncated_first':frame=good[:80]+good
   self.stage='connected';self.text+=frame
   result=a.frames.first_complete_frame(frame)
   if result is None:raise TimeoutError('Mock incomplete status')
   return result
  def command(self,line,timeout=30):
   assert not self.app_running,'Terminal command sent into a running APP'
   del timeout
   self.commands.append(line);reply=''
   if line=='identity':reply='UID='+('0000000000000000' if self.fault=='wrong_uid' else UID)+'\r\n'
   elif line=='crash show':reply='CRASH=NONE\r\n'
   elif line.startswith('ls '):
    if self.fault=='cleanup_error' and self.stage=='finally':raise OSError('Mock cleanup transport failure')
    path=line[3:].strip('"');canonical=self.canonical(path);assert canonical in self.dirs,path
    rows=[]
    for d in sorted(self.dirs):
     if d!='/' and str(Path(d).parent)==canonical:rows.append('d\t'+Path(d).name+'/')
    for p,data in sorted(self.files.items()):
     if str(Path(p).parent)==canonical:rows.append('f\t'+str(len(data))+'\t'+Path(p).name)
    reply='\r\n'.join(rows+[str(len(rows))+' '+('entry.' if len(rows)==1 else 'entries.')])+'\r\n'
   elif line.startswith('mkdir '):
    path=line[6:].strip('"');assert self.canonical(path) is None;self.dirs.add(path)
   elif line.startswith('fsput begin '):
    match=re.fullmatch(r'fsput begin "([^"]+)" (\d+) (\d+)',line);assert match,line
    path,n,crc=match[1],int(match[2]),int(match[3]);self.put=[path,n,crc,bytearray()];reply=f'@MKC:READY {n}\r\n'
   elif line.startswith('fsput data '):
    _,_,offset,hexdata=line.split();assert self.put is not None and int(offset)==len(self.put[3]);self.put[3]+=bytes.fromhex(hexdata);reply=f'@MKC:ACK {len(self.put[3])}\r\n'
   elif line=='fsput end':
    path,n,crc,data=self.put;assert len(data)==n and posix_cksum(bytes(data))==crc
    if path.endswith('.APP'):path=path[:-4]+'.app'
    self.files[path]=bytes(data);self.put=None;reply=f'@MKC:DONE {n} {crc}\r\n'
   elif line=='fsput cancel':self.put=None
   elif line.startswith('fsget '):
    path=line[6:].strip('"');path=self.canonical(path);assert path in self.files,path;data=self.files[path];crc=posix_cksum(data)
    if self.fault=='bad_crc' and path.endswith('MARKER.bin'):crc^=1
    rows=[f'@MKC:GET {len(data)} {crc}']
    for off in range(0,len(data),32):rows.append(f'@MKC:DATA {off} '+data[off:off+32].hex())
    rows.append(f'@MKC:END {len(data)} {crc}');reply='\r\n'.join(rows)+'\r\n'
   elif line.startswith('rm '):
    path=self.canonical(line[3:].strip('"'));assert path is not None
    if path in self.files:del self.files[path]
    else:assert not any(str(Path(p).parent)==path for p in [*self.files,*self.dirs] if p!=path);self.dirs.remove(path)
   else:raise AssertionError(('Unknown hardware command',line))
   reply+='mk61> ';self.text+=reply.encode();return reply
  def open(self,path):
   assert self.canonical(path) in self.files
   if self.fault=='app_active_stale_prompt':self.text+=b'\r\nmk61> '
   self.open_text_start=len(self.text)
   self.app_running=True;self.commands_at_app_entry=len(self.commands)
   variant=next(v for v,d in apps.items() if Path(path).stem==d['name']);self.apps+=1
   # Visible register/stack/program strings would stay unchanged. Hidden
   # state changes reproduce why a legacy partial restore cannot be used.
   self.calc['bank_map']=[0,0,0];self.calc['return_stack']=[];self.calc['input_flags']=0;self.calc['handlers']={}
   self.env['rtc_set']=1;self.env['settings']['speed']=99;self.env['alarms']['A']='ONCE'
   data=(PACKET/'protocol'/variant/'synthetic-result.bin').read_bytes()
   if self.fault=='bad_result':data=bytes([data[0]^1])+data[1:]
   if self.fault=='oversized_result':data=bytes(70000)
   self.files[DIRECTORY+'/RESULT.bin']=data
   if self.fault=='unknown_file':self.files[DIRECTORY+'/UNKNOWN.bin']=b'preserve this'
   if self.fault=='changed_owned':self.files[self.canonical(path)]+=b'changed'
   if self.fault=='attributes_changed':self.attributes['/Original/Hidden.bin']=0x02
   if self.fault in ('app_active_timeout','app_active_stale_prompt','app_late_return','app_output_fake_prompt'):
    if self.fault=='app_output_fake_prompt':self.text+=b'APP text contains mk61> '
    return
   self.app_running=False;self.text+=b'APP_FLOW_RESULT=0\r\nmk61> '
   if self.fault=='app_timeout':raise TimeoutError('Mock APP completion timeout')
  def wait_text(self,expected,start,timeout):
   self.wait_calls+=1
   if self.app_running:
    if self.fault=='app_late_return' and self.wait_calls>1:
     self.app_running=False;self.text+=b'APP_FLOW_RESULT=0\r\nmk61> '
    elif expected not in self.text[start:]:raise TimeoutError('Mock APP is still running; no fresh prompt')
   assert expected in self.text[start:]
  def __exit__(self,*unused):self.closed=True

 class Preservation:
  def __init__(self,p):self.port=p
  def capture_full(self,w):
   coverage=FULL_FIELDS-{'return_stack'} if self.port.fault=='partial_state' else FULL_FIELDS
   return dict(coverage=sorted(coverage),fresh=self.port.fault!='stale_state',uid=UID,build=BUILD,data=json.dumps(self.port.calc,sort_keys=True).encode())
  def capture_environment(self,w):return copy.deepcopy(self.port.env)
  def capture_all_sd(self,w):return dict(fresh=self.port.fault!='stale_all_anchor',complete=True,includes_hidden_and_large=True,uid=UID,build=BUILD,
    files={p:sha(b) for p,b in self.port.files.items()},dirs=sorted(self.port.dirs),fat_attributes=copy.deepcopy(self.port.attributes))
  def verify_all_sd(self,w,before):
   self.port.stage='finally'
   if self.port.fault=='sd_verify_error':raise OSError('Mock ALL-SD verification failure')
   assert before['files']=={p:sha(b) for p,b in self.port.files.items()} and before['dirs']==sorted(self.port.dirs) and before['fat_attributes']==self.port.attributes
  def restore_environment(self,w,before):
   self.port.environment_attempted=True
   if self.port.fault=='environment_error':raise OSError('Mock environment restore failure')
   self.port.env=copy.deepcopy(before)
  def verify_environment(self,w,before):assert self.port.env==before
  def restore_full(self,w,before):
   self.port.restore_attempted=True
   if self.port.fault=='full_restore_error':raise OSError('Mock full-state restore failure')
   self.port.calc=json.loads(before['data'])
   if self.port.fault=='full_restore_changes_env':self.port.env['rtc_set']=1
  def verify_full(self,w,before):assert self.port.calc==json.loads(before['data'])

 cases=[]
 for fault in ('normal','wrong_uid','bad_first_good_later','truncated_first','partial_state','collision',
  'bad_crc','app_timeout','bad_result','unknown_file','changed_owned','cleanup_error','sd_verify_error','environment_error',
  'full_restore_error','full_restore_changes_env','evidence_error','journal_error','attributes_changed','stale_state','stale_all_anchor',
  'invalid_app_name','oversized_result','app_active_timeout','app_active_stale_prompt','app_late_return','app_output_fake_prompt'):
  selected=copy.deepcopy(apps)
  if fault=='invalid_app_name':selected['alu']['name']='../IALU'
  p=FakePort(fault);w=Wire(a,lambda:p);life=Lifecycle(a,w,Preservation(p),output/fault,selected,
   lambda raw,v:decoder.decode(raw,physical=False,expected_rounds=2,expected_samples=4,variant=v))
  # Trigger cleanup transport failure at the point where cleanup starts.
  cleanup=life.cleanup
  def cleanup_stage():p.stage='finally';return cleanup()
  life.cleanup=cleanup_stage
  original_evidence=life.evidence;original_save=life.save
  if fault=='evidence_error':
   def bad_evidence(name,data):
    if name=='received-before-finally.bin':raise OSError('Mock evidence disk full')
    return original_evidence(name,data)
   life.evidence=bad_evidence
  if fault=='journal_error':
   def bad_save():
    if p.stage=='finally':raise OSError('Mock journal disk full')
    return original_save()
   life.save=bad_save
  result=life.execute()
  assert p.closed and result['serial_closed'],fault
  assert all(p.files.get(k)==v for k,v in p.original_files.items()),(fault,'original user bytes changed')
  assert not any(re.match(r'(dfu|reset|format|disk|flash|rm -)',s) for s in p.commands)
  if fault=='normal':
   assert result['status']=='PASS' and p.calc==p.calc_before and p.env==p.env_before
   assert p.files==p.original_files and p.dirs==p.original_dirs
  else:
   assert result['status']=='HOLD',fault
   unsafe=fault in ('app_active_timeout','app_active_stale_prompt','app_output_fake_prompt')
   if fault not in ('wrong_uid','bad_first_good_later','truncated_first','partial_state','stale_state') and not unsafe:
    assert p.restore_attempted and p.environment_attempted,(fault,'finally restoration was skipped')
   if fault!='full_restore_error' and not unsafe:assert p.calc==p.calc_before,(fault,'hidden state not restored')
   if unsafe:
    assert p.app_running and not p.restore_attempted and not p.environment_attempted
    assert len(p.commands)==p.commands_at_app_entry,'Sent a command after an unacknowledged APP timeout'
    assert result['manual_recovery_required'] and result['pending_restoration'] and not result['command_channel_available']
    assert (output/fault/'calculator-before.bin').is_file() and (output/fault/'received-before-finally.bin').is_file()
    for operation in (lambda:w.status(),lambda:w.command('identity'),lambda:w.read('/Original/Hidden.bin'),lambda:w.upload('/INTRP01/X.bin',b'x')):
     try:operation()
     except RuntimeError as error:assert 'APP has no acknowledged return' in str(error)
     else:raise AssertionError('Wire allowed a command into an unreturned APP')
    assert len(p.commands)==p.commands_at_app_entry
   if fault in ('unknown_file','changed_owned','bad_crc','cleanup_error'):assert any(k.startswith(DIRECTORY+'/') for k in p.files),'Unknown/changed files removed'
   if fault in ('app_timeout','app_late_return'):assert (output/fault/'alu-RESULT.bin').is_file(),'Lost raw failed APP result'
   if fault=='bad_first_good_later':
    assert b'CRASH=HARDFAULT' in (output/fault/'initial-first-status.txt').read_bytes() and not p.commands
   if fault=='truncated_first':assert (output/fault/'initial-received.bin').read_bytes()==good[:80]+good and not p.commands
   if fault=='oversized_result':assert not any(s.startswith('fsget ') and 'RESULT.bin' in s for s in p.commands)
  cases.append(dict(case=fault,status=result['status'],serial_closed=True,original_user_bytes_preserved=True,
   full_restore_attempted=p.restore_attempted,command_channel_available=result.get('command_channel_available'),
   manual_recovery_required=result.get('manual_recovery_required',False),
   primary_failure=result['primary_failure'],finally_failures=result['finally_failures']))
  print('PASS',fault,flush=True)
 template=json.loads((Path(__file__).parent/'bindings.template.json').read_text())
 hold=hardware_requirements(template);assert hold['status']=='HELD' and not hold['port_opened'] and len(hold['missing'])==5
 report=dict(status='PASS_OFFLINE',hardware_verified=False,hardware_constructor_called=False,cases=cases,
  transport_reference_sha256=REFERENCE_SHA,candidate_manifest_sha256=PACKET_SHA,
  accepted_python_pins_sha256=sha(Path(a.reference['library_root']).joinpath('pins.json').read_bytes()),
  source_sha256={name:sha(Path(__file__).resolve().parent.joinpath(name).read_bytes()) for name in
   ('lifecycle.py','test_lifecycle.py','bindings.template.json')},
  scope='Real lifecycle/finally/ownership logic and exact accepted frame/put/get/POSIX-CRC code; only physical CDC, APP execution and incomplete full-state/ALL-SD provider are faked. The null hardware bindings are not implemented by these fakes.')
 (output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(dict(status=report['status'],cases=len(cases),hardware_verified=False,missing_hardware_bindings=hold['missing']),indent=2))
if __name__=='__main__':main()
