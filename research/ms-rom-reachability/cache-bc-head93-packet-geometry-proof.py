#!/usr/bin/env python3
"""Native partial canonical marker restoration holding hiddenP10.

Full stock key protocols/mirrors. Strict original ALL5 within explicitly
separate windows, no state imports/ROM edits/checkpoint repairs. Detached
primary planning cannot replace native keyboard/ALL5 verification.
"""
from pathlib import Path
import json
import runpy
import subprocess
import sys

from z3 import And

root=Path(__file__).resolve().parent
num=runpy.run_path(str(root/'cache-bc-head93-packet-number-proof.py'))
prep,prior,control=(num[n] for n in ('prep','prior','control'))
r,w,q=(num[n] for n in ('r','w','q'))
raw,stage,replay,period,preserved_number=(num[n] for n in
    ('raw','stage','replay','period','preserved_number'))
F,ZERO,NUMBER,ONE=(num[n] for n in ('F','ZERO','NUMBER','ONE'))
labels=['packet-restore-aux0F','packet-restore-clone1','packet-restore-clone2',
        'packet-restore-TF','packet-restore-X1F','packet-restore-removeP8']


def native(clock=False):
    return json.loads(subprocess.check_output(['node',str(root/
        'cache-bc-head93-packet-geometry-native.cjs'),'--proof-input',
        *(['--clock-control'] if clock else [])],text=True))


def a7_skip_contract():
    a=q['State']('geometry_A7_skip');p=w['base'](a,0xA7);out=[]
    b=w['ex'](a,0xA7,*q['arbitrary_keys']('geometry_A7_skip_keys'),emitted_outputs=out)
    w['prove'](p,And(w['ip'](b)==0xE5,*[out[j]==a.m[j] for j in range(42)],
        *[b.r[3*j]==a.r[3*j] for j in range(12)]),
        'universal A7 ->E5, A/all42 outgoing held; current marker is NOT tested here')


def check(data,clock=False):
    report=data['report'];assert report['onlyPublicKeys'] and report['ALL5mirror']
    inlet=stage(data,'packet-sign-repeat');final=stage(data,'packet-idle')
    assert inlet['markers']==['Ms:P8'] and inlet['words']['Ms:P10']==NUMBER
    assert final['markers']==['X','W','Q','aux0','aux1']
    assert final['words']['Ms:P10']==NUMBER and final['words'].get('X1')==ZERO
    assert final['registers']==inlet['registers'] and final['program']==inlet['program']
    assert report['packetAudit']['checkedWords']==(468750 if clock else 468720)
    assert report['packetAudit']['numberHeld'] and report['packetAudit']['firstDifference'] is None
    period(data['windows']['packet-idle'],'geometry/'+('clock24+6' if clock else 'no-extra-wait'))
    for name in labels+['packet-restore-cx','packet-restore-clearX1','packet-idle']:
        preserved_number(data['windows'][name],data['cells'])
    sections=[]
    for name,length,source,owners in zip(labels,[139,139,139,124,118,125],
        ['register:R3','register:RC','register:RC','register:R8','register:R4','register:RC'],
        [['unclassified:aux0','unclassified:aux1','stack:X','stack:Y']]*3+
        [['stack:T','stack:X1','Ms:U','Ms:V'],['stack:Y','stack:Z','stack:T','stack:X1'],
         ['Ms:W','Ms:Q','Ms:P7','Ms:P8']]):
        records=data['windows'][name];assert len(records)==length
        d6=[v for v in records if v['ip']==0xD6]
        assert len(d6)==1 and d6[0]['ordinaryOwner']==[source]
        assert d6[0]['fullAfter']['ik1302']['r'][36]+16*d6[0]['fullAfter']['ik1302']['r'][39]==0xA7
        frame=prep['quadruple'](records,name)
        assert [v['numericOwner'] for v in frame]==[[s] for s in owners]
        assert not any(v['ip']==0xD4 for v in records)
        sections.append((name,records))
    remove=data['windows']['packet-restore-removeP8']
    assert remove[0]['ip']==0x9C and remove[0]['numericOwner']==['Ms:Q']
    assert remove[1]['ip']==0x9D and any(v['ip']==0x9E for v in remove)
    assert [v for v in remove if v['ip']==1][-1]['numericOwner']==['Ms:W']
    last=next(v for v in reversed(remove) if v['ip']==0xE7)
    assert last['numericOwner']==['Ms:P9']
    assert raw(last['fullBefore']['ik1302']['r'][0:36:3])==ONE
    assert raw(last['emitted'][1:36:3])==ONE
    # The conditional entry template planner predicted the right flags, but
    # not this P9/1 endpoint: real first9C/Q rejected before valid9C/P9.
    print('PASS NATIVE P8 removed, aux0F held; lateP9=1, NOT the conditional '
          'fixed-entry modelP9=0. No snapshot repair to conceal template gap.',flush=True)
    cx=data['windows']['packet-restore-cx'];assert len(cx)==1112
    assert not any(v['ip'] in (0xEE,0xE7,0xE9,0xD6) for v in cx)
    assert {tuple(v['numericOwner']) for v in cx if v['ip']==0x9C}=={
        ('unclassified:aux1',),('Ms:U',)}
    header=next(v for v in cx if v['ip']==0xA3)
    assert header['numericOwner']==['Ms:U'] and raw(header['emitted'][1:36:3])=='FFF000000000'
    sections.extend([('CX_rejected_head',cx[:6]),('CX_error_return',cx[-12:])])
    records=data['windows']['packet-restore-clearX1'];assert len(records)==(127 if clock else 133)
    gates=[v for v in records if v['ip']==0x9C]
    if clock:
        assert gates[0]['numericOwner']==['Ms:U'] and records[1]['ip']==0x9E
    else:
        assert records[0]['numericOwner']==['unclassified:aux1'] and records[1]['ip']==0x9D
        assert gates[1]['numericOwner']==['Ms:U'] and any(v['ip']==0x9E for v in records)
    d6=next(v for v in records if v['ip']==0xD6)
    assert d6['ordinaryOwner']==['register:R5']
    assert raw(d6['fullBefore']['ik1302']['m'][0:36:3])==ZERO
    assert [v for v in records if v['ip']==1][-1]['numericOwner']==['Ms:W']
    frame=prep['quadruple'](records,'clear_X1_'+('clock' if clock else 'no_wait'))
    assert [v['numericOwner'] for v in frame]==[
        ['stack:Y'],['stack:Z'],['stack:T'],['stack:X1']]
    assert raw(frame[-1]['fullBefore']['ik1302']['m'][1:36:3])==F
    assert raw(frame[-1]['emitted'][1:36:3])==ZERO
    sections.extend([('clear_X1',records),('idle',data['windows']['packet-idle'])])
    if clock:sections=sections[-2:]
    print('PASS NATIVE', '24+6 real-clock control' if clock else 'preferred NO extra pause',
          'X1 cleared; sourceR5=0, primary rootW; aux0F/P10 held; '
          'X/W/Q/aux1 still remain, CX alone failed. NOT normal geometry or full K1/K2.',flush=True)
    return sections


def run():
    r['inlet']['immutable_reference']();a7_skip_contract();covered=direct=skipped=count=0
    for clock in (False,True):
        data=native(clock);sections=check(data,clock)
        if '--contracts-only' not in sys.argv:
            for label,records in sections:
                a,b=replay(records,'geometry/'+('clock/' if clock else 'no_wait/')+label)
                covered+=len(records);direct+=a;skipped+=b;count+=1
        if '--no-clock-control' in sys.argv:break
    if '--contracts-only' not in sys.argv:
        assert covered==direct+skipped==(965 if '--no-clock-control' in sys.argv else 1122)
        assert count==(10 if '--no-clock-control' in sys.argv else 12)
        print('PASS TOTAL',covered,'originalALL5 words in',count,'SEPARATE windows/slices;',
              'direct',direct,'fixed-pin skips',skipped,'not whole1112-word CX wait/native prefix.',flush=True)
    r['inlet']['immutable_reference']()


if __name__=='__main__':run()
