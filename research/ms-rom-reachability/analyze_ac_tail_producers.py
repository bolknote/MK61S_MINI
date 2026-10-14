#!/usr/bin/env python3
"""Trace saved AC tail inputs through proved exact copy transfers.

The two values stay paired across register swaps and saved-stack copies.
Stop at arithmetic, an untracked source, or a copy that splits the pair
across the original three aligned tail lanes. Report that ROM boundary,
without treating its input as reachable.
"""
import runpy
from collections import defaultdict, deque
from functools import lru_cache
from pathlib import Path

root=Path(__file__).resolve().parent
if 'tail_origins' not in globals():
    tail_origins=runpy.run_path(str(root/'analyze_ac_tail_origins.py'))
ac=tail_origins['ac_slice']
rp,rf=ac['rp'],ac['rf']
names=rf['NAMES']
registers=tail_origins['registers']
aligned_pairs=tail_origins['levels']+tuple(
    (names.index(f'R{30+i}'),names.index(f'R{33+i}')) for i in range(3))


def bits(mask):
    while mask:
        one=mask & -mask
        yield one.bit_length()-1
        mask^=one


def pair_domain(st,pair):
    if pair[0]==pair[1]:
        return sum(1<<(17*v) for v in rf['bit_values'](rf['domains'][st][pair[0]]))
    assert pair[0]<pair[1]
    return rp['domains'][st][rp['PAIR_INDEX'][pair]]


@lru_cache(None)
def invert(mask,operations):
    op0,op1=operations
    i,j=op0[1],op1[1]
    pair=tuple(sorted((i,j)))
    delta0=op0[2] if op0[0]=='add' else 8 if op0[0]=='xor8' else 0
    delta1=op1[2] if op1[0]=='add' else 8 if op1[0]=='xor8' else 0
    result=0
    for v in bits(mask):
        x=((v//16)-delta0)%16
        y=((v%16)-delta1)%16
        if i==j and x!=y:
            continue
        if i>j:
            x,y=y,x
        result|=1<<(16*x+y)
    return pair,result


domains={}
queue=deque()
pending=set()
for edges in tail_origins['exact_roots'].values():
    for (st,_),mask in edges.items():
        node=st,registers
        domains[node]=domains.get(node,0)|mask
        if node not in pending:
            queue.append(node);pending.add(node)
frontiers=defaultdict(dict)
links={}
witness_links={}
updates=0
while queue:
    node=queue.popleft();pending.remove(node)
    target,pair=node
    for st in ac['incoming'][target]:
        operations=tuple(rf['specs'][st[0]][i] for i in pair)
        if not all(op[0]=='copy' for op in operations):
            edge=st,target,pair
            frontiers[st[0]][edge]=frontiers[st[0]].get(edge,0)|domains[node]
            continue
        source_pair,mask=invert(domains[node],operations)
        if source_pair not in aligned_pairs:
            edge=st,target,pair
            frontiers[st[0]][edge]=frontiers[st[0]].get(edge,0)|domains[node]
            continue
        mask &= pair_domain(st,source_pair)
        branch=rf['branch_masks'][st[0],target[0]]
        mask &= rp['rectangle'](branch[source_pair[0]],branch[source_pair[1]])
        if not mask:
            continue
        parent=st,source_pair
        old=domains.get(parent,0)
        if mask & ~old:
            domains[parent]=old|mask
            links.setdefault(parent,node)
            for value in bits(mask & ~old):
                output_value=(16*(value%16)+value//16
                              if operations[0][1]>operations[1][1] else value)
                assert domains[node] & (1<<output_value)
                witness_links[parent,value]=(node,output_value)
            if parent not in pending:
                pending.add(parent);queue.append(parent)
    updates+=1
    if updates%50000==0:
        print(f'tail producers: {updates} transfers, {len(domains)} nodes, '
              f'{len(queue)} pending',flush=True)
print(f'PASS: paired tail producer closure: {updates} transfers, '
      f'{len(domains)} state/pair nodes, queue empty.',flush=True)
for ip,edges in sorted(frontiers.items()):
    fields=sorted({pair for _,_,pair in edges})
    print(f'  {ip:02X}: {len(edges)} projected frontier edges; '+
          ', '.join('/'.join(names[i] for i in pair) for pair in fields),flush=True)
print('Non-copy and pair-splitting frontiers are deliberately unfiltered; neither they '
      'nor paired graph paths are physical preparations.',flush=True)
