#!/usr/bin/env python3
"""Native hiddenP10 read, numerical SIGN1 and repeat after marker cleanup.

Fixed public keys on fresh guarded stock references and observer-free mirrors.
Strict original ALL5 replay is continuous in each explicitly separate window;
no state imports, control/phase patches, ROM edits or checkpoint repairs.
P10 is the relocated stack's LastX, not an independent arbitrary-use register.
"""
from pathlib import Path
import json
import runpy
import subprocess
import sys

from z3 import And, BitVec

root=Path(__file__).resolve().parent
control=runpy.run_path(str(root/'cache-bc-head93-t-packet-control-proof.py'))
prep=control['prep'];prior=control['prior']
r,w,q=(control[n] for n in ('r','w','q'))
raw,stage,replay,period,preserved_number=(control[n] for n in
    ('raw','stage','replay','period','preserved_number'))
owner,outgoing=(control[n] for n in ('chip_owner','outgoing'))
F,ZERO,NUMBER=(control[n] for n in ('F','ZERO','NUMBER'))
ONE='000010000000'


def native(negative=False,overwrite=False):
    data=json.loads(subprocess.check_output(['node',str(root/
        'cache-bc-head93-packet-number-native.cjs'),'--proof-input',
        *(['--no-cleanup'] if negative else ['--buffer-overwrite'] if overwrite else [])],text=True))
    assert data['report']['onlyPublicKeys'] and data['report']['ALL5mirror']
    period(data['windows']['packet-idle'],'packet-number/'+('no-cleanup' if negative else 'repeat'))
    return data


def copy_contract(v,chip,code,read=False,label='copy'):
    a=r['concrete_primary'](v['fullBefore'][chip])
    symbolic=[BitVec(label+'_n'+str(j),4) for j in range(12)]
    for j,n in enumerate(symbolic):
        (a.m if read else a.r)[1+3*j if read else 3*j]=n
    p=w['base'](a,code);out=[]
    b=prior['engine']['models'][chip]['execute_command'](a,code,
        *prior['all5']['pins'](v)[chip],
        serial_inputs=[q['N4'](n) for n in v['fullAfter'][chip]['m']],emitted_outputs=out)
    wanted=[b.r[3*j] if read else out[1+3*j] for j in range(12)]
    w['prove'](p,And(*[wanted[j]==symbolic[j] for j in range(12)]),
        'conditional '+label+' all12 fields exact, observed other control/serial context')


def positive(data):
    inlet=stage(data,'packet-sign-retry');final=stage(data,'packet-idle')
    assert inlet['markers']==['Y','Ms:P8','aux1']
    names=['packet-flush1','packet-flush2','packet-flush3','packet-lastx-clean',
           'packet-sign-clean','packet-lastx-repeat','packet-sign-repeat','packet-idle']
    wanted_lengths=[124,124,124,154,184,154,184,30]
    sections=[]
    for name,length in zip(names,wanted_lengths):
        records=data['windows'][name];assert len(records)==length,(name,len(records))
        preserved_number(records,data['cells'])
        s=stage(data,name);assert s['registers']==inlet['registers'] and s['program']==inlet['program']
        assert not any(v['ip']==0xD4 for v in records)
        sections.append((name,records))
    for i in range(1,4):
        records=data['windows']['packet-flush'+str(i)]
        d6=[v for v in records if v['ip']==0xD6]
        assert len(d6)==1 and d6[0]['ordinaryOwner']==['register:R2']
        assert raw(d6[0]['fullBefore']['ik1302']['m'][0:36:3])==ZERO
        assert [v for v in records if v['ip']==1][-1]['numericOwner']==['Ms:P8']
        frame=prep['quadruple'](records,'P8_only_flush'+str(i))
        assert [v['numericOwner'] for v in frame]==[
            ['unclassified:aux0'],['unclassified:aux1'],['stack:X'],['stack:Y']]
        assert raw(frame[0]['fullBefore']['ik1302']['r'][0:36:3])==ZERO
    assert stage(data,'packet-flush3')['markers']==['Ms:P8']
    for name in ('packet-lastx-clean','packet-lastx-repeat'):
        records=data['windows'][name]
        assert not any(v['ip']==0xD6 for v in records),'no ordinary backup register read'
        source=next(v for v in records if v['ip']==0xEE)
        assert source['numericOwner']==['Ms:P10']
        assert raw(source['fullBefore']['ik1302']['m'][1:36:3])==NUMBER
        assert raw(source['fullAfter']['ik1302']['r'][0:36:3])==NUMBER
        assert source['fullBefore']['ik1302']['st'][36]+16*source['fullBefore']['ik1302']['st'][39]==0xF0
        copy_contract(source,'ik1302',0xEE,True,name+'_P10_reader')
        frame=prep['quadruple'](records,name+'_lift')
        assert [v['numericOwner'] for v in frame]==[
            ['unclassified:aux0'],['unclassified:aux1'],['stack:X'],['stack:Y']]
        assert raw(frame[0]['emitted'][1:36:3])==NUMBER
        s=stage(data,name);assert s['words']['aux0']==NUMBER and s['display']=='12345678,'
        print('PASS NATIVE',name,'EE/P10 at',source['word'],'-> E7/aux0 at',frame[0]['word'],
              'exact normal number; no D6/ordinary backup reads, P10 held.',flush=True)
    for name in ('packet-sign-clean','packet-sign-repeat'):
        records=data['windows'][name]
        assert not any(v['ip']==0xD6 for v in records)
        source=next(v for v in records if v['ip']==0xEE)
        assert source['numericOwner']==['unclassified:aux0']
        assert raw(source['fullAfter']['ik1302']['r'][0:36:3])==NUMBER
        buffer=next(v for v in records if v['ip']==0xE9)
        assert buffer['numericOwner']==['Ms:P10']
        assert raw(buffer['emitted'][1:36:3])==NUMBER
        copy_contract(buffer,'ik1302',0xE9,False,name+'_P10_buffer')
        request=next(v for v in records if v['ip']==0xA3)
        assert request['numericOwner']==['Ms:P9']
        assert raw(request['emitted'][1:36:3])=='327000000000'
        third=[(v,v['fullBefore']['ik1306']['r'][36]+16*v['fullBefore']['ik1306']['r'][39])
               for v in records]
        read=next(v for v,ip in third if ip==0x16)
        result=next(v for v,ip in third if ip==0xFF)
        ack=next(v for v,ip in third if ip==0xFD)
        assert owner(data,read,'ik1306')==owner(data,result,'ik1306')==['unclassified:aux0']
        assert raw(read['fullBefore']['ik1306']['m'][1:36:3])==NUMBER
        assert raw(read['fullAfter']['ik1306']['r'][0:36:3])==NUMBER
        assert raw(result['fullBefore']['ik1306']['r'][0:36:3])==ONE
        assert raw(outgoing(result,'ik1306')[1:36:3])==ONE
        assert owner(data,ack,'ik1306')==['Ms:P9']
        assert raw(outgoing(ack,'ik1306')[1:36:3])=='3F7000000000'
        copy_contract(read,'ik1306',0x16,True,name+'_number_reader')
        copy_contract(result,'ik1306',0xFF,False,name+'_result_writer')
        control['third_ack'](ack)
        s=stage(data,name);assert s['words']['aux0']==ONE and s['display']=='1,'
        print('PASS NATIVE',name,'request32/P9 at',request['word'],
              'IK1306/16 reads12345678 at',read['word'],
              'FD/3F at',ack['word'],'FF/aux0 writes1 at',result['word'],
              'display1, P10/raw12 held. Route',
              [f'{ip:02X}' for v,ip in third if read['word']<=v['word']<=result['word']],flush=True)
    assert final['words']['Ms:P10']==NUMBER and final['words']['aux0']==final['words']['aux1']==ONE
    assert final['display']=='1,' and final['markers']==['Ms:P8']
    assert data['report']['packetAudit']['checkedWords']==342720
    print('PASS NATIVE342720 audited whole words/P10 held; numerical read/SIGN/repeat works. '
          'Relocated stack/LastX only, not independent arbitrary-use register, normal geometry or full K1/K2.',flush=True)
    return sections


def negative(data):
    reads=data['windows']['packet-lastx'];call=data['windows']['packet-sign-number']
    assert len(reads)==139 and len(call)==124
    preserved_number(reads,data['cells'])
    source=next(v for v in reads if v['ip']==0xEE)
    assert source['numericOwner']==['stack:Y']
    assert raw(source['fullBefore']['ik1302']['m'][1:36:3])==F
    assert not any(v['ip']==0xD6 for v in reads+call)
    write=next(v for v in call if v['ip']==0xE9)
    assert write['word']==797485 and write['numericOwner']==['Ms:P10']
    assert raw(write['fullBefore']['ik1302']['m'][1:36:3])==NUMBER
    assert raw(write['emitted'][1:36:3])==ZERO
    copy_contract(write,'ik1302',0xE9,False,'unclean_E9_P10_loss')
    assert stage(data,'packet-idle')['words']['Ms:P10']==ZERO
    print('PASS NATIVE no-cleanup control: LastX readsY/F, notP10; SIGN/E9/P10 erases '
          'all12 number fields at797485. Native258720-word audit finds same first loss; '
          'ordinary reserve remains but is not read in these calls.',flush=True)
    return [('unclean_LastX',reads),('unclean_SIGN',call),('unclean_idle',data['windows']['packet-idle'])]


def buffer_overwrite(data):
    inlet=stage(data,'packet-sign-repeat');final=stage(data,'packet-idle')
    assert inlet['words']['Ms:P10']==NUMBER and inlet['words']['aux0']==ONE
    assert final['words']['Ms:P10']==final['words']['aux0']==ONE
    assert final['display']=='1,' and final['markers']==['Ms:P8']
    assert inlet['registers']==final['registers'] and inlet['program']==final['program']
    records=data['windows']['packet-sign-overwrite'];assert len(records)==184
    assert not any(v['ip']==0xD6 for v in records)
    source=next(v for v in records if v['ip']==0xEE)
    assert source['numericOwner']==['unclassified:aux0']
    assert raw(source['fullAfter']['ik1302']['r'][0:36:3])==ONE
    write=next(v for v in records if v['ip']==0xE9)
    assert write['word']==898300 and write['numericOwner']==['Ms:P10']
    assert raw(write['fullBefore']['ik1302']['m'][1:36:3])==NUMBER
    assert raw(write['emitted'][1:36:3])==ONE
    copy_contract(write,'ik1302',0xE9,False,'normal_SIGN_updates_LastX')
    value=prior['physical_word']
    for v in records:
        for moment in ('Before','After'):
            wanted=NUMBER if v['word']<write['word'] or (
                v['word']==write['word'] and moment=='Before') else ONE
            assert value(v['full'+moment],v['tags'+moment],data['cells'],'Ms','P10')==wanted
    audit=data['report']['packetAudit']
    assert audit['checkedWords']==359520 and not audit['numberHeld']
    assert audit['firstDifference']=={
        'word':898300,'stage':'packet-sign-overwrite','moment':'after','actual':ONE}
    print('PASS NATIVE post-success SIGN(1): display still1, but E9/P10 at898300 '
          'replaces12345678 with1. Real LastX-buffer semantics, NOT independent '
          'storage immune to ordinary calculations; ordinary backup is held.',flush=True)
    return [('buffer_overwrite_SIGN',records),('buffer_overwrite_idle',data['windows']['packet-idle'])]


def run():
    r['inlet']['immutable_reference']()
    if '--buffer-only' in sys.argv:
        data=native(overwrite=True);sections=buffer_overwrite(data)
        if '--contracts-only' not in sys.argv:
            totals=[replay(records,'packet-number/'+label) for label,records in sections]
            assert sum(a+b for a,b in totals)==214
            print('PASS TOTAL buffer diagnostic214 originalALL5 words/2 separate windows;',
                  'not historical prefix/full359520-word native audit.',flush=True)
        r['inlet']['immutable_reference']();return
    baseline=json.loads(subprocess.check_output(['node','-e',
        'console.log(JSON.stringify(require('+json.dumps(str(root/'cache-bc-head93-q-normal-roundtrip-native.cjs'))+
        ').baseline("1")))'],text=True))
    assert baseline['word']==ONE and baseline['display']=='1,'
    direct=skipped=covered=count=0
    for bad in (False,True):
        data=native(bad);sections=negative(data) if bad else positive(data)
        if '--contracts-only' not in sys.argv:
            for label,records in sections:
                a,b=replay(records,'packet-number/'+label)
                direct+=a;skipped+=b;covered+=len(records);count+=1
        if '--positive-only' in sys.argv:break
    if '--contracts-only' not in sys.argv:
        assert covered==direct+skipped==(1078 if '--positive-only' in sys.argv else 1371)
        assert count==(8 if '--positive-only' in sys.argv else 11)
        print('PASS TOTAL',covered,'original ALL5 words in',count,'SEPARATE continuous windows;',
              'direct',direct,'fixed-pin skips',skipped,'not historical prefix/full native waits.',flush=True)
    r['inlet']['immutable_reference']()


if __name__=='__main__':run()
