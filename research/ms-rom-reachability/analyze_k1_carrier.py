#!/usr/bin/env python3
"""Find structural one-pair K1 candidates with the numeric word kept in A.

Reuse the C8-inclusive reset control abstraction. Positive paths still need
exact path and native checks. A missing path is NOT general K1 impossibility:
this first cover excludes storing the payload elsewhere or transforming it.
"""
from collections import deque
from pathlib import Path
import runpy
from z3 import And, unsat


def analyze(m, aligned=True, preserves=None):
    ctl=runpy.run_path(str(Path(__file__).with_name('audit_ms_rom_control.py')))
    successors,_=ctl['graph'](m)
    q=m['q']
    if preserves is None:
        preserves=set()
        for ip in range(256):
            a=q['State'](f'k1_carrier_{ip}')
            b=q['execute_command'](a,ip,*q['arbitrary_keys'](f'k1_carrier_keys_{ip}'))
            if ip==0x93:b=q['execute_command'](b,0x94,*q['arbitrary_keys']('k1_carrier_93_94'))
            if ip==0x12:b=q['execute_command'](b,0xC6,*q['arbitrary_keys']('k1_carrier_12_C6'))
            p=q['base_solver'](a,ip);p.add(~And(*[b.r[3*i]==a.r[3*i] for i in range(12)]))
            if p.check()==unsat:preserves.add(ip)
    print('Universal whole-A preserving macro steps:',len(preserves),flush=True)
    # Each start is immediately after a D6 read; phase 0 denotes its physical
    # page. E7 and the eventual D4 must meet that same page in the aligned run.
    parents={};queue=deque();start_count=0
    for state in successors:
        if state[0]!=0xD6:continue
        start_count+=1
        for target in successors[state]:
            key=(target,0,1 if aligned else 0)
            if key not in parents:parents[key]=(None,state);queue.append(key)
    terminals=[]
    while queue:
        item=queue.popleft();state,stage,phase=item;ip=state[0]
        # Only DD has the full twelve-tetrade alignment contract. DE changes
        # numeric fields and is not an interchangeable store preparation.
        if stage==1 and ip==0xDD and 4 in state[3] and (not aligned or (phase+1)%15==0):
            if any(t[0]==0xD4 for t in successors[state]):
                terminals.append(item)
                if len(terminals)>=8:break
        if stage==0 and ip==0xE7 and (not aligned or phase==0):new_stage=1
        elif ip in preserves and ip!=0xD4:new_stage=stage
        else:continue
        length=2 if ip in (0x12,0x93) else 1
        next_phase=(phase+length)%15 if aligned else 0
        for target in successors[state]:
            key=(target,new_stage,next_phase)
            if key not in parents:
                parents[key]=(item,None);queue.append(key)
        if len(parents)%50000==0:print('K1 carrier states',len(parents),'pending',len(queue),flush=True)
    print('K1 carrier:',start_count,'D6 starts,',len(parents),'product states,',
          len(terminals),'candidate terminals,',len(queue),'pending;',
          'same physical page' if aligned else 'phase unchecked',flush=True)
    paths=[]
    for item in terminals:
        path=[]
        while item is not None:
            state,stage,phase=item;path.append((state,stage,phase))
            previous,start=parents[item]
            if start is not None:path.append((start,-1,0))
            item=previous
        path.reverse();paths.append(path)
        print('CANDIDATE:',' '.join(f'{state[0]:02X}' for state,_,_ in path)+' D4',flush=True)
        print('  E7 entries:',[(state[1],state[2],state[3],phase)
                              for state,_,phase in path if state[0]==0xE7],flush=True)
    return {'paths':paths,'preserves':preserves,'parents':parents,'pending':len(queue)}


if __name__=='__main__':
    import sys
    aligned='--unaligned' not in sys.argv
    sys.argv=['analyze_gates.py','--target','c7','--r38','--check-c8-invariants']
    m=runpy.run_path(str(Path(__file__).with_name('analyze_gates.py')))
    analyze(m,aligned)
