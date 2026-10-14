#!/usr/bin/env python3
"""Check every paired tail producer boundary in one symbolic execution."""
import runpy
from collections import defaultdict
from pathlib import Path
from z3 import sat, unsat

root=Path(__file__).resolve().parent
if 'producers' not in globals():
    producers=runpy.run_path(str(root/'analyze_ac_tail_producers.py'))
ac=producers['ac']
q,rf=ac['q'],ac['rf']
executions={}
retained=defaultdict(dict)
for ip,edges in sorted(producers['frontiers'].items()):
    for (st,target,pair),mask in edges.items():
        a,p=ac['entry'](st)
        if ip not in executions:
            b=q['execute_command'](a,ip,*q['arbitrary_keys'](f'tail_producer_{ip}'))
            if ip==0x93:
                b=q['execute_command'](b,0x94,*q['arbitrary_keys']('tail_producer_93_94'))
            if ip==0x12:
                b=q['execute_command'](b,0xC6,*q['arbitrary_keys']('tail_producer_12_C6'))
            executions[ip]=b
        b=executions[ip]
        fs=rf['fields'](b)
        p.add(ac['context_at'](target,b),ac['pair_constraint'](fs[pair[0]],fs[pair[1]],mask))
        outcome=p.check()
        assert outcome in (sat,unsat)
        if outcome==sat:
            retained[ip][st,target,pair]=mask
    pairs={pair for _,_,pair in retained[ip]}
    print(f'{ip:02X}: {len(retained[ip])}/{len(edges)} joint edges; '+
          '; '.join('/'.join(rf['NAMES'][i] for i in pair)+' <- '+
                    str(tuple(rf['specs'][ip][i] for i in pair)) for pair in sorted(pairs)),flush=True)
print('PASS: joint producer boundary checks completed; these are local '+
      'possibilities, not reset-to-AC paths.',flush=True)
