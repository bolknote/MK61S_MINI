#!/usr/bin/env python3
"""Does any secondary ROM command observe a difference in R23 alone?

Every command is tested with arbitrary other chip state, common arbitrary
keys and incoming serial word. A counterexample is local, not reachable.
"""
import runpy
from pathlib import Path
from z3 import BitVec, Or, sat, unsat

q=runpy.run_path(str(Path(__file__).with_name('analyze_ms_pending_opcodes.py')))
State,ex,base,keys=(q[n] for n in ('State','ex','base','keys'))
observers=[]
for ip in range(256):
    a=State('r23_%02X'%ip);b=a.copy();b.r[23]=BitVec('other_r23_%02X'%ip,4)
    p=base(a,ip);incoming=State('incoming_%02X'%ip).m;signals=keys('keys_%02X'%ip)
    oa=[];ob=[]
    aa=ex(a,ip,*signals,serial_inputs=incoming,emitted_outputs=oa)
    bb=ex(b,ip,*signals,serial_inputs=incoming,emitted_outputs=ob)
    differences=[x!=y for i,(x,y) in enumerate(zip(aa.r,bb.r)) if i!=23]
    differences += [x!=y for name in ('st','m') for x,y in zip(getattr(aa,name),getattr(bb,name))]
    differences += [getattr(aa,name)!=getattr(bb,name) for name in ('s','s1','l','t','carry')]
    differences += [x!=y for x,y in zip(oa,ob)]
    p.add(Or(*differences));answer=p.check()
    assert answer in (sat,unsat)
    if answer==sat:observers.append('%02X'%ip)
    if ip%32==31:print('checked through %02X; potential observers:'%ip,observers,flush=True)
print('RESULT secondary commands potentially observing R23:',observers,flush=True)
print('LIMIT: local arbitrary states; a SAT observer is not a reachable keyboard path.',flush=True)
