#!/usr/bin/env python3
"""Strict proof of the measured failed second-slot route, not a success.

Fresh public-key originals/full mirrors; source/ownership and destructive
frame checked without state imports, checkpoints or ROM/control repairs.
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
FIRST='007012345678';SECOND='007024681357';F='0000F0000000'


def run():
    r['inlet']['immutable_reference']()
    bad='--input-control' in sys.argv
    data=json.loads(subprocess.check_output(['node',str(root/'cache-bc-head93-second-frontier-native.cjs'),
        '--proof-input',*(['--input-control'] if bad else [])],text=True))
    assert data['report']['onlyPublicKeys'] and data['report']['ALL5mirror']
    period(data['windows']['packet-idle'],'second-frontier/'+('input' if bad else 'source'))
    if bad:
        fifth=data['windows']['packet-second-input5']
        assert stage(data,'packet-second-input4')['words']['Ms:P7']==F
        assert stage(data,'packet-second-input5')['words']['Ms:P7']=='004024681000'
        assert 'Ms:P7' not in stage(data,'packet-second-input5')['markers']
        print('PASS input control: fifth digit replacesP7/F; later SIGN cannot use the intendedP7 buffer root.',flush=True)
        labels=['packet-second-input5','packet-second-write','packet-idle']
    else:
        stored=next(v for v in data['windows']['packet-second-source-store'] if v['ip']==0xD4)
        assert stored['ordinaryOwner']==['register:R7']
        read=next(v for v in data['windows']['packet-second-open4'] if v['ip']==0xD6)
        assert read['ordinaryOwner']==['register:R7']
        assert raw(read['fullBefore']['ik1302']['m'][0:36:3])==SECOND
        frame=prep['quadruple'](data['windows']['packet-second-open4'],'second_stage_U')
        assert frame[0]['numericOwner']==['Ms:U'] and raw(frame[0]['emitted'][1:36:3])==SECOND
        records=data['windows']['packet-second-open5']
        push=prep['quadruple'](records,'second_destructive_P7_P10')
        assert [v['numericOwner'] for v in push]==[['Ms:P7'],['Ms:P8'],['Ms:P9'],['Ms:P10']]
        assert raw(push[0]['emitted'][1:36:3])==F
        assert raw(push[-1]['fullBefore']['ik1302']['m'][1:36:3])==FIRST
        assert push[-1]['word']==2015500 and raw(push[-1]['emitted'][1:36:3])=='3F7000000000'
        copied=[v for v in records if v['ip']==0xE7 and v['numericOwner']==['Ms:P7']][-1]
        assert raw(copied['fullBefore']['ik1302']['r'][0:36:3])==SECOND
        assert raw(copied['emitted'][1:36:3])==SECOND
        num['copy_contract'](copied,'ik1302',0xE7,False,'actual_second_single_P7_formatter')
        sign=next(v for v in data['windows']['packet-second-write'] if v['ip']==0xE9)
        assert sign['numericOwner']==['stack:X'],'the actual writer is NOT P9'
        print('PASS measured failure: realR7 second -> U, destructiveP7..P10 push at2015500 '
              'removes firstP10, late singleE7/P7 writes the second and erasesP7/F; '
              'SIGN E9 addressesX, notP9. Temporary first reserveR6 is still present.',flush=True)
        labels=['packet-second-source-store','packet-second-source-flush4',
            'packet-second-open1','packet-second-open2','packet-second-open3',
            'packet-second-open4','packet-second-open5','packet-second-write','packet-idle']
    if '--contracts-only' not in sys.argv:
        direct=skipped=0
        for label in labels:
            a,b=replay(data['windows'][label],'second-frontier/'+label);direct+=a;skipped+=b
        print('PASS TOTAL',direct+skipped,'originalALL5 words/',len(labels),'separate continuous windows;',
              'direct',direct,'fixed-pin skips',skipped,'FAILED second-storage frontier, not a two-word success.',flush=True)
    r['inlet']['immutable_reference']()


if __name__=='__main__':run()
