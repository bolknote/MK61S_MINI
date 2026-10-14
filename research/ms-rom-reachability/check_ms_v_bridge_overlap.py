#!/usr/bin/env python3
"""Word-transfer composition, NOT a new microcode entry theorem.

Native tests establish the two actual interleavings, exact E7/A8 and 4E/2A
transfers, duplicated source in X/Y, and harmless intervening formatters.
Here an arbitrary 48-bit source proves why T, rather than Y, is stable.
"""
from z3 import BitVec, BitVecVal, Solver, unsat, sat
v,marker,request=[BitVec(n,48) for n in ['source','marker','request']]
zero=BitVecVal(0,48)
for overlap in [False,True]:
    ring=dict(zip('XYZT',[v,v,marker,request]));a=zero
    a,ring['X']=ring['X'],a
    a,ring['Y']=ring['Y'],a
    if overlap:b,ring['X']=ring['X'],v
    a,ring['Z']=ring['Z'],a
    if overlap:ring['Y']=b
    a,ring['T']=ring['T'],a
    a=zero
    for name in 'XYZT':a,ring[name]=ring[name],a
    p=Solver();p.add(ring['T']!=v);assert p.check()==unsat
    once=[ring[n] for n in 'YZTX']
    p=Solver();p.add(v!=zero,once[0]!=(v if overlap else zero));assert p.check()==unsat
    for _ in range(3):ring=dict(zip('XYZT',[ring[n] for n in 'YZTX']))
    p=Solver();p.add(ring['X']!=v);assert p.check()==unsat
    p=Solver();p.add(v!=zero);assert p.check()==sat
    print('PASS:',('overlapping last 4E/2A' if overlap else 'no overlapping output'),
          'T retains all 48 source bits after two zero lifts; three rotations return the source.',flush=True)
print('COUNTERPATH: without overlap, one rotation selects zero for every nonzero source. Entry, loop termination and formatter premises are native checks, not proved by this word model.',flush=True)
