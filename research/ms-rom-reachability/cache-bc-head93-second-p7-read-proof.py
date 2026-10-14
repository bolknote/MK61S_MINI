#!/usr/bin/env python3
"""Physical P7 read after real ordinary math, both Ms originals retained.

Fresh reference/mirror, no ordinary source copies, original ALL5 windows.
No claim of P10 re-read, repeated cycle or full eight-word/programme K1/K2.
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
    data=json.loads(subprocess.check_output(['node',str(root/'cache-bc-head93-second-p7-read-native.cjs'),
        '--proof-input'],text=True))
    assert data['report']['onlyPublicKeys'] and data['report']['ALL5mirror']
    start=stage(data,'packet-normal-preclear4');before=stage(data,'packet-p7-read-front3');final=stage(data,'packet-idle')
    assert stage(data,'packet-normal-plus')['display']=='5,'
    assert FIRST not in start['registers'] and SECOND not in start['registers']
    assert FIRST not in before['registers'] and SECOND not in before['registers']
    assert start['words']['Ms:P7']==before['words']['Ms:P7']==SECOND
    assert start['words']['Ms:P10']==before['words']['Ms:P10']==FIRST
    assert before['markers']==['V','aux0']
    records=data['windows']['packet-p7-read-output']
    assert not any(v['ip']==0xD6 for v in records),'no ordinary source/reserve read'
    source=next(v for v in records if v['ip']==0xEE)
    assert source['numericOwner']==['Ms:P7']
    assert raw(source['fullBefore']['ik1302']['m'][1:36:3])==SECOND
    assert raw(source['fullAfter']['ik1302']['r'][0:36:3])==SECOND
    num['copy_contract'](source,'ik1302',0xEE,True,'post_math_physical_P7_reader')
    saved=next(v for v in records if v['ip']==0xD4)
    assert saved['ordinaryOwner']==['register:R6']
    prior['ordinary_latched_copy'](saved,'post_math_SECOND_R6_output',SECOND)
    writers=[v for v in records if v['ip'] in (0xE7,0xA8,0xE9)]
    assert len(writers)==1 and writers[0]['numericOwner']==['stack:Y']
    assert raw(writers[0]['emitted'][1:36:3])==SECOND
    num['copy_contract'](writers[0],'ik1302',0xE7,False,'post_math_P7_to_visible_Y')
    assert final['display']=='24681357,' and final['registers'][6]==SECOND
    assert final['words']['Ms:P7']==SECOND and final['words']['Ms:P10']==FIRST
    assert final['program']==start['program']
    expected=before['registers'].copy();expected[6]=SECOND
    assert final['registers']==expected
    for key in ('packetAudit','secondSlotAudit','secondRelocationAudit'):
        assert data['report'][key]['numberHeld'] and data['report'][key]['firstDifference'] is None
    period(data['windows']['packet-idle'],'post-math-P7-read-both-held')
    print('PASS NATIVE after normal2+3=5, actual physicalP7/24681357 -> realR6/display; '
        'all ordinary source copies erased before math. Late E7 writes visibleY, '
        'NOT P7; P7/P10 and program105 held. P10 re-read/repeat/full K1/K2 remain.',flush=True)
    if '--contracts-only' not in sys.argv:
        labels=[*['packet-p7-read-F'+str(i) for i in range(1,5)],
            'packet-p7-read-U','packet-p7-read-V','packet-p7-read-clearY',
            *['packet-p7-read-front'+str(i) for i in range(1,4)],
            'packet-p7-read-output','packet-idle']
        direct=skipped=0
        for label in labels:
            x,y=replay(data['windows'][label],'p7-read/'+label);direct+=x;skipped+=y
        print('PASS TOTAL',direct+skipped,'originalALL5 words/',len(labels),
            'separate continuous windows; direct',direct,'fixed-pin skips',skipped,
            'NOT all preparation words/arbitrary bank/full K1/K2.',flush=True)
    r['inlet']['immutable_reference']()


if __name__=='__main__':run()
