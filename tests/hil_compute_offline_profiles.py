#!/usr/bin/env python3
"""Classic persisted clock profiles; requires diagnostic one-shot boot probe.

The source-copy boot hook launches the same finite APP in offline profiles,
records hardware USB gating, saves profile0 and resets before host reconnection.
Never run this driver with a production image lacking that recovery hook.
"""
import argparse,json,re,time
from pathlib import Path
from types import SimpleNamespace
import hil_compute_clock as clock
from hil_chip8_fps import receive_file
from hil_c6_system_bootstrap import write_file,read_file
from hil_classic_cdc_guard import current_binding
from hil_vm_cache_latency import fast_control

MHZ=(96,108,120,132,138)
def fields(raw):return {k:int(v) for k,v in re.findall(r'(\w+)=(\d+)',raw.decode('ascii'))}
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--build',required=True);p.add_argument('--selector',type=Path,required=True);p.add_argument('--probe',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--port',default='/dev/cu.usbmodem2068336B47311');a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
 files={'CLKSET.APP':a.selector,'CLKTEST.APP':a.probe};rows=[]
 with clock.connect(a.port,a.build) as port:
  fast_control(port);assert clock.DIRECTORY[1:] not in port.command('ls');port.command('mkdir '+clock.DIRECTORY)
  for name,path in files.items():
   data=path.read_bytes();write_file(port,clock.DIRECTORY+'/'+name,data);read_file(port,clock.DIRECTORY+'/'+name,data)
 try:
  for stage,profile in enumerate((0,1,2,3,4,3,4,0)):
   proof=None;transport=None
   if profile<3:
    clock.set_profile(a,profile)
    with clock.connect(a.port,a.build) as port:
     port.attach();port.begin_measurement();clock.launch(port,'CLKTEST.APP',12);port.end_measurement()
     payload=receive_file(port,clock.DIRECTORY+'/clock.txt');transport=dict(pongs=len(port.pings),pong_max_s=max(port.pings));assert transport['pongs']>0
     port.command('rm "'+clock.DIRECTORY+'/clock.txt"');port.send(0x13);port.pump(.15)
   else:
    with clock.connect(a.port,a.build) as port:
     fast_control(port);write_file(port,clock.DIRECTORY+'/profile.txt',str(profile).encode());clock.launch(port,'CLKSET.APP',7)
     selection=receive_file(port,clock.DIRECTORY+'/select.txt');f=fields(selection);assert f['STEP']==4 and f['SAVED']&255==profile,selection
     port.command('rm "'+clock.DIRECTORY+'/select.txt"');old=current_binding(a.port)['device_id'];port.write_line('rst now');time.sleep(.15)
    gone=False;end=time.monotonic()+3
    while time.monotonic()<end:
     try:
      if current_binding(a.port)['device_id']!=old:gone=True;break
     except AssertionError as e:
      if e.args!=(('ambiguous/missing OS CDC binding',0),):raise
      gone=True;break
     time.sleep(.02)
    assert gone,'offline boot did not remove USB device'
    with clock.connect(a.port,a.build) as port:
     raw=receive_file(port,clock.DIRECTORY+'/offline.txt');proof=fields(raw);(a.output/f'{stage}-offline.json').write_text(json.dumps(proof,indent=2));assert proof['OPEN']==1,proof
     payload=receive_file(port,clock.DIRECTORY+'/clock.txt')
     assert proof['PROFILE']==profile and proof['HZ']==MHZ[profile]*500000,proof
     assert all(proof[k]==0 for k in ('GATE0','IRQ0','GATE1','IRQ1')),proof
     port.command('rm "'+clock.DIRECTORY+'/clock.txt"');port.command('rm "'+clock.DIRECTORY+'/offline.txt"')
   v=fields(payload);expected=[MHZ[profile]*500000,MHZ[profile]*1000000,MHZ[profile]*500000] if profile else [96000000]*3
   assert [v[f'HZ{i}'] for i in range(3)]==expected,v
   assert v['HASH']==3289793925 and v['MATCH']==v['END']==v['DUP']==1,v
   assert max(v[f'GAP{i}'] for i in range(3))<=30000,v
   (a.output/f'{stage}-{MHZ[profile]}.txt').write_bytes(payload)
   row=dict(stage=stage,profile=profile,mhz=MHZ[profile],result=v,usb_gating=proof,transport=transport)
   rows.append(row);(a.output/'rows.json').write_text(json.dumps(rows,indent=2)+'\n');print('Persisted profile',MHZ[profile],'MHz',expected,'PASS',flush=True)
 finally:
  # The completed last step and every offline boot return profile0. If a
  # prior online step failed, this explicit save/reset also restores USB96.
  clock.set_profile(a,0)
  with clock.connect(a.port,a.build) as port:
   for name in (*files,'profile.txt','select.txt','clock.txt','offline.txt'):port.command('rm "'+clock.DIRECTORY+'/'+name+'"')
   port.command('rmdir '+clock.DIRECTORY)
   health={n:port.command(n,timeout=15) for n in ('identity','df','crash show','mpu status','prof')};(a.output/'health.json').write_text(json.dumps(health,indent=2));assert 'CRASH none' in health['crash show'] and 'layout=ok' in health['mpu status'] and 'clock=96000000' in health['prof']
if __name__=='__main__':main()
