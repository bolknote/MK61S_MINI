#!/usr/bin/env python3
"""Native header6 gadget copies ordinaryP8 into hidden Ms:P10 while holdingQ.

Two arithmetic payloads are created with public keys, retained through the
native Q-only constructor, then copied by originalD6/E7/A8 microcode. ALL5
replays never repair working/control/return/phase/RAM at checkpoints. Fresh
observer-free references mirror every complete action. The reserve's initial
arithmetic generation is native/guarded, not included in the replay count.
This is a COPY, not BC/K2, general-old-bank preservation or an inverse.
"""
from pathlib import Path
import runpy
import sys

from z3 import And, BitVec

root=Path(__file__).resolve().parent
previous=runpy.run_path(str(root/'cache-bc-head93-native-q-isolated-proof.py'))
reader,r,w,q=(previous[n] for n in ('reader','r','w','q'))
raw=reader['raw']


def header_contracts():
    a=q['State']('payload_DE_B6');p=w['base'](a,0xDE);p.add(a.r[34]==6)
    b=w['ex'](a,0xDE,*q['arbitrary_keys']('payload_DE_B6keys'))
    w['prove'](p,w['ip'](b)==0xD6,'DE with B11=6 -> D6, other working fields/keys free')
    w['prove'](p,w['stack'](b)[0]==w['stack'](a)[0],
        'DE keeps original top return; E5 is NOT a fabricated DE return')
    a=q['State']('payload_D6_local');p=w['base'](a,0xD6);p.add(a.r[41]==15)
    b=w['ex'](a,0xD6,*q['arbitrary_keys']('payload_D6_localkeys'))
    w['prove'](p,And(*[b.r[3*j]==a.m[3*j] for j in range(12)],
        b.s1==a.r[35],w['ip'](b)==w['stack'](a)[0]),
        'D6/R41F reads full M1, takes S1 from original R35 and returns through original top')
    a=q['State']('payload_E6_fork');p=w['base'](a,0xE6)
    b=w['ex'](a,0xE6,*q['arbitrary_keys']('payload_E6_forkkeys'))
    for selector,target in [(0,0xE0),(13,0xED)]:
        p.push();p.add(a.s1==selector)
        w['prove'](p,w['ip'](b)==target,
            f'E6 original selector{selector:X} -> {target:02X}, other working fields/keys free')
        p.pop()


def copy_kernel(records,label):
    """Conditional raw12 copy at the OBSERVED E7(P9)/A8(P10) inlet.

Only oldP9 numeric12 becomes arbitrary in this detached primary model.
This is not universal keyboard construction/late survival of arbitrary
payloads: data-dependent marker bits can affect surrounding/later scans.
    """
    a=r['concrete_primary'](records[0]['fullBefore']['ik1302'])
    assert records[0]['ip']==0xE7 and records[1]['ip']==0xA8
    data=[BitVec(label+'_oldP9_'+str(j),4) for j in range(12)]
    for j,v in enumerate(data):a.m[1+3*j]=v
    p=w['base'](a,0xE7)
    for i,record in enumerate(records):
        out=[];code=record['ip']
        w['prove'](p,w['ip'](a)==code,label+' fixed localIP',False)
        a=w['ex'](a,code,*q['arbitrary_keys'](label+'_keys'+str(i)),
            serial_inputs=[q['N4'](v) for v in record['fullAfter']['ik1302']['m']],
            emitted_outputs=out)
        if i==0:
            w['prove'](p,And(*[a.r[3*j]==data[j] for j in range(12)],
                *[out[1+3*j]==0 for j in range(12)]),
                label+' zero-write displaces oldP9 intoA',False)
        else:
            w['prove'](p,And(*[out[1+3*j]==data[j] for j in range(12)],
                *[out[j]==record['fullBefore']['ik1302']['m'][j]
                  for j in range(42) if j%3!=1 or j>=37]),
                label+' A8 copies arbitrary oldP9 numeric12 verbatim, other lanes/services held',False)
    print('PASS CONDITIONAL LOCAL',label,'E7(P9)/A8(P10) carries all16^12 raw words; '
          'observed control/serial context only, not universal whole-path payload compatibility.',flush=True)


def run_case(label,word):
    native=reader['native']('--q-payload-'+label+'-proof-input')
    assert native['report']['qReserveGhost8'] and native['report']['qAddressRead']=='D'
    assert native['report']['ghostWord']==word
    assert native['ghostPrepared']['registers'][8]==word
    ready=native['isolatedStable'];final=native['addressStable']
    assert ready['markers']==['Q','aux0'] and ready['registers'][8]==word
    assert ready['words']['Ms:P10']=='000000000000'
    assert final['registers']==ready['registers'] and final['program']==ready['program']
    assert final['registers']==['000000000000']*8+[word]+['000000000000']*6
    assert final['words']['Ms:P10']==word and final['words']['Q']=='0000F0000000'
    assert final['markers']==['Q']
    assert final['words']['aux0']==final['words']['aux1']=='000000000000'
    assert final['ST2']==[0,0,0] and final['ip']==0x35 and final['modeR2']==8
    expected={'stop':91,'store':136,'read':6,'read-after-clear':9,'lastx-lift':14,
        'clear-real':4,'zero-r9-source':129,'marker-read9':108,'q-idle':30,
        'cleanup-r2-1':115,'cleanup-r2-2':119,'cleanup-idle':30,
        'q-address-read':209,'q-address-idle':30}
    assert set(native['windows'])==set(expected);total=0
    for name,count in expected.items():
        records=native['windows'][name];assert len(records)==count,(name,len(records))
        total+=reader['replay'](records,label+'/'+name)
    assert total==1030
    records=native['windows']['q-address-read']
    assert records[0]['word']==189297 and records[-1]['word']==189505
    assert records[0]['ip']==0x9C and records[-1]['ip']==0xBE
    d6=[v for v in records if v['ip']==0xD6];assert len(d6)==2
    assert [v['ordinaryOwner'] for v in d6]==[['register:R8'],['register:R7']]
    assert raw(d6[0]['fullAfter']['ik1302']['r'][0:36:3])==word
    assert raw(d6[1]['fullAfter']['ik1302']['r'][0:36:3])=='000000000000'
    de=next(v for v in records if v['ip']==0xDE)
    assert de['fullBefore']['ik1302']['r'][34]==6
    assert raw(de['fullBefore']['ik1302']['r'][1:36:3])==word
    assert de['fullBefore']['ik1302']['st'][36]+16*de['fullBefore']['ik1302']['st'][39]==0xE5
    after_de=next(v for v in records if v['word']==de['word']+1);assert after_de['ip']==0xD6
    after_d6=next(v for v in records if v['word']==after_de['word']+1)
    assert after_d6['ip']==0xE5 and after_d6['fullBefore']['ik1302']['s1']==0
    assert any(v['ip']==0xE0 for v in records)
    writes=previous['writers'](records)
    assert [(v['ip'],v['numericOwner']) for v in writes]==[
        (0xE7,['Ms:P9']),(0xA8,['Ms:P10']),(0xA8,['unclassified:aux0']),
        (0xA8,['unclassified:aux1']),(0xE7,['Ms:P9']),(0xA8,['Ms:P10']),
        (0xA8,['unclassified:aux0']),(0xA8,['unclassified:aux1']),(0xE7,['Ms:P9'])]
    assert raw(writes[0]['emitted'][1:36:3])==word
    assert raw(writes[5]['emitted'][1:36:3])==word
    assert writes[4]['word']==189399 and writes[5]['word']==189400
    assert not any(v['ip'] in (0xBB,0xBC,0xC7) for v in records)
    j=records.index(writes[4]);copy_kernel(records[j:j+2],label+'_copy')
    previous['period'](native['windows']['q-address-idle'],label+' hiddenP10/Q idle')
    print('PASS',label,'real',word,'ordinaryP8 -> P9 -> hiddenP10; sourceP8/Q held, '
          'all15 ordinary registers and program held from isolatedQ. '
          'Original DE/B11=6 -> D6/P7=0 -> E5/selector0/E0/A7 -> second push; '
          'old aux0/aux1 are cleared, savedTYPE/KIND=0/0, NOT0/2/D or K2.',flush=True)
    return total


def run():
    r['inlet']['immutable_reference']()
    header_contracts()
    cases=[('short','600010000003'),('long','600012345678')]
    if '--short-only' in sys.argv:cases=cases[:1]
    if '--long-only' in sys.argv:cases=cases[1:]
    for label,word in cases:
        assert run_case(label,word)==1030
        r['inlet']['immutable_reference']()
    print('PASS1030 original ALL5 transitions per payload in14 SEPARATE windows, '
          'not a historical-total addition. Two chosen data fixtures are NOT a '
          'universal valid-number/opaque-program-byte theorem. Native nonzero COPY '
          'exists without BB/BC; old-Ms reserves/normal controller/0/2/D/inverse '
          'remain. No live/browser test, emulator state import or immutable source edit.',flush=True)


if __name__=='__main__':
    if '--contracts-only' in sys.argv:
        r['inlet']['immutable_reference']();header_contracts();r['inlet']['immutable_reference']()
    else:run()
