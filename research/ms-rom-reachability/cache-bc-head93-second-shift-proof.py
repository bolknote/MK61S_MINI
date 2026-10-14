#!/usr/bin/env python3
"""Two physical Ms words at the new nondestructive shift frontier.

Basic mode retains explicit temporary ordinary R6/R7 copies. --erase deletes
them; --read then recovers physical P7. Not a clean normal arithmetic cycle
or two independent readers from the final new mixed state.
Original ALL5 replay is continuous within each separate selected window.
"""
from pathlib import Path
import json
import runpy
import subprocess
import sys
from z3 import And, BitVec

root=Path(__file__).resolve().parent
num=runpy.run_path(str(root/'cache-bc-head93-packet-number-proof.py'))
r=num['r'];prep=num['prep']
raw,stage,replay,period,preserved=(num[n] for n in
    ('raw','stage','replay','period','preserved_number'))
FIRST='007012345678';SECOND='007024681357';F='0000F0000000'


def ordinary_latched_copy(written,label,wanted):
    """D4 writes S,A0..A10, NOT the unrotated A0..A11.

    The native prefix supplies that alignment. The failed naive unrotated
    assertion exposed this latch; it was not weakened into a false copy claim.
    """
    w,q=(num[n] for n in ('w','q'))
    before=written['fullBefore']['ik1302']
    assert raw([before['s'],*before['r'][0:33:3]])==wanted
    a=r['concrete_primary'](before)
    arbitrary=[BitVec(label+'_latched'+str(j),4) for j in range(12)]
    a.s=arbitrary[0]
    for j in range(11):a.r[3*j]=arbitrary[j+1]
    p=w['base'](a,0xD4);out=[]
    w['ex'](a,0xD4,written['keysX'],written['keysY'],
        serial_inputs=[q['N4'](n) for n in written['fullAfter']['ik1302']['m']],emitted_outputs=out)
    w['prove'](p,And(*[out[3*j]==arbitrary[j] for j in range(12)],
        *[out[j]==a.m[j] for j in range(42) if j%3!=0 or j>=36]),
        label+' local all12 latched(S,A0..A10) D4 copy, every other lane held')


def run():
    r['inlet']['immutable_reference']()
    read='--read' in sys.argv
    erase='--erase' in sys.argv or read
    data=json.loads(subprocess.check_output(['node',str(root/'cache-bc-head93-second-shift-native.cjs'),
        '--proof-input',*(['--read'] if read else ['--erase'] if erase else [])],text=True))
    assert data['report']['onlyPublicKeys'] and data['report']['ALL5mirror']
    assert data['secondShift']['firstHeld'] and data['secondShift']['twoPhysicalSlots']
    ledger=data['report']['packetAudit']
    assert ledger['checkedWords']==(1594320 if read else 1560720 if erase else 1527120) and ledger['numberHeld'] and ledger['firstDifference'] is None
    second_ledger=data['report']['secondSlotAudit']
    assert second_ledger['numberHeld'] and second_ledger['firstDifference'] is None
    assert len(second_ledger['writes'])==1 and second_ledger['writes'][0]['actual']==SECOND
    inlet=stage(data,'packet-second-open4')
    assert inlet['words']['U']==SECOND and inlet['words']['Ms:P10']==FIRST
    for i,target in enumerate(('V','W','Q'),1):
        label='packet-second-shift'+str(i);records=data['windows'][label]
        assert stage(data,label)['words'][target]==SECOND
        d6=next(v for v in records if v['ip']==0xD6)
        assert d6['ordinaryOwner']==['register:R8']
        assert raw(d6['fullBefore']['ik1302']['m'][0:36:3])==F
        frame=prep['quadruple'](records,'second_safe_U_Q_'+str(i))
        assert [v['numericOwner'] for v in frame]==[['Ms:'+n] for n in ('U','V','W','Q')]
        assert raw(frame[0]['emitted'][1:36:3])==F
        moved=frame[i]
        assert raw(moved['emitted'][1:36:3])==SECOND
        preserved(records,data['cells'])
    records=data['windows']['packet-second-shift-Q']
    d6=next(v for v in records if v['ip']==0xD6)
    assert d6['ordinaryOwner']==['register:RD']
    assert raw(d6['fullBefore']['ik1302']['m'][0:36:3])=='000000000000'
    frame=prep['quadruple'](records,'second_safe_Q_P9')
    assert [v['numericOwner'] for v in frame]==[['Ms:'+n] for n in ('Q','P7','P8','P9')]
    assert raw(frame[0]['fullBefore']['ik1302']['m'][1:36:3])==SECOND
    assert raw(frame[1]['emitted'][1:36:3])==SECOND
    preserved(records,data['cells'])
    final=stage(data,'packet-idle')
    assert final['words']['Ms:P7']==SECOND and final['words']['Ms:P10']==FIRST
    if erase:
        erased=stage(data,'packet-second-erase7')
        assert erased['registers'][6]==erased['registers'][7]=='000000000000'
        assert FIRST not in erased['registers'] and SECOND not in erased['registers']
        assert [n for n,v in erased['words'].items() if v==FIRST]==['Ms:P10']
        assert [n for n,v in erased['words'].items() if v==SECOND]==['Ms:P7']
        if not read:assert final['registers']==erased['registers']
        for reg in (6,7):
            label='packet-second-erase'+str(reg);records=data['windows'][label]
            source=next(v for v in records if v['ip']==0xEE)
            assert source['numericOwner']==['Ms:Q']
            assert raw(source['fullBefore']['ik1302']['m'][1:36:3])=='000000000000'
            written=next(v for v in records if v['ip']==0xD4)
            assert written['ordinaryOwner']==['register:R'+str(reg)]
            assert raw(written['emitted'][0:36:3])=='000000000000'
            ordinary_latched_copy(written,label,'000000000000')
    else:
        assert final['registers'][6]==FIRST and final['registers'][7]==SECOND
    if read:
        opened=data['windows']['packet-second-read-open']
        zero=next(v for v in opened if v['ip']==0xD6)
        assert zero['ordinaryOwner']==['register:R7']
        assert raw(zero['fullBefore']['ik1302']['m'][0:36:3])=='000000000000'
        frame=prep['quadruple'](opened,'second_P7_reader_open')
        assert [v['numericOwner'] for v in frame]==[['stack:X1'],['Ms:U'],['Ms:V'],['Ms:W']]
        records=data['windows']['packet-second-read-output']
        source=next(v for v in records if v['ip']==0xEE)
        assert source['numericOwner']==['Ms:P7']
        assert raw(source['fullBefore']['ik1302']['m'][1:36:3])==SECOND
        num['copy_contract'](source,'ik1302',0xEE,True,'second_full_P7_reader')
        assert not any(v['ip']==0xD6 for v in records),'no ordinary source read'
        written=next(v for v in records if v['ip']==0xD4)
        assert written['ordinaryOwner']==['register:R6']
        ordinary_latched_copy(written,'second_P7_output',SECOND)
        assert final['registers'][6]==SECOND and final['registers'][7]=='000000000000'
        assert FIRST not in final['registers'] and final['display']=='24681357,'
        preserved(records,data['cells'])
        print('PASS NATIVE physicalP7 EE -> realR6 D4/display24681357 AFTER both ordinary '
            'sources erased; P7 and P10 continuously held; no ordinary D6 number-source.',flush=True)
    assert final['program']==inlet['program']
    period(data['windows']['packet-idle'],'second-shift/P7-and-P10')
    print('PASS NATIVE U->V->W->Q->P7=24681357; P10=12345678 held at EVERY '
          'observed native word; '+('ALL ordinary numerical reserves erased at storage endpoint; '
          'only physicalP7/P10 numerical copies remained.' if erase else
          'ordinary R6/R7 reserves remain explicitly.'),flush=True)
    labels=['packet-second-source-store','packet-second-source-flush4',
        'packet-second-open1','packet-second-open2','packet-second-open3','packet-second-open4',
        'packet-second-shift1','packet-second-shift2','packet-second-shift3',
        'packet-second-shift-Q',*(['packet-second-erase6','packet-second-erase7'] if erase else []),
        *(['packet-second-read-open','packet-second-read-output'] if read else []),'packet-idle']
    if '--erasure-only' in sys.argv:
        assert erase
        labels=['packet-second-erase6','packet-second-erase7','packet-idle']
    if '--reader-only' in sys.argv:
        assert read
        labels=['packet-second-erase6','packet-second-erase7','packet-second-read-open','packet-second-read-output','packet-idle']
    if '--contracts-only' not in sys.argv:
        direct=skipped=0
        for label in labels:
            a,b=replay(data['windows'][label],'second-shift/'+label);direct+=a;skipped+=b
        print('PASS TOTAL',direct+skipped,'originalALL5 words/',len(labels),
            'separate continuous windows; direct',direct,'fixed-pin skips',skipped,
            'NOT full prefix replay, independent readers or normal-use bank.',flush=True)
    r['inlet']['immutable_reference']()


if __name__=='__main__':run()
