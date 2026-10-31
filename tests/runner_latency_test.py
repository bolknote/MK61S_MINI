#!/usr/bin/env python3
"""HOST latency/hold/hole observations; never a Classic or USB timing claim."""
import argparse,json,statistics,tempfile
from pathlib import Path
from runner_async_port import Port,helper
from runner_game_test import ROOT,BOARDS

def main():
 a=argparse.ArgumentParser();a.add_argument('binary',type=Path);a.add_argument('--output',type=Path);args=a.parse_args()
 binary=args.binary.resolve();rows=[]
 with tempfile.TemporaryDirectory(prefix='runner-latency-') as temp:
  for level,board in enumerate(BOARDS,1):
   times=[]
   for phase in (*range(0,1000,125),*range(1000,2000,125)):
    folder=Path(temp)/f'{level}-{phase}';folder.mkdir();p=Port(ROOT/'programs/games/Runner',level,31,80,folder,binary)
    try:
     p.pump(phase/1000);start=p.state['ms'];p.sendcmd('down 6');p.sendcmd('up 6')
     target=board['start']%12+1
     while p.state['ms']<start+5000:
      masks=helper.decode(p.frames[-1],level)
      if masks and masks.count(107)==1 and masks.index(107)==target:break
      p.pump(.02)
     else:raise AssertionError(('no visible step',level,phase))
     times.append(dict(phase_ms=phase,latency_ms=p.state['ms']-start))
    finally:p.close()
   folder=Path(temp)/f'{level}-hold';folder.mkdir();p=Port(ROOT/'programs/games/Runner',level,31,80,folder,binary)
   try:
    p.sendcmd('down 6');p.pump(3);p.sendcmd('up 6');masks=helper.decode(p.frames[-1],level)
    assert masks and masks.count(107)==1
    held=masks.index(107)-board['start']%12;assert held>=4,(level,held)
   finally:p.close()
   folder=Path(temp)/f'{level}-hole';folder.mkdir();p=Port(ROOT/'programs/games/Runner',level,31,80,folder,binary)
   try:
    tile=board['start']%12+1;p.sendcmd('down 9');p.sendcmd('up 9');start=p.state['ms'];burn=None
    while p.state['ms']<start+8000:
     masks=helper.decode(p.frames[-1],level)
     if masks and masks[tile]==0 and burn is None:burn=p.state['ms']
     if burn is not None and masks and masks[tile]==8:break
     p.pump(.02)
    else:raise AssertionError(('hole not restored',level))
    hole=p.state['ms']-burn;assert 3900<=hole<=5000,(level,hole)
   finally:p.close()
   rows.append(dict(level=level,observed_steps=times,median_ms=statistics.median(x['latency_ms'] for x in times),max_ms=max(x['latency_ms'] for x in times),held_cells_in_3_seconds=held,hole_visible_ms=hole))
 result=dict(status='HOST_PASS',device_IO=0,not_physical_USB_model=True,step_ms=31,observer_ms=80,levels=rows)
 if args.output:args.output.write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps(result))
if __name__=='__main__':main()
