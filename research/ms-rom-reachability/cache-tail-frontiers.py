#!/usr/bin/env python3
"""Narrow copy candidates for a numeric ST modifier after native reader 35.

The cached controller is an overapproximation and copy classification is
incomplete. Results are candidate paths or bounded local frontiers, never a
native protocol or a partial-K2 exclusion.
"""
from collections import Counter, deque
import gzip
import json
from pathlib import Path
import runpy
import subprocess

root=Path(__file__).resolve().parent
q=runpy.run_path(str(root/'ik1302_symbolic.py'))
audit=runpy.run_path(str(root/'k1-formatter-entry-audit.py'))
with gzip.open(audit['cache_path'],'rt') as stream:graph=json.load(stream)
assert graph['metadata']['sourceSha256']==audit['fingerprints']()
assert graph['metadata']['complete'] and not graph['metadata']['pending']
states,edges=graph['states'],graph['successors']
compiler=runpy.run_path(str(root/'analyze_k1_buffers.py'))
copies=compiler['compile_copies']({'q':q})
native=json.loads(subprocess.check_output(['node','-e',
  "const{reader}=require('./check_partial_k2_cache_exit.cjs');"
  "const{machineSnapshot}=require('./probe_c8_pc_reader.cjs');"
  "console.log(JSON.stringify(machineSnapshot(reader()).ik1302))"],cwd=root,text=True))

def compatible(st):
    ip,sp,vector,selector,delta,r38,dr38,r26,types=st
    a=native
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
assert starts
tokens=bytearray(86)
for i,pos in enumerate((0,3,9,12,18,21),1):tokens[pos]=i
modifiers={0xBE,0xAC,0x8C,0x40,0x47,0x93,0x95}
patterns=[tuple(int(v,16)for v in s.split())for s in
  ('35 45 8B 48 B1','35 B5 83 45 8B 48 B1','35 B5 B7 45 8B 48 B1',
   '7A 7C 75','7A 7C 73',
   '35 C5 8A 65 7B B7 45 8B 48 B1 B3 BE',
   '35 C5 8A 65 7B B7 45 8B 48 B1 B3 BD',
   '35 45 8B 48 4A 4C 4E 97 99 9B 9C 9E 9F')]
decoder=tuple(int(v,16)for v in '35 C5 8A 65 7B B7 45 8B 48 B1 B3'.split())
patterns.extend(decoder+(ip,)for ip in range(0xB0,0xC0)if ip not in (0xB8,0xB9))
function_decoder=decoder+tuple(int(v,16)for v in 'B9 F8 FA 7A 7C'.split())
patterns.extend(function_decoder+(ip,)for ip in range(0x70,0x80)
                if ip not in (0x76,0x77,0x78,0x79))
prefixes={()}
for p in patterns:prefixes.update(p[:i]for i in range(1,len(p)))

def advance(history,ip):
    extended=history+(ip,)
    if any(len(p)<=len(extended) and extended[-len(p):]==p for p in patterns):return None
    return max((p for p in prefixes if not p or extended[-len(p):]==p),key=len)

def find(limit=500000):
    initial=[(i,bytes(tokens),advance((),0x35))for i in starts]
    parents={v:None for v in initial};queue=deque(initial)
    frontiers={};losses=Counter()
    while queue and len(parents)<limit:
        item=queue.popleft();index,payload,history=item;ip=states[index][0]
        if ip in modifiers:
            frontiers.setdefault(ip,item)
            continue
        if ip==0xEE:losses[ip]+=1;continue
        following=compiler['transport'](copies[ip],payload)[:86]
        if not all(t in following for t in range(1,7)):
            losses[ip]+=1;continue
        for ni in edges[index]:
            hist=advance(history,states[ni][0])
            if hist is None:continue
            nxt=(ni,following,hist)
            if nxt not in parents:parents[nxt]=item;queue.append(nxt)
    print('FIRST-MODIFIER COPY COVER:',len(starts),'native-compatible cached contexts;',
          len(parents),'visited;',len(queue),'pending;',flush=True)
    print('losses:',[(f'{ip:02X}',n)for ip,n in losses.most_common(12)],flush=True)
    results={}
    for ip,item in sorted(frontiers.items()):
        path=[]
        while item is not None:
            path.append(states[item[0]][0]);item=parents[item]
        path.reverse()
        expanded=[]
        for command in path:
            expanded.append(command)
            if command==0x12:expanded.append(0xC6)
        results[ip]=expanded
        print('CANDIDATE FIRST MODIFIER',f'{ip:02X}',':',
              ' '.join(f'{v:02X}'for v in expanded),flush=True)
    return results

if __name__=='__main__':
    for ip,sequence in find().items():
        checker=runpy.run_path(str(root/'verify_c8_recovery_candidate.py'),
                              init_globals={'transport':{'q':q}})
        checker['verify_sequence'](sequence,native)
