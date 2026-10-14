#!/usr/bin/env python3
"""Actual T/aux1 bottleneck: accepted single store versus rejected lifts.

Fresh fixed public-key native protocols and full observer-free mirrors only.
Strict ALL5 replay covers explicitly SEPARATE slices, not entire long waits.
The secondary request-header theorem is detached/local to observed control
and serial context; its symbolic states are NEVER loaded into the emulator.
"""
from pathlib import Path
import json
import runpy
import subprocess
import sys

from z3 import And, BitVec, If

root=Path(__file__).resolve().parent
prior=runpy.run_path(str(root/'cache-bc-head93-p9-controller-cleanup-proof.py'))
reader,r,w,q,all5,engine=(prior[n] for n in ('reader','r','w','q','all5','engine'))
raw=prior['raw'];stage=prior['stage'];period=prior['period']
F,ZERO,NUMBER=(prior[n] for n in ('F','ZERO','NUMBER'))
preserved_number=prior['preserved_number'];replay=prior['replay_periods']


def owner(data,v,chip='ik1303',moment='Before'):
    return sorted({data['cells'][tag]['area']+':'+str(data['cells'][tag]['word'])
        for j,tag in enumerate(v['tags'+moment][chip]) if j%3==1})


def native(args):
    data=json.loads(subprocess.check_output(['node',str(root/
        'cache-bc-head93-t-marker-recovery-native.cjs'),'--proof-input',*args],text=True))
    report=data['report'];assert report['minimal'] and report['onlyPublicKeys'] and report['ALL5mirror']
    inlet=stage(data,'restore-next-idle');final=stage(data,'t-recovery-idle')
    assert inlet['markers']==final['markers']==['T','aux1']
    assert inlet['words']['Ms:P10']==final['words']['Ms:P10']==NUMBER
    assert inlet['registers']==final['registers'] and inlet['program']==final['program']
    assert final['words']['aux0']==ZERO and final['display']=='ЕГГ0Г'
    assert final['ip']==0x35 and final['pc']=='06'
    wanted=dict(inlet['words'])
    if report['qTRecoveryProfile']=='sign':wanted['Y']=ZERO
    assert final['words']==wanted
    audit=report['tRecoveryAudit']
    assert audit['numberHeld'] and audit['firstDifference'] is None
    assert audit['checkedWords']==(15120 if report['qTRecoveryProfile']=='enter' else 23520)
    period(data['windows']['t-recovery-idle'],'T-recovery/'+report['qTRecoveryProfile'])
    for v in data['windows']['t-recovery-idle']:
        for moment in ('Before','After'):
            assert prior['physical_word'](v['full'+moment],v['tags'+moment],data['cells'],'stack','T')==F
            assert prior['physical_word'](v['full'+moment],v['tags'+moment],data['cells'],'unclassified','aux1')==F
    for name,records in data['windows'].items():
        if name.startswith('t-recovery-'):preserved_number(records,data['cells'])
    if '--calc' in args:
        audit=report['postCalcAudit']
        assert audit['checkedWords']==42000 and audit['numberHeld'] and audit['firstDifference'] is None
        assert stage(data,'restore-post-plus')['display']=='ЕГГ0Г'
    return data


def single_store(record):
    assert record['ip']==0xE9 and record['numericOwner']==['stack:Y']
    assert raw(record['fullBefore']['ik1302']['r'][0:36:3])==ZERO
    assert raw(record['fullBefore']['ik1302']['m'][1:36:3])==NUMBER
    assert raw(record['emitted'][1:36:3])==ZERO
    a=r['concrete_primary'](record['fullBefore']['ik1302'])
    data=[BitVec('T_SIGN_A'+str(j),4) for j in range(12)]
    old=[BitVec('T_SIGN_oldY'+str(j),4) for j in range(12)]
    for j in range(12):a.r[3*j]=data[j];a.m[1+3*j]=old[j]
    p=w['base'](a,0xE9);out=[]
    b=w['ex'](a,0xE9,*q['arbitrary_keys']('T_SIGN_store_keys'),
        serial_inputs=[q['N4'](n) for n in record['fullAfter']['ik1302']['m']],emitted_outputs=out)
    w['prove'](p,And(w['ip'](b)==0xA2,*[out[1+3*j]==data[j] for j in range(12)],
        *[b.r[3*j]==data[j] for j in range(12)],
        *[out[j]==a.m[j] for j in range(42) if j%3!=1 or j>=37]),
        'conditional E9 single-store: all16^12 A/oldY, other lanes/services held; no four-word push')


def header_write(record,label):
    assert record['ip']==0xA3 and record['numericOwner']==['stack:X1']
    before=record['fullBefore']['ik1302'];expected=before['r'][27:36:3]
    assert record['emitted'][28:35:3]==expected
    a=r['concrete_primary'](before)
    lower=[BitVec(label+'_lower'+str(j),4) for j in range(9)]
    for j in range(9):a.m[1+3*j]=lower[j]
    p=w['base'](a,0xA3);out=[]
    w['ex'](a,0xA3,record['keysX'],record['keysY'],
        serial_inputs=[q['N4'](n) for n in record['fullAfter']['ik1302']['m']],emitted_outputs=out)
    w['prove'](p,And(*[out[1+3*j]==lower[j] for j in range(9)],
        *[out[j]==q['N4'](n) for j,n in zip((28,31,34),expected)],
        *[out[j]==a.m[j] for j in range(42) if j not in (28,31,34)]),
        label+' conditional header3-only write, all16^9 lower fields held')


def zero_guard():
    a=q['State']('T_recovery_zero_guard');p=w['base'](a,0x9C)
    p.add(a.m[31]==0,a.m[34]==0);out=[]
    b=w['ex'](a,0x9C,*q['arbitrary_keys']('T_recovery_guard_keys'),emitted_outputs=out)
    w['prove'](p,And(w['ip'](b)==0x9D,*[out[j]==a.m[j] for j in range(42)]),
        'universal9C/header00 -> reject9D/no writes; other state and keys arbitrary')


def control_locator():
    a=q['State']('T_recovery_A2_locator');p=w['base'](a,0xA2);out=[]
    b=w['ex'](a,0xA2,*q['arbitrary_keys']('T_recovery_locator_keys'),emitted_outputs=out)
    w['prove'](p,And(w['ip'](b)==If(a.m[22]==15,q['BitVecVal'](0xA3,8),
        q['BitVecVal'](0xA2,8)),*[out[j]==a.m[j] for j in range(42)]),
        'universal A2 scans to firstM22F; A3 is the FOLLOWING word, no scan writes')
    print('CONDITIONAL GEOMETRY: after E9/Y, A2 startsZ; T/F selects X1/control. '
          'With only T.field7 cleared and other current marker fields held, '
          'A2 reaches aux1 and selects X/control. No native T-clear constructor claimed.',flush=True)


def quiet_secondary(data,records):
    start=next(i for i,v in enumerate(records) if v['word']>668132
        and v['fullBefore']['ik1303']['r'][36]+16*v['fullBefore']['ik1303']['r'][39]==0x6E
        and owner(data,v)==['Ms:W'])
    loop=records[start:start+15]
    expected=[0x6E]*8+[0x5E,0x50,0x52,0x53,0x4F,0x24,0x39]
    assert [v['fullBefore']['ik1303']['r'][36]+16*v['fullBefore']['ik1303']['r'][39]
            for v in loop]==expected
    assert owner(data,loop[7])==['unclassified:aux1']
    assert owner(data,loop[8])==['stack:X']
    assert loop[8]['fullBefore']['ik1303']['m'][31:35:3]==[0,0]
    assert owner(data,loop[12])==['stack:X1']
    assert loop[12]['fullBefore']['ik1303']['m'][31:35:3]==[2,3]
    model=engine['models']['ik1303']
    a=r['concrete_primary'](loop[0]['fullBefore']['ik1303']);p=w['base'](a,0x6E)
    request=[BitVec('T_secondary_wrong_request_'+str(j),4) for j in range(2)]
    for i,v in enumerate(loop):
        code=expected[i];old=a;out=[]
        w['prove'](p,w['ip'](a)==code,'wrong-pair secondary forced'+f'{code:02X}',False)
        incoming=[q['N4'](n) for n in v['fullAfter']['ik1303']['m']]
        if owner(data,v,moment='After')==['stack:X1']:
            incoming[31],incoming[34]=request
        a=model['execute_command'](a,code,*all5['pins'](v)['ik1303'],
                                   serial_inputs=incoming,emitted_outputs=out)
        w['prove'](p,And(*[out[j]==old.m[j] for j in range(42)]),
                   'wrong-pair secondary no outgoing changes'+f'{code:02X}',False)
    w['prove'](p,And(w['ip'](a)==0x6E,a.r[29]==0),
        'conditional secondary quiet loop ignores ALL256 X1 request bytes; X/control remains00')
    expected=r['concrete_primary'](loop[-1]['fullAfter']['ik1303'])
    w['prove'](p,And(*[getattr(a,n)[j]==getattr(expected,n)[j]
        for n in ('r','st','m') for j in range(42)],
        *[getattr(a,n)==getattr(expected,n) for n in ('s','s1','l','t','carry')]),
        'conditional ALL256 wrong-slot bytes leave the complete secondary515-bit state identical')
    print('OBSERVED secondary aux1 -> X/control00, while primary request32 is in X1; '
          '15-command local loop, observed other fields/serial schedule/pins only.',flush=True)
    return loop


def run():
    r['inlet']['immutable_reference']();zero_guard();control_locator()
    profiles=[('sign',[],'t-recovery-sign',2441),
        ('zeroE',['--zero'],'t-recovery-zero1',2190),
        ('zero6',['--zero','--digit-six'],'t-recovery-zero1',2310),
        ('zeroE_lead2',['--zero','--lead-two'],'t-recovery-zero1',2190),
        ('enter',['--enter'],'t-recovery-enter1',2190),
        ('lastx',['--lastx'],'t-recovery-lastx1',2175)]
    if '--sign-only' in sys.argv:profiles=profiles[:1]
    if '--blocked-only' in sys.argv:profiles=profiles[1:]
    covered=direct=skipped=windows=0
    for label,args,name,length in profiles:
        data=native(args+(['--calc'] if label=='sign' and '--calc' in sys.argv else []))
        records=data['windows'][name];assert len(records)==length
        sections=[]
        if label=='sign':
            assert records[1]['ip']==0x9E
            write=next(v for v in records if v['ip']==0xE9);single_store(write)
            headers=[v for v in records if v['ip']==0xA3]
            assert len(headers)==2 and headers[0]['word']==668132 and headers[1]['word']==670532
            assert raw(headers[0]['emitted'][1:36:3])=='320000000000'
            assert raw(headers[1]['emitted'][1:36:3])=='FFF000000000'
            for i,v in enumerate(headers):header_write(v,'SIGN_header'+str(i))
            loop=quiet_secondary(data,records)
            sections=[('head_to_request',records[:31]),('secondary_quiet',loop),
                      ('timeout_to_stop',records[-12:])]
        else:
            assert records[0]['ip']==0x9C and records[1]['ip']==0x9D
            assert records[0]['numericOwner']==['stack:X']
            assert records[0]['fullBefore']['ik1302']['m'][31:35:3]==[0,0]
            assert not any(v['ip'] in (0xD6,0xE7,0xA8,0xE9) for v in records)
            header=next(v for v in records if v['ip']==0xA3);header_write(header,label+'_error')
            sections=[('rejected_head',records[:6]),('error_to_stop',records[-12:])]
        sections.append(('idle',data['windows']['t-recovery-idle']))
        if '--contracts-only' not in sys.argv:
            for suffix,selected in sections:
                a,b=replay(selected,'T-recovery/'+label+'/'+suffix)
                direct+=a;skipped+=b;covered+=len(selected);windows+=1
        print('PASS NATIVE',label,data['report']['tRecoveryAudit']['checkedWords'],
              'whole diagnostic words/P10 held; recorded whole command',length,
              'words, replay slices NOT entire wait. T/aux1 remain/error.',flush=True)
    if '--contracts-only' not in sys.argv:
        expected=88 if '--sign-only' in sys.argv else 240 if '--blocked-only' in sys.argv else 328
        assert covered==direct+skipped==expected,(covered,direct,skipped)
        assert windows==(4 if '--sign-only' in sys.argv else 15 if '--blocked-only' in sys.argv else 19)
        print('PASS TOTAL',covered,'words in',windows,'SEPARATE slices; direct',direct,
              'fixed-pin skips',skipped,'not entire native histories.',flush=True)
    print('BOUNDARY: numerical copy exists, but T is not removed; primaryT/X1 '
          'and secondaryaux1/X select incompatible controls. Need compatible '
          'native marker/control constructor, not longer blind pauses.',flush=True)
    r['inlet']['immutable_reference']()


if __name__=='__main__':run()
