#!/usr/bin/env python3
"""ALL5 replay of real49/BE entry, including the exact40 flag overwrite."""
import json
from pathlib import Path
import runpy
import subprocess

root = Path(__file__).resolve().parent
source = runpy.run_path(str(root / 'cache-be-ancestor-contract.py'))
r, w = source['r'], source['w']
early = runpy.run_path(str(root / 'cache-input-mask-early-exit.py'))
engine = early['engine']
mapping = {'П→X': (8, 9), '9': (11, 1), 'F': (11, 9), 'Сx': (10, 8), '1': (3, 1)}


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
            if not reader and command in (2264, 2280, 2314, 2315, 2325, 2340, 2341):
                a = state['ik1302']; ip = r['number'](w['ip'](a))
                assert ip == {2264: 0x8C, 2280: 0x82, 2314: 0x40, 2315: 0x41,
                              2325: 0x47, 2340: 0xBE, 2341: 0xB0}[command]
                if command == 2264: assert r['number'](a.r[23]) == 0
                if command == 2280: assert r['number'](a.r[26]) == 0
                if command == 2314: assert r['number'](a.st[23]) == report['C']
                if command in (2315, 2325): assert r['number'](a.st[23]) == 0
                if command == 2340:
                    assert [r['number'](a.r[j]) for j in (2, 23, 26)] == [5, 0, 0]
        if command == following: continue
        pins = dict(initial_pins); index, offset = divmod(command, 1120)
        pins['ik1302'] = mapping[keys[index]] if index < len(keys) and offset < 560 else (0, 0)
        if following == command+1 and command in checkpoints and following in checkpoints:
            phase, _ = engine['step'](state, tags, phase, pins); command += 1; selected += 1
        else:
            phase, command = early['advance_fixed'](state, tags, phase, command,
                following, pins, losses=[], label=report['name']+('_reader' if reader else '_suffix'))
    assert command == end['command']
    assert selected == (438 if reader else 188), (report['name'], reader, selected)
    early['snapshot_matches'](state, phase, end['state'])
    assert r['inlet']['match_controller'](state['ik1302'])
    return selected


if __name__ == '__main__':
    r['inlet']['immutable_reference']()
    controls = json.loads(subprocess.check_output([
        'node', str(root / 'cache-be-ancestor-native.cjs'), '--proof-input'], text=True))
    assert len(controls) == 2
    count = 0
    for native in controls:
        report = native['report']
        assert report['nativeKeyboardOnly'] and report['observerIndependent']
        assert report['all105Programme56Ms15OrdinaryHeld'] and report['nativeOriginalBEEntry']
        assert not report['nativeWriterGateOpen'] and not report['persistentMsCopy'] and not report['partialK2']
        local = replay(native, reader=True)+replay(native, reader=False); count += local
        source['native_sign8_counterfactual'](native)
        print(f'PASS {report["name"]}:{local} consecutive ALL5 transitions; complete6720/5040 '
              'ends, all fields/wires/phase; fresh unobserved mirrors/105/56/15. '
              'ORIGINAL49/full91/BE reached,40 overwrites the third-buffer flag, BE→B0. '
              'Separate sign8-only hypothesis also fails the writer.', flush=True)
    assert count == 1252
    source['first_restore_origin']()
    source['two_restore_flag_origin']()
    source['complete_82_writer_interfaces']()
    source['original_47_conveyor']()
    r['inlet']['immutable_reference']()
    print('PASS native originalBE entry in two controls,1252 consecutive ALL5 transitions/'
          'four complete ends. Upstream byte/flag origins proved; no native writer or partialK2.', flush=True)
