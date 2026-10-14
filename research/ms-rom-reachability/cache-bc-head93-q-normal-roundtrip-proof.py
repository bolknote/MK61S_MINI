#!/usr/bin/env python3
"""An ordinary number survives STOP+idle in hiddenP10, then reads normally.

The real sourceP6 and logicalX are cleared before STOP; ONLY hiddenP10 keeps
the selected ordinary word. A second public S/P reads it into physicalP9
and the display. Native preparation is continuous/mirrored, never loaded.
Each ALL5 window replays strictly from its FIRST snapshot without repairs.
The reset/marker-cleanup prefix is separate from the two whole program runs.
This is a relocated-stack storage/read demonstration, NOT an independent
normal-geometry extra register, arbitrary-old-bank exchange or fullK1/K2.
"""
from pathlib import Path
import json
import runpy
import subprocess
import sys

from z3 import And,BitVec

root=Path(__file__).resolve().parent
earlier=runpy.run_path(str(root/'cache-bc-head93-q-payload-roundtrip-proof.py'))
reader,r,previous=(earlier[n] for n in ('reader','r','previous'))
w,q=(reader[n] for n in ('w','q'))
raw=reader['raw']


def native(args):
    data=json.loads(subprocess.check_output(['node',str(root/
        'cache-bc-head93-q-normal-roundtrip-native.cjs'),'--proof-input',*args],text=True))
    report=data['report']
    assert report['minimal'] and report['onlyPublicKeys'] and report['ALL5mirror']
    assert report['qNormalReserve'] and report['qReadbackIdleCheck']
    return data


def emitted_records(data,name):
    return [v for v in data['windows'][name] if v['ip']==0x9C]


def check(data,word,control):
    ready=data['addressStable'];stored=next(v for v in data['exitStages']
        if v['name']=='plain-storage-idle');final=data['readbackStable']
    dummy='600010000003';zero='000000000000'
    assert ready['registers'][6]==word and ready['registers'][8]==dummy
    assert ready['words']['Ms:P10']==dummy and ready['markers']==['Q']
    expected=[zero]*15;expected[8]=dummy
    assert stored['registers']==expected,'no ordinary copy of the normal number remains'
    assert stored['display']=='0,' and stored['modeR2']==8 and stored['ip']==0x35
    assert stored['markers']==['Q'] and stored['words']['Q']=='0000F0000000'
    assert stored['words']['Ms:P10']==(zero if control=='no_enter' else word)
    assert stored['words']['Ms:P9']==zero
    assert all(stored['words'][n]==zero for n in ('X','Y','Z','T','X1','U','V','W','Ms:P8'))
    if not control:
        assert [n for n,v in stored['words'].items() if v==word]==['Ms:P10']
    assert final['ip']==0x35 and final['ST2']==[0,0,0] and final['markers']==['Q']
    assert final['words']['Ms:P10']==(word if control=='no_swap' else zero)
    assert final['words']['Ms:P9']==(zero if control else word)
    assert final['words']['Q']==stored['words']['Q']
    if not control:expected[9]=word
    assert final['registers']==expected
    assert final['display']==('0,' if control else data['baseline']['display'])
    if not control:assert final['modeR2']==data['baseline']['R2']
    storage=[0x6B]+([] if control=='no_enter' else [0x0E])+[0x0D,0x4B,0x50]
    retrieval=([] if control=='no_swap' else [0x14])+[0x4E,0x50]
    instructions=storage+retrieval
    assert final['program'][71:71+len(instructions)]==instructions
    assert [i for i,(a,b) in enumerate(zip(ready['program'],final['program'])) if a!=b]==list(range(71,71+len(instructions)))
    assert stored['program']==final['program']
    for name,opcodes in [('payload-exit-run',storage),('payload-readback-run',retrieval)]:
        records=data['windows'][name]
        assert records[0]['ip']==0x9C and records[-1]['ip']==0x35
        actual=[v['fullBefore']['ik1302']['r'][30]+16*v['fullBefore']['ik1302']['r'][33]
            for v in emitted_records(data,name)]
        assert actual==opcodes,(name,actual)
        assert not any(v['ip'] in (0xBB,0xBC,0xC7) for v in records)
    body=data['windows']['payload-exit-run']
    d6=next(v for v in body if v['ip']==0xD6)
    assert d6['ordinaryOwner']==['register:R6']
    assert raw(d6['fullAfter']['ik1302']['r'][0:36:3])==word
    erased=[v for v in body if v['ip']==0xD4]
    assert len(erased)==1 and erased[0]['ordinaryOwner']==['register:R6']
    assert raw(erased[0]['emitted'][0:36:3])==zero
    read=data['windows']['payload-readback-run']
    saved=[v for v in read if v['ip']==0xD4]
    assert len(saved)==1 and saved[0]['ordinaryOwner']==['register:R9']
    assert raw(saved[0]['emitted'][0:36:3])==(zero if control else word)
    if not control:
        seen=next(v for v in read if v['ip']==0xEE and raw(v['fullBefore']['ik1302']['m'][1:36:3])==word)
        assert seen['numericOwner']==['Ms:P9'] and seen['word']<saved[0]['word']
    return stored,final


def enter_contract(data):
    """Only a LOCAL duplicate/push theorem, not universal whole-path numbers."""
    body=data['windows']['payload-exit-run'];inlets=emitted_records(data,'payload-exit-run')
    entry=next(v['word'] for v in inlets if v['fullBefore']['ik1302']['r'][30]+16*v['fullBefore']['ik1302']['r'][33]==0x0E)
    stop=next(v['word'] for v in inlets if v['fullBefore']['ik1302']['r'][30]+16*v['fullBefore']['ik1302']['r'][33]==0x0D)
    e7=next(v for v in body if entry<v['word']<stop and v['ip']==0xE7)
    j=body.index(e7);records=body[j:j+2]
    assert records[1]['ip']==0xA8 and records[1]['numericOwner']==['Ms:P10']
    a=r['concrete_primary'](e7['fullBefore']['ik1302'])
    symbols=[BitVec('normal_enter_raw'+str(k),4) for k in range(12)]
    for k,s in enumerate(symbols):a.r[3*k]=s;a.m[1+3*k]=s
    p=w['base'](a,0xE7)
    for i,v in enumerate(records):
        out=[];w['prove'](p,w['ip'](a)==v['ip'],'normal ENTER local route',False)
        a=w['ex'](a,v['ip'],*q['arbitrary_keys']('normal_enter_keys'+str(i)),
            serial_inputs=[q['N4'](n) for n in v['fullAfter']['ik1302']['m']],emitted_outputs=out)
        w['prove'](p,And(*[out[1+3*k]==symbols[k] for k in range(12)]),
            'normal ENTER local duplicate/push keeps all12 fields',False)
    print('PASS CONDITIONAL LOCAL original E7/A8 duplicates all16^12 raw words '
        'when currentA and oldP9 agree; observed control/serial context only, '
        'not a universal valid-number/opaque-code construction.',flush=True)


def run_case(label,args,word,control=None,full_prefix=False):
    data=native(args);check(data,word,control)
    if label=='integer':enter_contract(data)
    selected={name:v for name,v in data['windows'].items() if full_prefix
        or name.startswith('payload-exit-') or name in ('plain-storage-idle','payload-readback-run','q-readback-idle')}
    total=0
    for name,records in selected.items():
        if name in ('plain-storage-idle','q-readback-idle') or (name.startswith('payload-exit-') and name!='payload-exit-run'):
            assert len(records)==30
        total+=reader['replay'](records,label+'/'+name)
    for name in ('plain-storage-idle','q-readback-idle'):
        previous['period'](data['windows'][name],label+'/'+name)
    expected_total={'integer':1664,'negative':1664,'small':1664,
        'no-enter':1394,'no-swap':1499}[label]+(1030 if full_prefix else 0)
    assert total==expected_total,(label,total,expected_total)
    detail=('SourceP6/X cleared, normal word stored ONLY in hiddenP10 through '
        'STOP+idle, second S/P -> ordinaryP9 and baseline display.' if control is None
        else 'No-enter control: hiddenP10/P9/display stay0.' if control=='no_enter'
        else 'No-swap control: word stays in hiddenP10, P9/display stay0.')
    print('PASS',label,total,'strict original ALL5 transitions in',len(selected),
        'SEPARATE windows.',detail,'Original Q/ROM unchanged, not independent '
        'normal-stack storage/arbitrary-old-bank exchange or fullK1/K2.',flush=True)
    r['inlet']['immutable_reference']()


def run():
    r['inlet']['immutable_reference']()
    if '--add-one-only' in sys.argv:
        data=native(['--add-one']);check(data,'007012345678',None)
        steps=data['arithmeticStages'];assert len(steps)==2
        assert steps[0]['display']=='1,' and steps[0]['words']['Ms:P10']=='007012345678'
        assert steps[1]['display']=='12345679,' and steps[1]['words']['Ms:P9']=='007012345679'
        assert steps[1]['registers']==data['readbackStable']['registers']
        assert steps[1]['program']==data['readbackStable']['program']
        assert steps[1]['words']['Q']=='0000F0000000' and steps[1]['ip']==0x35
        total=0
        for name,code in [('normal-use-one',0x01),('normal-use-plus',0x10)]:
            records=data['windows'][name]
            assert records[0]['ip']==0x9C and records[-1]['ip']==0xBE
            a=records[0]['fullBefore']['ik1302']['r'];assert a[30]+16*a[33]==code
            total+=reader['replay'](records,'normal-use/'+name)
        print('PASS',total,'NEW strict ALL5 arithmetic transitions in2 separate windows; '
            'retrieved12345678 + public1/+ ->12345679, ordinaryP9/program/Q held. '
            'This selected operation is not an arbitrary-key/controller or '
            'normal-geometry independent hidden-register guarantee.',flush=True)
        r['inlet']['immutable_reference']();return
    cases=[('integer',[],'007012345678',None),
           ('negative',['--negative'],'007987654321',None),
           ('small',['--small'],'950012345678',None),
           ('no-enter',['--no-enter'],'007012345678','no_enter'),
           ('no-swap',['--no-swap'],'007012345678','no_swap')]
    requested=next((flag for flag in ['integer','negative','small','no-enter','no-swap'] if '--'+flag+'-only' in sys.argv),None)
    if requested:cases=[c for c in cases if c[0]==requested]
    for case in cases:run_case(*case,full_prefix='--with-prefix' in sys.argv)
    print('Ordinary payloads no longer need header6 decoding; header6 is disposable '
        'preparation only. Source-directed two-STOP relocated-stack storage, not '
        'a global protocol for every value or for unrelated user program/oldMs. '
        'No emulator state load, ROM/core edits, hardware/browser or112STEP change.',flush=True)


if __name__=='__main__':run()
