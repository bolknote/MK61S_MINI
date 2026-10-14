#!/usr/bin/env python3
"""Third read withoutP7 and exact native fixed-key/timing cycle recurrence.

Native complete-state recurrence is distinct from selected independent ALL5
replay windows. No model state imports, ROM/control/phase writes or repairs.
The577920-word native macrocycle is NOT called a continuous symbolic replay.
"""
from pathlib import Path
import json
import runpy
import subprocess
import sys

from z3 import And, If, UGE

root=Path(__file__).resolve().parent
num=runpy.run_path(str(root/'cache-bc-head93-packet-number-proof.py'))
r,w,q=(num[n] for n in ('r','w','q'));prep=num['prep']
raw,stage,replay,period,preserved_number=(num[n] for n in ('raw','stage','replay','period','preserved_number'))
F,ZERO,NUMBER=(num[n] for n in ('F','ZERO','NUMBER'))
SEVEN='000070000000'


def guard_contract():
    a=q['State']('steady_9C_guard');p=w['base'](a,0x9C);out=[]
    b=w['ex'](a,0x9C,*q['arbitrary_keys']('steady_9C_keys'),emitted_outputs=out)
    accepted=If(a.m[31]==15,UGE(a.m[34],1),UGE(a.m[34],7))
    w['prove'](p,And(w['ip'](b)==If(accepted,q['BitVecVal'](0x9E,8),q['BitVecVal'](0x9D,8)),
        *[out[j]==a.m[j] for j in range(42)]),
        'universal9C exact header guard and outgoing held; header00 rejects, F1 accepts')


def native():
    data=json.loads(subprocess.check_output(['node',str(root/'cache-bc-head93-canonical-steady-native.cjs'),
        '--proof-input'],text=True))
    assert data['report']['onlyPublicKeys'] and data['report']['ALL5mirror']
    baseline=stage(data,'packet-repeat-idle');final=stage(data,'packet-idle')
    assert baseline['words']['Ms:P7']==final['words']['Ms:P7']==ZERO
    assert baseline['display']==final['display']=='12345678,'
    assert baseline['words']==final['words'] and baseline['registers']==final['registers']
    assert data['nativeIdleStates']['packet-repeat-idle']==data['nativeIdleStates']['packet-idle']
    before=data['windows']['packet-repeat-idle'][0];after=data['windows']['packet-idle'][0]
    assert before['fullBefore']==after['fullBefore'] and before['tagsBefore']==after['tagsBefore']
    assert after['word']-before['word']==577920
    for name in ('packet-repeat-idle','packet-idle'):period(data['windows'][name],'steady/'+name)
    audit=data['report']['packetAudit']
    assert audit['checkedWords']==2088240 and audit['numberHeld'] and audit['firstDifference'] is None
    for name,records in data['windows'].items():
        if name.startswith('packet-repeat2-') or name in ('packet-repeat-idle','packet-idle'):
            preserved_number(records,data['cells'])
    print('PASS NATIVE2088240 audited words/P10 held; exact complete native endpoint '
          'and original fullBefore/630-tag recurrence after577920 actual words. '
          'By deterministic frozen frame/tick/key code, SAME fixed key/timing cycle repeats. '
          'Not arbitrary operations/data or live hardware.',flush=True)
    return data


def contracts(data):
    for label in ('packet-repeat2-reopen-P8F','packet-repeat2-reopen-W0'):
        records=data['windows'][label];gates=[v for v in records if v['ip']==0x9C]
        assert len(gates)==2
        first,accepted=gates
        assert first['numericOwner']==['Ms:Q'] and first['fullBefore']['ik1302']['m'][31:35:3]==[0,0]
        assert first['fullAfter']['ik1302']['r'][36]+16*first['fullAfter']['ik1302']['r'][39]==0x9D
        assert accepted['numericOwner']==['unclassified:aux1']
        assert accepted['fullBefore']['ik1302']['m'][31:35:3]==[15,1]
        assert accepted['fullAfter']['ik1302']['r'][36]+16*accepted['fullAfter']['ik1302']['r'][39]==0x9E
        assert all(v['numericOwner']!=['Ms:P7'] for v in gates)
        print('PASS native noP7 gate',label,'Q/00 reject',first['word'],
              '-> aux1/F1 accept',accepted['word'],flush=True)
    plus=data['windows']['packet-repeat2-plus'];buffer=next(v for v in plus if v['ip']==0xE9)
    assert buffer['numericOwner']==['stack:X'] and raw(buffer['emitted'][1:36:3])==SEVEN
    num['copy_contract'](buffer,'ik1302',0xE9,False,'steady_LastX7_not_P10')
    normal=next(v for v in data['windows']['packet-repeat2-lastx'] if v['ip']==0xEE)
    assert normal['numericOwner']==['stack:X'] and raw(normal['fullBefore']['ik1302']['m'][1:36:3])==SEVEN
    source=next(v for v in data['windows']['packet-repeat2-reopen-lastx'] if v['ip']==0xEE)
    assert source['numericOwner']==['Ms:P10'] and source['word']==2627005
    assert raw(source['fullBefore']['ik1302']['m'][1:36:3])==NUMBER
    num['copy_contract'](source,'ik1302',0xEE,True,'third_hidden_P10_number_reader')
    frame=prep['quadruple'](data['windows']['packet-repeat2-reopen-lastx'],'third_hidden_P10_lift')
    assert frame[0]['numericOwner']==['unclassified:aux0'] and frame[0]['word']==2627021
    assert raw(frame[0]['emitted'][1:36:3])==NUMBER
    print('PASS third physical reader2627005 EE/P10 ->2627021 E7/aux0; ordinaryRE0, '
          'no D6 or ordinary numerical backup read in LastX.',flush=True)
    assert not any(v['ip']==0xD6 for v in data['windows']['packet-repeat2-reopen-lastx'])


def sections(data):
    result=[('packet-repeat-idle',data['windows']['packet-repeat-idle'])]
    for label,records in data['windows'].items():
        if not label.startswith('packet-repeat2-'):continue
        if label=='packet-repeat2-flush1':
            assert len(records)==1181 and not any(v['ip'] in (0xD6,0xE7,0xE9) for v in records)
            result.extend([(label+'_head',records[:6]),(label+'_error',records[-12:])])
        else:result.append((label,records))
    result.append(('packet-idle',data['windows']['packet-idle']))
    assert len(result)==40 and sum(len(v) for _,v in result)==4822
    return result


def run():
    r['inlet']['immutable_reference']();guard_contract()
    data=native();contracts(data);chosen=sections(data)
    part=next((a.split('=',1)[1] for a in sys.argv if a.startswith('--part=')),None)
    assert part in (None,'1','2')
    if part:chosen=chosen[:20] if part=='1' else chosen[20:]
    if '--contracts-only' not in sys.argv:
        direct=skipped=0
        for label,records in chosen:
            a,b=replay(records,'steady/'+label);direct+=a;skipped+=b
        assert direct+skipped==sum(len(v) for _,v in chosen)
        print('PASS TOTAL',direct+skipped,'originalALL5 words/',len(chosen),'separate windows/slices;',
              'part',part or 'all','direct',direct,'fixed-pin skips',skipped,
              'NOT continuous577920-word symbolic macrocycle, full1181-word reject or historical prefix.',flush=True)
    r['inlet']['immutable_reference']()


if __name__=='__main__':run()
