#!/usr/bin/env python3
"""Classic offline PLL timing; strict full board and retained node validation."""
import argparse,hashlib,json,struct,time
from pathlib import Path
from hil_compute_chess import TimedPingPort
import hil_compute_clock as clock
from hil_usb_crc_ram import exchange
from hil_classic_cdc_guard import current_binding
from hil_portable_apps import cobs_decode
from hil_c6_system_bootstrap import write_file,read_file
from hil_vm_cache_latency import fast_control
from hil_turochamp_performance import Font,ROOT,prepare_search,completed_board,board_pixels,require_launcher_ok,stop_game
from hil_chess_screen_mode import sample,checked,node_probe,PROBE_FILES
from hil_portable_system_apps import png

class OfflinePort(TimedPingPort):
 def __init__(self,path):
  self.responses=[];self.open_text_start=0
  super().__init__(path)
 def receive_packet(self,encoded):
  raw=cobs_decode(encoded)
  # Parent checks packet length, CRC and all screen geometry even for RPC.
  super().receive_packet(encoded)
  if raw[3]==0x26 and len(raw)==23:self.responses.append(struct.unpack('<III',raw[9:-2]))

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--build',required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--port',default='/dev/cu.usbmodem2068336B47311');p.add_argument('--frequencies',type=int,nargs='+',required=True);p.add_argument('--repeat',type=int,default=3);a=p.parse_args()
 assert all(x in (96,120,132,138) for x in a.frequencies)
 a.game_dir='/Games/Turochamp';a.timeout=180;a.build_id=a.build;a.output.mkdir(parents=True,exist_ok=False);clock.PingPort=OfflinePort
 font=Font((ROOT/'programs/games/Turochamp/Turochamp.FMK').read_bytes());rows=[]
 with clock.connect(a.port,a.build) as port:port.write_line('rst now');time.sleep(.2)
 with clock.connect(a.port,a.build) as port:
  fast_control(port);listing=port.command('ls "'+a.game_dir+'"');assert all(n.casefold() not in listing.casefold() for n in PROBE_FILES)
  for n,data in PROBE_FILES.items():write_file(port,a.game_dir+'/'+n,data);read_file(port,a.game_dir+'/'+n,data)
  port.write_line('rst now');time.sleep(.2)
 try:
  for stage,mhz in enumerate(a.frequencies):
   for repeat in range(a.repeat):
    with clock.connect(a.port,a.build) as reset_port:
     reset_port.write_line('rst now');time.sleep(.2)
    index=len(rows);out=a.output/f'{stage}-{mhz}-{repeat}';out.mkdir()
    with clock.connect(a.port,a.build) as port:
     before=sample(port.command('prof'));port.attach()
     try:prepare_search(port,font,a,out)
     except BaseException:
      if port.frames:png(port.frames[-1],out/'failure.png');(out/'failure.frame').write_bytes(port.frames[-1])
      (out/'terminal.txt').write_bytes(port.text);raise
     old=current_binding(a.port)['device_id'];exchange(port,mhz,0xD5)
     port.send(0x30,b'\x25\x01');time.sleep(.1) # cancel() releases virtual keys; no late key-up across USB teardown
     # MCU closes USB before starting its KEYWAIT interval; do not parse
     # the cancelled stream or include re-enumeration in measured time.
     port.attached=False
    deadline=time.monotonic()+180;gone=False
    while time.monotonic()<deadline:
     try:
      binding=current_binding(a.port)
      if binding['device_id']!=old:gone=True;break
     except AssertionError as e:
      if e.args!=(('ambiguous/missing OS CDC binding',0),):raise
      gone=True
     time.sleep(.1)
    assert gone,'USB did not disconnect'
    with clock.connect(a.port,a.build) as port:
     port.attach();end=time.monotonic()+15;golden=None
     while time.monotonic()<end:
      port.pump(.04);require_launcher_ok(port)
      for frame in port.frames:
       if completed_board(font,frame):golden=frame
      if golden is not None:break
     assert golden is not None,'missing complete board'
     digest=hashlib.sha256(board_pixels(golden)).hexdigest();assert digest=='ef261082a0230600d21d7c4ae116e7cfc226f0fb9ce43a22fbbc26bcbe580460',digest
     png(golden,out/'move-e2-e3.png');(out/'move.frame').write_bytes(golden);stop_game(port)
     after=sample(port.command('prof'));elapsed=checked(before,after,'headless',8)
     nodes=node_probe(port,a.game_dir,out);port.send(0x13);port.pump(.15)
    row=dict(stage=stage,mhz=mhz,repeat=repeat,seconds=elapsed,nodes=nodes,move='e2e3',board_sha256=digest,usb_disconnected=True,before=before,after=after)
    rows.append(row);(a.output/'rows.json').write_text(json.dumps(rows,indent=2)+'\n');print(f'Offline chess {mhz} MHz {repeat}: {elapsed:.6f}s / {nodes} nodes PASS',flush=True)
 finally:
  with clock.connect(a.port,a.build) as port:
   for n in PROBE_FILES:port.command('rm "'+a.game_dir+'/'+n+'"')
   health={n:port.command(n,timeout=15) for n in ('identity','df','crash show','mpu status')};(a.output/'health.json').write_text(json.dumps(health,indent=2));assert 'CRASH none' in health['crash show'] and 'layout=ok' in health['mpu status']
if __name__=='__main__':main()
