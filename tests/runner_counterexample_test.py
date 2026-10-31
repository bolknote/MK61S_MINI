#!/usr/bin/env python3
"""Actual W7 visible L2 state, eight delivery phases; disclosed HOST fixture."""
import json,sys,tempfile
from pathlib import Path
from types import SimpleNamespace
from runner_async_port import Port,helper
from runner_frame_player import observe,won
from runner_game_test import ROOT

def main():
 binary=Path(sys.argv[1]).resolve();rows=[]
 with tempfile.TemporaryDirectory(prefix='runner-counterexample-') as temp:
  for phase in (0,125,250,375,500,625,750,875):
   folder=Path(temp)/str(phase);folder.mkdir()
   p=Port(ROOT/'programs/games/Runner',2,31,80,folder,binary);oldtime=helper.time
   try:
    p.sendcmd('world 15 18 4 36 19');end=p.state['ms']+5000
    while p.state['ms']<end:
     masks=helper.decode(p.frames[-1],2);view=observe(2,masks,1) if masks and masks.count(107)==1 else None
     if view and view['hero']==15 and view['guards']==[18,19]:break
     p.pump(.02)
    else:raise AssertionError('fixture publication missing')
    p.pump(phase/1000);helper.time=SimpleNamespace(monotonic=lambda:p.state['ms']/1000)
    report=helper.play_level(p,2,initial_stage='middle-left',reset_start=False)
    assert report['won'] and won(2,helper.decode(p.frames[-1],2))
    rows.append(dict(phase_ms=phase,status='PASS'))
   finally:helper.time=oldtime;p.close()
 print(json.dumps(dict(status='PASS',cases=rows,device_IO=0,scope='visible state fixture, not reconstructed hidden physical phase')))
if __name__=='__main__':main()
