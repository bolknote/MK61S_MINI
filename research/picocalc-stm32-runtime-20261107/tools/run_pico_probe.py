#!/usr/bin/env python3
"""One leased native APP UART bring-up, owned scratch files, no state backup."""
from pathlib import Path
import argparse,fcntl,hashlib,json,os,re,sys,time
R=Path(__file__).resolve().parents[1];ROOT=R.parents[1]
BASE=ROOT/'.build/stm32-module-runtime-20261107/southbridge-runtime'
sys.path.insert(0,str(ROOT/'.build/mk61ai/fullmodel-v10/hil'))
import guard as g
import native_transport as n
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
EXPECTED_COUNTERS=dict(ERRORS=0,QPI_FALLBACKS=1,TAIL_TIMEOUTS=0,CRC_ERRORS=0,DMA_TIMEOUTS=0,
 LCD_ERRORS=0,SD_SPEED_FALLBACKS=0,SD_PROBE_FAILURES=0,I2C_TIMEOUTS=0,I2C_ABORTS=135,SCREEN_ERRORS=0)
def ready(status):
 v=g.filtered(status)
 for k,value in dict(BUILD='F0E86C32',EXPECTED='5009F89E',ACTUAL='5009F89E',FIRMWARE_CRC='valid',
                     SERVICE='CLOSED',RUNTIME='NONE',RUN='0',BUSY='0',USB_DISK='0',SYS_HZ='125000000',PERI_HZ='48000000').items():
  g.need(v[k]==value,'Unexpected '+k)
 g.need(v['error_counters']==EXPECTED_COUNTERS,'Error counters changed from observed post-boot baseline')
 g.need(v['fs_error']=='','Filesystem error');g.need(g.field(status,'SD')=='OK','SD not ready')
 g.need(g.field(status,'KBD')=='OK'and g.field(status,'APP_BUFFERS')=='0','Keyboard/buffer readiness')
 n.readiness(status,'F0E86C32','5009F89E',int(v['PHYSICAL_KEYS']))
 return v
def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--bench',action='store_true');args=parser.parse_args()
 B=BASE/('pico-bench'if args.bench else'pico-probe')
 prefix='S3BENCH'if args.bench else'S3PROBE';scratch='/S3BEN7'if args.bench else'/S3UART7'
 m=json.loads((B/'manifest.json').read_text());app=Path(m['app'])
 g.need(sha(app)==m['sha256'],'APP changed')
 for name,digest in m['source_hashes'].items():g.need(sha(ROOT/name)==digest,name)
 for name in ['host-verification','uart-verification']:
  g.need('PASS'in json.loads((BASE/'pico-probe'/(name+'.json')).read_text())['status'],'HOST gate missing')
 if args.bench:
  proof=json.loads((BASE/'module-bench/arm-verification.json').read_text())
  g.need(proof['status']=='M3_BENCH_ARM_PASS'and proof['package_sha256']==m['module_sha256'],'Bench module ARM gate')
  common=json.loads((BASE/'pico-probe/manifest.json').read_text())
  for file in ['stm3_client.c','stm3_client.h','pico_uart1.c','pico_uart1.h']:
   key=str((R/'pico'/file).relative_to(ROOT));g.need(m['source_hashes'][key]==common['source_hashes'][key],'Untested common source')
 report=dict(operation='STM32_UART_module_bringup',physical_io=True,app_sha256=sha(app),save_or_restore=False,
             pico_firmware_changed=False,pico_clock_changed=False,module_package_sha256=m['module_sha256'],experiment=prefix)
 owned=[];port=None;binding=None
 with(ROOT/'.build/m0-libc-batch-20261107-v1/ROOT-PICO-LEASE-001.json').open('r+')as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  try:
   binding=g.binding();g.noholders(binding);report['binding']=binding
   port=n.Serial(time.monotonic()+100);g.need(os.fstat(port.fd).st_rdev==binding['cu_rdev'],'Changed CDC')
   report['before']=ready(port.status());port.commands();n.identity(port)
   root_command='ls "/"'
   rows=n.listing_rows(port.command(root_command),root_command)
   names=[row.split(b'\t')[-1].rstrip(b'/').lower()for row in rows]
   g.need(scratch[1:].lower().encode()not in names,'Scratch path already exists')
   command=f'mkdir "{scratch}"';reply=port.command(command)
   g.need(reply==command.encode()+b'\r\nmk61> ','Scratch mkdir not acknowledged')
   owned.append(scratch);(B/'owned.json').write_text(json.dumps(owned)+'\n')
   command=f'ls "{scratch}"';g.need(not n.listing_rows(port.command(command),command),'Scratch is not empty')
   destination=scratch+'/'+prefix+'.APP';report['upload']=n.upload(port,destination,app.read_bytes())
   print('Native UART probe uploaded/readback verified; starting finite APP',flush=True)
   reply=port.command(f'run "{destination}"',seconds=20,allow_error=True)
   records=[v.decode('ascii')for v in re.findall(rb'(?m)^'+prefix.encode()+rb' [^\r\n]*',reply)]
   report['records']=records
   for v in records:print(v,flush=True)
   passed=[v for v in records if v.startswith(prefix+' PASS ')]
   g.need(len(passed)==1 and 'rows=64'in passed[0]and 'uart_errors=0'in passed[0],'UART/module diagnostic did not pass')
   if args.bench:
    g.need(len([v for v in records if v.startswith('S3BENCH CYC ')])==12,'Missing DWT samples')
    g.need(len([v for v in records if v.startswith('S3BENCH CLOCK ')])==4,'Missing clock check')
    g.need(any('TRANSPORT blocks=64 bytes=32768'in v for v in records),'Missing transport data')
   report['status']='HARDWARE_M3_DWT_TRANSPORT_PASS'if args.bench else'HARDWARE_UART_MODULE_PASS'
  except BaseException as error:
   report.update(status='STOPPED',error=str(error));raise
  finally:
   cleanup_errors=[]
   if port:
    try:
     s=port.status()
     if g.field(s,'SERVICE')!='CLOSED'or g.field(s,'RUNTIME')!='NONE':n.leave_app(port)
     else:port.commands()
     for path in reversed(owned):port.command(f'rm -r "{path}"',seconds=20)
     port.send(b'\x1e');report['after']=ready(port.status())
    except BaseException as error:cleanup_errors.append(str(error))
    port.close()
   report.update(cdc_closed=not port or port.fd<0,cleanup_errors=cleanup_errors,lease_released=True)
   (B/'hardware-result.json').write_text(json.dumps(report,indent=2)+'\n');fcntl.flock(lock,fcntl.LOCK_UN)
 if binding:g.noholders(binding)
 g.need(not cleanup_errors,'Cleanup gate failed')
 print(json.dumps(dict(status=report['status'],report=str(B/'hardware-result.json'),cdc_closed=report['cdc_closed'],cleanup_errors=cleanup_errors),indent=2))
if __name__=='__main__':main()
