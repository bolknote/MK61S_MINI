#!/usr/bin/env python3
"""617 consecutive native ALL5 transitions and two whole controller ends.

The source60/48 low-type cut is universal and audited separately. These
native controls validate the reader/1F selector producers, not a high-type
77 constructor. No detached type/selector/state hypothesis is inserted.
"""
import json
from pathlib import Path
import runpy
import subprocess

root = Path(__file__).resolve().parent
source = runpy.run_path(str(root / 'cache-bc-60-inlet.py'))
r = source['r']
early = runpy.run_path(str(root / 'cache-input-mask-early-exit.py'))
engine = early['engine']
keymap = {'П→X': (8, 9), '9': (11, 1), 'K': (10, 9), '0': (2, 1)}


def replay(native, *, reader):
    initial = native['readerInitial' if reader else 'initial']
    end = native['readerEnd' if reader else 'end']
    groups = ('readerOrigin', 'readerCore') if reader else ('origin', 'core')
    checkpoints = {e['command']: e for group in groups for e in native[group]}
    keys = ['П→X', '9'] if reader else ['K', '0']
    state, tags, phase = engine['make'](initial)
    pins0 = {name: (initial['state'][name]['keyX'], initial['state'][name]['keyY'])
             for name in engine['models']}
    command = selected = 0
    boundaries = sorted({0, end['command'], *checkpoints,
        *(1120*i+j for i in range(2) for j in (0, 560, 1120))})
    for following in boundaries:
        if command in checkpoints: early['snapshot_matches'](state, phase, checkpoints[command]['state'])
        if following == command: continue
        pins = dict(pins0); index, offset = divmod(command, 1120)
        pins['ik1302'] = keymap[keys[index]] if index < 2 and offset < 560 else (0, 0)
        if following == command+1 and command in checkpoints and following in checkpoints:
            phase, _ = engine['step'](state, tags, phase, pins); command += 1; selected += 1
        else:
            phase, command = early['advance_fixed'](state, tags, phase, command,
                following, pins, losses=[], label=native['report']['name']+('_reader' if reader else '_suffix'))
    assert selected == (483 if reader else 134) and command == end['command']
    early['snapshot_matches'](state, phase, end['state'])
    assert r['inlet']['match_controller'](state['ik1302'])
    return selected


if __name__ == '__main__':
    r['inlet']['immutable_reference']()
    native = json.loads(subprocess.check_output([
        'node', str(root / 'cache-bc-60-native.cjs'), '--proof-input'], text=True))
    report = native['report']
    assert report['nativeKeyboardOnly'] and report['observerIndependent']
    assert report['all105Programme56Ms15OrdinaryHeld'] and not report['nativeBC']
    assert replay(native, reader=True)+replay(native, reader=False) == 617
    print(json.dumps(report, ensure_ascii=False), flush=True)
    r['inlet']['immutable_reference']()
    print('PASS617 consecutive native ALL5 transitions/full6720 and3360 ends/fresh '
          'unobserved mirror. Native1F makes selectorD, notC, with counter0; no60/BC writer '
          'in suffix. No state repair, exchange or partialK2.', flush=True)
