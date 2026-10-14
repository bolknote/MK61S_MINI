#!/usr/bin/env python3
"""Trace the saved tail as one pair through the three numeric ST levels.

Both tetras always travel together through the proved stack transfers.
The input R pair is the frontier, not an arbitrary separately chosen
source for each tetra. This is a conservative graph/data-flow closure.
"""
import runpy
from collections import defaultdict, deque
from pathlib import Path
from z3 import And, Or, sat, unsat

root=Path(__file__).resolve().parent
if 'ac_slice' not in globals():
    ac_slice=runpy.run_path(str(root/'analyze_ac_signature_sources.py'))
rp,rf,cover=(ac_slice[n] for n in ('rp','rf','cover'))
levels=tuple((rf['NAMES'].index(f'ST{30+i}'),rf['NAMES'].index(f'ST{33+i}'))
             for i in range(3))
registers=(rf['NAMES'].index('R30'),rf['NAMES'].index('R33'))
allowed=sum(1 << (16*i+9) for i in range(12,16))


def pair_domain(state,pair):
    mask=rp['domains'][state][rp['PAIR_INDEX'][pair]]
    return mask & allowed


incoming=ac_slice['incoming']
domains={}
queue=deque()
pending=set()
links={}
for st in ac_slice['wanted']:
    if st[0]!=0xAC:
        continue
    node=(st,2)
    domains[node]=pair_domain(st,levels[2])
    assert domains[node]
    queue.append(node);pending.add(node)
roots=defaultdict(dict)
updates=0
while queue:
    node=queue.popleft();pending.remove(node)
    target,level=node
    for st in incoming[target]:
        operations=[rf['specs'][st[0]][j] for j in levels[level]]
        assert all(op[0]=='copy' and op[2]==0 for op in operations),(st[0],operations)
        source_pair=tuple(op[1] for op in operations)
        assert source_pair in levels or source_pair==registers,(st[0],source_pair)
        carried=domains[node] & pair_domain(st,source_pair)
        if not carried:
            continue
        # Necessary source-value restrictions from this particular edge.
        masks=rf['branch_masks'][st[0],target[0]]
        carried &= rp['rectangle'](masks[source_pair[0]],masks[source_pair[1]])
        if not carried:
            continue
        if source_pair==registers:
            roots[st[0]][st,target]=roots[st[0]].get((st,target),0)|carried
            continue
        parent=(st,levels.index(source_pair))
        old=domains.get(parent,0)
        if carried & ~old:
            domains[parent]=old|carried
            for v in range(12,16):
                if carried & ~old & (1 << (16*v+9)):
                    links[parent,v]=(node,v)
            if parent not in pending:
                pending.add(parent);queue.append(parent)
    updates+=1
print(f'PASS: saved-tail ancestry closed: {len(domains)} state/level nodes, '
      f'{updates} transfers, queue empty.',flush=True)
exact_roots=defaultdict(dict)
for ip,edges in sorted(roots.items()):
    for (st,target),mask in edges.items():
        a,p=ac_slice['entry'](st)
        p.add(a.r[33]==9,Or(*[a.r[30]==v for v in range(12,16)
                             if mask & (1 << (16*v+9))]))
        outcome=p.check()
        assert outcome in (sat,unsat)
        if outcome==sat:
            exact_roots[ip][st,target]=mask
    states={st for st,_ in exact_roots[ip]}
    print(f'  {ip:02X}: {len(edges)} projected writer edges; '
          f'{len(exact_roots[ip])} survive joint source constraints, '
          f'{len(states)} source states.',flush=True)
    print('    input stacks: '+', '.join('/'.join(f'{n:02X}' for n in sp)
          for sp in sorted({st[1] for st in states})),flush=True)
print('Every retained source pushes the single pair R30 in C..F, R33=9. '
      'Positive sources are not physical preparations.',flush=True)
