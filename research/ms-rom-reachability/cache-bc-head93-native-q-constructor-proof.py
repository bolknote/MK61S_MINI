#!/usr/bin/env python3
"""Native exact Q/F constructor via original read/push microcode.

References receive public keys only; observations never repair the replay.
Q is real, but additional T/V markers and missing0/2/D/data/phase still
prevent declaring a usable K2 entry. No live experiment or state import.
"""
from pathlib import Path
import runpy

from z3 import And, If

root=Path(__file__).resolve().parent
reader=runpy.run_path(str(root/'cache-bc-head93-native-f-reader-proof.py'))
all5,r,w,q,engine=(reader[n] for n in ('all5','r','w','q','engine'))
raw=reader['raw']


def seek_contracts():
    a=q['State']('Q_constructor_seek01');p=w['base'](a,1)
    b=w['ex'](a,1,*q['arbitrary_keys']('Q_constructor_seek01keys'))
    w['prove'](p,And(w['ip'](b)==If(a.m[22]==15,q['BitVecVal'](2,8),
        q['BitVecVal'](1,8)),b.r[29]==0),
        '01 seeks numericM2[22]=F and resetsR29 exactly')
    a=q['State']('Q_constructor_seek02');p=w['base'](a,2)
    b=w['ex'](a,2,*q['arbitrary_keys']('Q_constructor_seek02keys'))
    w['prove'](p,And(w['ip'](b)==If(a.r[29]==a.r[32],q['BitVecVal'](3,8),
        q['BitVecVal'](2,8)),b.r[29]==a.r[29]+1),
        '02 exact equality counter, not a free absolute-register index')
    print('PASS startingR29=0 and operand n=0..14 gives n+1 consecutive02 words, '
          'then five03/04/BA/CB/DD words beforeD6; physical destination is relative '
          'to the marker reached by the ACTUAL preceding01 scan.',flush=True)


def run():
    r['inlet']['immutable_reference']()
    native=reader['native']('--q-whole-proof-input')
    exact='0000F0000000';zero='000000000000'
    assert native['after']['R9']==exact
    assert native['reread']['words']['W']==exact
    assert native['lastX']['words']['Z']==native['lastX']['words']['W']==exact
    assert native['realRemoved']['words']['T']==native['realRemoved']['words']['W']==exact
    final=native['qLifted'];stable=native['qStable']
    assert final['words']['Q']==stable['words']['Q']==exact
    assert [final['words'][n] for n in ('T','V','Q')]==[exact]*3
    assert final['words']['W']==zero
    assert final['words']['aux0']=='000FFFFFFFFF'
    assert final['ST2']==[0,0,0] and final['modeR2']==8
    for label in ('read','cleared','reread','lastX','realRemoved','qLifted','qStable'):
        assert native[label]['registers']==native['after']['registers']
        assert native[label]['program']==native['after']['program']
    expected={'stop':91,'store':136,'read':6,'read-after-clear':9,'lastx-lift':14,
        'clear-real':4,'marker-read9':108,'q-idle':30}
    assert set(native['windows'])==set(expected)
    count=0
    for label,length in expected.items():
        records=native['windows'][label];assert len(records)==length
        count+=reader['replay'](records,'Q/'+label)
    assert count==398
    records=native['windows']['marker-read9']
    seek=next(v for v in records if v['ip']==1 and v['numericOwner']==['unclassified:aux0'])
    assert seek['fullBefore']['ik1302']['m'][22]==15
    counters=[v for v in records if v['ip']==2]
    assert len(counters)==10
    assert [v['fullBefore']['ik1302']['r'][29] for v in counters]==list(range(10))
    assert all(v['fullBefore']['ik1302']['r'][32]==9 for v in counters)
    assert counters[0]['numericOwner']==['unclassified:aux1']
    d6=next(v for v in records if v['ip']==0xD6)
    assert d6['ordinaryOwner']==['register:R9']
    assert raw(d6['fullAfter']['ik1302']['r'][0:36:3])==exact
    push=[v for v in records if v['ip'] in (0xE7,0xA8)]
    assert [(v['ip'],v['numericOwner']) for v in push]==[
        (0xE7,['Ms:V']),(0xA8,['Ms:W']),(0xA8,['Ms:Q']),(0xA8,['Ms:P7']),
        (0xE7,['Ms:P9'])]
    assert [raw(v['emitted'][1:36:3]) for v in push]==[exact,zero,exact,zero,zero]
    assert records[0]['word']==108668 and records[-1]['word']==108775
    assert records[-1]['ip']==0xBE
    assert not any(v['ip'] in (0xBB,0xBC,0xC7) for v in records)
    for v in records:
        if v['ip'] not in (0xE7,0xA8):
            assert v['emitted']==v['fullBefore']['ik1302']['m']
        else:
            assert all(v['emitted'][j]==v['fullBefore']['ik1302']['m'][j]
                for j in range(42) if j%3!=1 or j>=37)
    print('PASS native108-word continuous01→02×10→D6/R9→E7/V→A8/W,Q,P7 '
          'then original formatter/zeroE7(P9)/BE; '
          'Q gets OLD W, while new R9 goes to V. This is a real numeric12 '
          'writer/push, not BC or a restored complete exchange.',flush=True)
    idle=native['windows']['q-idle']
    same=idle[-1]['fullAfter']==idle[0]['fullBefore'] and idle[-1]['tagsAfter']==idle[0]['tagsBefore']
    print('PASS Q held after an additional12 released-key native frames; '
          'first30-word completeALL5 state/tag cycle='+str(same)+'.',flush=True)
    assert same,'the complete released-input idle period must match exactly'
    assert all(all5['pins'](v)==all5['pins'](idle[0]) for v in idle)
    print('PASS exact fixed-input30-word whole-core period: Q/T/V/aux0 held '
          'under this unchanged released-key input. NOT a healthy arbitrary-command contract.',flush=True)
    seek_contracts()
    r['inlet']['immutable_reference']()
    print('PASS398 native ALL5 transitions in EIGHT SEPARATE windows; includes previous227 '
          'F-constructor and33 common transport words, NOT398+227+37. '
          'Fresh observer-free mirrors at all actions; six sources unchanged. '
          'NativeQ now exists, but extraT/V, old-Ms preservation, prepared0/2/D '
          'entry/data/phase, cleanup and inversion are NOT established.',flush=True)


if __name__=='__main__':run()
