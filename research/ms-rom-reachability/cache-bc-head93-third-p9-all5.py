#!/usr/bin/env python3
"""P9 third-number hypothesis through the genuine post-math FIRST reader.

Baseline must match the full 277200-word key/release schedule and all17
actual windows. Counterfactual changes ONLY initial P9 numeric data. No
calculator imports, later repairs or claim of a native third writer/reader.
"""
from pathlib import Path
import runpy
import sys
import json

root=Path(__file__).resolve().parent
base=runpy.run_path(str(root/'cache-bc-head93-second-swap-causal-all5.py'))
engine,all5,num,q=(base[n] for n in ('engine','all5','num','q'))
number=base['number'];raw=base['raw'];value=base['value']
FIRST='007012345678';SECOND='007024681357';THIRD='950013579246'


def schedule():
    rows=[*[(f'Y{i}',3,'rcl') for i in range(1,4)],('P8',10,'rcl'),
        ('Wzero1',10,'rcl'),('Wzero2',10,'rcl'),('aux0',6,'rcl'),
        ('T',7,'rcl'),('X1',7,'rcl'),('Wzero',0,'cx'),('X1zero',4,'rcl'),
        *[(f'flush{i}',5,'rcl') for i in range(1,5)],('read',0,'lastx'),('output',10,'store')]
    segments=[];offset=0
    operand=lambda n:(n+2,1) if n<10 else (n-3,8)
    for suffix,n,kind in rows:
        parts=[(560,(10,8)),(14*560,(0,0))] if kind=='cx' else [
            (560,(11,9) if kind=='lastx' else (6,9) if kind=='store' else (8,9)),
            (13*560,(0,0)),(560,(11,8) if kind=='lastx' else operand(n)),(15*560,(0,0))]
        for count,pins in parts:
            segments.append((offset,offset+count,pins,'packet-p7-first-'+suffix));offset+=count
    assert offset==277200
    return segments


def run(data,third=False):
    start=data['endpoints']['packet-p7-read-output'];finish=data['endpoints']['packet-p7-first-output']
    assert finish['word']-start['word']==277200
    state,tags,phase=base['initialize'](start)
    if third:
        for field,n in enumerate(reversed(THIRD)):
            ids=[i for i,c in enumerate(data['cells']) if c['area']=='Ms' and c['word']=='P9' and c['field']==field]
            assert len(ids)==1
            name,j,_=all5['cell_location'](state,tags,ids[0])
            (state[name] if name.startswith('ir') else state[name].m)[j]=q['N4'](int(n,16))
        print('CONDITIONAL INITIAL DATA ONLY: P9=1.3579246E-50, all12 fields; no native import/writer.',flush=True)
    observed={v['word']:v for n,rows in data['windows'].items() if n.startswith('packet-p7-first-') for v in rows}
    fixed={chip:(start['fullBefore'][chip]['keyX'],start['fullBefore'][chip]['keyY']) for chip in engine['models']}
    i=direct=skipped=checked=0;first_diff=None;periods=[]
    for begin,end,pins,label in schedule():
        assert i==begin;seen={};keys={**fixed,'ik1302':pins}
        while i<end:
            if third:
                assert value(state,tags,data,'Ms','P7')==SECOND and value(state,tags,data,'Ms','P10')==FIRST
                assert value(state,tags,data,'Ms','P9')==THIRD
            v=observed.get(start['word']+i) if not third else None
            if v:all5['compare'](state,tags,phase,v['fullBefore'],v['tagsBefore']);assert all5['pins'](v)==keys
            signature=all5['fingerprint'](state,tags,phase,keys)
            if signature in seen:
                length=i-seen[signature];limit=end
                if not third:
                    pending=[n-start['word'] for n in observed if n>=start['word']+i]
                    if pending:limit=min(limit,min(pending))
                advance=((limit-i)//length)*length
                if advance:
                    periods.append({'stage':label,'period':length,'skip':advance});skipped+=advance;i+=advance;seen.clear();continue
            seen[signature]=i
            before={chip:(engine['boundary_ip'](state[chip]),data['cells'][tags[chip][22]],
                raw([number(n) for n in state[chip].m[1:36:3]])) for chip in engine['models']}
            phase,outputs=engine['step'](state,tags,phase,keys);all5['reduce_calculated'](state);direct+=1
            if v:
                assert [number(n) for n in outputs['ik1302']]==v['emitted']
                all5['compare'](state,tags,phase,v['fullAfter'],v['tagsAfter']);checked+=1
            if third and value(state,tags,data,'Ms','P9')!=THIRD:
                writers=[]
                for chip,(ip,cell,old) in before.items():
                    emitted=raw([number(n) for n in outputs[chip][1:36:3]])
                    if old!=emitted:writers.append({'chip':chip,'ip':f'{ip:02X}','owner':cell['area']+':'+cell['word'],'old':old,'new':emitted})
                first_diff={'offset':i,'word':start['word']+i,'stage':label,'actual':value(state,tags,data,'Ms','P9'),'writers':writers}
                print('MEASURED CONDITIONAL FAILURE',json.dumps(first_diff),flush=True);return
            i+=1
    assert direct+skipped==277200
    if not third:
        assert checked==len(observed)
        all5['compare'](state,tags,phase,finish['fullBefore'],finish['tagsBefore'])
        print('PASS baseline WHOLE277200-word ALL5 FIRST-reader schedule, direct',direct,
            'exact fixed-input skips',skipped,'all',checked,'native active words/end state exact; no repairs.',flush=True)
    final={word:value(state,tags,data,'Ms',word) for word in ('P7','P9','P10')}
    print(json.dumps({'conditional':third,'direct':direct,'skipped':skipped,'firstDifference':first_diff,'final':final,
        'R6':value(state,tags,data,'register','R6'),'R7':value(state,tags,data,'register','R7'),
        'periods':periods,'boundary':'data-only P9 hypothesis; NOT native third write/read/whole cycle/full K1/K2' if third else 'entire real ALL5 reader baseline'}),flush=True)


if __name__=='__main__':
    data=base['read_evidence'](sys.argv[1]);assert data['metadata']['profile']=='p7-normal-retain-both'
    run(data)
    run(data,True)
