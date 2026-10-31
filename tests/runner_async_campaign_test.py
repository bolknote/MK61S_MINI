#!/usr/bin/env python3
"""Complete ordinary-key campaign with live async LCD delivery; no fixtures."""
import argparse,json,tempfile
from pathlib import Path
from types import SimpleNamespace
from runner_async_port import Port,helper
from runner_game_test import ROOT
from hil_runner_classic import DIGITS
from runner_frame_player import Action,observe,won,lost

def main():
 a=argparse.ArgumentParser();a.add_argument('binary',type=Path);a.add_argument('--step',type=int,default=31);a.add_argument('--observer',type=int,default=80);a.add_argument('--output',type=Path);args=a.parse_args()
 temp=tempfile.TemporaryDirectory(prefix='runner-async-') if args.output is None else None
 args.output=args.output or Path(temp.name);args.output.mkdir(exist_ok=True)
 p=Port(ROOT/'programs/games/Runner',0,args.step,args.observer,args.output,args.binary.resolve());oldtime=helper.time;helper.time=SimpleNamespace(monotonic=lambda:p.state['ms']/1000);result=dict(status='RUNNING',device_IO=0,step_ms=args.step,observer_ms=args.observer,fixture_mutations=0,cases=[])
 def gesture(k):
  p.send(0x30,bytes((DIGITS[k],1)));p.send(0x30,bytes((DIGITS[k],0)))
 def until(predicate,limit=20000):
  end=p.state['ms']+limit
  while p.state['ms']<end:
   if predicate():return
   p.pump(.02)
  raise AssertionError(('timeout',p.state))
 try:
  # L1 uses the same guard-turn cadence as the accepted physical HIL. RE is
  # test/driver timing here; frame-only L2/L3 never receive these registers.
  floor=1;phase=p.state['regs'][14];rows=[]
  for digit in '66244668666666666484444444444':
   until(lambda:p.state['regs'][14]>=0 and p.state['regs'][14]!=phase)
   phase=p.state['regs'][14];masks=helper.decode(p.frames[-1],1);view=observe(1,masks,floor);action=Action(1,view,int(digit));p.pump(.1);index=len(p.frames);gesture(int(digit));start=p.state['ms'];selected=None
   end=p.state['ms']+10000
   while p.state['ms']<end:
    for raw in p.frames[index:]:
     selected=helper.decode(raw,1)
     if selected and lost(selected):raise AssertionError('L1 visible defeat')
     if selected and (won(1,selected) or action.candidate(selected)):break
    else:index=len(p.frames);p.pump(.02);continue
    break
   else:raise AssertionError('L1 action timeout')
   floor=action.floor_hint;rows.append(dict(key=int(digit),at_ms=start,masks=selected))
  until(lambda:won(1,helper.decode(p.frames[-1],1)))
  selected=helper.decode(p.frames[-1],1)
  assert won(1,selected);result['cases'].append(dict(case='L1 full clear',rows=rows))
  for level,start,first in ((2,17,0),(3,18,5)):
   until(lambda:p.state['regs'][4:9]==[start,first,0,36,35] and p.state['regs'][3]==1 and p.state['timer_ms']>0 and not p.state['running'])
   report=helper.play_level(p,level);assert report['won'];result['cases'].append(dict(case=f'L{level} full clear',report=report))
  assert won(3,helper.decode(p.frames[-1],3));result['cases'].append(dict(case='ALL CLEAr final bitmap',masks=helper.decode(p.frames[-1],3)))
  p.pump(1.7);gesture(0)
  until(lambda:p.state['regs'][4:9]==[12,35,0,36,36] and p.state['regs'][3]==1 and not p.state['running'])
  result['cases'].append(dict(case='campaign restart',registers=p.state['regs']))
  gesture(9);until(lambda:p.state['regs'][7]==13 and p.state['regs'][3]==1 and not p.state['running'])
  p.sendcmd('clear-bindings');p.sendcmd('cancel');before=p.state['regs'];p.pump(5)
  assert p.state['regs']==before and p.state['timer_ms']==0 and not p.state['active']
  result['cases'].append(dict(case='common bind/trap/timer cancellation stays quiescent',physical_long_Cx_not_claimed=True))
  result['status']='PASS'
 except Exception as e:
  import traceback
  result.update(status='FAIL',error=repr(e),traceback=traceback.format_exc())
 finally:
  helper.time=oldtime;result.update(keys=p.key_edges,changes=p.changes,final=p.state);p.close();result['native_exit_code']=p.exit_code;(args.output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps({k:v for k,v in result.items() if k not in ('cases','keys','changes','final')}))
 assert result['status']=='PASS',result.get('traceback',result)
 if temp:temp.cleanup()
if __name__=='__main__':main()
