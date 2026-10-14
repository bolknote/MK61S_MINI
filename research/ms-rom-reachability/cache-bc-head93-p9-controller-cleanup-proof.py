#!/usr/bin/env python3
"""Native false-P9 cleanup holding P10; NOT a restored ordinary calculator.

Only fixed public keys act on fresh stock references, with an observer-free
full mirror. Original ALL5 replay starts once per separate recorded window;
no checkpoint repairs, ROM edits or model states are sent to a reference.
Optional exact fixed-pin period skips leave the calculated model unchanged
and require every omitted native transition to match the calculated cycle.
Detached local ROM contracts are explicitly conditional, not new inlets.
"""
from pathlib import Path
import copy
import json
import runpy
import subprocess
import sys

from z3 import And, BitVec

root=Path(__file__).resolve().parent
prior=runpy.run_path(str(root/'cache-bc-head93-q-restore-proof.py'))
reader,r,w,q=(prior[n] for n in ('reader','r','w','q'))
all5=reader['all5'];engine=reader['engine'];raw=reader['raw']
stage=prior['stage'];physical_word=prior['physical_word']
preserved_number=prior['preserved_number'];period=prior['period']
F=prior['F'];ZERO=prior['ZERO'];NUMBER=prior['NUMBER']


def native(calc=False,next_zero=False,wrong_post=False,post_calc=False):
    args=['node',str(root/'cache-bc-head93-p9-controller-cleanup-native.cjs'),
          '--proof-input','--ack']+(['--calc'] if calc else [])
    if next_zero:args+=['--next-zero']
    if wrong_post:args+=['--wrong-post-source']
    if post_calc:args+=['--post-calc']
    data=json.loads(subprocess.check_output(args,text=True))
    report=data['report']
    assert report['minimal'] and report['onlyPublicKeys'] and report['ALL5mirror']
    assert report['qControllerZeroDigit']=='A' and report['qControllerAck']
    assert report['qControllerClearDigit']=='5' and report['qRestoreControl']=='noP9'
    assert data['markerPrepared']['registers'][3]==F
    return data


def replay_periods(records,label):
    """Strict ALL5 plus exact constant-input cycle induction, no state repair."""
    assert records and all(v['word']==records[0]['word']+i for i,v in enumerate(records))
    first=records[0]
    # make() uses command only for a modulo-six phase check and unused dummy
    # tags. Keep the actual snapshot/phase untouched; copy the actual passive
    # carrier identities once, rather than rotating discarded dummy tags for
    # hundreds of thousands of earlier words.
    state,_,phase=engine['make']({'state':first['fullBefore'],
                                'command':first['word']%6})
    tags={name:list(first['tagsBefore'][name]) for name in engine['names']}
    seen={}
    i=calculated=skipped=0;cycles=[]
    fields=('ip','fullBefore','fullAfter','tagsBefore','tagsAfter',
            'keysX','keysY','emitted','ordinaryOwner','numericOwner')
    while i<len(records):
        v=records[i]
        all5['compare'](state,tags,phase,v['fullBefore'],v['tagsBefore'])
        assert engine['boundary_ip'](state['ik1302'])==v['ip']
        pins=all5['pins'](v)
        # This snapshot already equals the CALCULATED state, including all
        # 630 cells/tags, 3 controllers/scalars, wires and exact IR phase.
        # Its key pins are also part of the signature and the guard below.
        signature=json.dumps([v['fullBefore'],v['tagsBefore']],sort_keys=True,
                             separators=(',',':'))
        previous=seen.get(signature)
        if previous is not None:
            length=i-previous
            fixed=all(all5['pins'](x)==pins for x in records[previous:i])
            count=0
            while fixed and i+(count+1)*length<=len(records):
                block=records[i+count*length:i+(count+1)*length]
                baseline=records[previous:i]
                if not all(all(a[f]==b[f] for f in fields)
                           for a,b in zip(block,baseline)):
                    break
                count+=1
            if count:
                advance=count*length
                # A complete calculated fixed-input cycle returned to this
                # identical state. Repeating it leaves the model unchanged;
                # omitted native states/outputs/pins equal the proved cycle.
                skipped+=advance;i+=advance
                all5['compare'](state,tags,phase,records[i-1]['fullAfter'],
                               records[i-1]['tagsAfter'])
                cycles.append((length,count,advance));seen.clear();continue
        seen[signature]=i
        phase,outputs=engine['step'](state,tags,phase,pins)
        assert [all5['number'](x) for x in outputs['ik1302']]==v['emitted']
        all5['reduce_calculated'](state)
        all5['compare'](state,tags,phase,v['fullAfter'],v['tagsAfter'])
        calculated+=1;i+=1
    assert calculated+skipped==len(records)
    print('PASS',label,'covered',len(records),'original ALL5 words;',
          'direct',calculated,'exact fixed-pin period skips',skipped,
          'cycles',cycles,flush=True)
    return calculated,skipped


def four_word_contract(records,label):
    assert [v['ip'] for v in records]==[0xE7,0xA8,0xA8,0xA8]
    a=r['concrete_primary'](records[0]['fullBefore']['ik1302'])
    assert raw(records[0]['fullBefore']['ik1302']['r'][0:36:3])==ZERO
    data=[[BitVec(label+'_old'+str(i)+'_'+str(j),4) for j in range(12)]
          for i in range(4)]
    for j in range(12):a.m[1+3*j]=data[0][j]
    p=w['base'](a,0xE7)
    for i,v in enumerate(records):
        w['prove'](p,w['ip'](a)==v['ip'],label+' next IP',False)
        incoming=[q['N4'](x) for x in v['fullAfter']['ik1302']['m']]
        if i<3:
            for j in range(12):incoming[1+3*j]=data[i+1][j]
        old=a;out=[]
        a=w['ex'](a,v['ip'],*q['arbitrary_keys'](label+'_keys'+str(i)),
                  serial_inputs=incoming,emitted_outputs=out)
        wanted=[q['N4'](0)]*12 if i==0 else data[i-1]
        w['prove'](p,And(*[out[1+3*j]==wanted[j] for j in range(12)],
            *[out[j]==old.m[j] for j in range(42) if j%3!=1 or j>=37]),
            label+' numeric12 shift; all other lanes/services held',False)
    w['prove'](p,And(*[a.r[3*j]==data[3][j] for j in range(12)]),
               label+' fourth old word captured in A, not RAM',False)
    print('PASS CONDITIONAL LOCAL',label,'0/old0/old1/old2; old3 goes to A; '
          'all16^12 old words, observed control/serial calendar only.',flush=True)


def control_contract(records,label,marker_owner,destination):
    before,write=records[-2:]
    assert before['ip']==0xA2 and before['numericOwner']==[marker_owner]
    assert before['fullBefore']['ik1302']['m'][22]==15
    assert write['ip']==0xA3 and write['numericOwner']==[destination]
    source=write['fullBefore']['ik1302'];assert source['r'][27:36:3]==[15]*3
    assert all(write['emitted'][j]==source['m'][j] for j in range(42)
               if j not in (28,31,34))
    a=r['concrete_primary'](source)
    lower=[BitVec(label+'_lower'+str(j),4) for j in range(9)]
    for j,x in enumerate(lower):a.m[1+3*j]=x
    p=w['base'](a,0xA3);out=[]
    w['ex'](a,0xA3,write['keysX'],write['keysY'],
        serial_inputs=[q['N4'](n) for n in write['fullAfter']['ik1302']['m']],
        emitted_outputs=out)
    w['prove'](p,And(*[out[1+3*j]==lower[j] for j in range(9)],
        *[out[j]==15 for j in (28,31,34)],
        *[out[j]==a.m[j] for j in range(42) if j not in (28,31,34)]),
        label+' conditional A3 only writes FFF control header')
    a=q['State'](label+'_arbitrary_A2');p=w['base'](a,0xA2);p.add(a.m[22]==15)
    out=[];b=w['ex'](a,0xA2,*q['arbitrary_keys'](label+'_A2_keys'),emitted_outputs=out)
    w['prove'](p,And(w['ip'](b)==0xA3,*[out[j]==a.m[j] for j in range(42)]),
               label+' universal A2/M22F -> A3, no outgoing writes')
    print('OBSERVED',label,before['word'],marker_owner,'A2 ->',write['word'],
          destination,'A3/FFF; does not imply normal arithmetic.',flush=True)


def check(data,calc=False):
    stored=stage(data,'plain-storage-idle');assert stored['markers']==['Q']
    assert stored['words']['Ms:P10']==NUMBER and stored['registers'][6]==ZERO
    clear=stage(data,'restore-P9-clear');idle=stage(data,'restore-idle')
    assert clear['words']==idle['words'] and clear['registers']==idle['registers']
    assert clear['words']['Q']==clear['words']['Ms:P9']==ZERO
    assert clear['words']['Ms:P10']==NUMBER
    assert clear['markers']==['Z','U','aux1'] and clear['words']['aux0']==ZERO
    assert clear['words']['T']==clear['words']['Ms:P8']=='FFF000000000'
    assert clear['words']['Ms:P7']==ZERO
    assert clear['registers'][3]==clear['registers'][9]==F
    assert clear['registers'][13]==NUMBER and clear['registers'][8]==ZERO
    for s in data['exitStages']:
        if s['name'].startswith('restore-') and s['name'] not in (
                'restore-readF1','restore-readF2','restore-lastx','restore-backupD'):
            assert s['words']['Ms:P10']==NUMBER,s['name']
        if s['name'].startswith('restore-'):
            assert s['program']==stored['program'],s['name']
    window=data['windows']['restore-wipeQ-zero8']
    source=next(v for v in window if v['ip']==0xD6)
    assert source['ordinaryOwner']==['register:R8']
    assert raw(source['fullAfter']['ik1302']['r'][0:36:3])==ZERO
    assert [v for v in window if v['ip']==1][-1]['numericOwner']==['Ms:P9']
    window=data['windows']['restore-U-marker-ack']
    source=next(v for v in window if v['ip']==0xD6)
    assert source['ordinaryOwner']==['register:R9']
    assert raw(source['fullAfter']['ik1302']['r'][0:36:3])==F
    window=data['windows']['restore-P9-clear']
    assert len(window)==121 and window[0]['word']==612661 and window[-1]['word']==612781
    source=next(v for v in window if v['ip']==0xD6)
    assert source['ordinaryOwner']==['register:RC']
    assert raw(source['fullAfter']['ik1302']['r'][0:36:3])==ZERO
    assert [v for v in window if v['ip']==1][-1]['numericOwner']==['Ms:U']
    writes=[v for v in window if v['ip'] in (0xE7,0xA8)]
    assert [v['numericOwner'] for v in writes]==[
        ['Ms:Q'],['Ms:P7'],['Ms:P8'],['Ms:P9'],['stack:Z']]
    assert [raw(v['emitted'][1:36:3]) for v in writes]==[
        ZERO,ZERO,'FFF000000000',ZERO,F]
    assert raw(writes[3]['fullBefore']['ik1302']['m'][1:36:3])==F
    for name,records in data['windows'].items():
        if name.startswith('restore-') and name not in (
                'restore-marker-store','restore-readF1','restore-readF2',
                'restore-lastx','restore-backupD','restore-eraseQ'):
            preserved_number(records,data['cells'])
    j=window.index(writes[0]);four_word_contract(window[j:j+4],'clearP9_Q_P7_P8_P9')
    control_contract(data['windows']['restore-U-marker'],'primeZ_T','stack:Z','stack:T')
    if calc:
        audit=data['report']['calcAudit']
        assert audit['checkedWords']==42000 and audit['numberHeld']
        assert list(audit['stageCounts'].values())==[8400]*5
        assert stage(data,'restore-test-plus')['display']=='ЕГГ0Г'
        control_contract(data['windows']['restore-test-cx'],'CX_U_V','Ms:U','Ms:V')
        print('PASS NATIVE/MIRRORED 42000 diagnostic words: before/after each word '
              'P10 full12 held; CX/2/ENTER/3/+ still errors, not5.',flush=True)


def check_next(data,wrong_post=False,post_calc=False):
    before=stage(data,'restore-test-cx');final=stage(data,'restore-next-idle')
    assert before['words']['V']=='FFF000000000'
    assert final['words']['Ms:P10']==NUMBER
    assert final['words']['Q']==final['words']['Ms:P9']==ZERO
    assert final['registers']==before['registers']
    window=data['windows']['restore-zero-after-cx']
    source=next(v for v in window if v['ip']==0xD6)
    assert [v for v in window if v['ip']==1][-1]['numericOwner']==['unclassified:aux1']
    writes=[v for v in window if v['ip'] in (0xE7,0xA8)]
    if wrong_post:
        assert source['ordinaryOwner']==['register:R9']
        assert final['markers']==['Z','U','V','aux1']
        assert len(window)==133
        assert [v['numericOwner'] for v in writes]==[
            ['Ms:U'],['Ms:V'],['Ms:W'],['Ms:Q'],['stack:Z']]
        assert [raw(v['emitted'][1:36:3]) for v in writes]==[
            F,F,'FFF000000000',ZERO,F]
        print('PASS NEGATIVE old logical8 now reads realR9/F, not R0; '
              'U persists and V/F is added. Relative source must follow actual01.',flush=True)
    else:
        assert source['ordinaryOwner']==['register:R0']
        assert final['markers']==['T','aux1']
        assert final['words']['Z']==final['words']['U']==ZERO
        assert final['words']['T']==F and final['words']['X1']=='FFF000000000'
        assert final['display']=='0,'
        assert len(window)==148 and window[0]['word']==644584 and window[-1]['word']==644731
        assert [v['numericOwner'] for v in writes]==[
            ['stack:Z'],['stack:T'],['stack:X1'],['Ms:U'],['stack:Z']]
        assert [raw(v['emitted'][1:36:3]) for v in writes]==[
            ZERO,F,'FFF000000000',ZERO,ZERO]
        j=window.index(writes[0]);four_word_contract(window[j:j+4],'clearU_Z_T_X1_U')
        print('PASS NATIVE realR0 zero through logicalE removes Z/U, moves oldZ/F '
              'toT/F; late formatter writes zero/Z, not F. P10 held.',flush=True)
    preserved_number(window,data['cells'])
    period(data['windows']['restore-next-idle'],'post-CX '+('wrong8' if wrong_post else 'zeroE'))
    if post_calc:
        audit=data['report']['postCalcAudit']
        assert audit['checkedWords']==42000 and audit['numberHeld']
        assert audit['firstDifference'] is None
        assert stage(data,'restore-post-plus')['display']=='ЕГГ0Г'
        print('POST-EXIT NATIVE arithmetic',stage(data,'restore-post-plus')['display'],
              'P10 audit',audit,flush=True)


def period_self_test(data):
    """Synthetic replay-oracle test, NOT additional observed native words."""
    baseline=data['windows']['restore-idle'];period(baseline,'period self-test inlet')
    records=[]
    for k in range(3):
        for observed in baseline:
            v=copy.deepcopy(observed);v['word']+=30*k;records.append(v)
    direct,skipped=replay_periods(records,'SYNTHETIC triple fixed-pin idle')
    assert (direct,skipped)==(30,60),(direct,skipped)
    corrupted=copy.deepcopy(records);corrupted[75]['emitted'][0]^=1
    try:
        replay_periods(corrupted,'SYNTHETIC wrong outgoing in skipped candidate')
    except AssertionError:
        print('PASS replay-oracle self-test: corrupted outgoing in a candidate '
              'period is rejected, never silently skipped. Synthetic copied '
              'observations only; no emulator/model state edits.',flush=True)
    else:
        raise AssertionError('period verifier accepted corrupted observations')


def run():
    r['inlet']['immutable_reference']()
    calc='--calc' in sys.argv or '--calc-only' in sys.argv
    next_zero='--next-zero-only' in sys.argv
    wrong_post='--wrong-post-source' in sys.argv
    post_calc='--post-calc' in sys.argv
    data=native(calc,next_zero,wrong_post,post_calc);check(data,calc)
    if next_zero:check_next(data,wrong_post,post_calc)
    if '--period-self-test' in sys.argv:
        period_self_test(data);r['inlet']['immutable_reference']();return
    if '--contracts-only' not in sys.argv:
        selected={name:v for name,v in data['windows'].items()
            if (name in ('restore-zero-after-cx','restore-next-idle') if next_zero else
                name.startswith('restore-test-') if '--calc-only' in sys.argv else
                name.startswith('restore-') or '--with-prefix' in sys.argv)}
        direct=skipped=0
        for name,records in selected.items():
            a,b=replay_periods(records,'P9-cleanup/'+name);direct+=a;skipped+=b
        print('PASS TOTAL covered',direct+skipped,'in',len(selected),
              'SEPARATE windows; direct original ALL5',direct,
              'exact fixed-pin period skips',skipped,flush=True)
        expected=(163 if wrong_post else 178) if next_zero else (
            3355 if '--calc-only' in sys.argv else
            (5029 if '--with-prefix' in sys.argv else 2747)+(3355 if calc else 0))
        assert direct+skipped==expected,(direct,skipped,expected)
        assert len(selected)==(2 if next_zero else 5 if '--calc-only' in sys.argv else
                              (43 if '--with-prefix' in sys.argv else 14)+(5 if calc else 0))
        if '--calc-only' not in sys.argv and not next_zero:
            period(data['windows']['restore-idle'],'Q/P9 erased, P10 held')
    markers='Z/U/V/aux1' if wrong_post else 'T/aux1' if next_zero else 'Z/U/aux1'
    print('BOUNDARY: falseQ/P9 removed while P10=12345678 survives; '+
          markers+' markers, aux0=0 and shifted controls remain. '
          'Not independent extra memory, restored ordinary arithmetic or fullK1/K2.',flush=True)
    r['inlet']['immutable_reference']()


if __name__=='__main__':run()
