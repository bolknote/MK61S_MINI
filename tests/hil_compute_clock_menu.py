#!/usr/bin/env python3
"""Classic inline CPU menu: five distinct choices and exact96 roundtrip."""
import argparse,hashlib,json
from pathlib import Path
import hil_compute_clock as clock
from hil_portable_system_apps import png
from hil_turochamp_performance import board_pixels

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--build',required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--port',default='/dev/cu.usbmodem2068336B47311');a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False);shots=[]
 with clock.connect(a.port,a.build) as port:
  assert 'IP: 0' in port.command('reg');port.attach();port.begin_measurement()
  port.key(39)
  for _ in range(2):port.key(36)
  port.key(37)
  for _ in range(3):port.key(36)
  port.pump(1.2)
  for index,mhz in enumerate((96,108,120,132,138,96)):
   if index:port.key(37)
   port.pump(1.2 if mhz==96 else .25)
   frame=port.frames[-1];assert len(frame)==1536
   png(frame,a.output/f'{index}-{mhz}.png');(a.output/f'{index}-{mhz}.frame').write_bytes(frame)
   shots.append(dict(mhz=mhz,sha256=hashlib.sha256(board_pixels(frame)).hexdigest()))
  assert len({v['sha256'] for v in shots[:5]})==5,shots
  assert shots[0]['sha256']==shots[-1]['sha256'],shots
  port.key(39);port.key(39);port.pump(.25);port.end_measurement();port.send(0x13);port.pump(.15)
  assert 'IP: 0' in port.command('reg')
  result=dict(shots=shots,pongs=len(port.pings),pong_max_s=max(port.pings));(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print('Inline CPU96/108/120/132/138/96 distinct frames, exact roundtrip, stopped calculator and strict PONG PASS',flush=True)
if __name__=='__main__':main()
