#!/usr/bin/env python3
"""Two physical Ms readers after erasing both ordinary source copies.

Original guarded references/full mirrors. Selected ALL5 windows calculate
their complete state continuously; no model/import/ROM/control repairs.
Canonical arithmetic/two-word repeat/arbitrary bank are NOT claimed.
"""
from pathlib import Path
import json
import runpy
import subprocess
import sys
from z3 import And, BitVec

root=Path(__file__).resolve().parent
prior=runpy.run_path(str(root/'cache-bc-head93-second-shift-proof.py'))
num=prior['num'];r=num['r'];prep=num['prep']
raw,stage,replay,period,preserved=(num[n] for n in
    ('raw','stage','replay','period','preserved_number'))
FIRST='007012345678';SECOND='007024681357';ZERO='000000000000';F='0000F0000000'


def run():
    r['inlet']['immutable_reference']()
    data=json.loads(subprocess.check_output(['node',str(root/'cache-bc-head93-second-first-native.cjs'),
        '--read-first','--proof-input'],text=True))
    assert data['report']['onlyPublicKeys'] and data['report']['ALL5mirror']
    first=data['report']['packetAudit'];second=data['report']['secondSlotAudit']
    assert first['checkedWords']==1821150 and first['numberHeld'] and first['firstDifference'] is None
    assert second['checkedWords']==309652 and second['numberHeld'] and second['firstDifference'] is None
    erased=stage(data,'packet-second-erase7')
    assert FIRST not in erased['registers'] and SECOND not in erased['registers']
    assert erased['words']['Ms:P10']==FIRST and erased['words']['Ms:P7']==SECOND
    inlet=stage(data,'packet-second-read-output')
    assert inlet['registers'][6]==SECOND and FIRST not in inlet['registers']

    adapter=data['windows']['packet-second-first-adapter']
    assert not any(v['ip'] in (0xD6,0xEE,0xE7,0xA8) for v in adapter)
    write=next(v for v in adapter if v['ip']==0xA3)
    assert write['numericOwner']==['Ms:P9']
    assert stage(data,'packet-second-first-adapter')['display']=='ЕГГ0Г'
    assert stage(data,'packet-second-first-adapter')['words']['Ms:P9']=='FFF000000000'
    w,q=(num[n] for n in ('w','q'))
    a=r['concrete_primary'](write['fullBefore']['ik1302'])
    lower=[BitVec('first_P9_header_lower'+str(j),4) for j in range(9)]
    for j,n in enumerate(lower):a.m[1+3*j]=n
    p=w['base'](a,0xA3);out=[]
    w['ex'](a,0xA3,write['keysX'],write['keysY'],
        serial_inputs=[q['N4'](n) for n in write['fullAfter']['ik1302']['m']],emitted_outputs=out)
    w['prove'](p,And(*[out[1+3*j]==lower[j] for j in range(9)],
        *[out[j]==15 for j in (28,31,34)],
        *[out[j]==a.m[j] for j in range(42) if j not in (28,31,34)]),
        'measured A3/P9 control header only, arbitrary lower9/other lanes held')

    shapes={
        'V':('register:R7',ZERO,['stack:X1','Ms:U','Ms:V','Ms:W']),
        'W':('register:R7',ZERO,['stack:X1','Ms:U','Ms:V','Ms:W']),
        'Y':('register:R3',F,['unclassified:aux0','unclassified:aux1','stack:X','stack:Y']),
        'T':('register:R4',ZERO,['stack:Y','stack:Z','stack:T','stack:X1']),
        'X1':('register:R4',ZERO,['stack:Y','stack:Z','stack:T','stack:X1']),
        'X1zero':('register:R4',ZERO,['stack:Y','stack:Z','stack:T','stack:X1']),
        **{'flush'+str(i):('register:R2',ZERO,['unclassified:aux0','unclassified:aux1','stack:X','stack:Y']) for i in range(1,5)}}
    for suffix,(owner,source,targets) in shapes.items():
        records=data['windows']['packet-second-first-'+suffix]
        d6=next(v for v in records if v['ip']==0xD6)
        assert d6['ordinaryOwner']==[owner]
        assert raw(d6['fullBefore']['ik1302']['m'][0:36:3])==source
        frame=prep['quadruple'](records,'first_cleanup_'+suffix)
        assert [v['numericOwner'] for v in frame]==[[n] for n in targets]
        preserved(records,data['cells'])
    cx=data['windows']['packet-second-first-Wzero']
    writers=[v for v in cx if v['ip'] in (0xE7,0xA8,0xE9)]
    assert len(writers)==1 and writers[0]['numericOwner']==['Ms:W']
    assert raw(writers[0]['emitted'][1:36:3])==ZERO
    num['copy_contract'](writers[0],'ik1302',0xE7,False,'single_Cx_W_zero_not_P7_frame')
    assert stage(data,'packet-second-first-X1zero')['markers']==['Ms:P8','aux0']
    ready=stage(data,'packet-second-first-flush4')
    assert ready['markers']==['Ms:P8'] and ready['words']['Ms:P7']==SECOND and ready['words']['Ms:P10']==FIRST
    assert FIRST not in ready['registers'] and ready['registers'][6]==SECOND
    read=data['windows']['packet-second-first-read']
    assert not any(v['ip']==0xD6 for v in read)
    source=next(v for v in read if v['ip']==0xEE)
    assert source['numericOwner']==['Ms:P10']
    assert raw(source['fullBefore']['ik1302']['m'][1:36:3])==FIRST
    num['copy_contract'](source,'ik1302',0xEE,True,'second_bank_FIRST_from_physical_P10')
    frame=prep['quadruple'](read,'two_bank_first_reader_lift')
    assert frame[0]['numericOwner']==['unclassified:aux0']
    assert raw(frame[0]['emitted'][1:36:3])==FIRST
    saved=data['windows']['packet-second-first-output']
    assert not any(v['ip']==0xD6 for v in saved)
    d4=next(v for v in saved if v['ip']==0xD4)
    assert d4['ordinaryOwner']==['register:R7']
    prior['ordinary_latched_copy'](d4,'two_bank_first_output',FIRST)
    final=stage(data,'packet-idle')
    assert final['display']=='12345678,' and final['registers'][6]==SECOND and final['registers'][7]==FIRST
    assert final['words']['Ms:P10']==FIRST and final['words']['Ms:P7']==SECOND
    assert final['markers']==['Ms:P8'] and final['program']==inlet['program']
    period(data['windows']['packet-idle'],'two-bank/read-both-retain-both')
    print('PASS NATIVE BOTH original Ms numbers recovered AFTER ordinary sources erased: '
        'physicalP7 -> realR6=24681357, physicalP10 -> display/realR7=12345678; '
        'P7/P10 continuously held, normal arithmetic/two-bank repeat NOT proved.',flush=True)
    if '--contracts-only' not in sys.argv:
        # The initial rejecting adapter is a long calendar-control wait.
        # Audit only its explicit entry/header slices, not the whole wait.
        sections=[('adapter-entry',adapter[:12]),('adapter-header',adapter[-12:])]
        sections +=[(n,records) for n,records in data['windows'].items()
            if n.startswith('packet-second-first-') and n!='packet-second-first-adapter']
        sections.append(('packet-idle',data['windows']['packet-idle']))
        direct=skipped=0
        for label,records in sections:
            a,b=replay(records,'two-bank-first/'+label);direct+=a;skipped+=b
        print('PASS TOTAL',direct+skipped,'originalALL5 words/',len(sections),
            'separate continuous windows/slices; direct',direct,'fixed-pin skips',skipped,
            'NOT full1821150-word history or complete K1/K2.',flush=True)
    r['inlet']['immutable_reference']()


if __name__=='__main__':run()
