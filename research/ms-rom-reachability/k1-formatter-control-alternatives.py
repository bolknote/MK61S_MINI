#!/usr/bin/env python3
"""Nearest first writers after selected real EE return tags, using the cache.

Only universally whole-A-preserving, non-ring-writing intermediate macro
commands are traversed. This intentionally omits recovery from other
buffers; a missing path is not a global impossibility theorem.
"""
from collections import deque
import gzip
import json
from pathlib import Path
import runpy
from z3 import And, unsat

root=Path(__file__).resolve().parent
audit=runpy.run_path(str(root/'k1-formatter-entry-audit.py'))
with gzip.open(audit['cache_path'],'rt',encoding='utf8') as stream:data=json.load(stream)
assert data['metadata']['complete'] and data['metadata']['pending']==0
assert data['metadata']['sourceSha256']==audit['fingerprints']()
q=runpy.run_path(str(root/'ik1302_symbolic.py'))
states=data['states'];edges=data['successors'];properties={}

def classify(ip):
    if ip in properties:return properties[ip]
    a=q['State']('alt_%02X'%ip);p=q['base_solver'](a,ip);b=a;out=[]
    commands=[ip]+([0x94] if ip==0x93 else [0xC6] if ip==0x12 else [])
    for step,cmd in enumerate(commands):
        emitted=[];previous=b.m;b=q['execute_command'](b,cmd,*q['arbitrary_keys']('alt_%02X_%d'%(ip,step)),emitted_outputs=emitted)
        out += [x==y for x,y in zip(emitted,previous)]
    p.push();p.add(~And(*[b.r[3*j]==a.r[3*j] for j in range(12)]));held=p.check()==unsat;p.pop()
    p.push();p.add(~And(*out));quiet=p.check()==unsat;p.pop()
    properties[ip]=(held,quiet);return held,quiet

for tag in (0xA8,0xAB,0xAD,0xDD,0xE0,0xA1):
    starts=[i for i in data['indexes']['byIp']['EE'] if states[i][1][0]==tag]
    pending=deque();seen=set();terminals={};stops=set()
    for start in starts:
        for nxt in edges[start]:
            if nxt not in seen:seen.add(nxt);pending.append((nxt,[start,nxt]))
    while pending:
        index,path=pending.popleft();state=states[index];ip=state[0]
        if ip in (0xE7,0xE9,0xA8) or ip==0xDD and 4 in state[3]:
            key=(ip,state[1][0]);terminals.setdefault(key,path);continue
        if ip in (0xEE,0xE3,0x91,0x93,0xF1,0xDD):stops.add((ip,'read/normalizer/unaligned DD'));continue
        held,quiet=classify(ip)
        if not held or not quiet:stops.add((ip,'A changes' if not held else 'possible prior ring write'));continue
        for nxt in edges[index]:
            if nxt not in seen:seen.add(nxt);pending.append((nxt,path+[nxt]))
    print('EE/top%02X: %d initial states, %d finite graph nodes inspected'%(tag,len(starts),len(seen)),flush=True)
    for (writer,ret),path in sorted(terminals.items()):
        seq=[states[i][0] for i in path]
        phase=sum(2 if ip in (0x12,0x93) else 1 for ip in seq[:-1])%15
        print('  CANDIDATE', ' '.join('%02X'%ip for ip in seq),
              'writerOffsetMod15='+str(phase),'writerTop=%02X'%ret,'state='+str(path[-1]),flush=True)
    print('  STOP:',[('%02X'%ip,why) for ip,why in sorted(stops)],flush=True)
print('LIMIT: abstract existence plus universal A-carrier edges. Physical marker phases, exact source selection, pending other-chip work and a native keyboard entry remain unproved.',flush=True)
