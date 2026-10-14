#!/usr/bin/env python3
"""Native Q-only numeric marker: preventV, then removeT through visible stack.

All reference work uses public keys on fresh stock ALL5 calculators. Guarded
setters, passive carrier observations and independent observer-free mirrors
are retained. Every replayed state is calculated from its predecessor; no
data/control/IP/ROM/phase hypothesis is inserted into a reference or replay.
This isolates Q, NOT a prepared0/2/D/data/phase BC input or complete K2.
"""
from pathlib import Path
import runpy
import sys

root=Path(__file__).resolve().parent
previous=runpy.run_path(str(root/'cache-bc-head93-native-q-constructor-proof.py'))
reader,all5,r,w,q=(previous[n] for n in ('reader','all5','r','w','q'))
raw=reader['raw']


def writers(records):
    return [v for v in records if v['ip'] in (0xD4,0xE7,0xA8,0xE9,0xBC,0xC7)]


def period(records,label):
    assert len(records)==30
    assert records[0]['fullBefore']==records[-1]['fullAfter']
    assert records[0]['tagsBefore']==records[-1]['tagsAfter']
    assert all(all5['pins'](v)==all5['pins'](records[0]) for v in records)
    print('PASS',label,'exact30-word whole-core fixed-input period, '
          'including all working fields/IR cells/wires/phase/630 tags; '
          'not a contract for arbitrary subsequent keys.',flush=True)


def negative_clear():
    r['inlet']['immutable_reference']()
    native=reader['native']('--q-clear-v-proof-input')
    records=native['windows']['cleanup-cx'];assert len(records)==74
    assert records[0]['ip']==0x9C and records[0]['numericOwner']==['unclassified:aux1']
    entry=records[0]['fullBefore']['ik1302']
    assert entry['r'][30]+16*entry['r'][33]==0x0D and entry['s1']==13
    assert native['cleanupStages'][0]['words']==native['qStable']['words']
    assert [(v['ip'],v['numericOwner']) for v in writers(records)]==[(0xE7,['Ms:P9'])]
    assert raw(writers(records)[0]['emitted'][1:36:3])=='000000000000'
    reader['replay'](records,'negative/nativeCx after T/V/Q')
    r['inlet']['immutable_reference']()
    print('PASS74 separate negative ALL5 words: Cx is decoded correctly as0D/S1=D, '
          'but its zero formatter reaches E5(W), stops atQ and writesP9. '
          'The three additional markers remain. Not a global no-go for Cx/other prefixes.',flush=True)


def run():
    r['inlet']['immutable_reference']()
    native=reader['native']('--q-single-proof-input')
    exact,zero='0000F0000000','000000000000'
    assert native['report']['qZeroSource'] and native['report']['qFinalIdleCheck']
    assert native['realRemoved']['words']['T']==native['realRemoved']['words']['W']==exact
    cleared=native['zeroSource']
    assert cleared['R9']==zero and cleared['words']==native['realRemoved']['words']
    assert cleared['registers']==[zero]*15
    assert cleared['program']==native['after']['program']
    formed=native['qLifted']
    assert formed['words']['T']==formed['words']['Q']==exact
    assert formed['words']['V']==formed['words']['W']==zero
    first,second=native['cleanupStages']
    assert [v['keys'] for v in (first,second)]==[['П→X','2']]*2
    assert first['words']['T']==zero and first['words']['X1']==first['words']['Q']==exact
    assert second['words']['X1']==zero
    final=native['isolatedStable']
    assert final['words']==second['words']
    assert final['markers']==['Q','aux0']
    assert final['words']['Q']==exact and final['words']['aux0']=='000FFFFFFFFF'
    for name,value in final['words'].items():
        if name not in ('Q','aux0','aux1'):assert value==zero,(name,value)
    assert final['words']['aux1']=='FFF000000000'
    assert final['ip']==0x35 and final['modeR2']==8 and final['ST2']==[0,0,0]
    for v in (formed,first,second,final):
        assert v['registers']==cleared['registers'] and v['program']==cleared['program']

    expected={'stop':91,'store':136,'read':6,'read-after-clear':9,'lastx-lift':14,
        'clear-real':4,'zero-r9-source':129,'marker-read9':108,'q-idle':30,
        'cleanup-r2-1':115,'cleanup-r2-2':119,'cleanup-idle':30}
    assert set(native['windows'])==set(expected)
    total=0
    for label,length in expected.items():
        records=native['windows'][label];assert len(records)==length,(label,len(records))
        total+=reader['replay'](records,'Q-only/'+label)
    assert total==791

    zero_records=native['windows']['zero-r9-source']
    assert [(v['ip'],v['ordinaryOwner'] if v['ip']==0xD4 else v['numericOwner'])
        for v in writers(zero_records)]==[(0xD4,['register:R9']),(0xE7,['Ms:V'])]
    d4=next(v for v in zero_records if v['ip']==0xD4)
    assert raw(d4['emitted'][0:36:3])==zero
    formation=writers(native['windows']['marker-read9'])
    assert [(v['ip'],v['numericOwner']) for v in formation]==[
        (0xE7,['Ms:V']),(0xA8,['Ms:W']),(0xA8,['Ms:Q']),
        (0xA8,['Ms:P7']),(0xE7,['Ms:P9'])]
    assert [raw(v['emitted'][1:36:3]) for v in formation]==[zero,zero,exact,zero,zero]
    print('PASS source prevention: public STORE9 clears physicalR9 while T/W are held; '
          'next READ9 writes new zero to V and OLD W/F to Q. No V/F is created.',flush=True)

    for label,later in [('cleanup-r2-1','Ms:W'),('cleanup-r2-2','Ms:P9')]:
        records=native['windows'][label]
        d6=next(v for v in records if v['ip']==0xD6)
        assert d6['ordinaryOwner']==['register:R2']
        assert raw(d6['fullAfter']['ik1302']['r'][0:36:3])==zero
        selected=writers(records)
        assert [(v['ip'],v['numericOwner']) for v in selected]==[
            (0xE7,['stack:Y']),(0xA8,['stack:Z']),(0xA8,['stack:T']),
            (0xA8,['stack:X1']),(0xE7,[later])]
        assert raw(selected[3]['emitted'][1:36:3])==(exact if label.endswith('-1') else zero)
        assert all(raw(v['emitted'][1:36:3])==zero for v in [*selected[:3],selected[-1]])
        for v in records:
            if v['ip'] not in (0xE7,0xA8):assert v['emitted']==v['fullBefore']['ik1302']['m']
            else:
                assert all(v['emitted'][j]==v['fullBefore']['ik1302']['m'][j]
                    for j in range(42) if j%3!=1 or j>=37)
    print('PASS two source-selected READ2 suffixes: real D6/P2=0; '
          'E7(Y)/A8(Z,T,X1) first carries T/F into X1, then removes it. '
          'Neither prefix writes numeric Q; later formatter writes W thenP9 zeros.',flush=True)
    period(native['windows']['q-idle'],'T/Q intermediate')
    period(native['windows']['cleanup-idle'],'isolatedQ final')
    assert not any(v['ip'] in (0xBB,0xBC,0xC7) for label,records in native['windows'].items()
        if label in ('zero-r9-source','marker-read9','cleanup-r2-1','cleanup-r2-2') for v in records)
    previous['seek_contracts']()
    r['inlet']['immutable_reference']()
    print('PASS791 native ALL5 transitions in TWELVE SEPARATE windows. '
          'Common260 prefix words include previous227 and33; never add791+398. '
          '531 words belong to the changed/new source/formation/cleanup/idle windows. '
          'Only additionalQ marker remains, R9 cleared, all15 registers nowzero, '
          'program held from after initialF store. No arbitrary-old-bank preservation, '
          'prepared0/2/D/data/phase input, nativeBC/Ms:P10 or completeK2 claim. '
          'All six immutable sources held; no live/browser test or state import.',flush=True)


if __name__=='__main__':
    if '--negative-only' in sys.argv:negative_clear()
    else:
        run()
        negative_clear()
