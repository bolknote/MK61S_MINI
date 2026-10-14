#!/usr/bin/env python3
"""Canonical return, new6+7/LastX and repeated original hiddenP10 read.

Original ALL5 continuous replay per explicit window/slice; no checkpoint
repair/state imports/ROM edits. Matched omitted-stack-clear control included.
"""
from pathlib import Path
import json
import runpy
import subprocess
import sys

root=Path(__file__).resolve().parent
num=runpy.run_path(str(root/'cache-bc-head93-packet-number-proof.py'))
r=num['r'];prep=num['prep']
raw,stage,replay,period,preserved_number=(num[n] for n in ('raw','stage','replay','period','preserved_number'))
F,ZERO,NUMBER=(num[n] for n in ('F','ZERO','NUMBER'))
SEVEN='000070000000';THIRTEEN='001013000000'


def native(negative=False):
    data=json.loads(subprocess.check_output(['node',str(root/'cache-bc-head93-canonical-cycle-native.cjs'),
        '--proof-input',*(['--no-preclear-control'] if negative else [])],text=True))
    assert data['report']['onlyPublicKeys'] and data['report']['ALL5mirror']
    period(data['windows']['packet-idle'],'canonical-cycle/'+('uncleared' if negative else 'repeat'))
    for label,records in data['windows'].items():
        if label.startswith('packet-repeat-') or label=='packet-idle':preserved_number(records,data['cells'])
    return data


def positive(data):
    inlet=stage(data,'packet-reopen-lastx');restored=stage(data,'packet-repeat-port5-zero')
    assert restored['markers']==['aux0'] and restored['registers']==inlet['registers']
    assert [n for n,v in restored['words'].items() if v==NUMBER]==['Ms:P10']
    plus=data['windows']['packet-repeat-plus'];write=next(v for v in plus if v['ip']==0xE9)
    assert write['numericOwner']==['stack:X'] and raw(write['emitted'][1:36:3])==SEVEN
    num['copy_contract'](write,'ik1302',0xE9,False,'repeat_ADD_LastX7_not_P10')
    assert stage(data,'packet-repeat-plus')['display']=='13,'
    normal=next(v for v in data['windows']['packet-repeat-lastx'] if v['ip']==0xEE)
    assert normal['numericOwner']==['stack:X']
    assert raw(normal['fullBefore']['ik1302']['m'][1:36:3])==SEVEN
    num['copy_contract'](normal,'ik1302',0xEE,True,'repeat_normal_LastX7')
    assert stage(data,'packet-repeat-lastx')['display']=='7,'
    for i in range(1,5):
        label=f'packet-repeat-preclear{i}';records=data['windows'][label]
        read=next(v for v in records if v['ip']==0xD6)
        assert read['ordinaryOwner']==['register:R0']
        assert raw(read['fullBefore']['ik1302']['m'][0:36:3])==ZERO
        frame=prep['quadruple'](records,label)
        assert [v['numericOwner'] for v in frame]==[['stack:Y'],['stack:Z'],['stack:T'],['stack:X1']]
    for name in ['Y','Z','T','X1']:assert stage(data,'packet-repeat-preclear4')['words'][name]==ZERO
    finalread=data['windows']['packet-repeat-reopen-lastx']
    assert not any(v['ip']==0xD6 for v in finalread)
    source=next(v for v in finalread if v['ip']==0xEE)
    assert source['numericOwner']==['Ms:P10']
    assert raw(source['fullBefore']['ik1302']['m'][1:36:3])==NUMBER
    num['copy_contract'](source,'ik1302',0xEE,True,'second_hidden_P10_number_reader')
    frame=prep['quadruple'](finalread,'second_hidden_P10_lift')
    assert frame[0]['numericOwner']==['unclassified:aux0']
    assert raw(frame[0]['emitted'][1:36:3])==NUMBER
    assert stage(data,'packet-idle')['display']=='12345678,'
    print('PASS NATIVE repeated cycle: first hidden12345678 read -> clean aux0-only return -> '
          'normal6 ENTER7+=13/LastX7 -> four actualR0 zero recalls -> '
          'second EE/P10',source['word'],'-> E7/aux0',frame[0]['word'],
          'returns original12345678. M1 restored, RE0, P10 held1510320 native words.',flush=True)
    sections=[]
    for label,records in data['windows'].items():
        if label.startswith('packet-repeat-'):
            if label=='packet-repeat-flush1':
                assert len(records)==1181 and not any(v['ip'] in (0xD6,0xE7,0xE9) for v in records)
                sections.extend([(label+'_head',records[:6]),(label+'_error',records[-12:])])
            else:sections.append((label,records))
    sections.append(('packet-idle',data['windows']['packet-idle']))
    assert sum(len(v) for _,v in sections)==4792 and len(sections)==39
    return sections


def negative(data):
    assert not any(n.startswith('packet-repeat-preclear') for n in data['windows'])
    assert stage(data,'packet-repeat-plus')['display']=='13,'
    carried=prep['quadruple'](data['windows']['packet-repeat-reopen-P8F'],'uncleared_stack_13_to_X1')
    assert carried[3]['numericOwner']==['stack:X1'] and raw(carried[3]['emitted'][1:36:3])==THIRTEEN
    pair=data['windows']['packet-repeat-reopen-W0']
    frame=prep['quadruple'](pair,'uncleared_stack_13_to_U')
    assert frame[1]['numericOwner']==['Ms:U'] and raw(frame[1]['emitted'][1:36:3])==THIRTEEN
    stored=data['windows']['packet-repeat-reopen-Zzero']
    early=next(v for v in stored if v['ip']==0xEE)
    assert early['numericOwner']==['Ms:U']
    assert raw(early['fullBefore']['ik1302']['m'][1:36:3])==THIRTEEN
    num['copy_contract'](early,'ik1302',0xEE,True,'uncleared_U_reads_13_not_zero')
    assert next(v for v in stored if v['ip']==0xD4)['ordinaryOwner']==['register:R5']
    assert stage(data,'packet-repeat-reopen-Zzero')['registers'][5]==THIRTEEN
    finalread=data['windows']['packet-repeat-reopen-lastx']
    assert not any(v['ip']==0xEE and v['numericOwner']==['Ms:P10'] for v in finalread)
    final=stage(data,'packet-idle')
    assert final['display']=='13,' and final['markers']==['Z','Ms:P8']
    print('PASS matched NO-preclear control: residual13 movesX1->U, '
          'EE/U reads13 before STORE/R5; Z/F remains, final13 is NOT hidden12345678. '
          'P10 itself held1443120 native words.',flush=True)
    labels=['packet-repeat-after-clear','packet-repeat-reopen-YF','packet-repeat-reopen-P8F','packet-repeat-reopen-W0',
        'packet-repeat-reopen-aux0zero','packet-repeat-reopen-Zzero','packet-repeat-reopen-lastx','packet-idle']
    sections=[(n,data['windows'][n]) for n in labels]
    assert sum(len(v) for _,v in sections)==886
    return sections


def run():
    r['inlet']['immutable_reference']()
    cases=[True] if '--negative-only' in sys.argv else [False] if '--positive-only' in sys.argv else [False,True]
    direct=skipped=covered=count=0
    for bad in cases:
        data=native(bad);sections=negative(data) if bad else positive(data)
        if '--contracts-only' not in sys.argv:
            for label,records in sections:
                a,b=replay(records,'canonical-cycle/'+('uncleared/' if bad else 'positive/')+label)
                direct+=a;skipped+=b;covered+=len(records);count+=1
    if '--contracts-only' not in sys.argv:
        print('PASS TOTAL',covered,'originalALL5 words/',count,'separate windows/slices;',
              'direct',direct,'fixed-pin skips',skipped,
              'not full1181-word reject or historical native prefix.',flush=True)
    r['inlet']['immutable_reference']()


if __name__=='__main__':run()
