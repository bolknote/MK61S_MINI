#!/usr/bin/env python3
"""Strict ALL5 replay of the minimal PUBLIC exact-F word constructor.

A real stock reference is operated ONLY with public keys. Two passive windows
cover native STOP/9F/EE and STORE/9F/EE/DD/D4. Every subsequent modeled state
is calculated from the first observed state; no checkpoints repair the replay.
No symbolic data hypothesis, emulator setter or ROM/control/phase change.
The result is an ordinaryR9 rawF word, NOT a Ms:Q marker or restored K2.
"""
from pathlib import Path
import json
import runpy
import subprocess

root=Path(__file__).resolve().parent
all5=runpy.run_path(str(root/'cache-bc-head93-q-marker-all5.py'))
r,w,q,engine=(all5[n] for n in ('r','w','q','engine'))


def run():
    r['inlet']['immutable_reference']()
    native=json.loads(subprocess.check_output(['node',
        str(root/'cache-bc-head93-blank-marker-native.cjs'),'--stop-proof-input'],text=True))
    report=native['report']
    assert report['minimal'] and report['zeros']==1
    assert report['onlyPublicKeys'] and report['ALL5mirror']
    assert native['blank']['words']['Y']=='0000F0000000'
    assert native['after']['R9']=='0000F0000000'
    total=0
    for label,records in native['windows'].items():
        assert records[0]['ip']==0x9F and records[-1]['ip']==0xE7
        assert len(records)==(91 if label=='stop' else 136)
        state,tags,phase=all5['initialize'](records[0])
        for i,record in enumerate(records):
            assert not i or record['word']==records[i-1]['word']+1
            all5['compare'](state,tags,phase,record['fullBefore'],record['tagsBefore'])
            assert engine['boundary_ip'](state['ik1302'])==record['ip']
            phase,out=engine['step'](state,tags,phase,all5['pins'](record))
            assert [all5['number'](v) for v in out['ik1302']]==record['emitted']
            all5['reduce_calculated'](state)
            all5['compare'](state,tags,phase,record['fullAfter'],record['tagsAfter'])
        total+=len(records)
        print('PASS native',label,len(records),'consecutive ALL5 ORIGINAL words; '
              'all working fields/IR cells/wires/phase/carrier tags.',flush=True)
    assert total==227
    store=native['windows']['store']
    ee=next(v for v in store if v['ip']==0xEE)
    d4=next(v for v in store if v['ip']==0xD4)
    raw=lambda values:''.join(f'{v:X}' for v in reversed(values[:12]))
    assert raw(ee['fullBefore']['ik1302']['m'][1:36:3])=='0000F0000000'
    assert raw(ee['fullAfter']['ik1302']['r'][0:36:3])=='0000F0000000'
    assert d4['word']>ee['word']
    assert not report['nativeQMarkerF']
    r['inlet']['immutable_reference']()
    print('PASS227 strict native ALL5 transitions, no input-state hypotheses. '
          'Keys create exact0000F0000000 inY and store it unnormalized in ordinaryR9; '
          'fresh unobserved ALL5 mirrors. NativeQ remains zero; no live/completeK2 claim.',flush=True)


if __name__=='__main__':run()
