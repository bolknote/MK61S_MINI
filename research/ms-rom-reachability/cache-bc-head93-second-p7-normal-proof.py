#!/usr/bin/env python3
"""Native normal arithmetic with SECOND still in P7, FIRST in P10.

Explicit fixed safe ROM frame contracts; fresh full mirrors; separate
continuous ALL5 windows/slices. Not a readback/repeat/full eight-word K1/K2.
"""
from pathlib import Path
import json
import runpy
import subprocess
import sys
from z3 import And,BitVec

root=Path(__file__).resolve().parent
prior=runpy.run_path(str(root/'cache-bc-head93-second-shift-proof.py'))
num=prior['num'];r=num['r'];prep=num['prep']
raw,stage,replay,period=(num[n] for n in ('raw','stage','replay','period'))
FIRST='007012345678';SECOND='007024681357';ZERO='000000000000';F='0000F0000000'


def run():
    r['inlet']['immutable_reference']()
    data=json.loads(subprocess.check_output(['node',str(root/'cache-bc-head93-second-p7-normal-native.cjs'),
        '--math','--proof-input'],text=True))
    assert data['report']['onlyPublicKeys'] and data['report']['ALL5mirror']
    for key in ('packetAudit','secondSlotAudit','secondRelocationAudit'):
        a=data['report'][key];assert a['numberHeld'] and a['firstDifference'] is None
    assert data['report']['secondRelocationAudit']['location']=='P7'
    assert data['report']['secondRelocationAudit']['moves']==[]
    shapes={**{'shift'+str(i):('register:R7',ZERO,['stack:X1','Ms:U','Ms:V','Ms:W']) for i in range(1,4)},
        'X1':('register:R8',F,['stack:X1','Ms:U','Ms:V','Ms:W']),
        **{'flush'+str(i):('register:R4',ZERO,['stack:Y','stack:Z','stack:T','stack:X1']) for i in range(1,5)}}
    for suffix,(owner,source,targets) in shapes.items():
        records=data['windows']['packet-normal-retain-'+suffix]
        d6=next(v for v in records if v['ip']==0xD6)
        assert d6['ordinaryOwner']==[owner]
        assert raw(d6['fullBefore']['ik1302']['m'][0:36:3])==source
        frame=prep['quadruple'](records,'p7_normal_'+suffix)
        assert [v['numericOwner'] for v in frame]==[[n] for n in targets]
    cx=data['windows']['packet-normal-retain-clearP8']
    writes=[v for v in cx if v['ip'] in (0xE7,0xA8,0xE9)]
    assert len(writes)==1 and writes[0]['numericOwner']==['Ms:P8']
    assert raw(writes[0]['emitted'][1:36:3])==ZERO
    num['copy_contract'](writes[0],'ik1302',0xE7,False,'p7_normal_single_P8_zero_no_shift')
    header=data['windows']['packet-normal-retain-header']
    assert not any(v['ip'] in (0xD6,0xEE,0xE7,0xA8) for v in header)
    written=next(v for v in header if v['ip']==0xA3)
    assert written['numericOwner']==['unclassified:aux1']
    a=r['concrete_primary'](written['fullBefore']['ik1302']);w,q=(num[n] for n in ('w','q'))
    lower=[BitVec('p7_normal_header_lower_'+str(j),4) for j in range(9)]
    for j,n in enumerate(lower):a.m[1+3*j]=n
    p=w['base'](a,0xA3);out=[]
    w['ex'](a,0xA3,*num['prior']['all5']['pins'](written)['ik1302'],
        serial_inputs=[q['N4'](n) for n in written['fullAfter']['ik1302']['m']],emitted_outputs=out)
    w['prove'](p,And(*[out[1+3*j]==lower[j] for j in range(9)],
        *[out[j]==15 for j in (28,31,34)]),
        'conditional aux1/FFF adapter: arbitrary lower9 held; observed other controls')
    ready=stage(data,'packet-normal-port5-zero');final=stage(data,'packet-idle')
    assert ready['markers']==['aux0'] and ready['registers'][5]==ZERO
    assert FIRST not in ready['registers'] and SECOND not in ready['registers']
    assert ready['words']['Ms:P7']==SECOND and ready['words']['Ms:P10']==FIRST
    assert final['words']['Ms:P7']==SECOND and final['words']['Ms:P10']==FIRST
    assert final['markers']==['aux0'] and final['registers']==ready['registers']
    assert final['program']==ready['program']==stage(data,'packet-second-first-output')['program']
    assert stage(data,'packet-normal-plus')['display']=='5,'
    assert stage(data,'packet-normal-lastx')['display']=='3,'
    source=next(v for v in data['windows']['packet-normal-lastx'] if v['ip']==0xEE)
    assert source['numericOwner']==['stack:X'] and raw(source['fullBefore']['ik1302']['m'][1:36:3])=='000030000000'
    num['copy_contract'](source,'ik1302',0xEE,True,'p7_normal_genuine_LastX3')
    saved=next(v for v in data['windows']['packet-normal-port5-zero'] if v['ip']==0xD4)
    assert saved['ordinaryOwner']==['register:R5'];prior['ordinary_latched_copy'](saved,'p7_normal_port5_zero',ZERO)
    period(data['windows']['packet-idle'],'P7-P10-normal-math')
    print('PASS NATIVE P7/SECOND and P10/FIRST never relocated/lost; canonical aux0 '
        'and realR5=0, no ordinary numeric copies, 2+3=5/LastX3 and clear work. '
        'Program105 unchanged. Readback/repeat/arbitrary eight-word K1/K2 still unproved.',flush=True)
    if '--contracts-only' not in sys.argv:
        labels=[*['packet-normal-retain-shift'+str(i) for i in range(1,4)],
            'packet-normal-retain-clearP8','packet-normal-retain-X1',
            *['packet-normal-retain-flush'+str(i) for i in range(1,5)],
            'packet-normal-port5-zero','packet-normal-plus','packet-normal-lastx',
            'packet-normal-preclear4','packet-idle']
        sections=[(n,data['windows'][n]) for n in labels]
        sections.extend([('header-entry',header[:12]),('header-tail',header[-12:])])
        direct=skipped=0
        for label,records in sections:
            x,y=replay(records,'p7-normal/'+label);direct+=x;skipped+=y
        print('PASS TOTAL',direct+skipped,'originalALL5 words/',len(sections),
            'separate continuous windows/slices; direct',direct,'fixed-pin skips',skipped,
            'NOT full preparation replay/full K1/K2.',flush=True)
    r['inlet']['immutable_reference']()


if __name__=='__main__':run()
