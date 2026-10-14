#!/usr/bin/env python3
"""Copy-only candidate continuation from the native raw reader to A-source46.

Reuses the complete cached controller, not a recomputed controller. Only 256
local copy maps are compiled. Neither a bounded negative nor a graph path is
a native protocol: non-copy transforms and external payload reserves are absent.
"""
from collections import Counter,deque
from pathlib import Path
import runpy

root=Path(__file__).resolve().parent
m=runpy.run_path(str(root/'cache-tail-frontiers.py'))
states,edges,copies=(m[n]for n in ('states','edges','copies'))
starts=[(i,bytes(m['tokens']),m['advance']((),0x35))for i in m['starts']]
compiler=m['compiler'];q=m['q']

def find(limit=500000):
    parents={v:None for v in starts};queue=deque(starts)
    losses=Counter();first40=None;terminal=None
    while queue and len(parents)<limit:
        item=queue.popleft();index,payload,history=item;ip=states[index][0]
        if ip==0x40 and first40 is None:first40=item
        if ip==0x46 and all(token in payload[:36:3]for token in range(1,7)):
            terminal=item;break
        if ip in (0xEE,0xC9):losses[ip]+=1;continue
        after=compiler['transport'](copies[ip],payload)[:86]
        if not all(token in after for token in range(1,7)):
            losses[ip]+=1;continue
        for ni in edges[index]:
            history2=m['advance'](history,states[ni][0])
            if history2 is None:continue
            nxt=(ni,after,history2)
            if nxt not in parents:parents[nxt]=item;queue.append(nxt)
    print('COPY ONLY noEE/noM3:',len(parents),'visited;',len(queue),'pending;',
          'A-source46 candidate=',terminal is not None,flush=True)
    print('Copy-losing/cut frontiers:',[(f'{ip:02X}',n)for ip,n in losses.most_common(15)],flush=True)
    result={}
    for label,item in [('first40',first40),('A-source46',terminal)]:
        if item is None:continue
        path=[]
        while item is not None:path.append(item);item=parents[item]
        path.reverse();sequence=[]
        for i,_,_ in path:
            ip=states[i][0];sequence.append(ip)
            if ip==0x93:sequence.append(0x94)
            if ip==0x12:sequence.append(0xC6)
        result[label]=sequence
        print('CANDIDATE',label,':',' '.join(f'{ip:02X}'for ip in sequence),flush=True)
        print('  six token R/ST positions at endpoint:',
              {t:[i for i,n in enumerate(path[-1][1])if n==t]for t in range(1,7)},flush=True)
    return result

if __name__=='__main__':
    checker=runpy.run_path(str(root/'verify_c8_recovery_candidate.py'),
                          init_globals={'transport':{'q':q}})
    for label,sequence in find().items():
        r=checker['verify_sequence'](sequence,m['native'])
        print('EXACT IK1302 FILTER',label,':',r['result'],
              'failed index='+str(r.get('index')) if 'index'in r else '',flush=True)
    print('LIMIT: no graph-copy result settles native A-source46 or partial K2.',flush=True)
