#!/usr/bin/env python3
"""Classic Flash candidates: double backup, unused extension, unconditional restore."""
import argparse,hashlib,importlib.util,json,subprocess,sys,time
from pathlib import Path
if not __debug__:raise RuntimeError("Run without -O: hardware preservation checks are required")
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT/'tests'))
from hil_c5_stack import read_file,write_file
from hil_multi_device_identity import parse_identity
from hil_system_memory import connect,health,require_empty,valid_classic_dfu_listing,flash,SERIAL
from hil_packbits_firmware import fingerprint,firmware_info
spec=importlib.util.spec_from_file_location('fill_flash',HERE.parent/'stm32f411-rom-2026-10-21/flash-experiment.py')
old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--port',required=True)
 p.add_argument('--dfu-util',type=Path,required=True)
 p.add_argument('--payload',type=Path,required=True);p.add_argument('--app',type=Path,required=True)
 p.add_argument('--output',type=Path,required=True);p.add_argument('--runs',type=int,default=3)
 p.add_argument('--selected-runtime',action='store_true')
 p.add_argument('--shared-app',type=Path)
 p.add_argument('--sizes',type=int,nargs='+',default=[0,1,2,3,4,7,8,15,16,17,31,32,33,63,64,65,127,128,129,255,256,257,511,512,1024,4096])
 p.add_argument('--alignments',type=int,nargs='+',default=[0,1,2,3])
 a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
 layout=json.loads((a.payload/'layout.json').read_text());raw=(a.payload/'payload.bin').read_bytes()
 assert hashlib.sha256(raw).hexdigest()==layout['sha256']
 validation=json.loads((a.payload/'validation.json').read_text());assert all(r['status']=='PASS' for r in validation['results'])
 assert validation['elf_sha256']==hashlib.sha256((a.payload/'payload.elf').read_bytes()).hexdigest()
 checker=(ROOT/'.build/stm32f411-rom-20261021/flash-check/FLREAD.APP').read_bytes()
 backup=None;entered=False;report=dict(status='RUNNING',layout=layout)
 def save():(a.output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
 with connect(a.port,old.BUILD,wait=0) as port:
  identity=parse_identity(port.command('identity'));healthy=health(port,old.BUILD);require_empty(healthy)
  original_state=old.state(port);files=fingerprint(port)
  assert not any(x.casefold() in ('/flread.app','/flcrc.bin') or x.casefold().startswith('/mmov-fl') for x in files['files'])
  report.update(identity=str(identity),files_before=files);save()
 try:
  with connect(a.port,old.BUILD) as port:
   port.drain();port.write_line('dfu');entered=True;time.sleep(.2)
  deadline=time.monotonic()+20
  while True:
   r=subprocess.run([a.dfu_util,'-l'],capture_output=True,text=True,timeout=8)
   if valid_classic_dfu_listing(r.stdout,r.stderr,r.returncode):break
   if time.monotonic()>=deadline:raise TimeoutError('Pinned DFU descriptor absent')
   time.sleep(.3)
  reads=[]
  for name in ('a','b'):
   path=a.output/f'flash-original-{name}.bin'
   r=subprocess.run([a.dfu_util,'-d','0483:df11','-S',SERIAL,'-a','0','-s',f'0x08000000:{old.FLASH_BYTES}','-U',path],capture_output=True,text=True,timeout=120)
   (a.output/f'upload-{name}.txt').write_text(r.stdout+r.stderr);assert r.returncode==0
   b=path.read_bytes();assert len(b)==old.FLASH_BYTES and hashlib.sha256(b[:old.IMAGE_BYTES]).hexdigest()==old.ORIGINAL_SHA
   reads.append(b)
  assert reads[0]==reads[1];backup=reads[0]
  offset=layout['base']-0x08000000
  assert offset>=old.IMAGE_BYTES and backup[offset:offset+len(raw)]==b'\xff'*len(raw)
  candidate=bytearray(backup);candidate[offset:offset+len(raw)]=raw
  assert candidate[:offset]==backup[:offset] and candidate[offset+len(raw):]==backup[offset+len(raw):]
  path=a.output/'flash-test.bin';path.write_bytes(candidate)
  report['backup_sha256']=hashlib.sha256(backup).hexdigest();save()
  print('Double backup verified; installing isolated Flash candidates',flush=True)
  flash(a,dict(path=str(path),build=old.BUILD),a.output/'install.json')
  with connect(a.port,old.BUILD) as port:
   write_file(port,'/FLREAD.APP',checker);port.command('open "/FLREAD.APP"',timeout=90)
   report['installed_crc']=old.proof(port,candidate)
   port.command('rm /FLREAD.APP');port.command('rm /FLCRC.bin')
   assert old.state(port)==original_state
  command=[sys.executable,str(HERE/'run.py'),'--cpu','m4','--port',a.port,'--app',str(a.app),'--directory','/MMOV-FL','--output',str(a.output/'bench'),'--runs',str(a.runs),'--sizes',*[str(n) for n in a.sizes],'--alignments',*[str(n) for n in a.alignments]]
  if a.selected_runtime:command.append('--selected-runtime')
  subprocess.run(command,check=True)
  report['benchmark_status']=json.loads((a.output/'bench/result.json').read_text())['status']
  if a.shared_app:
   shared=command.copy()
   shared[shared.index('--app')+1]=str(a.shared_app)
   shared[shared.index('--output')+1]=str(a.output/'shared')
   # Keep all alignments and overlap directions, with representative sizes.
   begin=shared.index('--sizes')+1;end=shared.index('--alignments')
   shared[begin:end]=['1','4','16','33','64','256','4096']
   shared.append('--selected-runtime')
   subprocess.run(shared,check=True)
   report['shared_status']=json.loads((a.output/'shared/result.json').read_text())['status']
 finally:
  if entered and backup is not None:
   print('Restoring original full Flash',flush=True)
   flash(a,dict(path=str(a.output/'flash-original-a.bin'),build=old.BUILD),a.output/'restore.json')
   with connect(a.port,old.BUILD) as port:
    write_file(port,'/FLREAD.APP',checker);port.command('open "/FLREAD.APP"',timeout=90)
    report['restored_crc']=old.proof(port,backup)
    port.command('rm /FLREAD.APP');port.command('rm /FLCRC.bin')
    assert old.state(port)==original_state and fingerprint(port)==files
    assert parse_identity(port.command('identity'))==identity
    report['final_health']=health(port,old.BUILD)
    report.update(files_preserved=True,state_preserved=True,identity_preserved=True)
  report['status']='PASS' if report.get('benchmark_status')=='PASS' and (not a.shared_app or report.get('shared_status')=='PASS') and report.get('restored_crc',{}).get('status')=='PASS' else 'FAIL';save()
 assert report['status']=='PASS'
if __name__=='__main__':main()
