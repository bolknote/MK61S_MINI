#!/usr/bin/env python3
"""Fresh read-only Pico admission after the user power-cycled the STM32."""
from pathlib import Path
import fcntl,json,sys,time
R=Path(__file__).resolve().parents[1];ROOT=R.parents[1]
B=ROOT/'.build/stm32-module-runtime-20261107/southbridge-runtime'
sys.path.insert(0,str(ROOT/'.build/mk61ai/fullmodel-v10/hil'))
import guard as g
import native_transport as n
record=dict(operation='read_only_post_stm32_boot',physical_io=True,pico_flash_writes=0,
            reset_commands=0,clock_writes=0,user_state_saved=False)
port=None
with(ROOT/'.build/m0-libc-batch-20261107-v1/ROOT-PICO-LEASE-001.json').open('r+')as lock:
 fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 try:
  binding=g.binding();g.noholders(binding);record['native_binding']=binding
  port=n.Serial(time.monotonic()+15);status=port.status();fields=g.filtered(status)
  record.update(native=fields,kbd=g.field(status,'KBD'),app_buffers=g.field(status,'APP_BUFFERS'))
  for key,value in dict(BUILD='F0E86C32',EXPECTED='5009F89E',ACTUAL='5009F89E',FIRMWARE_CRC='valid',
                        SERVICE='CLOSED',RUNTIME='NONE',RUN='0',BUSY='0',USB_DISK='0',
                        SYS_HZ='125000000',PERI_HZ='48000000').items():g.need(fields[key]==value,'Unexpected '+key)
  g.need(record['kbd']=='OK','Keyboard I2C is not OK')
  g.need(not any(fields['error_counters'].values()),'Hardware errors')
  record['status']='POST_STM32_PICO_READY'
 except BaseException as error:
  record.update(status='STOPPED',error=str(error));raise
 finally:
  if port:port.close()
  record.update(cdc_closed=not port or port.fd<0,lease_released=True)
  (B/'post-boot-admission.json').write_text(json.dumps(record,indent=2)+'\n')
  fcntl.flock(lock,fcntl.LOCK_UN)
g.noholders(binding);print(json.dumps(record,indent=2))
