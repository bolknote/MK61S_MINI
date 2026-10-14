#!/usr/bin/env python3
"""Independent ALL5 replay of uncancelled-reader call-prefix controls.

Snapshots come from fresh guarded stock machines with public keys only and
fresh completely unobserved mirrors. This independent ROM/ring model gets
NO hypothetical flags/dispatch/return addresses. Skipping requires an
executed full ALL5/wires/phase/tags period under unchanged key pins.
"""
import json
from pathlib import Path
import runpy
import subprocess

root = Path(__file__).resolve().parent
contract = runpy.run_path(str(root / 'cache-call-return-transport.py'))
r, w, q = contract['r'], contract['w'], contract['q']
early = runpy.run_path(str(root / 'cache-input-mask-early-exit.py'))
engine = early['engine']


def validate(native):
    report = native['report']
    assert report['observerIndependent'] is True and report['nativeKeyboardOnly'] is True
    assert report['partialK2'] is False and report['nativeCacheExport'] is False
    assert report['newSTReserve'] is False
    state, tags, phase = engine['make'](native['initial'])
    groups = ('origin', 'operandPrefix', 'replacement', 'pointer')
    checkpoints = {e['command']: e for group in groups for e in native[group]}
    keys, end = report['keys'], report['end']; command = selected = 0
    initial_pins = {name: (native['initial']['state'][name]['keyX'],
                          native['initial']['state'][name]['keyY']) for name in engine['models']}
    mapping = {'K': (10, 9), 'ПП': (5, 9), '8': (10, 1), 'В/О': (4, 9)}
    boundaries = sorted({0, end, *checkpoints,
        *(i*1120+offset for i in range(len(keys)) for offset in (0, 560, 1120))})
    for following in boundaries:
        if command in checkpoints:
            early['snapshot_matches'](state, phase, checkpoints[command]['state'])
            # Specifically compare both sides of the first physical EE read.
            if command == report['firstEE']:
                assert [r['number'](state['ik1302'].r[j]) for j in w['raw']] == [3, 10, 4, 13, 5, 7]
            if command == report['firstCacheReplacement']:
                assert [r['number'](state['ik1302'].r[j]) for j in w['raw']] != [3, 10, 4, 13, 5, 7]
        if command == following: continue
        pins = dict(initial_pins); index, offset = divmod(command, 1120)
        pins['ik1302'] = mapping[keys[index]] if index < len(keys) and offset < 560 else (0, 0)
        if following == command+1 and command in checkpoints and following in checkpoints:
            phase, _ = engine['step'](state, tags, phase, pins); command += 1; selected += 1
        else:
            phase, command = early['advance_fixed'](state, tags, phase, command,
                following, pins, losses=[], label=report['name'])
    assert command == end
    expected = {'call_prefix': 128, 'call_operand8': 314, 'return_key': 108}[report['name']]
    assert selected == expected, (selected, expected)
    early['snapshot_matches'](state, phase, native['end']['state'])
    assert r['inlet']['match_controller'](state['ik1302'])
    if report['name'] == 'call_prefix':
        assert report['firstCacheReplacement'] == -1
        assert report['dataChanges'] == {'program': [], 'ms': [], 'registers': []}
        assert report['endIp'] == 0x35 and report['endInputFlag'] == 1
    print(f'PASS {report["name"]}: {selected} consecutive ALL5 transitions '
          f'/complete{end} end; all fields/wires/phase, fresh unobserved mirror. '
          'No native programme-cache export or partialK2.', flush=True)
    return selected


if __name__ == '__main__':
    r['inlet']['immutable_reference']()
    controls = json.loads(subprocess.check_output([
        'node', str(root / 'cache-call-prefix-native.cjs'), '--proof-input'], text=True))
    assert len(controls) == 3
    count = sum(validate(control) for control in controls)
    assert count == 550
    contract['original_returns']()
    contract['distinct_exchange_lanes']()
    contract['local_page_exchange_equations']()
    contract['c8_original_return_boundary']()
    r['inlet']['immutable_reference']()
    print('PASS three native controls /550 consecutive ALL5 transitions '
          '/all three complete ends. K/ПП preserves the cache but creates no '
          'ST reserve; operand8 and В/О reread numeric X before a cache export.', flush=True)
