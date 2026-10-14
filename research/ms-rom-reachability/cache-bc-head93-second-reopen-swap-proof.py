#!/usr/bin/env python3
"""ALL5 audit of the failed SWAP reverse-reader candidate.

PRIMARY planning can issue the request but cannot model other chips' writes.
Identify the actual readers/writers from passive physical carrier tags.
"""
from pathlib import Path
import json
import runpy
import subprocess
import sys
from z3 import And,BitVec

root=Path(__file__).resolve().parent
num=runpy.run_path(str(root/'cache-bc-head93-packet-number-proof.py'))
raw,stage,replay,period=(num[n] for n in ('raw','stage','replay','period'))
owner,outgoing=(num[n] for n in ('owner','outgoing'))
FIRST='007012345678';SECOND='007024681357';ZERO='000000000000'


def physical_p7(data,v,position):
    values=[None]*12
    for chip,tags in v['tags'+position].items():
        for j,tag in enumerate(tags):
            cell=data['cells'][tag]
            if cell['area']=='Ms' and cell['word']=='P7' and isinstance(cell.get('field'),int):
                values[cell['field']]=v['full'+position][chip]['m'][j]
    assert all(n is not None for n in values)
    return raw(values)


def restore_b_contract(v):
    r,w,prior=(num[n] for n in ('r','w','prior'))
    a=r['concrete_primary'](v['fullBefore']['ik1303'])
    symbolic=[BitVec('swap_restore_B_'+str(j),4) for j in range(12)]
    for j,n in enumerate(symbolic):a.r[1+3*j]=n
    p=w['base'](a,0x61)
    b=prior['engine']['models']['ik1303']['execute_command'](a,0x61,
        *prior['all5']['pins'](v)['ik1303'],
        serial_inputs=[num['q']['N4'](n) for n in v['fullAfter']['ik1303']['m']])
    w['prove'](p,And(*[b.r[3*j]==symbolic[j] for j in range(12)]),
        'conditional SWAP61 restores all12 B fields to A, observed other control')


def run():
    num['r']['inlet']['immutable_reference']()
    data=json.loads(subprocess.check_output(['node',str(root/'cache-bc-head93-second-reopen-swap-native.cjs'),
        '--proof-input'],text=True))
    before=stage(data,'packet-reopen-control-front3');final=stage(data,'packet-idle')
    assert data['report']['onlyPublicKeys'] and data['report']['ALL5mirror']
    assert before['markers']==['V','aux0']
    assert before['words']['Ms:P8']==SECOND and before['words']['Ms:P10']==FIRST
    assert SECOND not in before['registers'] and FIRST not in before['registers']
    assert final['words']['Ms:P8']==ZERO and final['words']['Ms:P10']==FIRST
    assert SECOND not in final['words'].values(), ('diagnostic must expose any relocated numerical copy',final['words'])
    assert final['registers']==before['registers'] and final['program']==before['program']
    assert data['report']['packetAudit']['numberHeld']
    assert data['report']['secondRelocationAudit']['firstDifference']=={
        'word':2889684,'stage':'packet-reopen-control-swap','moment':'after','location':'P8','actual':ZERO}
    records=data['windows']['packet-reopen-control-swap']
    at=lambda word:next(v for v in records if v['word']==word)
    read,restored,written,lost,late=map(at,(2889669,2889682,2889683,2889684,2889742))
    assert owner(data,read,'ik1303')==['Ms:P8']
    assert raw(read['fullAfter']['ik1303']['r'][0:36:3])==SECOND
    assert raw(restored['fullBefore']['ik1303']['r'][1:36:3])==SECOND
    assert raw(restored['fullAfter']['ik1303']['r'][0:36:3])==SECOND
    assert owner(data,written,'ik1303')==['Ms:P7']
    assert raw(outgoing(written,'ik1303')[1:36:3])==SECOND
    assert owner(data,lost,'ik1303')==['Ms:P8']
    assert raw(lost['fullAfter']['ik1303']['r'][0:36:3])==SECOND
    assert late['ip']==0xE7 and late['numericOwner']==['Ms:P7']
    assert raw(late['fullBefore']['ik1302']['m'][1:36:3])==SECOND
    assert raw(late['emitted'][1:36:3])==ZERO
    for v in records:
        if written['word']<=v['word']<=late['word']:
            for position in ('Before','After'):
                if v['word']==written['word'] and position=='Before':expected=ZERO
                elif v['word']==late['word'] and position=='After':expected=ZERO
                else:expected=SECOND
                assert physical_p7(data,v,position)==expected,(v['word'],position)
    num['copy_contract'](read,'ik1303',0x53,True,'swap_P8_read_all12')
    restore_b_contract(restored)
    num['copy_contract'](written,'ik1303',0x4E,False,'swap_A_to_P7_all12')
    num['copy_contract'](lost,'ik1303',0x2A,True,'swap_P8_old_to_A_all12')
    num['copy_contract'](late,'ik1302',0xE7,False,'swap_late_P7_zero_write_all12')
    print('PASS MEASURED PARTIAL: IK1303 reads P8/SECOND, restores B->A, '
        'writes ALL12 into P7 at2889683; then primary E7/P7 overwrites it '
        'with0 at2889742. Transfer occurred, but final output/recovery failed.',flush=True)
    changes=[]
    for v in records:
        for chip in ('ik1302','ik1303','ik1306'):
            a=v['fullBefore'][chip];b=v['fullAfter'][chip]
            ip=a['r'][36]+16*a['r'][39]
            old=raw(a['m'][1:36:3]);emitted=raw(outgoing(v,chip)[1:36:3])
            old_a=raw(a['r'][0:36:3]);new_a=raw(b['r'][0:36:3])
            if old!=emitted or (new_a==SECOND and old_a!=SECOND):
                changes.append({'word':v['word'],'chip':chip,'ip':f'{ip:02X}',
                    'owner':owner(data,v,chip),'old':old,'emitted':emitted,'A_before':old_a,'A_after':new_a})
    print('MEASURED SWAP numeric changes',json.dumps(changes),flush=True)
    endpoint=data['nativeEndpoints']['packet-reopen-control-swap']['fullBefore']
    buffers={chip:[raw(endpoint[chip]['r'][lane:36:3]) for lane in range(3)]
        for chip in ('ik1302','ik1303','ik1306')}
    print('MEASURED post-SWAP working lanes, NOT recovered outputs',json.dumps(buffers),flush=True)
    period(data['windows']['packet-idle'],'failed-swap/P8-zero-P10-first')
    print('PASS MEASURED NEGATIVE: real SWAP request from V/aux0 erases numericP8; '
        'no SECOND in final15 numerical words/ordinary bank. FIRST/P10 held. '
        'PRIMARY-only unchangedP8 is NOT the ALL5 result; no successful reader/repeat.',flush=True)
    if '--contracts-only' not in sys.argv:
        labels=['packet-reopen-control-front1','packet-reopen-control-front2',
            'packet-reopen-control-front3','packet-reopen-control-swap','packet-idle']
        direct=skipped=0
        for label in labels:
            a,b=replay(data['windows'][label],'reverse-swap/'+label);direct+=a;skipped+=b
        print('PASS TOTAL',direct+skipped,'originalALL5 words/',len(labels),
            'separate continuous windows; direct',direct,'fixed-pin skips',skipped,
            'FAILED reverse SWAP, not recovery of SECOND.',flush=True)
    num['r']['inlet']['immutable_reference']()


if __name__=='__main__':run()
