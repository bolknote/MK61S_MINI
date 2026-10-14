#!/usr/bin/env python3
"""Canonical aux0-only restore, arithmetic/register access and true LastX.

Full fixed public-key native protocol and observer-free mirrors. All original
ALL5 computed continuously in separate selected windows; no checkpoint repair,
ROM/control/phase writes or emulator state imports. One integer NUM fixture,
not arbitrary-old-bank safety or a whole K1/K2 implementation.
"""
from pathlib import Path
import json
import runpy
import subprocess
import sys

root=Path(__file__).resolve().parent
num=runpy.run_path(str(root/'cache-bc-head93-packet-number-proof.py'))
geo=runpy.run_path(str(root/'cache-bc-head93-packet-geometry-proof.py'))
r=num['r'];prep=num['prep'];prior=num['prior']
raw,stage,replay,period,preserved_number=(num[n] for n in ('raw','stage','replay','period','preserved_number'))
F,ZERO,NUMBER=(num[n] for n in ('F','ZERO','NUMBER'))
FIVE='000050000000';THREE='000030000000'


def no_port_control():
    source=('const v=require('+json.dumps(str(root/'cache-bc-head93-t-packet-prepare-native.cjs'))+
        ').run({proof:true,phase:"ykn"});console.log(JSON.stringify(v));')
    data=json.loads(subprocess.check_output(['node','-e',source],text=True))
    report=data['report'];assert report['onlyPublicKeys'] and report['ALL5mirror']
    assert 'packet-clean-port5' not in data['windows']
    assert stage(data,'packet-clean-plus')['display']=='5,'
    assert stage(data,'packet-clean-plus')['words']['Ms:P10']==THREE
    assert stage(data,'packet-idle')['markers']==['Ms:P8']
    assert report['packetAudit']['checkedWords']==737520
    assert not report['packetAudit']['numberHeld']
    assert report['packetAudit']['firstDifference']=={
        'word':1167655,'stage':'packet-clean-plus','moment':'after','actual':THREE}
    call=data['windows']['packet-clean-plus'];write=next(v for v in call if v['ip']==0xE9)
    assert write['numericOwner']==['Ms:P10'] and raw(write['fullBefore']['ik1302']['m'][1:36:3])==NUMBER
    assert raw(write['emitted'][1:36:3])==THREE
    num['copy_contract'](write,'ik1302',0xE9,False,'no_port_ADD_overwrites_P103')
    for name,code in [('packet-clean-store2',0xD4),('packet-clean-read2',0xD6)]:
        event=next(v for v in data['windows'][name] if v['ip']==code)
        assert event['ordinaryOwner']==['register:RE']
    lastx=data['windows']['packet-clean-lastx'];read=next(v for v in lastx if v['ip']==0xEE)
    assert read['numericOwner']==['Ms:P10']
    assert raw(read['fullBefore']['ik1302']['m'][1:36:3])==THREE
    period(data['windows']['packet-idle'],'canonical-no-port-control')
    print('PASS NATIVE matched NO-P5/F control:2+3 still5, but P10 becomes3 at1167655; '
          'STORE2/RCL2 actually useRE, LastX readsP10, P8 is still base. '
          'Correct display does NOT prove storage/normal addressing.',flush=True)
    labels=['packet-clean-plus','packet-clean-store2','packet-clean-read2','packet-clean-lastx','packet-idle']
    total=0
    if '--contracts-only' not in sys.argv:
        for label in labels:
            a,b=replay(data['windows'][label],'canonical-no-port/'+label);total+=a+b
        assert total==646
        print('PASS TOTAL control646 originalALL5 words/5 separate continuous windows;',
              'not whole737520-word native history.',flush=True)


def run():
    r['inlet']['immutable_reference']();geo['a7_skip_contract']()
    if '--no-port-control' in sys.argv:
        no_port_control();r['inlet']['immutable_reference']();return
    data=json.loads(subprocess.check_output(['node',str(root/
        'cache-bc-head93-canonical-number-native.cjs'),'--proof-input'],text=True))
    report=data['report'];assert report['onlyPublicKeys'] and report['ALL5mirror']
    inlet=stage(data,'packet-sign-repeat');restore=stage(data,'packet-clean-port5-zero')
    final=stage(data,'packet-idle');assert restore['markers']==final['markers']==['aux0']
    assert restore['registers']==inlet['registers']
    expected=list(inlet['registers']);expected[14]=ZERO
    assert final['registers']==expected and NUMBER not in final['registers']
    assert restore['program']==final['program']==inlet['program']
    assert final['words']['Ms:P10']==NUMBER and final['display']=='0,'
    assert [n for n,v in final['words'].items() if v==NUMBER]==['Ms:P10']
    period(data['windows']['packet-idle'],'canonical-number')
    names=[n for n in data['windows'] if n.startswith('packet-clean-')]+['packet-idle']
    sections=[]
    for name in names:
        records=data['windows'][name];preserved_number(records,data['cells'])
        if name=='packet-clean-flush1':
            assert len(records)==1181 and records[1]['ip']==0x9D
            assert not any(v['ip'] in (0xD6,0xE7,0xE9) for v in records)
            header=next(v for v in records if v['ip']==0xA3)
            assert header['numericOwner']==['unclassified:aux1']
            sections.extend([(name+'_head',records[:6]),(name+'_error',records[-12:])])
        else:sections.append((name,records))
    for name in [*(f'packet-clean-zero{i}' for i in range(1,5)),
        'packet-clean-aux0F','packet-clean-YF','packet-clean-X1F','packet-clean-P8',
        *(f'packet-clean-flush{i}' for i in range(2,6))]:
        records=data['windows'][name];frame=prep['quadruple'](records,name)
        assert not any(v['numericOwner']==['Ms:P10'] for v in frame)
    for name,source in [('packet-clean-aux0F','register:R3'),('packet-clean-YF','register:R5'),
        ('packet-clean-X1F','register:R8'),('packet-clean-P8','register:RB')]:
        d6=next(v for v in data['windows'][name] if v['ip']==0xD6)
        assert d6['ordinaryOwner']==[source]
    assert stage(data,'packet-clean-port5')['registers'][5]==F
    assert stage(data,'packet-clean-flush5')['markers']==['aux0']
    assert restore['registers'][5]==ZERO
    plus=data['windows']['packet-clean-plus']
    buffer=next(v for v in plus if v['ip']==0xE9)
    assert buffer['numericOwner']==['stack:X'] and raw(buffer['emitted'][1:36:3])==THREE
    num['copy_contract'](buffer,'ik1302',0xE9,False,'canonical_add_LastX3_not_P10')
    request=next(v for v in plus if v['ip']==0xA3)
    assert request['numericOwner']==['unclassified:aux1']
    assert raw(request['emitted'][1:36:3])=='100000000000'
    assert stage(data,'packet-clean-plus')['display']=='5,'
    assert stage(data,'packet-clean-plus')['words']['Y']==FIVE
    for name,code,owner in [('packet-clean-store2',0xD4,'register:R2'),
        ('packet-clean-read2',0xD6,'register:R2'),('packet-clean-register-zero2',0xD4,'register:R2')]:
        event=next(v for v in data['windows'][name] if v['ip']==code)
        assert event['ordinaryOwner']==[owner]
        print('PASS native normal address',name,hex(code),owner,event['word'],flush=True)
    read=next(v for v in data['windows']['packet-clean-read2'] if v['ip']==0xD6)
    assert raw(read['fullBefore']['ik1302']['m'][0:36:3])==FIVE
    lastx=data['windows']['packet-clean-lastx'];source=next(v for v in lastx if v['ip']==0xEE)
    assert source['numericOwner']==['stack:X']
    assert raw(source['fullBefore']['ik1302']['m'][1:36:3])==THREE
    num['copy_contract'](source,'ik1302',0xEE,True,'normal_LastX_reads_X3_not_hiddenP10')
    assert stage(data,'packet-clean-lastx')['display']=='3,'
    erased=next(v for v in data['windows']['packet-clean-backup-zero'] if v['ip']==0xD4)
    assert erased['ordinaryOwner']==['register:RE']
    assert stage(data,'packet-clean-backup-zero')['registers'][14]==ZERO
    assert report['packetAudit']['checkedWords']==754320
    assert report['packetAudit']['numberHeld'] and report['packetAudit']['firstDifference'] is None
    print('PASS NATIVE canonical-only aux0, normal2 ENTER3+=5, normalR2 store/read/restore, '
          'normalLastX3 distinct from hiddenP10/12345678. M1 ports restored, ordinary '
          'NUM/RE backup deliberately cleared, no ordinary NUM copy; program105 held; '
          '754320 audited whole native words/P10 held.',flush=True)
    print('BOUNDARY: unusedQ/headerFFF and P9/old3F7 are not arbitrary oldMs preserved; '
          'reverse read from normal geometry and eight-word/56-step K1/K2 remain.',flush=True)
    direct=skipped=covered=0
    if '--contracts-only' not in sys.argv:
        for label,records in sections:
            a,b=replay(records,'canonical/'+label);direct+=a;skipped+=b;covered+=len(records)
        assert covered==direct+skipped
        print('PASS TOTAL',covered,'originalALL5 words in',len(sections),'SEPARATE windows/slices;',
              'direct',direct,'fixed-pin skips',skipped,'not entire1181-word rejected wait/native prefix.',flush=True)
    r['inlet']['immutable_reference']()


if __name__=='__main__':run()
