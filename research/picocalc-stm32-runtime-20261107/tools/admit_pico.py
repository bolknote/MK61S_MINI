#!/usr/bin/env python3
"""One read-only native C5 admission; no APP install, flash/reset/clock/state."""
from pathlib import Path
import fcntl,hashlib,json,os,sys,time
R=Path(__file__).resolve().parents[1];ROOT=R.parents[1];B=ROOT/'.build/stm32-module-runtime-20261107'
sys.path.insert(0,str(ROOT/'.build/mk61ai/fullmodel-v10/hil'))
import guard as g
import native_transport as n
handoff=ROOT/'.build/m0-libc-batch-20261107-v1/amendment-v2/PAUSE-HANDOFF-001.json'
assert hashlib.sha256(handoff.read_bytes()).hexdigest()=='e68c378dfd3faf7e64537bfed77879a8bd96b7eee5b2ec1b33edfebd4b088b42'
v=json.loads(handoff.read_text());binding=v['native_binding'];n.PORT=binding['cu']
lease=ROOT/'.build/m0-libc-batch-20261107-v1/ROOT-PICO-LEASE-001.json'
record=dict(operation='read_only_native_admission',physical_io=True,flash_writes=0,reset_commands=0,clock_writes=0,user_state_saved=False,root_handoff_sha256=hashlib.sha256(handoff.read_bytes()).hexdigest())
port=None
with lease.open('r+')as lock:
 fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 try:
  g.need(g.binding()==binding,'Stale binding');g.noholders(binding)
  port=n.Serial(time.monotonic()+15)
  g.need(os.fstat(port.fd).st_rdev==binding['cu_rdev'],'Changed serial device')
  status=port.status();fields=g.filtered(status)
  expected=v['expected']
  for k,val in dict(BUILD=expected['build'],ACTUAL=expected['crc'],EXPECTED=expected['crc'],IMAGE=str(expected['bytes']),BOOTS=v['boot_fields']['BOOTS'],CRASH='NONE',SERVICE='CLOSED',RUNTIME='NONE',SYS_HZ='125000000',PERI_HZ='48000000',RUN='0',BUSY='0',USB_DISK='0').items():g.need(fields[k]==val,'Unexpected '+k)
  g.need(not any(fields['error_counters'].values()),'Hardware errors')
  record.update(status='PASS',native=fields,native_binding=binding,app_buffers=g.field(status,'APP_BUFFERS'))
 finally:
  if port is not None:port.close()
  record['cdc_closed']=port is None or port.fd<0
  fcntl.flock(lock,fcntl.LOCK_UN)
record['holders']=g.noholders(binding)
(B/'pico-admission.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record,indent=2))
