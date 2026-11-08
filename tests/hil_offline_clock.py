#!/usr/bin/env python3
"""Addressed Classic correctness with USB hardware off during custom PLL runs."""
import argparse,json,time
from pathlib import Path
import hil_compute_clock as clock
from hil_usb_crc_transport import CapturePort
from hil_usb_crc_ram import exchange
from hil_c6_system_bootstrap import write_file,read_file
from hil_vm_cache_latency import fast_control
from hil_classic_cdc_guard import current_binding

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--build',required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--artifacts',type=Path,required=True);p.add_argument('--app',type=Path,required=True);p.add_argument('--port',default='/dev/cu.usbmodem2068336B47311');p.add_argument('--frequencies',nargs='+',type=int,default=[96,120,132,138,96]);p.add_argument('--repeat',type=int,default=2);a=p.parse_args()
 assert all(hz in (96,120,132,138,144) for hz in a.frequencies) and 1<=a.repeat<=3
 a.output.mkdir(parents=True,exist_ok=False);clock.PingPort=CapturePort
 fixtures={'CLKSET.APP':a.artifacts/'fixed-ui/CLKSET.APP','CRCWORK.APP':a.app};rows=[]
 with clock.connect(a.port,a.build) as port:
  fast_control(port);assert clock.DIRECTORY[1:] not in port.command('ls');port.command('mkdir '+clock.DIRECTORY)
  for name,path in fixtures.items():
   data=path.read_bytes();write_file(port,clock.DIRECTORY+'/'+name,data);read_file(port,clock.DIRECTORY+'/'+name,data)
 try:
  clock.set_profile(a,0)
  for stage,mhz in enumerate(a.frequencies):
   for repeat in range(a.repeat):
    before=current_binding(a.port)['device_id']
    with clock.connect(a.port,a.build) as port:
     port.attach();exchange(port,mhz,0xD3);port.open(clock.DIRECTORY+'/CRCWORK.APP');time.sleep(.1)
    gone=False;end=time.monotonic()+2
    while time.monotonic()<end:
     try:
      if current_binding(a.port)['device_id']!=before:gone=True;break
     except AssertionError:gone=True;break
     time.sleep(.02)
    assert gone,'USB did not disconnect for offline workload'
    with clock.connect(a.port,a.build) as port:
     port.attach();values=[exchange(port,i,0xD4)[2] for i in range(70)]
     fail=[exchange(port,i,0xD4)[2] for i in range(112,116)] if values[62] else []
     port.send(0x13);port.pump(.15);assert not port.bad_packets,port.bad_packets
    row=dict(stage=stage,mhz=mhz,repeat=repeat,usb_disconnected=gone,results=values,format_failure=fail)
    row['pass']=all(values[20*i]==3289793925 and values[20*i+1]==mhz*1000000 for i in range(3)) and values[60]==values[62]==0 and values[61]==mhz and values[63]==0x31415926 and all(v==0 for v in values[64:70])
    row['keyboard_gap_pass']=all(values[20*p+4+i]<=30000 for p in range(3) for i in range(7));row['pass'] &= row['keyboard_gap_pass']
    rows.append(row);(a.output/'rows.json').write_text(json.dumps(rows,indent=2)+'\n');print('Offline',mhz,'MHz repeat',repeat,'formatErrors',values[62],'atomic',values[64:70],'copyErrors',values[60],'PASS',row['pass'],flush=True)
 finally:
  with clock.connect(a.port,a.build) as port:
   for name in (*fixtures,'profile.txt','select.txt'):port.command('rm "'+clock.DIRECTORY+'/'+name+'"')
   port.command('rmdir '+clock.DIRECTORY)
   health={n:port.command(n,timeout=15) for n in ('identity','df','crash show','mpu status')};(a.output/'health.json').write_text(json.dumps(health,indent=2));assert 'CRASH none' in health['crash show'] and 'layout=ok' in health['mpu status']
if __name__=='__main__':main()
