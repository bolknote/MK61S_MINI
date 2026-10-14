#!/usr/bin/env python3
"""Both physical Ms numbers recovered after real ordinary arithmetic.

The earlier ordinary inputs/output copies were erased before math. P7/P10
hold throughout. Separate strict ALL5 windows, not a full K1/K2/repeat proof.
"""
from pathlib import Path
import json
import runpy
import subprocess
import sys

root=Path(__file__).resolve().parent
prior=runpy.run_path(str(root/'cache-bc-head93-second-shift-proof.py'))
num=prior['num'];r=num['r'];prep=num['prep']
raw,stage,replay,period=(num[n] for n in ('raw','stage','replay','period'))
FIRST='007012345678';SECOND='007024681357';ZERO='000000000000';F='0000F0000000'


def run():
    r['inlet']['immutable_reference']()
    data=json.loads(subprocess.check_output(['node',str(root/'cache-bc-head93-second-p7-both-native.cjs'),
        '--proof-input'],text=True))
    assert data['report']['onlyPublicKeys'] and data['report']['ALL5mirror']
    start=stage(data,'packet-normal-preclear4');second=stage(data,'packet-p7-read-output')
    assert FIRST not in start['registers'] and SECOND not in start['registers']
    assert stage(data,'packet-normal-plus')['display']=='5,'
    assert second['registers'][6]==SECOND and FIRST not in second['registers']
    for key in ('packetAudit','secondSlotAudit','secondRelocationAudit'):
        assert data['report'][key]['numberHeld'] and data['report'][key]['firstDifference'] is None
    sections={n:v for n,v in data['windows'].items() if n.startswith('packet-p7-first-')}
    for label,records in sections.items():
        assert not any(v['ip']==0xD6 and v['ordinaryOwner']==['register:R6'] for v in records),label+' no second output reused as source'
    shapes={**{'Y'+str(i):('register:R3',F,['stack:Y','stack:Z','stack:T','stack:X1']) for i in range(1,4)},
        'P8':('register:RA',ZERO,['Ms:U','Ms:V','Ms:W','Ms:Q']),
        'Wzero1':('register:R7',ZERO,['stack:X1','Ms:U','Ms:V','Ms:W']),
        'Wzero2':('register:R7',ZERO,['stack:X1','Ms:U','Ms:V','Ms:W']),
        'aux0':('register:R3',F,['unclassified:aux0','unclassified:aux1','stack:X','stack:Y']),
        **{n:('register:R4',ZERO,['stack:Y','stack:Z','stack:T','stack:X1']) for n in ('T','X1','X1zero')},
        **{'flush'+str(i):('register:R2',ZERO,['unclassified:aux0','unclassified:aux1','stack:X','stack:Y']) for i in range(1,5)}}
    for suffix,(owner,source,targets) in shapes.items():
        records=sections['packet-p7-first-'+suffix]
        d6=next(v for v in records if v['ip']==0xD6)
        assert d6['ordinaryOwner']==[owner] and raw(d6['fullBefore']['ik1302']['m'][0:36:3])==source
        frame=prep['quadruple'](records,'post_math_first_'+suffix)
        assert [v['numericOwner'] for v in frame]==[[n] for n in targets]
    ready=stage(data,'packet-p7-first-flush4')
    assert ready['markers']==['Ms:P8'] and FIRST not in ready['registers']
    assert [n for n,v in ready['words'].items() if v==FIRST]==['Ms:P10']
    read=sections['packet-p7-first-read']
    assert not any(v['ip']==0xD6 for v in read)
    source=next(v for v in read if v['ip']==0xEE)
    assert source['numericOwner']==['Ms:P10'] and raw(source['fullBefore']['ik1302']['m'][1:36:3])==FIRST
    num['copy_contract'](source,'ik1302',0xEE,True,'post_math_FIRST_actual_P10')
    frame=prep['quadruple'](read,'post_math_first_reader_frame')
    assert frame[0]['numericOwner']==['unclassified:aux0'] and raw(frame[0]['emitted'][1:36:3])==FIRST
    saved=sections['packet-p7-first-output']
    d4=next(v for v in saved if v['ip']==0xD4)
    assert d4['ordinaryOwner']==['register:R7'];prior['ordinary_latched_copy'](d4,'post_math_FIRST_R7',FIRST)
    final=stage(data,'packet-idle')
    assert final['display']=='12345678,' and final['registers'][6]==SECOND and final['registers'][7]==FIRST
    expected=start['registers'].copy();expected[6]=SECOND;expected[7]=FIRST
    assert final['registers']==expected and final['program']==start['program']
    assert final['words']['Ms:P7']==SECOND and final['words']['Ms:P10']==FIRST
    period(data['windows']['packet-idle'],'post-math-both-read-both-held')
    print('PASS NATIVE both P7/SECOND and P10/FIRST read after ordinary2+3=5 '
        'and erasing earlier numerical outputs. R6/R7 are new physical-source outputs; '
        'both original Ms words held. Repeat/arbitrary eight-word/full K1/K2 NOT achieved.',flush=True)
    if '--contracts-only' not in sys.argv:
        labels=[*sections.keys(),'packet-idle'];direct=skipped=0
        for label in labels:
            x,y=replay(data['windows'][label],'p7-both/'+label);direct+=x;skipped+=y
        print('PASS TOTAL',direct+skipped,'originalALL5 words/',len(labels),
            'separate continuous windows; direct',direct,'fixed-pin skips',skipped,
            'NOT replay of all preparation words/full K1/K2.',flush=True)
    r['inlet']['immutable_reference']()


if __name__=='__main__':run()
