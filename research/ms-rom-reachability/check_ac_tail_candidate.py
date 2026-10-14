#!/usr/bin/env python3
"""Exact checks of an abstract paired-tail path, including core contexts.

Call through runpy with producers and candidate (a list of core states).
SAT remains a local artificial preparation, never a keyboard recipe.
"""
import runpy
from pathlib import Path
from z3 import sat, unsat

if 'candidate' not in globals() or 'producers' not in globals():
    raise SystemExit('Supply candidate and producers via runpy init_globals.')
ac=producers['ac']
q=ac['q']
address=ac['cover']['address']
a,p=ac['entry'](candidate[0])
b=a
entries=[]
outcome=sat
for index,(st,target) in enumerate(zip(candidate,candidate[1:])):
    p.add(ac['context_at'](st,b))
    entries.append(b)
    ip=st[0]
    b=b.copy();b.r[36]=q['N4'](ip);b.r[39]=q['N4'](ip>>4)
    b=q['execute_command'](b,ip,*q['arbitrary_keys'](f'tail_candidate_{index}'))
    if ip==0x93:
        b=q['execute_command'](b,0x94,*q['arbitrary_keys'](f'tail_candidate_94_{index}'))
    if ip==0x12:
        b=q['execute_command'](b,0xC6,*q['arbitrary_keys'](f'tail_candidate_C6_{index}'))
    p.add(ac['context_at'](target,b))
    if index==0 and 'first_pair' in globals():
        pair,value=first_pair
        fs=ac['rf']['fields'](b)
        p.add(fs[pair[0]]==value//16,fs[pair[1]]==value%16)
    outcome=p.check()
    assert outcome in (sat,unsat)
    if outcome==unsat:
        print(f'EXCLUDED: first joint contradiction at edge {index}: '
              f'{ip:02X}->{target[0]:02X}.',flush=True)
        break
else:
    p.add(ac['signature'](b))
    outcome=p.check()
    assert outcome in (sat,unsat)
    print(f'Full projected route plus joint AC signature: {outcome}.',flush=True)
print('No physical preparation is claimed.',flush=True)
