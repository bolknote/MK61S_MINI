#!/usr/bin/env python3
"""Backward slice of the joint AC preparation, stopping at field writers.

The entire five-field signature is retained together on each exact edge.
Loops through commands preserving those five fields are closed to a
fixpoint. A positive writer boundary is not a reachable initialization.
"""
import runpy
from collections import defaultdict, deque
from pathlib import Path
from z3 import And, Or, UGE, sat, unsat, substitute

root=Path(__file__).resolve().parent
if 'restore_pairs' not in globals():
    restore_pairs=runpy.run_path(str(root/'analyze_restore_field_pairs.py'),
                               init_globals={'all_pairs':True})
rp=restore_pairs
rf=rp['f']
cover,q=rf['cover'],rf['q']
fields=rf['fields']
indices=tuple(rf['NAMES'].index(n) for n in ('R1','R31','R34','ST32','ST35'))
TOP=rf['TOP']


def signature(a):
    return And(UGE(a.r[1],5),a.r[31]==8,a.r[34]==5,UGE(a.st[32],12),a.st[35]==9)


def pair_constraint(x,y,mask):
    rows=[]
    for value in range(16):
        columns=(mask >> (16*value)) & TOP
        if columns:
            rows.append(And(x==value,Or(*[y==j for j in rf['bit_values'](columns)])))
    return Or(*rows)


def entry(state):
    a,p=cover['entry_solver'](state)
    fs=fields(a)
    unary=rf['domains'][state]
    for expr,mask in zip(fs,unary):
        if mask!=TOP:
            p.add(Or(*[expr==n for n in rf['bit_values'](mask)]))
    for (i,j),mask in zip(rp['PAIRS'],rp['domains'][state]):
        if mask!=rp['rectangle'](unary[i],unary[j]):
            p.add(pair_constraint(fs[i],fs[j],mask))
    return a,p


core_contexts={}
def context_at(state,b):
    if state not in core_contexts:
        a,p=cover['entry_solver'](state)
        core_contexts[state]=(a,And(*p.assertions()))
    a,pred=core_contexts[state]
    replacements=[(x,y) for group in ('r','m','st')
                  for x,y in zip(getattr(a,group),getattr(b,group))]
    replacements += [(getattr(a,n),getattr(b,n)) for n in ('s','s1','l','t','carry')]
    return substitute(pred,*replacements)


incoming=defaultdict(list)
for st in rp['domains']:
    for nxt in cover['successors'][st]:
        if nxt in rp['domains']:
            incoming[nxt].append(st)
wanted=set()
for st in rp['domains']:
    if st[0]!=0xAC:
        continue
    a,p=entry(st)
    p.add(signature(a))
    outcome=p.check()
    assert outcome in (sat,unsat)
    if outcome==sat:
        wanted.add(st)
print(f'AC full joint signature: {len(wanted)} pair-covered core contexts remain.',flush=True)
queue=deque(wanted)
roots=defaultdict(set)
executions={}
checked=0
last_report=0
while queue:
    target=queue.popleft()
    for st in incoming[target]:
        ip=st[0]
        a,p=entry(st)
        if ip not in executions:
            b=q['execute_command'](a,ip,*q['arbitrary_keys'](f'ac_joint_{ip}'))
            if ip==0x93:
                b=q['execute_command'](b,0x94,*q['arbitrary_keys']('ac_joint_93_94'))
            if ip==0x12:
                b=q['execute_command'](b,0xC6,*q['arbitrary_keys']('ac_joint_12_C6'))
            executions[ip]=b
        b=executions[ip]
        p.add(context_at(target,b),signature(b))
        outcome=p.check()
        assert outcome in (sat,unsat)
        checked+=1
        if outcome==unsat:
            continue
        preserved=all(rf['specs'][ip][i]==('copy',i,0) for i in indices)
        if preserved:
            if st not in wanted:
                wanted.add(st)
                queue.append(st)
        else:
            roots[ip].add((st,target))
    if len(wanted)>=last_report+500:
        print(f'joint AC slice: {len(wanted)} states, {len(queue)} pending',flush=True)
        last_report=len(wanted)
print(f'PASS: AC preparation slice closed: {len(wanted)} states, '
      f'{checked} checked incoming edges, queue empty.',flush=True)
for ip,edges in sorted(roots.items()):
    changed=[rf['NAMES'][i] for i in indices if rf['specs'][ip][i]!=('copy',i,0)]
    print(f'  writer {ip:02X}: {len(edges)} edges; changes '+','.join(changed)+
          '; next '+','.join(f'{n:02X}' for n in sorted({t[0] for _,t in edges})),flush=True)
print('Writer frontiers remain conservative, not a keyboard recipe.',flush=True)
