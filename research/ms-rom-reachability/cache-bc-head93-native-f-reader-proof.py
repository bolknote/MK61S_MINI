#!/usr/bin/env python3
"""Native raw-F readers/W constructors, not a compatible Q/K2 entry.

Fresh stock references receive public keys only. ALL5 windows are passive;
every subsequent modeled state is calculated, never repaired at checkpoints.
All action endpoints match fresh observer-free mirrors. The universal 9C
guard is a separate ROM theorem, not a successful whole keyboard route.
"""
from pathlib import Path
import json
import runpy
import subprocess

from z3 import And, BitVec, If, UGE, sat

root=Path(__file__).resolve().parent
all5=runpy.run_path(str(root/'cache-bc-head93-q-marker-all5.py'))
r,w,q,engine=(all5[n] for n in ('r','w','q','engine'))
raw=lambda values:''.join(f'{v:X}' for v in reversed(values[:12]))


def native(flag):
    result=json.loads(subprocess.check_output(['node',
        str(root/'cache-bc-head93-blank-marker-native.cjs'),flag],text=True))
    assert result['report']['minimal'] and result['report']['onlyPublicKeys']
    assert result['report']['ALL5mirror']
    return result


def replay(records,label):
    assert records and all(v['word']==records[0]['word']+i for i,v in enumerate(records))
    state,tags,phase=all5['initialize'](records[0])
    for record in records:
        all5['compare'](state,tags,phase,record['fullBefore'],record['tagsBefore'])
        assert engine['boundary_ip'](state['ik1302'])==record['ip']
        phase,outputs=engine['step'](state,tags,phase,all5['pins'](record))
        assert [all5['number'](v) for v in outputs['ik1302']]==record['emitted']
        all5['reduce_calculated'](state)
        all5['compare'](state,tags,phase,record['fullAfter'],record['tagsAfter'])
    print('PASS',label,len(records),'consecutive original ALL5 words; '
          'R/ST/M/scalars,504 IR cells,10 wires,phase/630 tags and primary42 outputs.',flush=True)
    return len(records)


def raw_reader_contract(records,label):
    """All 16^12 words at the OBSERVED local D6 context, in a separate model.

Only source M1 numeric12 is made arbitrary. Working/control fields and
future serial pages are the observed inputs, NOT a universal prefix or an
ALL5 symbolic reachability result. This model is never sent to a reference.
    """
    assert records[0]['ip']==0xD6 and records[-1]['ip']==0xE7
    a=r['concrete_primary'](records[0]['fullBefore']['ik1302'])
    data=[BitVec(label+'_raw'+str(i),4) for i in range(12)]
    for i,value in enumerate(data):a.m[3*i]=value
    p=w['base'](a,0xD6);assert p.check()==sat
    for i,record in enumerate(records):
        code=record['ip'];w['prove'](p,w['ip'](a)==code,label+' forced IP',False)
        output=[]
        incoming=[q['N4'](v) for v in record['fullAfter']['ik1302']['m']]
        a=w['ex'](a,code,*q['arbitrary_keys'](label+'_keys'+str(i)),
            serial_inputs=incoming,emitted_outputs=output)
        if code==0xE7:
            w['prove'](p,And(*[output[1+3*j]==data[j] for j in range(12)]),
                label+' arbitrary12 raw fields written verbatim',False)
        else:
            w['prove'](p,And(*[a.r[3*j]==data[j] for j in range(12)]),
                label+' all12 A fields held',False)
    print('PASS CONDITIONAL LOCAL',label,'all16^12 raw words reach E7 unchanged; '
          'observed control/serial-page premises, no constructed new prefix.',flush=True)


def guard_contract():
    a=q['State']('native_F_9C_guard');p=w['base'](a,0x9C)
    b=w['ex'](a,0x9C,*q['arbitrary_keys']('native_F_9C_guard_keys'))
    accepted=If(a.m[31]==15,UGE(a.m[34],1),UGE(a.m[34],7))
    w['prove'](p,w['ip'](b)==If(accepted,q['BitVecVal'](0x9E,8),
        q['BitVecVal'](0x9D,8)),'9C exact global accept9E/reject9D guard')
    for label,word,expected in [('bareF','0000F0000000',0x9D),
            ('logicalF','9990FFFFFFF0',0x9E)]:
        pp=w['base'](a,0x9C)
        pp.add(a.m[31]==int(word[1],16),a.m[34]==int(word[0],16))
        w['prove'](pp,w['ip'](b)==expected,'9C '+label+' header outcome')
    print('LIMIT: both words have M2[22]=F, but only the second passes9C. '
          'Marker geometry alone does not imply an accepted command origin.',flush=True)


def run():
    r['inlet']['immutable_reference']()
    main=native('--q-lift-proof-input')
    assert main['after']['R9']=='0000F0000000'
    assert main['read']['words']['X1']=='0000F0000000'
    assert main['cleared']['words']['Y']=='000000000000'
    assert main['cleared']['words']['X1']=='0000F0000000'
    assert main['reread']['words']['W']=='0000F0000000'
    assert main['lastX']['words']['Z']==main['lastX']['words']['W']=='0000F0000000'
    assert main['realRemoved']['words']['aux0']=='000FFFFFFFFF'
    assert main['qLifted']['words']['Q']=='000000000000'
    assert main['qLifted']['words']['W']=='000000000000'
    total=0
    for label,expected in [('read',6),('read-after-clear',9),('lastx-lift',14),
            ('clear-real',4),('q-lastx',4)]:
        records=main['windows'][label];assert len(records)==expected
        total+=replay(records,'bareF/'+label)
    assert total==37
    for label,destination in [('read','stack:X1'),('read-after-clear','Ms:W')]:
        records=main['windows'][label]
        assert records[0]['ordinaryOwner']==['register:R9']
        assert records[-1]['numericOwner']==[destination]
        assert raw(records[0]['fullBefore']['ik1302']['m'][0:36:3])=='0000F0000000'
        assert raw(records[-1]['emitted'][1:36:3])=='0000F0000000'
        raw_reader_contract(records,label.replace('-','_'))
    for label in ('read','cleared','reread','lastX','realRemoved','qLifted'):
        assert main[label]['registers']==main['after']['registers']
        assert main[label]['program']==main['after']['program']
    print('PASS native P9/rawF -> X1 -> W; old Z/W tail does not clear aux0 or placeQ. '
          '37 new strict ALL5 transitions exclude the previously verified227 constructor words.',flush=True)

    fifo=native('--fifo-proof-input');count=0
    for label,records in fifo['windows'].items():
        if not label.startswith('read-fifo'):continue
        assert len(records)==6
        assert records[0]['ordinaryOwner']==['register:R9']
        assert records[-1]['numericOwner']==['stack:X1']
        assert raw(records[-1]['emitted'][1:36:3])=='0000F0000000'
        count+=replay(records,'FIFO/'+label)
    assert count==24
    for stage in fifo['stages']:
        assert stage['R9']=='0000F0000000'
        assert all(stage['words'][n]=='000000000000' for n in
            ('U','V','W','Q','Ms:P7','Ms:P8','Ms:P9','Ms:P10'))
    print('PASS four native FIFO controls: rawF is read and written to X1, '
          'not normalized before E7; no hidden F at endpoints.',flush=True)

    logical=native('--logical-w-proof-input');count=0
    assert logical['report']['logical']
    assert logical['after']['R9']==logical['after']['words']['W']=='9990FFFFFFF0'
    for label,expected in [('stop',67),('store',109)]:
        records=logical['windows'][label];assert len(records)==expected
        count+=replay(records,'logicalF/'+label)
    assert count==176
    guard_contract()
    r['inlet']['immutable_reference']()
    print('PASS immutable six sources. Separate37 raw-transport /24 FIFO /176 logical-constructor '
          'ALL5 sets; no historical total inflation. W is native; compatibleQ/K2 is still missing. '
          'No live/browser experiment or emulator hypothesis/state import.',flush=True)


if __name__=='__main__':run()
