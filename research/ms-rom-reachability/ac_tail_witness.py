#!/usr/bin/env python3
"""Reconstruct value-consistent projected paths from a tail producer to AC.

This follows data-flow provenance, not shortest keyboard sequences. The
result is an abstract candidate until checked by joint symbolic execution.
"""


def build(producers,edge,value):
    origins=producers['tail_origins']
    st,target,pair=edge
    states=[st,target]
    node=(target,pair)
    seen=set()
    while (node,value) in producers['witness_links']:
        assert (node,value) not in seen
        seen.add((node,value))
        node,value=producers['witness_links'][node,value]
        states.append(node[0])
    st,pair=node
    assert pair==origins['registers']
    assert value%16==9 and value//16>=12
    low=value//16
    candidates=[]
    for (source,target),mask in origins['exact_roots'][st[0]].items():
        if source!=st or not mask & (1<<value):
            continue
        level=2 if st[0]==0x93 else 0
        if origins['domains'].get((target,level),0) & (1<<value):
            candidates.append((target,level))
    assert candidates
    node=sorted(candidates,key=str)[0]
    states.append(node[0])
    seen=set()
    while (node,low) in origins['links']:
        assert (node,low) not in seen
        seen.add((node,low))
        node,low=origins['links'][node,low]
        states.append(node[0])
    assert node[0][0]==0xAC and node[1]==2
    return states


def expand(states):
    ips=[]
    for st in states[:-1]:
        ips.append(st[0])
        if st[0]==0x93:
            ips.append(0x94)
        if st[0]==0x12:
            ips.append(0xC6)
    return ips+[states[-1][0]]


def shortest(producers,refined,ip):
    candidates=[]
    for edge,mask in refined['retained'][ip].items():
        for value in producers['bits'](mask):
            states=build(producers,edge,value)
            candidates.append((len(expand(states)),value,states))
    return sorted(candidates,key=lambda row:(row[0],row[1],str(row[2])))
