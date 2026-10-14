#!/usr/bin/env python3
"""Joint immediate inputs of the saved-tail pushers in the AC ancestry.

Every source predicate and target core context use one exact execution.
This refines local candidates only; it does not establish a reset path.
"""
import runpy
from collections import defaultdict
from pathlib import Path
from z3 import And, Or, sat, unsat

root=Path(__file__).resolve().parent
if 'tail_origins' not in globals():
    tail_origins=runpy.run_path(str(root/'analyze_ac_tail_origins.py'))
ac=tail_origins['ac_slice']
q=ac['q']
rows={}
executions={}
for target_ip, root_edges in sorted(tail_origins['exact_roots'].items()):
    targets=defaultdict(int)
    for (st,_),mask in root_edges.items():
        targets[st]|=mask
    sources=defaultdict(list)
    for target,mask in targets.items():
        for st in ac['incoming'][target]:
            a,p=ac['entry'](st)
            ip=st[0]
            if ip not in executions:
                b=q['execute_command'](a,ip,*q['arbitrary_keys'](f'tail_input_{ip}'))
                if ip==0x93:
                    b=q['execute_command'](b,0x94,*q['arbitrary_keys']('tail_input_93_94'))
                if ip==0x12:
                    b=q['execute_command'](b,0xC6,*q['arbitrary_keys']('tail_input_12_C6'))
                executions[ip]=b
            b=executions[ip]
            p.add(ac['context_at'](target,b),b.r[33]==9,
                  Or(*[b.r[30]==v for v in range(12,16) if mask & (1<<(16*v+9))]))
            outcome=p.check()
            assert outcome in (sat,unsat)
            if outcome==sat:
                sources[ip].append((st,target))
    rows[target_ip]=dict(sources)
    print(f'Joint inputs of {target_ip:02X}:',flush=True)
    for ip,edges in sorted(sources.items()):
        print(f'  {ip:02X}: {len(edges)} edges, {len({s for s,_ in edges})} sources; '+
              'SP='+','.join('/'.join(f'{v:02X}' for v in sp)
                            for sp in sorted({s[1] for s,_ in edges})),flush=True)
print('PASS: complete joint local input check; retained sources are not keyboard preparations.',flush=True)
