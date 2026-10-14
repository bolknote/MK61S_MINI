#!/usr/bin/env python3
"""Repeated return/math/read-both without re-entering either payload.

Exact full idle endpoint comparison is a separate assertion from output
equality. Separate ALL5 windows; never claim all arbitrary operations/data.
"""
from pathlib import Path
import json
import runpy
import subprocess
import sys

root=Path(__file__).resolve().parent
prior=runpy.run_path(str(root/'cache-bc-head93-second-shift-proof.py'))
num=prior['num'];r=num['r']
raw,stage,replay,period=(num[n] for n in ('raw','stage','replay','period'))
FIRST='007012345678';SECOND='007024681357'


def run():
    r['inlet']['immutable_reference']()
    data=json.loads(subprocess.check_output(['node',str(root/'cache-bc-head93-second-p7-repeat-native.cjs'),
        '--proof-input'],text=True))
    assert data['report']['onlyPublicKeys'] and data['report']['ALL5mirror']
    for name in ('packetAudit','secondSlotAudit','secondRelocationAudit'):
        assert data['report'][name]['numberHeld'] and data['report'][name]['firstDifference'] is None
    before=stage(data,'packet-p7-repeat-inlet');ready=stage(data,'packet-p7-repeat-normal-port5-zero')
    assert ready['markers']==['aux0'] and ready['registers'][5]=='000000000000'
    assert FIRST not in ready['registers'] and SECOND not in ready['registers']
    assert stage(data,'packet-p7-repeat-normal-plus')['display']=='5,'
    second=data['windows']['packet-p7-repeat-p7-read-output'];first=data['windows']['packet-p7-repeat-p7-first-read']
    for records,word,value,label in ((second,'P7',SECOND,'repeat_SECOND'),(first,'P10',FIRST,'repeat_FIRST')):
        assert not any(v['ip']==0xD6 for v in records)
        source=next(v for v in records if v['ip']==0xEE)
        assert source['numericOwner']==['Ms:'+word]
        assert raw(source['fullBefore']['ik1302']['m'][1:36:3])==value
        num['copy_contract'](source,'ik1302',0xEE,True,label+'_physical_source')
    final=stage(data,'packet-p7-repeat-idle')
    assert final['registers'][6]==SECOND and final['registers'][7]==FIRST
    assert final['words']['Ms:P7']==SECOND and final['words']['Ms:P10']==FIRST
    assert final['program']==before['program']
    a=data['nativeIdleStates']['packet-p7-repeat-inlet'];b=data['nativeIdleStates']['packet-p7-repeat-idle']
    assert a==b,'outputs repeat, but whole-core closure must also hold'
    assert data['repeatDiagnostic']['equal']
    period(data['windows']['packet-p7-repeat-inlet'],'two-number-repeat/inlet')
    period(data['windows']['packet-p7-repeat-idle'],'two-number-repeat/end')
    print('PASS NATIVE repeated BOTH physical Ms reads after clearing R6/R7 outputs '
        'and ordinary2+3=5. Full idle states/all5 fields+UI/wires/phase/630 tags '
        'equal at ends; fixed SAME schedule is closed. NOT arbitrary bank/8 words/56 steps/K1/K2.',flush=True)
    if '--contracts-only' not in sys.argv:
        labels=['packet-p7-repeat-normal-retain-shift1','packet-p7-repeat-normal-retain-shift3',
            'packet-p7-repeat-normal-retain-clearP8','packet-p7-repeat-normal-retain-X1',
            'packet-p7-repeat-normal-retain-flush1','packet-p7-repeat-normal-retain-flush4',
            'packet-p7-repeat-normal-port5-zero','packet-p7-repeat-normal-plus',
            'packet-p7-repeat-p7-read-front3','packet-p7-repeat-p7-read-output',
            'packet-p7-repeat-p7-first-P8','packet-p7-repeat-p7-first-read',
            'packet-p7-repeat-p7-first-output','packet-p7-repeat-inlet','packet-p7-repeat-idle']
        sections=[(n,data['windows'][n]) for n in labels]
        header=data['windows']['packet-p7-repeat-normal-retain-header']
        sections.extend([('header-entry',header[:12]),('header-tail',header[-12:])])
        direct=skipped=0
        for label,records in sections:
            x,y=replay(records,'p7-repeat/'+label);direct+=x;skipped+=y
        print('PASS TOTAL',direct+skipped,'originalALL5 words/',len(sections),
            'separate continuous windows/slices; direct',direct,'fixed-pin skips',skipped,
            'NOT full repeated/preparation history/full K1/K2.',flush=True)
    r['inlet']['immutable_reference']()


if __name__=='__main__':run()
