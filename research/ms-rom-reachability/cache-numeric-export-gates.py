#!/usr/bin/env python3
"""Exact numeric export/stack-lift-flag inventory plus closed no-EE cuts.

Conditional source contracts and a complete reset-controller overapproximation.
No positive control path is treated as a native keyboard or payload witness.
"""
from collections import Counter,deque
import gzip
import json
from pathlib import Path
import runpy

from z3 import And,Or,sat,unsat

root=Path(__file__).resolve().parent
w=runpy.run_path(str(root/'cache46-writer-contracts.py'))
q=w['q'];raw=(0,3,9,12,18,21)
audit=runpy.run_path(str(root/'k1-formatter-entry-audit.py'))
graph=json.loads(gzip.decompress(audit['cache_path'].read_bytes()))
assert graph['schema']=='mk61-reset-control-graph-v1'
assert graph['metadata']['sourceSha256']==audit['fingerprints']()
assert graph['metadata']['argv']==audit['argv']
assert graph['metadata']['complete'] and graph['metadata']['pending']==0
assert graph['metadata']['terminal'] is None
states,edges=graph['states'],graph['successors']
assert len(states)==len(edges)==len(graph['parents'])
assert all(0<=v<len(states) for row in edges for v in row)


def inventory():
    writers={0:[],1:[]};setters={}
    for code in range(256):
        a=q['State'](f'export_gate_{code:02X}');out=[]
        b=q['execute_command'](a,code,*q['arbitrary_keys'](f'export_gate_keys_{code:02X}'),
                               emitted_outputs=out)
        for lane in (0,1):
            p=q['base_solver'](a,code)
            p.add(~w['eq'](out[lane:36:3],a.m[lane:36:3]))
            answer=p.check();assert answer in (sat,unsat)
            if answer==sat:writers[lane].append(code)
        p=q['base_solver'](a,code)
        w['prove'](p,Or(a.r[41]!=0,Or(b.r[41]==0,b.r[41]==15)),
                   f'R41 invariant zero entry{code:02X}',False)
        w['prove'](p,Or(a.r[41]!=15,Or(b.r[41]==0,b.r[41]==15)),
                   f'R41 invariant F entry{code:02X}',False)
        p.push();p.add(b.r[41]!=a.r[41]);changes=p.check();p.pop()
        assert changes in (sat,unsat)
        if changes==sat:
            p.push();values=q['possible_values'](b.r[41],p,17);p.pop()
            assert len(values)==1
            setters[code]=values[0]
            if values[0]==15:
                w['prove'](p,And(b.r[41]==15,*[b.r[j]==a.r[j] for j in raw]),
                           f'{code:02X} sets R41=F and holds rawA6')
    assert writers[0]==[0xD4]
    assert writers[1]==[0x32,0x34,0xA3,0xA8,0xBC,0xC7,0xE7,0xE9]
    assert setters=={0x29:15,0x6E:0,0x87:0,0x9F:15,0xAD:15,0xCF:0,0xEF:0,0xF0:15}
    print('PASS all256 primary words: sole numeric M1 writer D4; M2 writers',
          ' '.join(f'{v:02X}' for v in writers[1]),flush=True)
    print('PASS all256 primary words: only29/9F/AD/F0 set lift flagF;',
          'only6E/87/CF/EF clear it; allF setters hold rawA6.',flush=True)
    return writers,setters


def closed_cut(writers,setters):
    starts=[i for i,s in enumerate(states) if s[0]==0xC9]
    assert len(starts)==146
    reached=set(starts);todo=deque(starts);parents={i:None for i in starts}
    while todo:
        index=todo.popleft()
        if states[index][0]==0xEE:continue
        for nxt in edges[index]:
            if nxt not in reached:
                reached.add(nxt);todo.append(nxt);parents[nxt]=index
    assert len(reached)==10695
    counts=Counter(states[i][0] for i in reached)
    # Positive reachability in this conservative graph is NOT an execution
    # witness. In particular D4 is present; it must not be excluded merely
    # because the native comma/digit bridges choose other exits.
    assert counts[0xD4]==63
    reachable_writers=[code for code in writers[1] if counts[code]]
    reachable_setters=[code for code,value in setters.items() if value==15 and counts[code]]
    assert reachable_writers==[0x34,0xA3,0xA8,0xBC,0xE7]
    assert reachable_setters==[0x9F,0xAD]
    print('PASS complete noEE cut:146 C9 starts,10695 reached,pending0;',
          'sole M1 writer D4 has63 conditional controller contexts.',flush=True)
    print('PASS remaining M2 writer contexts:',
          [(f'{code:02X}',counts[code]) for code in reachable_writers],flush=True)
    print('PASS remaining flagF setter contexts:',
          [(f'{code:02X}',counts[code]) for code in reachable_setters],flush=True)
    print('LIMIT: positiveD4/34/A3/A8/BC/E7 or9F/AD control contexts do NOT '
          'prove cache survival, simultaneous metadata, a physical destination '
          'or keyboard entry. Prior/encoded reserves and partial K2 remain open.',flush=True)
    paths={}
    for code in (0xD4,0xAD):
        index=next(i for i in parents if states[i][0]==code)
        chain=[]
        while index is not None:chain.append(index);index=parents[index]
        chain.reverse();sequence=[]
        for index in chain:
            sequence.append(states[index][0])
            if states[index][0]==0x93:sequence.append(0x94)
            elif states[index][0]==0x12:sequence.append(0xC6)
        paths[code]=sequence
    return paths


def feeds():
    for code in (0x34,0xA3):
        a=q['State'](f'export_feed_{code:02X}');out=[]
        b=q['execute_command'](a,code,*q['arbitrary_keys'](f'export_feed_keys_{code:02X}'),
                               emitted_outputs=out)
        p=q['base_solver'](a,code)
        w['prove'](p,And(w['eq'](out[1:28:3],a.m[1:28:3]),
                          w['eq'](out[28:36:3],a.r[27:36:3]),
                          *[b.r[j]==a.r[j] for j in raw]),
                   f'{code:02X} writes only numeric tail A9/A10/A11, holds direct rawA6')
    for code,lane,source in ((0xD4,0,'rA'),(0xBC,1,'rB'),(0xA8,1,'rA'),(0xE7,1,'rA')):
        a=q['State'](f'export_feed_{code:02X}');out=[]
        b=q['execute_command'](a,code,*q['arbitrary_keys'](f'export_feed_keys_{code:02X}'),
                               emitted_outputs=out)
        p=q['base_solver'](a,code)
        values=a.r[(1 if source=='rB' else 0):36:3]
        if code in (0xD4,0xBC):values=[a.s]+values[:11]
        w['prove'](p,w['eq'](out[lane:36:3],values),
                   f'{code:02X} exact numeric M{lane+1} feed '+
                   ('S + '+source+'0..10' if code in (0xD4,0xBC) else source+'0..11'))
    print('LIMIT: these are current-word source identities. Earlier copies '
          'or encoding into B/S/the tail and true physical destinations remain open.',flush=True)


def candidate_filters(paths):
    exact=runpy.run_path(str(root/'verify_c8_recovery_candidate.py'),
                        init_globals={'transport':{'q':q}})
    for code,expected in ((0xD4,sat),(0xAD,unsat)):
        print('CANDIDATE shortest noEE route to',f'{code:02X}',
              ' '.join(f'{v:02X}' for v in paths[code]),flush=True)
        result=exact['verify_sequence'](paths[code])
        assert result['result']==expected
    print('LIMIT: SAT for D4 allows arbitrary initial metadata and arbitrary '
          'future serial inputs/per-tick physical key pins. It does NOT '
          'certify a native cache entry, program restoration or a usable '
          'exit. UNSAT rejects only this AD path, not all AD approaches.',flush=True)


if __name__=='__main__':
    writers,setters=inventory()
    paths=closed_cut(writers,setters)
    feeds()
    candidate_filters(paths)
