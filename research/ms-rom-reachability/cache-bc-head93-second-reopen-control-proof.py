#!/usr/bin/env python3
"""Measured reverse-constructor failure, not successful hidden readback.

The safe U/V/W/Q push is followed by a different EE/Y -> E7/P8 writer.
Fresh original/full mirror, original ALL5 replay and explicit lost value.
"""
from pathlib import Path
import json
import runpy
import subprocess
import sys

root=Path(__file__).resolve().parent
num=runpy.run_path(str(root/'cache-bc-head93-packet-number-proof.py'))
r=num['r'];prep=num['prep']
raw,stage,replay,period=(num[n] for n in ('raw','stage','replay','period'))
FIRST='007012345678';SECOND='007024681357';F='0000F0000000';ZERO='000000000000'


def physical(data,record,position,word):
    result=[None]*12
    for chip,tags in record['tags'+position].items():
        for j,tag in enumerate(tags):
            cell=data['cells'][tag]
            if cell['area']=='Ms' and cell['word']==word and isinstance(cell.get('field'),int):
                result[cell['field']]=record['full'+position][chip]['m'][j]
    assert all(n is not None for n in result)
    return raw(result)


def run():
    r['inlet']['immutable_reference']()
    clear_y='--clear-y' in sys.argv
    expected=ZERO if clear_y else F
    args=['node',str(root/'cache-bc-head93-second-reopen-control-native.cjs'),'--proof-input']
    if clear_y:args.append('--clear-y')
    data=json.loads(subprocess.check_output(args,text=True))
    assert data['report']['onlyPublicKeys'] and data['report']['ALL5mirror']
    before=stage(data,'packet-reopen-control-V');final=stage(data,'packet-idle')
    assert before['words']['Ms:P8']==SECOND and before['words']['Ms:P10']==FIRST
    assert FIRST not in before['registers'] and SECOND not in before['registers']
    if clear_y:
        cleared=stage(data,'packet-reopen-control-clearY')
        assert cleared['words']['Y']==ZERO and cleared['words']['Ms:P8']==SECOND
        assert cleared['words']['Ms:P10']==FIRST and 'Y' not in cleared['markers']
    records=data['windows']['packet-reopen-control-unsafe']
    d6=next(v for v in records if v['ip']==0xD6)
    assert d6['ordinaryOwner']==['register:RA']
    assert raw(d6['fullBefore']['ik1302']['m'][0:36:3])=='000000000000'
    frame=prep['quadruple'](records,'reverse_safe_frame_not_the_loss')
    assert [v['numericOwner'] for v in frame]==[['Ms:U'],['Ms:V'],['Ms:W'],['Ms:Q']]
    assert physical(data,frame[0],'Before','P8')==SECOND
    assert physical(data,frame[-1],'After','P8')==SECOND
    source=next(v for v in records if v['ip']==0xEE and v['word']>frame[-1]['word'])
    assert source['numericOwner']==['stack:Y'] and raw(source['fullBefore']['ik1302']['m'][1:36:3])==expected
    written=next(v for v in records if v['ip']==0xE7 and v['numericOwner']==['Ms:P8'])
    assert physical(data,written,'Before','P8')==SECOND
    assert raw(written['fullBefore']['ik1302']['r'][0:36:3])==expected
    assert raw(written['emitted'][1:36:3])==expected and written['word']==2838788+(8400 if clear_y else 0)
    assert source['word']<written['word']
    num['copy_contract'](source,'ik1302',0xEE,True,'bad_reverse_early_Y_'+('zero' if clear_y else 'F')+'_read')
    num['copy_contract'](written,'ik1302',0xE7,False,'bad_reverse_late_P8_'+('zero' if clear_y else 'F')+'_write')
    assert data['report']['secondRelocationAudit']['firstDifference']=={
        'word':written['word'],'stage':'packet-reopen-control-unsafe','moment':'after','location':'P8','actual':expected}
    assert data['report']['packetAudit']['numberHeld'] and data['report']['packetAudit']['firstDifference'] is None
    assert final['words']['Ms:P8']==expected and final['words']['Ms:P10']==FIRST
    assert final['registers']==before['registers'] and final['program']==before['program']
    period(data['windows']['packet-idle'],'failed-reverse/P8-lost-P10-held')
    print('PASS MEASURED NEGATIVE: U/V/W/Q frame preserves numericP8; later physical '
        f'EE/Y/{expected} -> E7/P8 overwrites24681357 at{written["word"]}. FIRST/P10 and ordinary '
        'zero numerical sources/program preserved; NOT a successful reader/global no-go.',flush=True)
    if '--contracts-only' not in sys.argv:
        labels=['packet-reopen-control-F1','packet-reopen-control-F2','packet-reopen-control-F3',
            'packet-reopen-control-F4','packet-reopen-control-U','packet-reopen-control-V',
            'packet-reopen-control-unsafe','packet-idle']
        if clear_y:labels.insert(6,'packet-reopen-control-clearY')
        direct=skipped=0
        for label in labels:
            a,b=replay(data['windows'][label],'reverse-control/'+label);direct+=a;skipped+=b
        print('PASS TOTAL',direct+skipped,'originalALL5 words/',len(labels),
            'separate continuous windows; direct',direct,'fixed-pin skips',skipped,
            'explicit FAILED reverse constructor, not recovery of SECOND.',flush=True)
    r['inlet']['immutable_reference']()


if __name__=='__main__':run()
