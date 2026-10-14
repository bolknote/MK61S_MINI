#!/usr/bin/env python3
"""Independent ALL5 replay of native C8 parking / ordinary F9 writer controls.

No hypothetical flag, selector, return tag or dispatch is injected. All
five-chip fields, wires and phase are matched at each selected consecutive
boundary and at the full6720 end. Skipping is only by an executed complete
ALL5/wires/phase/tags period at constant physical key pins.
"""
import json
from pathlib import Path
import runpy
import subprocess

root = Path(__file__).resolve().parent
source = runpy.run_path(str(root / 'cache-c9-page-island.py'))
r, w, q = source['r'], source['w'], source['q']
early = runpy.run_path(str(root / 'cache-input-mask-early-exit.py'))
engine = early['engine']


def validate(native):
    report = native['report']
    assert report['nativeKeyboardOnly'] and report['observerIndependent']
    assert report['all56MsBytesHeld'] and report['all15OrdinaryWordsHeld']
    assert not report['partialK2'] and not report['persistentMsCopy']
    state, tags, phase = engine['make'](native['initial'])
    checkpoints = {e['command']: e for name in ('origin', 'core') for e in native[name]}
    command = selected = 0; end = report['end']; keys = report['keys']
    mapping = {'П→X': (8, 9), '9': (11, 1), '3': (5, 1),
               'F': (11, 9), '/-/': (8, 8), 'В/О': (4, 9)}
    initial_pins = {name: (native['initial']['state'][name]['keyX'],
                          native['initial']['state'][name]['keyY']) for name in engine['models']}
    boundaries = sorted({0, end, *checkpoints,
        *(i*1120+offset for i in range(len(keys)) for offset in (0, 560, 1120))})
    pair_heads = {p['first']: p for p in report['pairs']}
    pair_tails = {p['second']: p for p in report['pairs']}
    for following in boundaries:
        if command in checkpoints:
            early['snapshot_matches'](state, phase, checkpoints[command]['state'])
            if command in pair_heads:
                item = pair_heads[command]
                assert [r['number'](v) for v in state['ik1302'].m[2:42:3]] == item['original14']
            if command in pair_tails:
                item = pair_tails[command]
                assert [r['number'](v) for v in state['ik1302'].r[1:42:3]] == item['returned14']
        if command == following: continue
        pins = dict(initial_pins); index, offset = divmod(command, 1120)
        pins['ik1302'] = mapping[keys[index]] if index < len(keys) and offset < 560 else (0, 0)
        if following == command+1 and command in checkpoints and following in checkpoints:
            phase, _ = engine['step'](state, tags, phase, pins); command += 1; selected += 1
        else:
            phase, command = early['advance_fixed'](state, tags, phase, command,
                following, pins, losses=[], label=report['name'])
    assert command == end == 6720
    assert selected == (484 if report['kind'] == 'editor' else 438)
    early['snapshot_matches'](state, phase, native['end']['state'])
    assert r['inlet']['match_controller'](state['ik1302'])
    print(f'PASS {report["name"]}: {selected} consecutive ALL5 transitions; '
          'complete6720 end, all fields/wires/phase, fresh unobserved mirror; '
          'native one-byte writer is an editor control, not Ms-source transport.', flush=True)
    return selected


if __name__ == '__main__':
    r['inlet']['immutable_reference']()
    controls = json.loads(subprocess.check_output([
        'node', str(root / 'cache-c9-page-island-native.cjs'), '--proof-input'], text=True))
    assert len(controls) == 3
    count = sum(validate(native) for native in controls)
    assert count == 1360
    source['original_call_and_wait_gates']()
    source['rotation_and_byte_gates']()
    source['opaque_page_families']()
    source['reader_flag_boundary']()
    r['inlet']['immutable_reference']()
    print('PASS three fresh native controls /1360 consecutive ALL5 transitions '
          '/three full6720 ends; temporary five-byte Ms parking and native '
          'single-byte programme patch verified. No persistent Ms exchange or K2.', flush=True)
