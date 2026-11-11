#!/usr/bin/env python3
"""Explicit STM32 ROM probe or reviewed bounded write; no backup/reset/options."""
from pathlib import Path
import argparse,fcntl,hashlib,json,os,plistlib,re,stat,subprocess,sys,time
R=Path(__file__).resolve().parents[1];ROOT=R.parents[1]
BASE=ROOT/'.build/stm32-module-runtime-20261107';B=BASE/'southbridge-runtime'
PORT='/dev/cu.usbserial-1120'
PACKET_SHA='6b98cc802b83daf6467c0ab05f5089aac49cd6d6bf58d95153a81e18b0fb84c8'
BIN_SHA='f16f54f8eec954966a6a810be583a0dd61fb9cd16fb0a461529552dcf12b2069'
sys.path.insert(0,str(ROOT/'.build/mk61ai/fullmodel-v10/hil'))
import guard as g
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def binding():
 raw=subprocess.run(['/usr/sbin/ioreg','-a','-r','-c','IOUSBHostDevice','-l','-w','0'],capture_output=True,check=True,timeout=5).stdout
 found=[]
 def walk(nodes,parents=()):
  for node in nodes:
   chain=parents+(node,)
   if node.get('IOCalloutDevice')==PORT:found.append(chain)
   walk(node.get('IORegistryEntryChildren',[]),chain)
 walk(plistlib.loads(raw));assert len(found)==1,'Absent or ambiguous CH340'
 chain=found[0];leaf=chain[-1];d=[n for n in chain if n.get('IOObjectClass')=='IOUSBHostDevice'][-1]
 assert (d.get('idVendor'),d.get('idProduct'))==(0x1a86,0x7523),'Not the mainboard CH340'
 tty=PORT.replace('/cu.','/tty.');assert leaf.get('IODialinDevice')==tty
 for p in [PORT,tty]:assert stat.S_ISCHR(os.stat(p).st_mode)
 return dict(cu=PORT,tty=tty,vid=0x1a86,pid=0x7523,usb_entry=d['IORegistryEntryID'],
             location=d['locationID'],session=d['sessionID'],serial_entry=leaf['IORegistryEntryID'],
             cu_rdev=os.stat(PORT).st_rdev,tty_rdev=os.stat(tty).st_rdev)
def pins():
 assert sha(B/'review-packet.json')==PACKET_SHA,'Review packet changed'
 p=json.loads((B/'review-packet.json').read_text())
 for name,digest in p['files'].items():assert sha(ROOT/name)==digest,name
 assert sha(Path(p['manifest']['bin']))==BIN_SHA
 return p
def main():
 global B,PACKET_SHA,BIN_SHA
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('operation',choices=['probe','write-verify'])
 parser.add_argument('--review-packet',type=Path)
 parser.add_argument('--expected-review-sha256')
 parser.add_argument('--expected-image-sha256')
 args=parser.parse_args()
 if args.review_packet:
  review=args.review_packet.resolve()
  if not review.is_relative_to(ROOT)or review.name!='review-packet.json':parser.error('Invalid repository review packet')
  if not all(re.fullmatch(r'[0-9a-f]{64}',v or '')for v in (args.expected_review_sha256,args.expected_image_sha256)):
   parser.error('Separate expected review and image SHA256 values are required')
  B=review.parent;PACKET_SHA=args.expected_review_sha256;BIN_SHA=args.expected_image_sha256
 elif args.expected_review_sha256 or args.expected_image_sha256:parser.error('Hashes require --review-packet')
 packet=pins();plan=packet['flash_plan'];image_bytes=packet['manifest']['flash_image_bytes']
 record=dict(operation=args.operation,time_unix=time.time(),physical_io=True,
             packet_sha256=PACKET_SHA,firmware_sha256=BIN_SHA,
             old_firmware_or_calculator_state_saved=False,pico_cdc_opened=False,
             automatic_go_or_reset=False,option_or_protection_commands=False)
 lease=ROOT/'.build/m0-libc-batch-20261107-v1/ROOT-PICO-LEASE-001.json'
 output=B/('rom-probe.json'if args.operation=='probe'else'write-verify.json')
 with os.fdopen(os.open(lease,os.O_RDONLY|os.O_NOFOLLOW),'r')as lock:
  meta=os.fstat(lock.fileno())
  assert stat.S_ISREG(meta.st_mode)and meta.st_nlink==1 and meta.st_ino==289244874,'Shared lease identity changed'
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  try:
   before=binding();g.noholders(before);record['binding']=before
   pico='/dev/cu.usbmodem11301'
   if Path(pico).exists():g.noholders(dict(cu=pico,tty=pico.replace('/cu.','/tty.')))
   argv=plan['info_argv']if args.operation=='probe'else plan['write_verify_argv']
   if args.operation=='write-verify':
    probe=json.loads((B/'rom-probe.json').read_text())
    assert probe['status']=='ROM_ID_MATCH'and probe['device_id']==0x410
    assert probe['binding']==before and 0<=time.time()-probe['time_unix']<=900,'ROM probe is stale'
    assert sha(Path(argv[0]))==probe['programmer_sha256'],'Programmer changed'
    assert argv==plan['write_verify_argv']and '-e'in argv and argv[argv.index('-e')+1]==str(plan['erase_pages'])
    assert plan['erase_pages']==(image_bytes+1023)//1024 and 0<plan['erase_pages']<=62
    assert int(plan['erased_end_exclusive'],16)<=0x0800f800
    assert argv[argv.index('-s')+1]=='0'and '-S'not in argv
    assert not any(x in argv for x in ['-g','-R','-i','-u','-j','-k','-o','-r'])
   record['programmer_sha256']=sha(Path(argv[0]));record['argv']=argv
   result=subprocess.run(argv,capture_output=True,text=True,timeout=20 if args.operation=='probe'else 90)
   log=result.stdout+result.stderr
   logpath=B/('rom-probe.log'if args.operation=='probe'else'write-verify.log');logpath.write_text(log)
   record.update(returncode=result.returncode,log=str(logpath),log_sha256=sha(logpath))
   assert binding()==before,'USB binding changed';g.noholders(before)
   assert result.returncode==0,log
   chip=re.search(r'Device ID\s*:\s*0x([0-9a-fA-F]+)',log)
   assert chip and int(chip[1],16)==0x410,'Wrong STM32 chip ID: '+log
   record['device_id']=int(chip[1],16)
   if args.operation=='probe':record['status']='ROM_ID_MATCH';record['flash_writes']=0
   else:
    assert '100.00%'in log and 'Wrote and verified address'in log and 'Done.'in log
    record.update(status='FLASH_WRITE_VERIFY_PASS',flash_written_bytes=image_bytes,
                  erased_range=[plan['start_address'],plan['erased_end_exclusive']],settings_pages_erased_by_programmer=False,
                  image_started=False,awaiting_dip1_off_and_power_cycle=True)
   print(log if args.operation=='probe'else f'STM32 FLASH_WRITE_VERIFY_PASS:{image_bytes} bytes,{plan["erase_pages"]} pages; no GO/reset/options/backup')
  except BaseException as error:
   record.update(status='STOPPED',error=str(error));raise
  finally:
   record['port_closed']=True;record['lease_released']=True
   output.write_text(json.dumps(record,indent=2)+'\n');fcntl.flock(lock,fcntl.LOCK_UN)
 print(json.dumps(record,indent=2))
if __name__=='__main__':main()
