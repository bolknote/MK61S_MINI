#!/usr/bin/env python3
"""Separate APP-only lifecycle; V2 arithmetic artifacts remain immutable.

This module has no Flash/reset path. A hardware invocation is HELD before a
port is constructed until reviewed full-state, ALL-SD and fresh lease bindings
exist. Tests inject a wire-level fake, but execute this preservation/finally
logic and the accepted CDC frame/put/get/CRC code.
"""
import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path
import re
import select
import sys
import time

HERE=Path(__file__).resolve().parent
# This is a pinned transaction on this host. Keep snapshot/source copies
# executable without silently resolving dependencies in a different checkout.
ROOT=Path('/Users/bolk/Projects/MK61S_MINI')
REFERENCE=ROOT/'.build/finish-picocalc-v138-20261023/PICO-APP-TRANSPORT-REUSE-REFERENCE.json'
REFERENCE_SHA='bf1f1eabc52233f8b364c4eec56f98f1e442ebe369f97471f396b7bd156a12ae'
PACKET=ROOT/'.build/rp2040-interpolator-20261023/packet-v2'
PACKET_SHA='849885aa360bf83cd45f21163a3079ba37b78c34fcd4dd9e822bea32197eccf0'
UID='E6657CD423721C35';BUILD='A7483AE6';DIRECTORY='/INTRP01'
FULL_FIELDS=frozenset(('register_banks','stack_last_x','program','bank_map','return_stack',
 'input_flags','handlers','ip','terminal_mode','ui_mode'))

def sha(data):return hashlib.sha256(data).hexdigest()
def require(condition,message):
 if not condition:raise RuntimeError(message)

def verified_apps():
 manifest=PACKET/'packet-manifest.json'
 require(sha(manifest.read_bytes())==PACKET_SHA,'Immutable V2 manifest changed')
 pins=json.loads(manifest.read_text())['files']
 for name,pin in pins.items():
  path=(PACKET/name).resolve()
  require(path.is_relative_to(PACKET) and not (PACKET/name).is_symlink() and
   path.stat().st_size==pin['bytes'] and sha(path.read_bytes())==pin['sha256'],'Frozen V2 artifact changed: '+name)
 return {v:dict(name=n,path=str(PACKET/'apps'/v/(n+'.APP')),sha256=pins['apps/'+v+'/'+n+'.APP']['sha256'])
  for v,n in (('alu','IALU'),('rsqrt','IRSQ'),('sqrt','ISQRT'),('address','IADDR'))}

class Accepted:
 """Validate the exact reference before importing its pure/CDC components."""
 def __init__(self):
  require(sha(REFERENCE.read_bytes())==REFERENCE_SHA,'Transport reference changed')
  self.reference=json.loads(REFERENCE.read_text());self.library=Path(self.reference['library_root'])
  for row in self.reference['components']:
   path=Path(row['path']);require(path.is_relative_to(self.library) and sha(path.read_bytes())==row['sha256'],'Accepted component changed: '+str(path))
  pins=self.library/'pins.json';require(sha(pins.read_bytes())==self.reference['pins_sha256'],'Accepted transitive pins changed')
  self.python_pins={name:value for name,value in json.loads(pins.read_text()).items() if name.endswith('.py')}
  for name,value in self.python_pins.items():
   path=(self.library/name).resolve();require(path.is_relative_to(self.library) and sha(path.read_bytes())==value,'Accepted Python dependency changed: '+name)
  sys.path[:0]=[str(self.library),str(self.library/'frozen/tests'),str(self.library/'frozen/tools')]
  for name in ('transaction_core','status_frames'):
   module=importlib.import_module(name)
   require(Path(module.__file__).resolve()==self.library/(name+'.py'),'Unpinned import: '+name)
   setattr(self,name,module)
  self.frames=self.status_frames;self.core=self.transaction_core
 def cdc_modules(self):
  # No constructor or port open occurs while importing these modules.
  modules={n:importlib.import_module(n) for n in ('hil_m0_math_compare','transfer','hil_c5_stack','device_port')}
  for n,m in modules.items():
   expected=self.library/('device_port.py' if n=='device_port' else 'frozen/tests/'+n+'.py')
   require(Path(m.__file__).resolve()==expected,'Wrong CDC import: '+n)
  return modules

class Wire:
 """Concrete accepted protocol adapter; port construction is supplied after guards."""
 def __init__(self,accepted,port_factory):
  self.a=accepted;self.factory=port_factory;self.p=None;self.command_ready=True;self.app_start=None
 def open(self):self.p=self.factory();return self
 @property
 def raw(self):return bytes(self.p.text) if self.p is not None else b''
 @property
 def passive_raw(self):return bytes(getattr(self.p,'interp_received',b'')) if self.p is not None else b''
 def require_command_channel(self):
  require(self.command_ready,'APP has no acknowledged return; transmitting commands is unsafe')
 def status(self):self.require_command_channel();return self.p.status()
 def command(self,text,timeout=30):
  self.require_command_channel()
  require(not re.match(r'(?i)\s*(dfu|reboot|reset|format|flash|disk|warm_reset)\b',text),'Forbidden lifecycle command')
  require(not re.match(r'(?i)\s*rm\s+-',text),'Recursive/flagged cleanup is forbidden')
  return self.p.command(text,timeout=timeout)
 def upload(self,path,data):
  self.require_command_channel();self.a.cdc_modules()['transfer'].write_file(self.p,path,data)
 def read(self,path):
  self.require_command_channel();return self.a.cdc_modules()['hil_c5_stack'].read_file(self.p,path)
 def listing(self,path):return self.a.core.parse_listing(self.command('ls '+self.a.core.quoted(path,True),60),path)
 def mkdir(self,path):require('ERROR' not in self.command('mkdir '+self.a.core.quoted(path)),'mkdir failed')
 def remove(self,path):require('ERROR' not in self.command('rm '+self.a.core.quoted(path)),'point removal failed')
 def run_app(self,path):
  self.require_command_channel();self.command_ready=False;self.app_start=None
  before=len(self.p.text)
  try:self.p.open(path)
  finally:
   # ScreenPort.open pumps a pending terminal tail before sending `open`.
   # Its own boundary excludes that old prompt, even if open/wait raises.
   boundary=getattr(self.p,'open_text_start',None)
   if isinstance(boundary,int) and before<=boundary<=len(self.p.text):self.app_start=boundary
  self.recover_command_channel(timeout=180)
  return bytes(self.p.text),self.app_start
 def recover_command_channel(self,timeout=5):
  if self.command_ready:return
  require(self.app_start is not None,'No trustworthy APP exchange boundary')
  # The adapter's FramedMathPort.pump is always receive-only, including after
  # an asynchronous valid CAPS packet changes the host's attached flag.
  self.p.wait_text(b'mk61> ',self.app_start,timeout=timeout)
  require(re.search(rb'(?:^|[\r\n])mk61> \Z',self.raw[self.app_start:]) is not None,'No complete fresh command prompt')
  self.command_ready=True
 def close(self):
  if self.p is not None:
   self.p.__exit__(None,None,None)
   require(getattr(self.p,'fd',-1)==-1 and getattr(self.p,'lock_fd',-1)==-1,'Port or exclusive lock remains open')

def accepted_port_type(accepted):
 """The exact accepted parent/lock/parser; defining it never opens a port."""
 parent=accepted.cdc_modules()['hil_m0_math_compare'].MathPort
 class FramedMathPort(parent):
  def status(self,timeout=5):return accepted.frames.acquire_status(self,timeout)
  def send(self,*args,**kwargs):
   raise RuntimeError('Screen packet TX is disabled in the APP-only adapter')
  def pump(self,duration=.05):
   # Keep the pinned frame decoder; replace only the receive loop. The
   # parent's loop can start transmitting pings after a late CAPS packet.
   # There is deliberately no send/write/keepalive path in this override.
   if not hasattr(self,'interp_received'):self.interp_received=bytearray()
   deadline=time.monotonic()+duration
   while time.monotonic()<deadline:
    ready,_,_=select.select([self.fd],[],[],min(.03,max(0,deadline-time.monotonic())))
    if not ready:continue
    incoming=os.read(self.fd,8192);self.interp_received.extend(incoming)
    for byte in incoming:
     if byte==0:
      if self.packet is None:self.packet=bytearray()
      elif self.packet:self.receive_packet(self.packet);self.packet=None
     elif self.packet is None:self.text.append(byte)
     else:self.packet.append(byte)
 return FramedMathPort

def hardware_requirements(bindings):
 """These null entries are actual missing implementations, not user approvals."""
 missing=[k for k in ('exclusive_lease','post_cold_anchor','full_calculator_provider','all_sd_provider','environment_provider') if not bindings.get(k)]
 return dict(status='HELD' if missing else 'BINDINGS_REQUIRE_REVIEW',missing=missing,port_opened=False,
  reason='A verified reg/stk/hout/dump/IP restore is insufficient for bankmap/returnstack/input flags/handlers. No Reader.install guard is bypassed.')

class Lifecycle:
 def __init__(self,accepted,wire,preservation,output,apps,admit):
  self.a=accepted;self.w=wire;self.p=preservation;self.output=Path(output);self.apps=apps;self.admit=admit
  self.state=dict(status='RUNNING',primary_failure=None,finally_failures=[],owned={},directory_created=False,serial_closed=False)
  self.output.mkdir(parents=True,exist_ok=False)
 def save(self):self.a.core.atomic_json(self.output/'receipt.json',self.state)
 def evidence(self,name,data):self.a.core.atomic_bytes(self.output/name,data)
 def status(self,label,boots=None):
  try:frame=self.w.status()
  finally:self.evidence(label+'-received.bin',self.w.raw)
  self.evidence(label+'-first-status.txt',frame.encode())
  # A partial previous line can hide a second complete header from the
  # accepted parser's line-anchored START expression. Retain and reject that
  # merged first frame rather than treating the later healthy tail as fresh.
  headers=re.findall(r'RESET_REASON=[0-9A-F]{8} BOOTS=\d+ CRASH=\S+ BUILD=[0-9A-F]{8}',frame)
  require(len(headers)==1,'Interleaved/embedded first status header')
  # The first complete frame must survive even when a later frame is healthy.
  self.a.frames.assert_observed_status_faults(self.w.raw)
  self.a.core.assert_idle(frame,BUILD);self.a.core.assert_health(frame,BUILD,'C0A51996',754344)
  if boots is not None:require(self.a.core.field(frame,'BOOTS')==boots,'Unexpected reboot')
  return frame
 def create_file(self,name,data):
  require(re.fullmatch(r'[A-Z0-9_]{1,8}\.(APP|bin)',name) is not None,'Unowned/unsafe APP filename')
  require(isinstance(data,bytes) and 0<len(data)<=65534,'Unbounded public upload')
  path=DIRECTORY+'/'+name
  require(not any(e['path'].casefold()==path.casefold() for e in self.w.listing(DIRECTORY)),'Owned target already exists')
  self.state['owned'][path]=dict(planned=True,sha256=sha(data),bytes=len(data),canonical=None);self.save()
  self.w.upload(path,data)
  entries=[e for e in self.w.listing(DIRECTORY) if e['path'].casefold()==path.casefold()]
  require(len(entries)==1 and entries[0]['kind']=='file','Unknown canonical uploaded path')
  actual=entries[0]['path'];require(self.w.read(actual)==data,'Upload readback differs')
  self.state['owned'][path]['canonical']=actual;self.save()
  return actual
 def capture_result(self,variant):
  entries=[e for e in self.w.listing(DIRECTORY) if e['path'].casefold()==(DIRECTORY+'/RESULT.bin').casefold()]
  require(len(entries)==1 and entries[0]['kind']=='file' and 0<entries[0]['bytes']<=65534,'Missing/ambiguous/unbounded APP result')
  path=entries[0]['path'];data=self.w.read(path)
  self.evidence(variant+'-RESULT.bin',data)
  self.state['owned'][DIRECTORY+'/RESULT.bin']=dict(planned=True,sha256=sha(data),bytes=len(data),canonical=path,creator=variant)
  self.save();return data
 def remove_known(self,key):
  row=self.state['owned'][key];path=row['canonical']
  require(path is not None,'Incomplete upload path preserved')
  actual=self.w.read(path);require(sha(actual)==row['sha256'] and len(actual)==row['bytes'],'Changed owned bytes preserved')
  self.w.remove(path);del self.state['owned'][key];self.save()
 def cleanup(self):
  if not self.state['directory_created']:return
  entries=self.w.listing(DIRECTORY)
  known={r['canonical'] for r in self.state['owned'].values() if r['canonical'] is not None}
  require(all(e['kind']=='file' and e['path'] in known for e in entries),'Unknown objects preserved in owned directory')
  # Verify all objects before the first deletion, including exact case/bytes.
  for row in self.state['owned'].values():
   require(row['canonical'] is not None,'Incomplete upload preserved')
   actual=self.w.read(row['canonical']);require(sha(actual)==row['sha256'],'Changed owned object preserved')
  for key in list(self.state['owned']):self.remove_known(key)
  require(not self.w.listing(DIRECTORY),'Owned directory is not empty')
  self.w.remove(DIRECTORY);self.state['directory_created']=False;self.save()
 def execute(self):
  full=environment=all_sd=None;opened=False;boots=None
  try:
   self.w.open();opened=True
   first=self.status('initial');boots=self.a.core.field(first,'BOOTS')
   require('TERMINAL=COMMAND' in first,'Require already acknowledged command mode; never change mode before full capture')
   identity=self.w.command('identity');self.evidence('identity.txt',identity.encode());require('UID='+UID in identity,'Wrong UID')
   crash=self.w.command('crash show');self.evidence('crash.txt',crash.encode());require('CRASH=NONE' in crash,'Retained crash evidence')
   candidate=self.p.capture_full(self.w)
   require(FULL_FIELDS<=set(candidate['coverage']) and candidate['fresh'] and candidate['uid']==UID and candidate['build']==BUILD,'Incomplete/stale full calculator snapshot')
   require(isinstance(candidate['data'],bytes) and 0<len(candidate['data'])<=65536,'Invalid full-state bytes')
   self.evidence('calculator-before.bin',candidate['data']);full=candidate
   self.state['calculator_sha256']=sha(full['data']);self.save()
   environment=self.p.capture_environment(self.w)
   self.a.core.atomic_json(self.output/'environment-before.json',environment)
   candidate_sd=self.p.capture_all_sd(self.w)
   require(candidate_sd['fresh'] and candidate_sd['complete'] and candidate_sd['includes_hidden_and_large'] and candidate_sd['uid']==UID and candidate_sd['build']==BUILD,'Missing fresh complete ALL-SD anchor')
   all_sd=candidate_sd
   self.a.core.atomic_json(self.output/'sd-before.json',all_sd)
   require(not any(e['path'].casefold()==DIRECTORY.casefold() for e in self.w.listing('/')),'Namespace collision')
   self.state['directory_planned']=DIRECTORY;self.save();self.w.mkdir(DIRECTORY);self.state['directory_created']=True;self.save()
   self.create_file('MARKER.bin',b'\0')
   for variant,app in self.apps.items():
    data=Path(app['path']).read_bytes();require(sha(data)==app['sha256'],'Frozen APP changed')
    target=self.create_file(app['name']+'.APP',data)
    self.status(variant+'-before',boots)
    before=len(self.w.raw);self.state['active_app']=variant;self.save()
    self.w.run_app(target)
    raw=self.w.raw[before:];self.evidence(variant+'-run.bin',raw)
    # Fetch a raw failure result before health/admission/cleanup can fail.
    result=self.capture_result(variant)
    require(raw.count(b'APP_FLOW_RESULT=0')==1 and b'APP returned an error' not in raw,'APP did not return successfully')
    self.status(variant+'-after',boots)
    report=self.admit(result,variant)
    self.a.core.atomic_json(self.output/(variant+'-decoded.json'),report)
    self.state.setdefault('completed',[]).append(variant);self.state.pop('active_app',None);self.save()
    self.remove_known(DIRECTORY+'/RESULT.bin')
   self.state['benchmark_completed']=True
  except BaseException as error:
   self.state['primary_failure']=repr(error)
  finally:
   def step(name,operation):
    try:operation();self.state[name]=True
    except BaseException as error:self.state['finally_failures'].append(dict(step=name,error=repr(error)))
    # A full/unwritable host disk must not skip independent restoration or
    # serial close. Keep the failure in memory and continue every finalizer.
    try:self.save()
    except BaseException as error:self.state['finally_failures'].append(dict(step=name+'-journal',error=repr(error)))
   if opened:
    step('failure_evidence_saved',lambda:self.evidence('received-before-finally.bin',self.w.raw))
    if not self.w.command_ready:step('command_channel_recovered',self.w.recover_command_channel)
    step('passive_wire_evidence_saved',lambda:self.evidence('passive-wire.bin',self.w.passive_raw))
    self.state['command_channel_available']=self.w.command_ready
    if self.w.command_ready:
     if self.state.get('active_app') and self.state['directory_created']:
      def failed_result():
       if any(e['path'].casefold()==(DIRECTORY+'/RESULT.bin').casefold() for e in self.w.listing(DIRECTORY)):
        self.capture_result(self.state['active_app'])
      step('failure_result_saved',failed_result)
     step('owned_cleanup',self.cleanup)
     if all_sd is not None:step('all_originals_verified',lambda:self.p.verify_all_sd(self.w,all_sd))
     # Every preservation stage runs independently after an unrelated failure.
     if environment is not None:
      step('environment_restored',lambda:self.p.restore_environment(self.w,environment))
      step('environment_verified',lambda:self.p.verify_environment(self.w,environment))
     if full is not None:
      def restore_full():
       require(sha((self.output/'calculator-before.bin').read_bytes())==self.state['calculator_sha256']==sha(full['data']),'Original full-state anchor changed')
       self.p.restore_full(self.w,full)
      step('calculator_restored',restore_full)
      step('calculator_verified',lambda:self.p.verify_full(self.w,full))
     if environment is not None:step('environment_final_verified',lambda:self.p.verify_environment(self.w,environment))
     if boots is not None and full is not None:step('final_health_verified',lambda:self.status('final',boots))
    else:
     self.state['manual_recovery_required']=True
     self.state['pending_restoration']=['owned_cleanup','all_originals_verified','environment_restored','calculator_restored','final_health_verified']
    step('final_transcript_saved',lambda:self.evidence('final-transcript.bin',self.w.raw))
    step('serial_closed',self.w.close)
   clean=not self.state['primary_failure'] and not self.state['finally_failures'] and self.state.get('benchmark_completed')
   self.state['status']='PASS' if clean else 'HOLD'
   try:self.save()
   except BaseException as error:
    self.state['finally_failures'].append(dict(step='final-journal',error=repr(error)));self.state['status']='HOLD'
  return self.state

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--bindings',type=Path,required=True);a=p.parse_args()
 # No serial discovery/import/construction while the mandatory bindings are null.
 bindings=json.loads(a.bindings.read_text());result=hardware_requirements(bindings)
 print(json.dumps(result,indent=2));raise SystemExit(2)
if __name__=='__main__':main()
