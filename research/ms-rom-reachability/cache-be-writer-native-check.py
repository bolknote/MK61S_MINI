#!/usr/bin/env python3
"""Independent ALL5 audit of ordinary store controls; no flag/return repair."""
import json
from pathlib import Path
import runpy
import subprocess

root = Path(__file__).resolve().parent
source = runpy.run_path(str(root / 'cache-be-writer-entry.py'))
r, w = source['r'], source['w']
early = runpy.run_path(str(root / 'cache-input-mask-early-exit.py'))
engine = early['engine']
# Exact public key table in the immutable mk61.cjs, not a guessed pin pair.
mapping = {'П→X': (8, 9), '9': (11, 1), 'X→П': (6, 9), '0': (2, 1)}


def replay(native, *, reader):
    report = native['report']
    initial = native['readerInitial' if reader else 'initial']
    end = native['readerEnd' if reader else 'end']
    groups = ('readerOrigin', 'readerCore') if reader else ('origin', 'core')
    checkpoints = {e['command']: e for group in groups for e in native[group]}
    state, tags, phase = engine['make'](initial)
    keys = ['П→X', '9'] if reader else report['keys']
    initial_pins = {name: (initial['state'][name]['keyX'], initial['state'][name]['keyY'])
                    for name in engine['models']}
    command = selected = 0
    boundaries = sorted({0, end['command'], *checkpoints,
        *(i*1120+offset for i in range(len(keys)) for offset in (0, 560, 1120))})
    for following in boundaries:
        if command in checkpoints:
            early['snapshot_matches'](state, phase, checkpoints[command]['state'])
            if not reader and command == 1177:
                a = state['ik1302']
                assert r['number'](w['ip'](a)) == 0xD3
                assert [r['number'](a.r[j]) for j in (2, 23, 26)] == [5, 0, 0]
            if not reader and command == 1178:
                assert r['number'](w['ip'](state['ik1302'])) == 0xD5
            if not reader and command == 1213:
                a = state['ik1302']
                assert r['number'](w['ip'](a)) == 0xE4
                assert [r['number'](a.r[j]) for j in (2, 23, 26)] == (
                    [5, 1, 0] if report['lateJointWriterFields'] else [0, 0, 0])
        if command == following: continue
        pins = dict(initial_pins); index, offset = divmod(command, 1120)
        pins['ik1302'] = mapping[keys[index]] if index < len(keys) and offset < 560 else (0, 0)
        if following == command+1 and command in checkpoints and following in checkpoints:
            phase, _ = engine['step'](state, tags, phase, pins); command += 1; selected += 1
        else:
            phase, command = early['advance_fixed'](state, tags, phase, command,
                following, pins, losses=[], label=report['name']+('_reader' if reader else '_suffix'))
    assert command == end['command']
    assert selected == (438 if reader else 204), (report['name'], reader, selected)
    early['snapshot_matches'](state, phase, end['state'])
    assert r['inlet']['match_controller'](state['ik1302'])
    return selected


if __name__ == '__main__':
    r['inlet']['immutable_reference']()
    controls = json.loads(subprocess.check_output([
        'node', str(root / 'cache-be-writer-native.cjs'), '--proof-input'], text=True))
    assert len(controls) == 2
    count = 0
    for native in controls:
        report = native['report']
        assert report['nativeKeyboardOnly'] and report['observerIndependent']
        assert report['all105Programme56MsHeld'] and report['other14OrdinaryHeld']
        assert not report['originalBEWriterCaller'] and not report['persistentMsCopy'] and not report['partialK2']
        local = replay(native, reader=True)+replay(native, reader=False); count += local
        print(f'PASS {report["name"]}:{local} consecutive ALL5 transitions; '
              'complete6720/3360 ends, all fields/wires/phase; fresh unobserved mirror. '
              'P0 changed by originalD4/M1, all105/56 and other14 ordinary words held; '
              'originalE4, not BE writer entry.', flush=True)
    assert count == 1284
    source['original_be_source_cut']()
    source['original_call_reserves']()
    source['independent_writer_interfaces']()
    r['inlet']['immutable_reference']()
    print('PASS two fresh native controls,1284 consecutive ALL5 transitions/four '
          'complete ends.14 positive caller interfaces remain conditional; '
          'no native BE joint inlet or partialK2.', flush=True)
