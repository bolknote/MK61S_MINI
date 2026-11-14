#!/usr/bin/env python3
"""One finite, hash-reviewed RAM experiment; no Flash or ROM-mode operations.

--prepare only reads HOST files. --go requires a fresh exact user/coordinator
package grant, then holds the existing root lease through CDC closure.
"""
from pathlib import Path
import argparse,fcntl,hashlib,json,os,re,subprocess,sys,time
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
WORK=ROOT/'.build/picocalc-fastlink-20261111';KIT=WORK/'kit-017'
# The archived hardware backend is intentionally session-specific. Import it
# only for explicit HIL execution; in-memory controller tests inject their own
# backend and never import historical .build controllers or open a device.
base=None
def load_backend():
 global base
 sys.path[:0]=[str(ROOT/'tests'),str(ROOT/'.build/spectrum-m3-audio-20261108')]
 import current_hil
 base=current_hil
EXPECTED={'build':'C99DE0AF','crc':'528F4874','bytes':1793244}
FOLDER='/FLTEST017';APP=FOLDER+'/FASTLINK.APP'
LEASE=ROOT/'.build/m0-libc-batch-20261107-v1/ROOT-PICO-LEASE-001.json'
PROOF=WORK/'PACKAGE-017.json';PHASE=WORK/'PHASE-017.json'
KNOWN_BOOT={'BOOTS':'20','BOOT_WATCHDOG':'0','RESET_REASON':'00010001','CRASH':'AVAILABLE'}
USER_REQUEST='что делаем дальше? делай'
USER_AUTHORIZATION={'source':'current_user','thread_id':'01a1aba4-18ce-76a2-9d5d-0aa75f6c67cf',
 'request':USER_REQUEST,'pico_hz':125000000,'m3_hz':72000000,'flash_writes':0,'reset_commands':0}
def save(p,value):p.write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def native_health(status,baseline=None,closed=False,identity=None,boot=None):
 """Original native checks, with one exact, evidenced pre-existing boot tuple.

 Read and return the original C5 text. Never clear or substitute the observed
 watchdog flag or pre-existing crash. Intake and final must match the pinned
 read-only Harness handoff; this experiment never clears the crash record.
 """
 expected=identity or EXPECTED;known=boot or KNOWN_BOOT
 fixed={
  'BUILD':expected['build'],'EXPECTED':expected['crc'],'ACTUAL':expected['crc'],
  'IMAGE':str(expected['bytes']),'FIRMWARE_CRC':'valid',
  'MATH_TEST':'OK','failures':'0','KBD':'OK','PANEL_INIT':'1','PSRAM':'OK','SD':'OK',
  'SYS_HZ':'125000000','PERI_HZ':'48000000','RUN':'0','BUSY':'0','DIRTY':'0',
  'USB_DISK':'0','USB_SCREEN':'OFF','APP_BUFFERS':'0','APP_BUFFER_BYTES':'0',
  'APP_EXTERNAL_BYTES':'0','APP_WINDOWS':'0','IO_ERRORS':'0','VALID':'1',
  'POWER_VALID':'1','POWER_PROTOCOL':'1',**known}
 if closed:fixed.update(SERVICE='CLOSED',RUNTIME='NONE',UI='CALCULATOR')
 for key,value in fixed.items():base.need(base.field(status,key)==value,'Native health differs '+key)
 if baseline is not None:
  for key,value in baseline.items():base.need(base.field(status,key)==value,'Native counter changed '+key)
 return status
def prepare():
 manifest=json.loads((KIT/'manifest.json').read_text());host=json.loads((KIT/'host-test.json').read_text())
 assert manifest['pico_build']==EXPECTED['build']and manifest['pico_crc']==EXPECTED['crc']and manifest['pico_flash_bytes']==EXPECTED['bytes']
 cycles=manifest['run_cycles'];assert 1<=cycles<=100
 nrz=manifest.get('nrz4',False)
 controller=json.loads((KIT/'controller-test.json').read_text())
 assert controller['status']=='PASS' and controller['physical_io']is False
 assert host['status']=='PASS' and host['module_sha256']==sha(KIT/'module.s3m')
 assert host['pico_app_sha256']==manifest['app_sha256']==sha(KIT/'app/FASTLINK.APP')
 pins={}
 for m in sys.modules.values():
  p=Path(getattr(m,'__file__','')).resolve()
  if p.is_file() and (p.is_relative_to(ROOT) or p.is_relative_to(ROOT/'.build/m0-atan-exp-hil-20261105-001')):pins[str(p)]=sha(p)
 for p in HERE.rglob('*'):
  if '__pycache__'in p.parts:continue
  if p.is_file():pins[str(p)]=sha(p)
 for name in ('manifest.json','host-test.json','controller-test.json','module-reuse.json','native-health-layout.txt','keyboard-layout.txt','module.s3m','identity.s3m','legacy_module.s3m','native_pins.h','packages.h','app/FASTLINK.APP','app/FASTLINK.elf'):
  p=KIT/name;pins[str(p)]=sha(p)
 p=KIT/'experiment_config.h';pins[str(p)]=sha(p)
 if nrz:
  p=KIT/'host-shared-test.json';pins[str(p)]=sha(p)
  p=WORK/'hardware-015/receipt.json';pins[str(p)]=sha(p)
  if manifest.get('nrz4_packer')=='frames':
   p=KIT/'host-pack-test.json';packing=json.loads(p.read_text())
   assert packing['status']=='PASS'and packing['module_sha256']==sha(KIT/'module.s3m')and packing['actual_ARM_packer_cases']==760
   pins[str(p)]=sha(p)
 receipt=ROOT/'.build/mk61ai/math-choice-20261111/hardware-candidate-001/receipt.json';pins[str(receipt)]=sha(receipt)
 p=Path(manifest['register_header']['path']);assert sha(p)==manifest['register_header']['sha256'];pins[str(p)]=sha(p)
 p=Path(manifest['i2c_header']['path']);assert sha(p)==manifest['i2c_header']['sha256'];pins[str(p)]=sha(p)
 p=Path(manifest['reset_header']['path']);assert sha(p)==manifest['reset_header']['sha256'];pins[str(p)]=sha(p)
 for p in (WORK/'kit-004/module.s3m',WORK/'cleanup-001/receipt.json',WORK/'hardware-005/receipt.json',WORK/'hardware-005/cdc-00-rx.bin',
           ROOT/'.build/mk61ai/math-candidates-20261111/hardware-001/receipt.json',
           ROOT/'.build/mk61ai/math-candidates-20261111/hardware-001/before.txt',
           ROOT/'.build/mk61ai/math-candidates-20261111/hardware-001/failed-final-status.txt'):
  pins[str(p)]=sha(p)
 reuse=json.loads((KIT/'module-reuse.json').read_text())
 assert reuse['status']in('EXACT_M3_REUSE','EXACT_IDENTITY_REUSE_WITH_TELEMETRY_EXTENSION','EXACT_M3_REUSE_WITH_PICO_I2C_RESTORE_FIX','NRZ4_WITH_QUALIFIED_I2C_RESTORE','NRZ4_PACKER_AB_WITH_QUALIFIED_I2C_RESTORE')
 p=Path(reuse['source_package']);assert sha(p)==reuse['source_package_sha256'];pins[str(p)]=sha(p)
 for item in reuse['files'].values():
  for key in ('source','target'):
   p=Path(item[key]);assert sha(p)==item['sha256'];pins[str(p)]=sha(p)
 harness=ROOT/'.build/mk61ai/math-candidates-20261111'
 for sub,names in [('crash-read-003',('receipt.json','before.txt','after.txt','crash.bin')),
                   ('hardware-003',('receipt.json','before.txt','failure-status.txt','failed-final-status.txt','error-trace.txt'))]:
  for name in names:
   p=harness/sub/name;pins[str(p)]=sha(p)
 handoff=json.loads((harness/'crash-read-003/receipt.json').read_text())
 assert handoff['status']=='PASS' and handoff['crash_preserved'] and handoff['CDC_closed'] and handoff['lease_closed']
 assert handoff['crash_sha256']==sha(harness/'crash-read-003/crash.bin')
 historic_identity={'build':'7C38C634','crc':'8A17554E','bytes':1793244}
 historic_boot={**KNOWN_BOOT,'BOOTS':'19'}
 for name in ('before.txt','after.txt'):
  native_health((harness/'crash-read-003'/name).read_text(),closed=True,identity=historic_identity,boot=historic_boot)
 current=ROOT/'research/picocalc-ai-performance-20261111/lut8-hybrid/hardware-002'
 for name in ('receipt.json','final-status.txt'):p=current/name;pins[str(p)]=sha(p)
 handoff=json.loads((current/'receipt.json').read_text())
 assert handoff['status']=='MEASURED'and handoff['temporary_removed']and handoff['CDC_closed']and handoff['lease_closed']and handoff['M3_writes']==0
 native_health((current/'final-status.txt').read_text(),closed=True)
 p=WORK/'hardware-014/receipt.json';pins[str(p)]=sha(p)
 prior=json.loads(p.read_text());assert prior['status']=='PASS' and prior['CLOSED'] and prior['owned_sd_removed'] and prior['CDC_closed'] and prior['lease_closed']
 if nrz:assert len(prior['measurements'])==9100 and prior['planned_i2c_restoration']['count']==8400
 native_health(prior['final'],closed=True,identity=historic_identity,boot=historic_boot)
 previous=json.loads((WORK/'cleanup-001/receipt.json').read_text())
 assert previous['status']=='PASS' and previous['CLOSED'] and previous['owned_sd_removed'] and previous['CDC_closed'] and previous['lease_closed']
 native=Path(manifest['resident_elf_path'])
 assert sha(native)==manifest['resident_elf_sha256'];pins[str(native)]=sha(native)
 for name in ('main.cpp','hardware.cpp','io_worker.cpp'):
  source=ROOT/'ports/picocalc'/name
  pins[str(source)]=sha(source)
 save(PHASE,dict(uid=base.UID,action='admit',pins=pins,deadline_seconds=850,flash_writes=0,sd_scope=FOLDER))
 proof=dict(status='HOST_REVIEW_READY',uid=base.UID,expected=EXPECTED,known_preexisting_boot=KNOWN_BOOT,user_authorization=USER_AUTHORIZATION,phase_sha256=sha(PHASE),pins=pins,
  source_kit=manifest,host_test=host,controller_test=controller,root_lease_inode=289244874,deadline_seconds=850,
  hardware_scope=dict(pico_gpio=[6,7,8,9],m3_gpio=['PB8','PB9','PC10','PC11'],
   two_wire='PB8 clock->GP7; PB9 data->GP6',
   four_wire='NRZ4 data bits PB9/PB8/PC11/PC10->GP6/7/8/9, common start8nibbles+stop'if nrz else'PB9 clock->GP6; PB8/PC11/PC10 data->GP7/GP8/GP9',
   nrz4=nrz,m3_resources=['TIM4 update','DMA1 channel7','I2C1 PE/CR2 IRQ bits','I2C1 GPIO OD recovery and peripheral SWRST with OAR/CCR/TRISE restore','USART3 CR1/CR3 and RX DMA3 enable']+(['TIM4 CC3','DMA1 channel5; other shared DMA request sources must be disabled']if nrz else[]),
   owned_startup_timer_cleanup='For NRZ only: acknowledge exactly inherited CC3IF8 once on first acquire with stopped/unclocked/pristine TIM4 and idleDMA; record it, reject any later dirty timer',
   pico_resources=['readonly ELF/DWARF-pinned keyboard pending/phase before lease; normal service until full transaction complete,100ms cap','readonly native I2C timeout/reset/abort/keyboard-error counters and worker stage/result at every ownership boundary; stop first delta','SDK-claimed PIO0 SM+'+('8'if nrz else'5')+' instructions','SDK-claimed RX DMA channel','I2C1 idle PE','UART1'],
   pico_i2c_restore='After GPIO returns: bounded I2C1-only peripheral reset, exact16-register idle configuration restore, native software counters untouched; planned resets separately counted',
   forbidden=['Flash writes','ROM mode','TIM1/2/3 writes','PMU I2C2 writes','global IRQ masking','overclock'],
   ready_guard_us=500,pico_restore_after_us=2500,m3_result_after_us=4000,
   maximum_m3_loop_burst_us=1000,maximum_m3_slice_us=2000,
   case_count=91*cycles,payload_bytes=(5208 if nrz else 3192)*cycles,gpio_restores=84*cycles,completion_timeout_seconds=min(750,30+6*cycles),
   patterns=['00','FF','55','AA','walking1','walking0','xorshift'],
   timer_target_bit_rates=[1000000,1500000,2000000]if nrz else[1000000,2000000,4500000,9000000],
   timer_target_unit='symbols_per_second'if nrz else'clocked_bits_per_second',
   timer_rates_are_targets_not_measurements=True),
  failure_policy='First failed case ends run. Only owned-resource restoration, UNLOAD/HELLO and final readback/closure follow.',
  closed_plan='Each burst restores both buses before returning to BIOS. APP unloads S3M, releases native SDK leases and UART1. Controller returns CALCULATOR/CLOSED/NONE, verifies and removes only its new SD file/directory, checks native counter deltas, closes CDC/termios and root lease.',
  measurement_limits='RAM fixture includes deliberate readiness/restoration/reply guards; total_us is not a production block latency. Model time/cycles are not hardware measurements.')
 save(PROOF,proof);print(json.dumps({'proof':str(PROOF),'sha256':sha(PROOF),'phase_sha256':sha(PHASE),'pins':len(pins)}))
def validate_go(path):
 go=json.loads(path.read_text());proof=json.loads(PROOF.read_text());now=time.time()
 base.need(go['status']in('COORDINATOR_EXPLICIT_HARDWARE_GO','USER_EXPLICIT_HARDWARE_GO')and go['uid']==base.UID,'No exact hardware authorization')
 if go['status']=='USER_EXPLICIT_HARDWARE_GO':
  base.need(go.get('authorization')==proof.get('user_authorization')==USER_AUTHORIZATION,'User authorization scope differs')
 base.need(go['package_proof_sha256']==sha(PROOF),'GO package differs')
 base.need(go['not_before_utc_epoch']<=now<go['start_before_utc_epoch']<go['finish_before_utc_epoch'],'Outside GO window')
 base.need(30<go['finish_before_utc_epoch']-now<=900,'GO duration outside cap')
 base.need(proof['phase_sha256']==sha(PHASE),'Phase differs from reviewed proof')
 for p,digest in proof['pins'].items():base.need(sha(p)==digest,'Reviewed source changed '+p)
 return go,proof
def measurements(wire):
 rows=[]
 for line in wire.decode('ascii','replace').splitlines():
  if not line.startswith('FL CASE '):continue
  row={k:v for k,v in re.findall(r'(\w+)=([^ ]+)',line)}
  for key in ('i','mode','bytes','rate_arg','pattern','m3_error','prep_us','prep_cycles','burst_us','burst_cycles',
              'wire_us','wire_cycles','m3_work','pico_work','capture_span_us','total_us','max_slice_us','capture_error',
              'idle_us','idle_samples','logical_us','logical_calls'):
   row[key]=int(row[key])
  if row['wire_cycles'] and not row['m3_error']:
   row['wire_effective_bits_per_second']=row['bytes']*8*72000000/row['wire_cycles']
   row['prep_wire_effective_bits_per_second']=row['bytes']*8*72000000/(row['prep_cycles']+row['wire_cycles'])
  rows.append(row)
 return rows
NATIVE_BOUNDARIES={1:'before_logical',2:'logical_service',3:'after_logical',4:'after_physical',
                   5:'after_restore_before_service',6:'post_service',7:'post_keypoll',8:'load_service',9:'cleanup'}
def native_observation(wire):
 lines=wire.decode('ascii','replace').splitlines();out={}
 for label in ('FAIL','BEFORE','AFTER'):
  matches=[line for line in lines if line.startswith('FL NATIVE_'+label+' ')]
  base.need(len(matches)<=1,'Ambiguous native fault '+label)
  if matches:out[label.lower()]={k:int(v,16 if k in('pins','status','raw','abort_source')else 10)for k,v in re.findall(r'(\w+)=([^ ]+)',matches[0])}
 if out:
  base.need(set(out)=={'fail','before','after'},'Incomplete native fault telemetry')
  base.need(out['fail']['boundary']in NATIVE_BOUNDARIES,'Invalid native fault boundary')
  out['boundary_name']=NATIVE_BOUNDARIES[out['fail']['boundary']]
 return out
def close_owned(p):
 """Close only this APP's foreground, then qualify counters after SD cleanup."""
 browser=False
 for _ in range(10):
  status=p.status();service,path,result=base.foreground(status)
  for key,value in (('BUILD',EXPECTED['build']),('FIRMWARE_CRC','valid'),('ACTUAL',EXPECTED['crc']),('CRASH',KNOWN_BOOT['CRASH'])):
   base.need(base.field(status,key)==value,'Unsafe closure identity/state '+key)
  runtime=base.field(status,'RUNTIME')
  if service=='CLOSED':
   base.need(runtime=='NONE' and base.field(status,'UI')=='CALCULATOR','Closed foreground differs');return status
  if service=='BROWSER' and browser:
   base.need(runtime=='NONE','Unexpected browser runtime');p.send(b'\x1b');p.pump(.25);continue
  base.need(path==APP,'Foreign foreground; refusing closure keys')
  if runtime=='APP':p.send(b'\x1b');p.pump(.35);continue
  base.need(service in ('VIEWER','CONSOLE') and runtime=='NONE' and result.startswith('APP finished;'),'Owned APP not finished')
  p.send(b'\x1e');p.send(b'\x1b');p.pump(.25);browser=True
 raise base.Hold('Owned UI did not close within finite cap')
def run(g):
 scope=g.final['expected_scope'];expected_cases=scope['case_count'];expected_bytes=scope['payload_bytes']
 p=base.Port(g);created=False;owned=False;baseline=None;root_names=None;error=None;closed=False
 try:
  with p:
   before=native_health(p.status(),closed=True)
   baseline={k:base.field(before,k) for k in (*base.CORE_COUNTERS,'BOOTS','IO_I2C_RESETS','BOOT_WATCHDOG','RESET_REASON','CRASH')}
   g.final.update(before=before,baseline=baseline,pico_flash_writes=0,m3_flash_writes=0,reset_commands=0)
   p.commands();base.need(base.field(p.command('identity'),'UID')==base.UID,'Wrong terminal UID')
   root_names=base.names(p.command('ls "/"'));base.need(FOLDER[1:] not in root_names,'Temporary folder already exists')
   p.command('mkdir "'+FOLDER+'"');created=True
   data=(KIT/'app/FASTLINK.APP').read_bytes();base.write_file(p,APP,data);owned=True
   base.need(base.read_file(p,APP)==data,'Staged APP differs');start=len(p.text)
   p.send(('open "'+APP+'"\r').encode('ascii'))
   try:
    base.wait_pattern(p,rb'^FL (?:PASS|FAIL) code=-?\d+ cases=\d+ bytes=\d+ uart_errors=\d+ resources_released=1\r?$',start,scope['completion_timeout_seconds'])
    p.pump(.15);wire=bytes(p.text[start:]);(g.out/'wire.txt').write_bytes(wire)
    rows=measurements(wire);g.final['measurements']=rows
    g.final['native_fault']=native_observation(wire)
    restores=re.findall(rb'(?m)^FL RESTORE i2c_restarts=(\d+) max_us=(\d+)\r?$',wire)
    if len(restores)==1:g.final['planned_i2c_restoration']={'count':int(restores[0][0]),'max_us':int(restores[0][1])}
    base.need(not g.final['native_fault'],'Native first-fault observation')
    passed=(r'(?m)^FL PASS code=0 cases=%u bytes=%u uart_errors=0 resources_released=1\r?$'%(expected_cases,expected_bytes)).encode()
    base.need(re.search(passed,wire),'RAM link probe failed')
    base.need(len(rows)==expected_cases and [r['i'] for r in rows]==list(range(expected_cases)),'Incomplete/ambiguous test rows')
    base.need(len(restores)==1 and int(restores[0][0])==scope['gpio_restores'],'Incomplete planned I2C restorations')
    base.need(all(not r['m3_error'] and not r['capture_error'] and r['max_slice_us']<=2000 for r in rows),'Case failed')
    base.need(len(re.findall(rb'(?m)^FL ID .*calculated=3BE158B4 ',wire))==2,'Missing before/after M3 identity')
   except BaseException as exc:error=exc
   # No new cases/retries after failure. The APP itself owns restoration;
   # only its known foreground and this controller's new SD directory exist.
   after=close_owned(p);closed=True;g.final['after']=after
   p.commands()
   base.need(base.read_file(p,APP)==data,'Owned APP changed; refusing removal')
   p.command('rm "'+APP+'"');owned=False
   base.need(not base.names(p.command('ls "'+FOLDER+'"')),'Unexpected file in owned folder')
   p.command('rmdir "'+FOLDER+'"');created=False
   base.need(base.names(p.command('ls "/"'))==root_names,'Root listing changed')
   g.final.update(CLOSED=True,owned_sd_removed=True,CDC_closed=False)
   g.final['final']=p.status()
   try:native_health(g.final['final'],baseline,closed=True)
   except BaseException as exc:
    g.final['final_qualification_error']=repr(exc)
    if error is None:error=exc
  g.final['CDC_closed']=p.closed
  if error:raise error
 except BaseException:
  g.final.update(owned_file_remains=owned,owned_folder_remains=created,CLOSED=closed)
  raise
 finally:g.final['CDC_closed']=p.closed
def main():
 global KIT,PROOF,PHASE,FOLDER,APP
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--prepare',action='store_true')
 ap.add_argument('--go',type=Path);ap.add_argument('--output',type=Path)
 ap.add_argument('--kit',type=Path,default=KIT);ap.add_argument('--session',default='017')
 a=ap.parse_args()
 assert re.fullmatch(r'[0-9]{3}[a-z]?',a.session)
 KIT=a.kit.resolve();assert KIT.is_relative_to(WORK)
 PROOF=WORK/('PACKAGE-'+a.session+'.json');PHASE=WORK/('PHASE-'+a.session+'.json')
 FOLDER='/FLTEST'+a.session.upper();APP=FOLDER+'/FASTLINK.APP'
 load_backend()
 if a.prepare:prepare();return
 if not a.go or not a.output:ap.error('--go and unique --output required')
 go,proof=validate_go(a.go);out=a.output.resolve()
 base.need(out.is_relative_to(WORK) and not out.exists(),'Use a fresh result directory in this experiment')
 grant=WORK/(out.name+'-root-grant.json')
 save(grant,dict(status='ROOT_EXPLICIT_PHASE_GO',uid=base.UID,phase_sha256=sha(PHASE),source_pins=proof['pins'],
  not_before_utc_epoch=go['not_before_utc_epoch'],start_before_utc_epoch=go['start_before_utc_epoch'],
  finish_before_utc_epoch=go['finish_before_utc_epoch']))
 fd=os.open(LEASE,os.O_RDONLY|os.O_NOFOLLOW);base.need(os.fstat(fd).st_ino==289244874,'Root lease inode changed')
 fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
 g=None;awake=None;ok=False;error=None
 try:
  g=base.Gate(PHASE,grant,out);g.final.update(lease_inode=289244874,lease_pid=os.getpid(),lease_closed=False)
  g.final['expected_scope']=proof['hardware_scope']
  awake=subprocess.Popen(['/usr/bin/caffeinate','-i','-w',str(os.getpid())],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  run(g);ok=True
 except BaseException as exc:error=repr(exc)
 finally:
  if awake is not None:awake.terminate();awake.wait(timeout=5)
  os.close(fd)
  if g is not None:
   g.final['lease_closed']=True;g.finish(ok,error)
 print(json.dumps({'status':'PASS' if ok else 'HOLD','output':str(out),'error':error}),flush=True)
 if not ok:raise SystemExit(1)
if __name__=='__main__':main()
