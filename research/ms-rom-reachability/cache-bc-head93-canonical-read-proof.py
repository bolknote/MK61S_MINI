#!/usr/bin/env python3
"""HiddenP10 read after canonical arithmetic and ordinary backup erasure.

Strict original ALL5 replay in separately named continuous windows; no model
state imports, checkpoint repairs, ROM/control/phase edits or live hardware.
Positive and matched wrong-address control, not a full eight-word K1/K2.
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


def native(wrong=False):
    data=json.loads(subprocess.check_output(['node',str(root/'cache-bc-head93-canonical-read-native.cjs'),
        '--proof-input',*(['--wrong-source-control'] if wrong else [])],text=True))
    assert data['report']['onlyPublicKeys'] and data['report']['ALL5mirror']
    inlet=stage(data,'packet-clean-backup-zero');final=stage(data,'packet-idle')
    assert inlet['markers']==['aux0'] and inlet['display']=='0,'
    assert inlet['registers'][14]==ZERO and NUMBER not in inlet['registers']
    assert [n for n,v in inlet['words'].items() if v==NUMBER]==['Ms:P10']
    assert stage(data,'packet-clean-plus')['display']=='5,'
    assert stage(data,'packet-clean-lastx')['display']=='3,'
    labels=[n for n in data['windows'] if n.startswith('packet-reopen-')]+['packet-idle']
    for label in labels:
        preserved_number(data['windows'][label],data['cells'])
        s=stage(data,label)
        assert s['registers']==inlet['registers'] and s['program']==inlet['program']
    period(data['windows']['packet-idle'],'canonical-read/'+('wrong9' if wrong else 'correct1'))
    audit=data['report']['packetAudit']
    assert audit['checkedWords']==939120 and audit['numberHeld'] and audit['firstDifference'] is None
    return data,labels


def contracts(data,wrong=False):
    sources={'packet-reopen-YF':'RC','packet-reopen-X1F':'R8','packet-reopen-WF':'RC',
        'packet-reopen-P8F':'R3','packet-reopen-W0':'R7',
        ('packet-reopen-aux0zero' if wrong else 'packet-reopen-aux0zero-native'):('R6' if wrong else 'RD'),
        **{f'packet-reopen-flush{i}':'R2' for i in range(1,4)}}
    for label,owner in sources.items():
        records=data['windows'][label]
        reads=[v for v in records if v['ip']==0xD6]
        assert len(reads)==1 and reads[0]['ordinaryOwner']==['register:'+owner]
        value=F if owner in ('RC','R8','R3') else ZERO
        assert raw(reads[0]['fullBefore']['ik1302']['m'][0:36:3])==value
        frame=prep['quadruple'](records,label+('_wrong' if wrong else '_correct'))
        assert not any(v['numericOwner']==['Ms:P10'] for v in frame)
    stored=next(v for v in data['windows']['packet-reopen-Zzero'] if v['ip']==0xD4)
    assert stored['ordinaryOwner']==['register:R5']
    lastx=data['windows']['packet-reopen-lastx']
    assert not any(v['ip']==0xD6 for v in lastx),'no ordinary numerical backup reader'
    source=next(v for v in lastx if v['ip']==0xEE)
    if wrong:
        assert source['numericOwner']==['stack:T']
        assert raw(source['fullBefore']['ik1302']['m'][1:36:3])==F
        assert stage(data,'packet-idle')['display']=='0,'
        print('PASS matched wrong-address control: ИП9 readsR6/0, notRD/0; '
              'first LastX EE readsT/F, notP10. P10 held but no numerical recovery.',flush=True)
    else:
        assert source['numericOwner']==['Ms:P10']
        assert raw(source['fullBefore']['ik1302']['m'][1:36:3])==NUMBER
        assert raw(source['fullAfter']['ik1302']['r'][0:36:3])==NUMBER
        assert source['word']==1477885
        num['copy_contract'](source,'ik1302',0xEE,True,'post_arithmetic_P10_number_reader')
        frame=prep['quadruple'](lastx,'post_arithmetic_P10_lift')
        assert [v['numericOwner'] for v in frame]==[
            ['unclassified:aux0'],['unclassified:aux1'],['stack:X'],['stack:Y']]
        assert frame[0]['word']==1477901 and raw(frame[0]['emitted'][1:36:3])==NUMBER
        assert stage(data,'packet-reopen-flush3')['markers']==['Ms:P8']
        final=stage(data,'packet-idle')
        assert final['markers']==['Ms:P8'] and final['display']=='12345678,'
        assert final['words']['aux0']==final['words']['Ms:P10']==NUMBER
        print('PASS NATIVE after canonical2+3/R2/LastX and ordinaryRE erasure: '
              'ИП1 actually readsRD/0, EE/P10 at1477885 -> E7/aux0 at1477901, '
              'display12345678; no ordinary numerical copy/read, P10 held939120 words.',flush=True)


def run():
    r['inlet']['immutable_reference']()
    direct=skipped=covered=count=0
    cases=[True] if '--negative-only' in sys.argv else [False] if '--positive-only' in sys.argv else [False,True]
    for wrong in cases:
        data,labels=native(wrong);contracts(data,wrong)
        if '--contracts-only' not in sys.argv:
            total=0
            for label in labels:
                a,b=replay(data['windows'][label],'canonical-read/'+('wrong/' if wrong else 'positive/')+label)
                direct+=a;skipped+=b;covered+=a+b;count+=1;total+=a+b
            assert total==(1448 if wrong else 1491)
            print('PASS SUBTOTAL',total,'originalALL5 words/',len(labels),'separate continuous windows',
                  'matched wrong address' if wrong else 'positive hidden read',flush=True)
    if '--contracts-only' not in sys.argv:
        print('PASS TOTAL',covered,'originalALL5 words in',count,'separate continuous windows;',
              'direct',direct,'fixed-pin skips',skipped,'not full historical prefix or939120-word native audit.',flush=True)
    r['inlet']['immutable_reference']()


if __name__=='__main__':run()
