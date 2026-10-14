#!/usr/bin/env python3
"""Read-only complete-controller audit of 46 and native-reader continuations.

The existing reset graph is never rebuilt. Graph absence excludes a reset
controller route in that overapproximation. Positive graph paths are only
candidates: they say nothing about payload survival or real timed keys.
"""
from collections import Counter, deque
import gzip
import json
from pathlib import Path
import runpy
import subprocess

root=Path(__file__).resolve().parent
audit=runpy.run_path(str(root/'k1-formatter-entry-audit.py'))
with gzip.open(audit['cache_path'],'rt') as stream:graph=json.load(stream)
assert graph['schema']=='mk61-reset-control-graph-v1'
assert graph['metadata']['sourceSha256']==audit['fingerprints']()
assert graph['metadata']['argv']==audit['argv']
assert graph['metadata']['complete'] and graph['metadata']['pending']==0
assert graph['metadata']['terminal'] is None
states,edges,parents=graph['states'],graph['successors'],graph['parents']
assert len(states)==len(edges)==len(parents)
assert all(0<=j<len(states)for js in edges for j in js)
incoming=[[]for _ in states]
for i,js in enumerate(edges):
    for j in js:incoming[j].append(i)

def expand(indexes):
    sequence=[]
    for i in indexes:
        ip=states[i][0];sequence.append(ip)
        if ip==0x93:sequence.append(0x94)
        if ip==0x12:sequence.append(0xC6)
    return sequence

def describe(sequence):return ' '.join(f'{ip:02X}'for ip in sequence)

at46=[i for i,st in enumerate(states)if st[0]==0x46]
tag46=[i for i,st in enumerate(states)if 0x46 in st[1]]
assert len(at46)==702 and len(tag46)==1631
assert {states[i][0]for j in at46 for i in incoming[j]}=={0x42,0x43}
assert all(states[j][0]==0xE5 and states[j][1][0]==0x47
           for i in at46 for j in edges[i])
assert all(0x46 not in states[i][1]for i in at46)
assert {states[i][1][0]for i in at46}=={0x43,0xED}
checks={
  '98/top46':[i for i,st in enumerate(states)if st[0]==0x98 and st[1][0]==0x46],
  '9A/top98/second46':[i for i,st in enumerate(states)if st[0]==0x9A and st[1][:2]==[0x98,0x46]],
  **{f'{ip:02X}/46-anywhere':[i for i,st in enumerate(states)if st[0]==ip and 0x46 in st[1]]
     for ip in (0x91,0x92,0x93,0x98,0x9A)},
}
assert all(not rows for rows in checks.values())
births=Counter((states[i][0],states[j][0])for i,js in enumerate(edges)for j in js
               if 0x46 not in states[i][1] and 0x46 in states[j][1])
assert set(births)=={(0x45,0x8B)}
print('PASS complete cache provenance:',len(states),'states;',sum(map(len,edges)),'edges.',flush=True)
print('PASS every46 context:',len(at46),'; predecessor IPs42/43; tops43/ED; '
      'no46 tag; every successor E5/top47.',flush=True)
print('46 top counts:',{f'{ip:02X}':n for ip,n in sorted(Counter(states[i][1][0]for i in at46).items())},flush=True)
print('46 vectors:',dict(Counter(str(states[i][2])for i in at46)),flush=True)
print('46 R26 domains:',dict(Counter(str(states[i][7])for i in at46)),flush=True)
print('46-tag births:',{f'{a:02X}->{b:02X}':n for(a,b),n in births.items()},flush=True)
print('46-tag IP inventory:',{f'{ip:02X}':n for ip,n in sorted(Counter(states[i][0]for i in tag46).items())},flush=True)
numeric_boundary=Counter((tuple(states[i][1]),states[j][0],tuple(states[j][1]))
                        for i,js in enumerate(edges)for j in js
                        if states[i][0]==0xBD and 0x46 in states[i][1])
assert all(before[-1]==0x46 and after==(0xBE,before[0],before[1])
           and ip in (0x91,0xBF)for before,ip,after in numeric_boundary)
print('BD numeric boundary discards46:',
      {'/'.join(f'{v:02X}'for v in before)+' -> '+f'{ip:02X}'+' / '+
       '/'.join(f'{v:02X}'for v in after):n
       for(before,ip,after),n in numeric_boundary.items()},flush=True)
for label,rows in checks.items():print('PASS excluded in complete reset graph:',label,'=',len(rows),flush=True)
alternative=(0x32,0xE9,0xBC)
def vector_allows(st,value):
    v=st[2]
    return v is None or v==value or (v=='diagonal' and value%16==value//16)
a3=[st for st in states if st[0]==0xA3]
assert all(st[2] is not None for st in a3)
print('A3 complete vector inventory:',dict(Counter(str(st[2])for st in a3)),flush=True)
for ip in alternative:
    queries={
      f'9A/top{ip:02X}':[st for st in states if st[0]==0x9A and st[1][0]==ip],
      f'C8/top{ip:02X}':[st for st in states if st[0]==0xC8 and st[1][0]==ip],
      f'A3/vector{ip:02X}':[st for st in a3 if vector_allows(st,ip)],
      f'A3->{ip:02X}':[j for i,js in enumerate(edges)if states[i][0]==0xA3
                       for j in js if states[j][0]==ip],
    }
    assert all(not values for values in queries.values())
    for label,values in queries.items():
        print('PASS excluded in complete reset graph:',label,'=',len(values),flush=True)

native=json.loads(subprocess.check_output(['node','-e',
  "const{reader}=require('./check_partial_k2_cache_exit.cjs');"
  "const{machineSnapshot}=require('./probe_c8_pc_reader.cjs');"
  "console.log(JSON.stringify(machineSnapshot(reader()).ik1302))"],cwd=root,text=True))

def compatible(st):
    ip,sp,vector,selector,delta,r38,dr38,r26,types=st;a=native
    if ip!=0x35 or sp!=[a['st'][36+i]+16*a['st'][39+i]for i in range(3)]:return False
    if vector=='diagonal' and a['r'][37]!=a['r'][40]:return False
    if isinstance(vector,int) and vector!=a['r'][37]+16*a['r'][40]:return False
    if selector is not None and a['s1'] not in selector:return False
    if delta is not None and delta!=(a['s1']-a['r'][35])%16:return False
    if r38 is not None and a['r'][38] not in r38:return False
    if dr38 is not None and dr38!=(a['r'][38]-a['r'][35])%16:return False
    if r26 is not None and a['r'][26] not in r26:return False
    assert types is None
    return True

starts=[i for i,st in enumerate(states)if compatible(st)]
assert len(starts)==4

def reach(blocked=(),target=0x46):
    previous={i:None for i in starts};queue=deque(starts)
    while queue:
        i=queue.popleft()
        if states[i][0] in blocked:continue
        for j in edges[i]:
            if j not in previous:previous[j]=i;queue.append(j)
    reached=[i for i in previous if states[i][0]==target]
    path=[]
    if reached:
        i=reached[0]
        while i is not None:path.append(i);i=previous[i]
        path.reverse()
    return previous,reached,expand(path)

if __name__=='__main__':
    for label,blocked in [('unrestricted',()),('noEE',(0xEE,)),
                          ('noM3-write',(0xC9,)),('noEE+noM3-write',(0xEE,0xC9))]:
        visited,reached,path=reach(blocked)
        print('CLOSED CONTROLLER CUT:',label,';',len(visited),'states;',
              len(reached),'46 contexts; pending0.',flush=True)
        if path:print('CONTROLLER CANDIDATE only:',describe(path),flush=True)
    for ip in alternative:
        for label,blocked in [('unrestricted',()),('noEE',(0xEE,)),
                              ('noM3-write',(0xC9,)),('noEE+noM3-write',(0xEE,0xC9))]:
            visited,reached,path=reach(blocked,ip)
            print('ALTERNATIVE CONTROLLER CUT:',label,';',f'{ip:02X}',
                  len(reached),'contexts; pending0.',flush=True)
            if path and label=='noEE+noM3-write':
                print('CONTROLLER CANDIDATE only:',describe(path),flush=True)
    print('LIMIT: positive paths contain no payload proof. No M3 here means '
          'IK1302 C9 excluded; it is the whole-ROM sole M3 writer.',flush=True)
