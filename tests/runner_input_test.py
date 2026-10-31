"""Async game controls. World fixtures are explicit, never a full-campaign claim."""
import json,sys,tempfile
from pathlib import Path
from runner_async_port import Port
from runner_game_test import ROOT
B=Path(sys.argv[1]).resolve();temp=tempfile.TemporaryDirectory(prefix='runner-controls-');O=Path(temp.name);results=[]
def case(name,fn,level=1):
 d=O/name;d.mkdir();p=Port(ROOT/'programs/games/Runner',level,31,80,d,B)
 try:
  fn(p);results.append(dict(case=name,status='PASS'))
 finally:
  (d/'trace.json').write_text(json.dumps(p.trace,indent=2)+'\n');p.close()
def world(p,h):p.sendcmd(f'world {h} 36 0 36 36');p.pump(.35)
def down(p,k):p.sendcmd(f'down {k:X}')
def up(p,k):p.sendcmd(f'up {k:X}')
def tap(p,k):down(p,k);up(p,k)
def opposites(p,h,keys):
 world(p,h)
 for k in keys:down(p,k)
 p.pump(.8);assert p.state['regs'][4]==h,(h,keys,p.state['regs'])
 for k in keys:up(p,k)
 p.pump(.5);assert p.state['regs'][4]==h
for name,h,keys in [('horizontal-4-6',12,[4,6]),('horizontal-6-4',17,[6,4]),('vertical-8-2',18,[8,2]),('vertical-2-8',20,[2,8])]:case(name,lambda p,h=h,keys=keys:opposites(p,h,keys))
def orthogonal(p):
 world(p,18)
 for k in [4,6,8]:down(p,k)
 p.pump(.8);assert p.state['regs'][4]==30,p.state['regs']
 for k in [4,6,8]:up(p,k)
case('horizontal-cancel-vertical-priority',orthogonal)
def held(p):
 world(p,17);down(p,4);p.pump(.95);assert p.state['regs'][4]<=15,p.state['regs']
 up(p,4);p.pump(.5);h=p.state['regs'][4];p.pump(.5);assert p.state['regs'][4]==h and p.state['regs'][9]==0
case('held-and-up-stops',held)
def busy(p):
 p.sendcmd('world 18 36 0 36 36')
 end=p.state['ms']+2000
 while not p.state['running']:
  p.pump(.02);assert p.state['ms']<end
 tap(p,6);p.pump(.9);assert p.state['regs'][4]==19 and p.state['regs'][10]==0,p.state['regs']
case('short-tap-during-native-render',busy)
def hole(p):
 world(p,12);tap(p,9);end=p.state['ms']+3000
 while p.state['regs'][7]!=13 or p.state['running'] or p.state['regs'][3]!=1:
  p.pump(.02);assert p.state['ms']<end
 start=p.state['ms'];p.pump(3.5);assert p.state['regs'][7]==13
 while p.state['regs'][7]!=36 or p.state['running'] or p.state['regs'][3]!=1:
  p.pump(.02);assert p.state['ms']<start+5500
 elapsed=p.state['ms']-start;assert 3900<=elapsed<=5000,elapsed
 results.append(dict(case='hole-visible-restore-latency',elapsed_ms=elapsed,physical_claim=False))
case('four-second-hole',hole)
def trapped(p):
 p.sendcmd('world 18 19 0 19 36');p.pump(3.5)
 assert p.state['regs'][5]==19 and p.state['regs'][7]==19
 p.pump(1)
 assert p.state['regs'][7]==36 and p.state['regs'][5] in (34,35),p.state['regs']
case('trapped-guard-release',trapped)

def restart(p):
 world(p,23);tap(p,0);p.pump(1.8);assert p.state['regs'][4:9]==[12,35,0,36,36],p.state['regs']
case('restart-world',restart)
def helpcase(p):
 count=p.state['manuals'];down(p,0x13);up(p,0x13);p.pump(.8);assert p.state['manuals']==count+1 and p.state['active']
 tap(p,6);p.pump(.8);assert p.state['regs'][4]==13
case('manual-returns-to-game',helpcase)
def esc(p):
 down(p,0x14);up(p,0x14);p.pump(.5);assert not p.state['active'] and p.state['timer_ms']==0
 before=p.state['regs'];p.sendcmd('unbound 6');p.pump(5);assert p.state['regs']==before and not p.state['active']
case('escape-quiescent',esc,level=0)

# Sweep the M61 line-budget and WAIT boundaries: a short gesture cannot be
# overwritten by clearing the previous action's mailbox.
for phase in range(100):
 def phase_tap(p,phase=phase):
  world(p,18);p.pump(phase/1000);tap(p,6);p.pump(1)
  assert p.state['regs'][4]==19,(phase,p.state['regs'])
 case(f'short-tap-phase-{phase}',phase_tap)
temp.cleanup();print(json.dumps(dict(status='PASS',cases=len(results),device_IO=0)))
