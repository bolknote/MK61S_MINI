#!/usr/bin/env python3
"""Independent ALL5 replay of source-selected counter/type controls.

Only the immutable reference receives public keys; no emulator setters or
counterfactual state are used here. Period skipping requires an executed
complete five-chip/wire/phase/physical-tag period at unchanged key pins.
"""
import json
from pathlib import Path
import runpy
import subprocess

root = Path(__file__).resolve().parent
contract = runpy.run_path(str(root / 'cache-decoder-source-contract.py'))
r, w, q = contract['r'], contract['w'], contract['q']
early = runpy.run_path(str(root / 'cache-input-mask-early-exit.py'))
engine = early['engine']


def validate(native):
    report = native['report']; assert report['observerIndependent'] is True
    assert report['all105Program56Ms15OrdinaryWordsHeld'] is True
    assert report['partialK2'] is False and report['nativeBC'] is False
    state, tags, phase = engine['make'](native['initial'])
    checkpoints = {e['command']: e for group in ('origin', 'decoder') for e in native[group]}
    keys, end = report['keys'], report['end']; command = selected = 0
    initial_pins = {name: (native['initial']['state'][name]['keyX'],
                          native['initial']['state'][name]['keyY']) for name in engine['models']}
    mapping = {'ШГ→': (7, 9), 'K': (10, 9), '3': (5, 1)}
    boundaries = sorted({0, end, *checkpoints,
        *(i*1120+offset for i in range(len(keys)) for offset in (0, 560, 1120))})
    for following in boundaries:
        if command in checkpoints:
            early['snapshot_matches'](state, phase, checkpoints[command]['state'])
            if report['name'] == 'step_counter8_ready' and command == 20:
                a = state['ik1302']
                assert r['number'](a.r[26]) == 8
                assert q['simplify'](r['ready'](a))
                assert [r['number'](a.r[j]) for j in w['raw']] == [3, 10, 4, 13, 5, 7]
        if command == following: continue
        pins = dict(initial_pins); index, offset = divmod(command, 1120)
        pins['ik1302'] = mapping[keys[index]] if index < len(keys) and offset < 560 else (0, 0)
        if following == command+1 and command in checkpoints and following in checkpoints:
            phase, _ = engine['step'](state, tags, phase, pins); command += 1; selected += 1
        else:
            phase, command = early['advance_fixed'](state, tags, phase, command,
                following, pins, losses=[], label=report['name'])
    assert command == end == 3360
    assert selected == (223 if report['name'] == 'operand3' else 178)
    early['snapshot_matches'](state, phase, native['end']['state'])
    assert r['inlet']['match_controller'](state['ik1302'])
    print(f'PASS {report["name"]}: {selected} consecutive ALL5 transitions '
          '/complete3360 end; all fields/wires/phase; fresh unobserved mirror; '
          '105/56/15 held. No native28/BC/exchange.', flush=True)
    return selected


if __name__ == '__main__':
    r['inlet']['immutable_reference']()
    data = json.loads(subprocess.check_output([
        'node', str(root / 'cache-decoder-source-native.cjs'), '--proof-input'], text=True))
    assert len(data) == 4
    count = sum(validate(native) for native in data)
    assert count == 757
    contract['counter_ready_packet_and_forced_return']()
    r['inlet']['immutable_reference']()
    print('PASS all4 guarded native controls /757 consecutive ALL5 transitions '
          '/four full ends; native counter8+readiness+raw cache at20 is real, '
          'but mandatory original6E replaces the cache. No partialK2.', flush=True)
