#!/usr/bin/env python3
"""Native Q erasure holding hiddenP10; remaining markers still block safe exit.

The fieldF reserve is generated through original STOP/STORE keys in ordinaryP3.
Normal storage/STOP is continued with fixed source-selected keys, not state
loads or keyboard sweeps. ALL5 replay is strict within each separate window.
The local four-word theorem is a detached symbolic ROM contract only.
"""
from pathlib import Path
import json
import runpy
import subprocess
import sys

from z3 import And,BitVec

root=Path(__file__).resolve().parent
previous=runpy.run_path(str(root/'cache-bc-head93-q-normal-roundtrip-proof.py'))
reader,r,w,q=(previous[n] for n in ('reader','r','w','q'))
period=previous['previous']['period'];raw=reader['raw']
F='0000F0000000';ZERO='000000000000';NUMBER='007012345678'


def native(args):
    data=json.loads(subprocess.check_output(['node',str(root/
        'cache-bc-head93-q-restore-native.cjs'),'--proof-input','--idle',*args],text=True))
    assert data['report']['minimal'] and data['report']['onlyPublicKeys']
    assert data['report']['ALL5mirror'] and data['report']['qRestoreIdleCheck']
    assert data['markerPrepared']['registers'][3]==F
    return data


def stage(data,name):
    return next(s for s in data['exitStages'] if s['name']==name)


def physical_word(snapshot,tags,cells,area,word):
    found={}
    for chip,ids in tags.items():
        for index,tag in enumerate(ids):
            cell=cells[tag];field=cell['field']
            if cell['area']==area and cell['word']==word and isinstance(field,int):
                assert field not in found;found[field]=snapshot[chip]['m'][index]
    assert set(found)==set(range(12)),(area,word,found)
    return raw([found[k] for k in range(12)])


def preserved_number(records,cells):
    for v in records:
        for moment in ('Before','After'):
            assert physical_word(v['full'+moment],v['tags'+moment],cells,'Ms','P10')==NUMBER,v['word']


def quadruple_contract(records):
    """Conditional U/V/W/Q raw shift; never a new native input hypothesis."""
    assert [v['ip'] for v in records]==[0xE7,0xA8,0xA8,0xA8]
    a=r['concrete_primary'](records[0]['fullBefore']['ik1302'])
    data=[[BitVec('eraseQ_page'+str(i)+'_n'+str(j),4) for j in range(12)] for i in range(4)]
    for j in range(12):a.m[1+3*j]=data[0][j]
    p=w['base'](a,0xE7)
    for i,v in enumerate(records):
        out=[];w['prove'](p,w['ip'](a)==v['ip'],'eraseQ local nextIP',False)
        incoming=[q['N4'](n) for n in v['fullAfter']['ik1302']['m']]
        if i<3:
            for j in range(12):incoming[1+3*j]=data[i+1][j]
        old=a
        a=w['ex'](a,v['ip'],*q['arbitrary_keys']('eraseQ_keys'+str(i)),
            serial_inputs=incoming,emitted_outputs=out)
        wanted=[q['N4'](0)]*12 if i==0 else data[i-1]
        w['prove'](p,And(*[out[1+3*j]==wanted[j] for j in range(12)],
            *[out[j]==old.m[j] for j in range(42) if j%3!=1 or j>=37]),
            'eraseQ local numeric12 shift/other lanes and services held',False)
    w['prove'](p,And(*[a.r[3*j]==data[3][j] for j in range(12)]),
        'last oldQ captured inA, not an outgoing RAM copy',False)
    print('PASS CONDITIONAL LOCAL U/V/W/Q ->0/U/V/W; oldQ goes toA. '
        'For oldU/V/W=0 this removes numericQ/F without touchingP10; '
        'observed control/serial calendar, not a native arbitrary-bank theorem.',flush=True)


def bad_control_header(record):
    assert record['ip']==0xA3 and record['numericOwner']==['Ms:P10']
    assert raw(record['emitted'][1:36:3])=='FFF012345678'
    before=record['fullBefore']['ik1302']
    assert before['r'][27:36:3]==[15,15,15]
    assert all(record['emitted'][j]==before['m'][j] for j in range(42) if j not in (28,31,34))
    a=r['concrete_primary'](before)
    lower=[BitVec('CX_badcontrol_lower'+str(j),4) for j in range(9)]
    for j,s in enumerate(lower):a.m[1+3*j]=s
    p=w['base'](a,0xA3);out=[]
    w['ex'](a,0xA3,record['keysX'],record['keysY'],
        serial_inputs=[q['N4'](n) for n in record['fullAfter']['ik1302']['m']],emitted_outputs=out)
    w['prove'](p,And(*[out[1+3*j]==lower[j] for j in range(9)],
        *[out[j]==15 for j in (28,31,34)],
        *[out[j]==a.m[j] for j in range(42) if j not in (28,31,34)]),
        'conditional CX/A3 overwrites only numeric upper3 with FFF; all16^9 lower fields held')
    a=q['State']('CX_badcontrol_A2_marker');p=w['base'](a,0xA2);p.add(a.m[22]==15)
    out=[];b=w['ex'](a,0xA2,*q['arbitrary_keys']('CX_badcontrol_A2keys'),emitted_outputs=out)
    w['prove'](p,And(w['ip'](b)==0xA3,*[out[j]==a.m[j] for j in range(42)]),
        'A2 seeing M22F exits to A3 without writes; other working fields/keys free')


def check(data,negative=False):
    stored=stage(data,'plain-storage-idle');final=stage(data,'restore-idle')
    assert stored['words']['Ms:P10']==NUMBER and stored['registers'][6]==ZERO
    assert stored['registers'][3]==F and stored['markers']==['Q']
    first=stage(data,'restore-readF1');second=stage(data,'restore-readF2')
    assert first['words']['Ms:P9']==F and first['words']['aux0']==NUMBER
    assert second['words']['Ms:P10']==F and second['words']['aux1']==NUMBER
    lastx=stage(data,'restore-lastx')
    assert lastx['words']['aux0']==F and lastx['words']['aux1']==ZERO
    assert lastx['words']['Ms:P9']==lastx['words']['Y']==NUMBER
    assert lastx['display']=='12345678,'
    assert stage(data,'restore-backup')['registers'][9]==NUMBER
    shifted=stage(data,'restore-eraseQ')
    assert shifted['words']['Ms:P10']==NUMBER and shifted['words']['aux1']==F
    assert shifted['words']['Ms:P9']==ZERO and shifted['words']['aux0']==ZERO
    assert final['registers']==shifted['registers'] and final['program']==shifted['program']
    assert final['ip']==0x35 and final['pc']=='06'
    if negative:
        assert final['words']['Q']==F and final['words']['aux0']==NUMBER
        assert final['words']['Ms:P10']==ZERO and final['markers']==['Q']
        return
    planted=stage(data,'restore-plantZ')
    assert planted['words']['Z']==planted['words']['Ms:P9']==F
    assert planted['words']['Ms:P10']==NUMBER and planted['words']['Q']==F
    assert final['words']['Q']==ZERO and final['words']['Ms:P10']==NUMBER
    assert final['markers']==['Z','Ms:P9','aux1'] and final['words']['aux0']==ZERO
    assert final['registers'][9]==NUMBER
    records=data['windows']['restore-wipeQ']
    writes=[v for v in records if v['ip'] in (0xE7,0xA8)]
    assert [v['numericOwner'] for v in writes]==[['Ms:U'],['Ms:V'],['Ms:W'],['Ms:Q'],['unclassified:aux1']]
    assert all(raw(v['emitted'][1:36:3])==ZERO for v in writes[:4])
    assert raw(writes[3]['fullBefore']['ik1302']['m'][1:36:3])==F
    d6=next(v for v in records if v['ip']==0xD6)
    assert d6['ordinaryOwner']==['register:RA'] and raw(d6['fullAfter']['ik1302']['r'][0:36:3])==ZERO
    assert records[0]['word']==528652 and records[-1]['word']==528763 and len(records)==112
    assert not any(v['ip'] in (0xBB,0xBC,0xC7) for v in records)
    preserved_number(records,data['cells'])
    j=records.index(writes[0]);quadruple_contract(records[j:j+4])


def run():
    r['inlet']['immutable_reference']()
    if '--calc-only' in sys.argv or '--damage-contract-only' in sys.argv:
        data=native(['--short','--calc']);check(data)
        record=data['windows']['restore-test-cx'];assert 0<len(record)<=8400
        change=[]
        for v in record:
            before=physical_word(v['fullBefore'],v['tagsBefore'],data['cells'],'Ms','P10')
            after=physical_word(v['fullAfter'],v['tagsAfter'],data['cells'],'Ms','P10')
            if before!=after:change.append((v['word'],f'{v["ip"]:02X}',before,after))
        assert len(change)==1 and change[0][2]==NUMBER and change[0][3]!=NUMBER,change
        assert change[0][3][3:]==NUMBER[3:],'first corruption affects the exponent/header only'
        bad_control_header(record[-1])
        prev=record[-2]
        assert prev['ip']==0xA2 and prev['numericOwner']==['Ms:P9']
        assert prev['fullBefore']['ik1302']['m'][22]==15
        print('OBSERVED first damage',change,'predecessor=',f'{prev["ip"]:02X}',
            prev['numericOwner'],flush=True)
        assert stage(data,'restore-test-cx')['words']['Ms:P10']=='FFF012345678'
        assert stage(data,'restore-test-plus')['display']=='3,'
        if '--damage-contract-only' not in sys.argv:
            reader['replay'](record,'negative/plainCX after Q erasure')
        print('PASS',len(record),'observed words to FIRSTCX damage'+
            (' (contract-only; ALL5 replay not repeated).' if '--damage-contract-only' in sys.argv
             else ' with strict original ALL5 replay.'),
            'P10 header damage=',change,'; full native/mirrored2/ENTER/3/+ ends3, '
            'not5, ordinaryP9 backup survives. No restored-controller claim.',flush=True)
    else:
        negative='--negative-only' in sys.argv
        data=native(['--noZ'] if negative else ['--short']);check(data,negative)
        selected={n:v for n,v in data['windows'].items() if n.startswith('restore-')
            or '--with-prefix' in sys.argv}
        total=0
        for name,records in selected.items():total+=reader['replay'](records,('noZ/' if negative else 'eraseQ/')+name)
        assert total==(3265 if negative and '--with-prefix' in sys.argv else
            983 if negative else 3377 if '--with-prefix' in sys.argv else 1095),total
        assert len(selected)==(37 if negative and '--with-prefix' in sys.argv else
            8 if negative else 38 if '--with-prefix' in sys.argv else 9),len(selected)
        period(data['windows']['restore-idle'],'negativeNoZ' if negative else 'Q erased/dataP10 held')
        print('PASS',total,'strict original ALL5 transitions in',len(selected),
            'SEPARATE windows. '+('Without Z marker, Q remains; number shifts toaux0.' if negative
            else 'Q is zero, hiddenP10=12345678 held including entire112-word wipe and12idle. '
            'Z/P9/aux1 F markers and wrong geometry remain.'),flush=True)
    r['inlet']['immutable_reference']()


if __name__=='__main__':run()
