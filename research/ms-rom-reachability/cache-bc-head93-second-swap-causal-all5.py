#!/usr/bin/env python3
"""Detached ALL5 causal tests of the native failed reverse SWAP.

Baseline must compute the genuine WHOLE public key/release/idle schedule.
The only counterfactual is initial aux0.field7 F->0 in this analysis model.
No calculator receives the model, and no later state/control/phase is fixed.
"""
from pathlib import Path
import hashlib
import json
import runpy
import sys

root=Path(__file__).resolve().parent
num=runpy.run_path(str(root/'cache-bc-head93-packet-number-proof.py'))
engine,all5=(num['prior'][n] for n in ('engine','all5'))
number=all5['number'];raw=num['raw'];q=num['q']
FIRST='007012345678';SECOND='007024681357'


def read_evidence(path):
    data=json.loads(Path(path).read_text())
    assert data['schema']=='mk61-two-word-reopen-passive-v1'
    assert data['metadata']['onlyPublicKeys'] and data['metadata']['ALL5mirror']
    expected=[root/'ik1302_symbolic.py',root/'analyze_gates.py',root/'audit_ms_rom_control.py',
        root/'k1-formatter-entry-audit.py',Path('/Users/bolk/Projects/MK-61/tests/emulator/mk61.cjs'),
        Path('/Users/bolk/Projects/MK-61/tests/emulator/rom.cjs')]
    assert set(data['metadata']['frozenSha256'])=={str(p) for p in expected}
    for p in expected:
        assert hashlib.sha256(p.read_bytes()).hexdigest()==data['metadata']['frozenSha256'][str(p)]
    return data


def initialize(entry):
    state,_,phase=engine['make']({'state':entry['fullBefore'],'command':entry['word']%6})
    tags={name:list(entry['tagsBefore'][name]) for name in engine['names']}
    return state,tags,phase


def value(state,tags,data,area,word):
    return all5['numeric_word'](state,tags,data['cells'],area,word)


def run_case(data,remove_aux0=False,post_request=False):
    origin=data['endpoints']['packet-reopen-control-front3']
    start=next(v for v in data['windows']['packet-reopen-control-swap'] if v['word']==2889666) if post_request else origin
    offset=start['word']-origin['word']
    finish=data['endpoints']['packet-reopen-control-swap']
    assert finish['word']-origin['word']==8400
    state,tags,phase=initialize(start)
    if remove_aux0:
        ids=[i for i,c in enumerate(data['cells']) if c['area']=='unclassified' and
            c['word']=='aux0' and c['field']==7]
        assert len(ids)==1
        name,j,old=all5['cell_location'](state,tags,ids[0]);assert number(old)==15
        (state[name] if name.startswith('ir') else state[name].m)[j]=q['N4'](0)
        print('CONDITIONAL INITIAL DATA ONLY: aux0.field7 F->0; all controls, phase, '
            'other cells unchanged. NEVER imported into a calculator.',flush=True)
    observed={v['word']:v for v in data['windows']['packet-reopen-control-swap'] if v['word']>=start['word']}
    otherpins={name:(start['fullBefore'][name]['keyX'],start['fullBefore'][name]['keyY'])
        for name in engine['models']}
    i=calculated=skipped=checked=0;seen={};changes=[];events=[];first_loss=None;periods=[]
    track_second=remove_aux0 and post_request
    second_location='P8';relocations=[];held_checks=0
    while i<8400-offset:
        end=(560 if i+offset<560 else 8400)-offset
        keys={**otherpins,'ik1302':(6,8) if i+offset<560 else (0,0)}
        if i+offset==560:seen.clear()
        if track_second:
            assert value(state,tags,data,'Ms',second_location)==SECOND
            assert value(state,tags,data,'Ms','P10')==FIRST
        v=observed.get(start['word']+i) if not remove_aux0 else None
        if v:
            all5['compare'](state,tags,phase,v['fullBefore'],v['tagsBefore'])
            assert all5['pins'](v)==keys
        signature=all5['fingerprint'](state,tags,phase,keys)
        if signature in seen:
            length=i-seen[signature]
            limit=end
            if not remove_aux0:
                pending=[n-start['word'] for n in observed if n>=start['word']+i]
                if pending:limit=min(limit,min(pending))
            advance=((limit-i)//length)*length
            if advance:
                periods.append({'period':length,'from':i,'skip':advance,'pins':keys['ik1302']})
                skipped+=advance;i+=advance;seen.clear();continue
        seen[signature]=i
        before={chip:{'ip':engine['boundary_ip'](state[chip]),
            'A':raw([number(n) for n in state[chip].r[0:36:3]]),
            'numeric':raw([number(n) for n in state[chip].m[1:36:3]]),
            'owner':data['cells'][tags[chip][22]]} for chip in engine['models']}
        phase,emitted=engine['step'](state,tags,phase,keys);all5['reduce_calculated'](state)
        calculated+=1
        if v:
            assert [number(n) for n in emitted['ik1302']]==v['emitted']
            all5['compare'](state,tags,phase,v['fullAfter'],v['tagsAfter']);checked+=1
        for chip,b in before.items():
            output=raw([number(n) for n in emitted[chip][1:36:3]])
            after_a=raw([number(n) for n in state[chip].r[0:36:3]])
            owner=b['owner']['area']+':'+b['owner']['word']
            if track_second and chip=='ik1303' and b['ip']==0x4E and owner=='Ms:P7':
                assert second_location=='P8' and start['word']+i==2889683
                assert b['A']==SECOND and output==SECOND
                second_location='P7';relocations.append({'word':start['word']+i,'from':'P8','to':'P7'})
            if output!=b['numeric']:
                changes.append({'offset':i,'chip':chip,'ip':f'{b["ip"]:02X}',
                    'owner':owner,'old':b['numeric'],'new':output})
            if chip=='ik1302' and b['ip'] in (0x9C,0xAD,0xE6,0xEE,0xE4,0xE7):
                event={'offset':i,'ip':f'{b["ip"]:02X}','owner':owner,
                    'M':b['numeric'],'A':b['A'],'afterA':after_a}
                comparable=lambda e:{k:v for k,v in e.items() if k not in ('offset','lastOffset','repeats')}
                if events and comparable(events[-1])==comparable(event):
                    events[-1]['lastOffset']=i;events[-1]['repeats']=events[-1].get('repeats',1)+1
                else:events.append(event)
        if first_loss is None and value(state,tags,data,'Ms','P10')!=FIRST:
            first_loss={'offset':i,'actual':value(state,tags,data,'Ms','P10')}
        if track_second:
            assert value(state,tags,data,'Ms',second_location)==SECOND
            assert value(state,tags,data,'Ms','P10')==FIRST;held_checks+=1
        i+=1
    assert calculated+skipped==8400-offset
    if not remove_aux0:
        assert checked==len(observed)
        all5['compare'](state,tags,phase,finish['fullBefore'],finish['tagsBefore'])
        print(f'PASS baseline entire{8400-offset}-word original ALL5 key/release/idle schedule: '
            f'direct{calculated}, exact fixed-pin period skips{skipped}, '
            f'all{checked} native SWAP words and whole endpoint matched; no repairs.',flush=True)
    final={c['area']+':'+c['word']:value(state,tags,data,c['area'],c['word'])
        for c in data['cells'] if c['field']==7 and c['area']!='register'}
    if track_second:
        assert first_loss is None and second_location=='P7' and len(relocations)==1
        assert final['Ms:P7']==SECOND and final['Ms:P8']=='000000000000'
        assert final['unclassified:aux0']=='000000000000' and final['Ms:V']=='0000F0000000'
        for j in range(15):
            assert value(state,tags,data,'register','R'+('0123456789ABCDE'[j])) not in (FIRST,SECOND)
        print(f'PASS CONDITIONAL ONLY: SECOND held P8->P7 before/after all{held_checks} '
            'direct ALL5 words; fixed-input cycles preserve all other states. '
            'Both values retained, no ordinary numerical output/reserve. '
            'Missing native aux0-removal constructor; NOT achieved K1/K2.',flush=True)
    print(json.dumps({'conditional':remove_aux0,'postRequestStart':post_request,'calculated':calculated,'skipped':skipped,
        'periods':periods,'firstP10Loss':first_loss,'secondRelocations':relocations,
        'finalNumeric':final,'changes':changes,'events':events,
        'boundary':'initial-aux0 hypothesis only, NOT keyboard constructor/native reader/repeat'
            if remove_aux0 else 'whole native SWAP baseline including all three processors'}),flush=True)


if __name__=='__main__':
    data=read_evidence(sys.argv[1])
    post_request='--post-request' in sys.argv
    run_case(data,post_request=post_request)
    run_case(data,True,post_request)
