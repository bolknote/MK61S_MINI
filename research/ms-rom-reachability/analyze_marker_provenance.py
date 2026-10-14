#!/usr/bin/env python3
"""Last marker/selector writer provenance on the completed reset graph.

This propagates history labels over ALL cached edges, not only the discovery
tree. No numeric constraints are removed or strengthened. Labels are joined,
so positive origins are overapproximations; an absent origin is excluded.
"""
import runpy
import sys
from collections import deque
from pathlib import Path

from z3 import And, Or, sat, unsat

sys.argv = ['analyze_gates.py','--target','cd','--r38','--first-entry-lemmas']
m = runpy.run_path(str(Path(__file__).with_name('analyze_gates.py')))
assert not m['queue'] and m['terminal'] is None
parents,templates,cache = (m[n] for n in ('parents','templates','cache'))
successors = {}

for state in parents:
    ip,sp,vector,selector,delta,r38,dr38,r26,types = state
    t = templates[ip]
    (a,addr,av,old,kind,pushed,new_vector,new_selector,final_selector,delta_op,
     sp_deps,final_r38,preserves_r38,dr38_op,final_r26,preserves_r26,
     final_types,type_preserved) = t
    key = (ip,tuple(sp[i] for i in sp_deps),vector,selector,delta,r38,dr38,r26,types)
    assert key in cache,('missing processed transition',ip)
    next_sp = (sp if kind=='same' else sp[1:]+sp[:1] if kind=='rotate' else
               (0xC7,0x13,sp[0]) if kind=='push2' else (pushed,sp[0],sp[1]))
    next_vector = vector if new_vector=='preserve' else new_vector
    next_delta = ((delta+delta_op[1])%16 if delta is not None else None) \
        if delta_op[0]=='add' else delta_op[1]
    next_dr38 = ((dr38+dr38_op[1])%16 if dr38 is not None else None) \
        if dr38_op[0]=='add' else dr38_op[1]
    next_states = []
    for nxt,sel,m38,m26,typ in cache[key]:
        if nxt in (0xC7,0xC8):
            continue
        target = (nxt,next_sp,next_vector,sel,next_delta,m38,next_dr38,m26,typ)
        assert target in parents,('successor outside completed cover',target)
        next_states.append(target)
    successors[state] = tuple(next_states)

# Marker labels also retain the selector value domain at that marker write.
# This is deliberately a union, not a claim that each value remains compatible
# with every subsequent numeric condition at the joined target.
origins26 = {state:set() for state in parents}
origins38 = {state:set() for state in parents}
start = m['start']
origins26[start].add(('reset',0))
origins38[start].add('reset')
queue,pending = deque([start]),{start}
updates = 0
while queue:
    state = queue.popleft()
    pending.remove(state)
    ip = state[0]
    t = templates[ip]
    writer26 = 0xC6 if ip==0x12 else ip
    out26 = origins26[state] if t[15] else {(writer26,n) for n in state[5]}
    out38 = origins38[state] if t[12] else {ip}
    for target in successors[state]:
        extra26 = out26-origins26[target]
        extra38 = out38-origins38[target]
        if not extra26 and not extra38:
            continue
        origins26[target].update(extra26)
        origins38[target].update(extra38)
        if target not in pending:
            queue.append(target)
            pending.add(target)
    updates += 1
assert all(origins26.values()) and all(origins38.values())

# Verify the completed history cover independently of worklist scheduling:
# every existing graph edge must carry every required origin into its target.
edges = 0
for state,targets in successors.items():
    ip,t = state[0],templates[state[0]]
    out26 = origins26[state] if t[15] else {(0xC6 if ip==0x12 else ip,n) for n in state[5]}
    out38 = origins38[state] if t[12] else {ip}
    for target in targets:
        assert out26<=origins26[target] and out38<=origins38[target]
        edges += 1
print(f'PASS: history fixpoint over {len(parents)} states and {edges} cached '
      f'edges; {updates} updates. Every edge is covered, queue empty.',flush=True)


def entry_solver(state):
    ip,sp,vector,selector,delta,r38,dr38,r26,types = state
    a,addr,av,old = templates[ip][:4]
    p = m['state_solver'](a,ip)
    if vector=='diagonal':
        p.add(a.r[37]==a.r[40])
    elif vector is not None:
        p.add(av==vector)
    p.add(Or(*[a.s1==n for n in selector]),Or(*[a.r[38]==n for n in r38]),
          Or(*[a.r[26]==n for n in r26]),*[v==n for v,n in zip(old,sp)])
    if delta is not None:
        p.add(a.s1-a.r[35]==delta)
    if dr38 is not None:
        p.add(a.r[38]-a.r[35]==dr38)
    return a,p


queries = {
    '60/selector9/marker1':(0x60,lambda a:And(a.r[38]==9,a.r[26]==1)),
    '1D/marker1':(0x1D,lambda a:a.r[26]==1),
    '6D/selector9/marker0':(0x6D,lambda a:And(a.r[38]==9,a.r[26]==0)),
    '07/selector9':(0x07,lambda a:a.r[38]==9),
    '4F->6F/selector9':(0x4F,lambda a:a.r[38]==9),
}
for name,(wanted,condition) in queries.items():
    selected = []
    for state in parents:
        if state[0]!=wanted:
            continue
        a,p = entry_solver(state)
        p.add(condition(a))
        if wanted==0x4F:
            p.add(templates[wanted][1]==0x6F)
        outcome = p.check()
        assert outcome in (sat,unsat)
        if outcome==sat:
            selected.append(state)
    marker = {label for state in selected for label in origins26[state]}
    selector = {label for state in selected for label in origins38[state]}
    def fmt(n):
        return n if isinstance(n,str) else f'{n:02X}'
    print(f'{name}: {len(selected)} contexts',flush=True)
    print('  last marker writer / selector at write: '+', '.join(
        f'{fmt(ip)}/{value:X}' for ip,value in sorted(marker,key=str)),flush=True)
    print('  last selector writer: '+', '.join(fmt(n) for n in sorted(selector,key=str)),flush=True)
print('Origins are a conservative history cover, not a concrete path or '
      'joint numeric feasibility certificate.',flush=True)
