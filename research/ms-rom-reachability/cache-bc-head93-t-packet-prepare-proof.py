#!/usr/bin/env python3
"""Native P8/Y marker preparation, no imported machine state or ROM edits.

Fresh fixed public keys and full observer-free native mirrors; strict ALL5
replay is continuous inside each explicitly separate recorded window only.
The symbolic four-word contract is detached/local, not an arbitrary-bank
keyboard constructor. P10 contains one normal fixture, not eight-word K1.
"""
from pathlib import Path
import json
import runpy
import subprocess
import sys

from z3 import And, BitVec

root=Path(__file__).resolve().parent
prior=runpy.run_path(str(root/'cache-bc-head93-p9-controller-cleanup-proof.py'))
r,w,q=(prior[n] for n in ('r','w','q'))
raw,stage,replay,period,preserved_number=(prior[n] for n in
    ('raw','stage','replay_periods','period','preserved_number'))
F,ZERO,NUMBER=(prior[n] for n in ('F','ZERO','NUMBER'))


def native(negative=False):
    args=['--old-y-address'] if negative else ['--shift-y']
    data=json.loads(subprocess.check_output(['node',str(root/
        'cache-bc-head93-t-packet-prepare-native.cjs'),'--proof-input',*args],text=True))
    report=data['report']
    assert report['minimal'] and report['onlyPublicKeys'] and report['ALL5mirror']
    assert data['extraMarkerPrepared']['registers'][12]==F
    stored=stage(data,'plain-storage-idle')
    assert stored['markers']==['Q'] and stored['words']['Ms:P10']==NUMBER
    assert stored['registers'][6]==ZERO and stored['registers'][12]==F
    backup=stage(data,'restore-backupE')
    assert backup['registers'][14]==NUMBER and backup['registers'][13]==ZERO
    assert stage(data,'packet-seed8')['registers'][8]==F
    p8=stage(data,'packet-move-q2-A')
    assert p8['markers']==['Z','U','Ms:P8','aux1']
    opened=stage(data,'packet-open-y')
    assert opened['markers']==['X','Z','U','Ms:P8','aux0']
    last=stage(data,'packet-shift-y-old-address' if negative else 'packet-shift-y')
    final=stage(data,'packet-idle')
    assert last['words']==final['words'] and last['registers']==final['registers']
    assert last['program']==final['program']==backup['program']
    assert final['registers']==p8['registers']
    assert final['ip']==0x35 and final['pc']=='06'
    assert final['markers']==(['X','Z','U','Ms:P9','aux0'] if negative else
                             ['Y','U','Ms:P8','aux1'])
    assert final['words']['Ms:P10']==NUMBER
    audit=report['packetAudit']
    assert audit['checkedWords']==157920 and audit['numberHeld']
    assert audit['firstDifference'] is None
    assert len(audit['stageCounts'])==10 and audit['stageCounts']['packet-idle']==6720
    period(data['windows']['packet-idle'],'packet/'+('old-D' if negative else 'Y'))
    for name,records in data['windows'].items():
        if name.startswith('packet-'):preserved_number(records,data['cells'])
    return data


def quadruple(records,label):
    start=next(i for i,v in enumerate(records) if v['ip']==0xE7
               and i+3<len(records) and [x['ip'] for x in records[i:i+4]]==[0xE7,0xA8,0xA8,0xA8])
    frames=records[start:start+4]
    a=r['concrete_primary'](frames[0]['fullBefore']['ik1302'])
    injected=[BitVec(label+'_A'+str(j),4) for j in range(12)]
    oldwords=[[BitVec(label+'_old'+str(i)+'_'+str(j),4) for j in range(12)]
              for i in range(4)]
    for j in range(12):a.r[3*j]=injected[j];a.m[1+3*j]=oldwords[0][j]
    p=w['base'](a,0xE7)
    for i,v in enumerate(frames):
        w['prove'](p,w['ip'](a)==v['ip'],label+' forced IP',False)
        incoming=[q['N4'](n) for n in v['fullAfter']['ik1302']['m']]
        if i<3:
            for j in range(12):incoming[1+3*j]=oldwords[i+1][j]
        before=a;out=[]
        a=w['ex'](a,v['ip'],*q['arbitrary_keys'](label+'_keys'+str(i)),
                  serial_inputs=incoming,emitted_outputs=out)
        wanted=injected if i==0 else oldwords[i-1]
        w['prove'](p,And(*[out[1+3*j]==wanted[j] for j in range(12)],
            *[out[j]==before.m[j] for j in range(42) if j%3!=1 or j>=37]),
            label+' exact arbitrary A/old0/old1/old2, other lanes/services held',False)
    w['prove'](p,And(*[a.r[3*j]==oldwords[3][j] for j in range(12)]),
               label+' fourth old word captured in A, not RAM',False)
    print('PASS CONDITIONAL LOCAL',label,'arbitrary five numeric words, '
          'observed control/serial calendar only;',
          'owners',[v['numericOwner'] for v in frames],flush=True)
    return frames


def check_sources(data,negative=False):
    expected={
        'packet-plant-u':('register:R8',['Ms:U','Ms:V','Ms:W','Ms:Q']),
        'packet-insert-q-ack':('register:RC',['Ms:Q','Ms:P7','Ms:P8','Ms:P9']),
        'packet-move-q1-ack':('register:RB',['Ms:Q','Ms:P7','Ms:P8','Ms:P9']),
        'packet-move-q2-A':('register:RB',['Ms:Q','Ms:P7','Ms:P8','Ms:P9']),
        'packet-open-y':('register:R3',['unclassified:aux0','unclassified:aux1','stack:X','stack:Y']),
        ('packet-shift-y-old-address' if negative else 'packet-shift-y'):
            (('register:RD',['Ms:Q','Ms:P7','Ms:P8','Ms:P9']) if negative else
             ('register:R2',['unclassified:aux0','unclassified:aux1','stack:X','stack:Y']))}
    for name,(source,owners) in expected.items():
        records=data['windows'][name]
        d6=[v for v in records if v['ip']==0xD6]
        assert len(d6)==1 and d6[0]['ordinaryOwner']==[source],(name,d6)
        if name not in ('packet-plant-u','packet-insert-q-ack','packet-open-y'):
            assert raw(d6[0]['fullBefore']['ik1302']['m'][0:36:3])==ZERO
        frames=quadruple(records,name+('_negative' if negative else ''))
        assert [v['numericOwner'] for v in frames]==[[s] for s in owners]
    p8=data['windows']['packet-move-q2-A']
    assert p8[0]['ip']==0x9C and p8[1]['ip']==0x9D
    assert any(v['ip']==0x9E for v in p8),'first reject is not whole-command failure'
    for name in ('packet-insert-q','packet-move-q1'):
        records=data['windows'][name]
        assert records[0]['ip']==0x9C and records[1]['ip']==0x9D
        assert not any(v['ip']==0xD6 for v in records)
        print('PASS NATIVE fixed header primer',name,'words',len(records),flush=True)
    selected=data['windows']['packet-shift-y-old-address' if negative else 'packet-shift-y']
    assert next(v for v in selected if v['ip']==1)['numericOwner']==['Ms:P10']
    assert [v for v in selected if v['ip']==1][-1]['numericOwner']==['unclassified:aux0']
    print('PASS NATIVE actual01 root aux0: corrected operand2 reads realR2/0; '
          'oldD reads realRD/0 but targets Q..P9, losing P8 instead of moving X/F toY.',flush=True)


def run():
    r['inlet']['immutable_reference']()
    data=native();check_sources(data)
    selected=['restore-marker-C-store','restore-backupE']+[
        n for n in data['windows'] if n.startswith('packet-')]
    covered=direct=skipped=count=0
    if '--contracts-only' not in sys.argv:
        for name in selected:
            records=data['windows'][name]
            a,b=replay(records,'packet/Y/'+name)
            covered+=len(records);direct+=a;skipped+=b;count+=1
    print('PASS NATIVE P8/Y preparation;157920 whole native words/P10 held; '
          'all ordinary registers/program held after selected seed/backup. '
          'U/aux1 still present; no normal exit/full K1/K2.',flush=True)
    if '--positive-only' not in sys.argv:
        bad=native(True);check_sources(bad,True)
        if '--contracts-only' not in sys.argv:
            for name in ('packet-shift-y-old-address','packet-idle'):
                records=bad['windows'][name]
                a,b=replay(records,'packet/old-D/'+name)
                covered+=len(records);direct+=a;skipped+=b;count+=1
        print('PASS NATIVE old-address negative:157920 words/P10 held, Y/F NOT constructed.',flush=True)
    if '--contracts-only' not in sys.argv:
        assert covered==direct+skipped
        print('PASS TOTAL',covered,'words in',count,'SEPARATE ALL5 windows;',
              'direct',direct,'exact fixed-pin skips',skipped,
              'not all native lead/key waits or historical prefix.',flush=True)
    r['inlet']['immutable_reference']()


if __name__=='__main__':run()
