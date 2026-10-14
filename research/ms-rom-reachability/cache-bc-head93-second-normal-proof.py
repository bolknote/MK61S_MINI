#!/usr/bin/env python3
"""Ordinary arithmetic with TWO hidden numbers, explicit P7->A->P8 move.

Never relabel the old P7-only failure audit as preservation. Fresh guarded
stock/full mirrors, original ALL5 replay in separate continuous windows.
Reverse readers from the new P8/P10 layout are NOT claimed here.
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
    data=json.loads(subprocess.check_output(['node',str(root/'cache-bc-head93-second-normal-native.cjs'),
        '--math','--proof-input'],text=True))
    assert data['report']['onlyPublicKeys'] and data['report']['ALL5mirror']
    a=data['report']['packetAudit'];b=data['report']['secondRelocationAudit'];old=data['report']['secondSlotAudit']
    assert a['checkedWords']==2182350 and a['numberHeld'] and a['firstDifference'] is None
    assert b['checkedWords']==670852 and b['numberHeld'] and b['firstDifference'] is None
    assert b['moves']==[{'word':2485927,'stage':'packet-normal-relocate','from':'P7','to':'A'},
        {'word':2485928,'stage':'packet-normal-relocate','from':'A','to':'P8'}]
    assert old['numberHeld'] is False
    assert old['firstDifference']=={'word':2485927,'stage':'packet-normal-relocate','moment':'after','actual':ZERO}
    erased=stage(data,'packet-normal-erase7')
    assert FIRST not in erased['registers'] and SECOND not in erased['registers']
    for reg in (6,7):
        records=data['windows']['packet-normal-erase'+str(reg)]
        d4=next(v for v in records if v['ip']==0xD4)
        assert d4['ordinaryOwner']==['register:R'+str(reg)]
        prior['ordinary_latched_copy'](d4,'normal_erase_R'+str(reg),ZERO)
    records=data['windows']['packet-normal-relocate']
    d6=next(v for v in records if v['ip']==0xD6)
    assert d6['ordinaryOwner']==['register:RB'] and raw(d6['fullBefore']['ik1302']['m'][0:36:3])==ZERO
    frame=prep['quadruple'](records,'true_second_relocation_not_loss')
    assert [v['numericOwner'] for v in frame]==[['Ms:W'],['Ms:Q'],['Ms:P7'],['Ms:P8']]
    assert raw(frame[2]['fullBefore']['ik1302']['m'][1:36:3])==SECOND
    assert raw(frame[2]['emitted'][1:36:3])==ZERO
    assert raw(frame[2]['fullAfter']['ik1302']['r'][0:36:3])==SECOND
    assert raw(frame[3]['emitted'][1:36:3])==SECOND
    print('PASS EXPLICIT original E7/A8 shift: P7 is overwritten, but its FULL12 '
        'fields survive in workingA for ONE word and then in physicalP8. '
        'The P7-only failure is retained, not suppressed.',flush=True)
    ready=stage(data,'packet-normal-port5-zero');final=stage(data,'packet-idle')
    assert ready['markers']==['aux0'] and ready['registers'][5]==ZERO
    assert FIRST not in ready['registers'] and SECOND not in ready['registers']
    assert ready['words']['Ms:P8']==SECOND and ready['words']['Ms:P10']==FIRST
    plus=data['windows']['packet-normal-plus']
    saved=next(v for v in plus if v['ip']==0xE9)
    assert saved['numericOwner']==['stack:X']
    assert raw(saved['emitted'][1:36:3])=='000030000000'
    num['copy_contract'](saved,'ik1302',0xE9,False,'two_number_normal_add_LastX3_not_P10')
    assert stage(data,'packet-normal-plus')['display']=='5,'
    assert stage(data,'packet-normal-plus')['words']['Y']=='000050000000'
    normal_last=data['windows']['packet-normal-lastx']
    source=next(v for v in normal_last if v['ip']==0xEE)
    assert source['numericOwner']==['stack:X']
    assert raw(source['fullBefore']['ik1302']['m'][1:36:3])=='000030000000'
    assert stage(data,'packet-normal-lastx')['display']=='3,'
    assert final['display']=='0,' and final['markers']==['aux0']
    assert final['registers']==ready['registers'] and final['program']==ready['program']
    assert FIRST not in final['registers'] and SECOND not in final['registers']
    assert final['words']['Ms:P8']==SECOND and final['words']['Ms:P10']==FIRST
    period(data['windows']['packet-idle'],'normal/P8-second-P10-first')
    print('PASS NATIVE ordinary aux0 geometry, 2 ENTER3+=5 and normal LastX3; '
        'R6/R7/output sources erased, visible stack cleared; SECOND inP8 '
        'and FIRST inP10 survive. Reverse two-word read/repeat still unproved.',flush=True)
    if '--contracts-only' not in sys.argv:
        labels=['packet-normal-erase6','packet-normal-erase7','packet-normal-aux0','packet-normal-port5',
            'packet-normal-Y','packet-normal-X1','packet-normal-relocate',
            'packet-normal-flush1','packet-normal-flush2','packet-normal-flush3','packet-normal-flush4',
            'packet-normal-port5-zero','packet-normal-two','packet-normal-enter','packet-normal-three',
            'packet-normal-plus','packet-normal-lastx','packet-normal-preclear4','packet-idle']
        sections=[(n,data['windows'][n]) for n in labels]
        adapter=data['windows']['packet-normal-adapter']
        sections += [('adapter-entry',adapter[:12]),('adapter-header',adapter[-12:])]
        direct=skipped=0
        for label,records in sections:
            x,y=replay(records,'two-normal/'+label);direct+=x;skipped+=y
        print('PASS TOTAL',direct+skipped,'originalALL5 words/',len(sections),
            'separate continuous windows/slices; direct',direct,'fixed-pin skips',skipped,
            'NOT full2182350-word history or full K1/K2.',flush=True)
    r['inlet']['immutable_reference']()


if __name__=='__main__':run()
