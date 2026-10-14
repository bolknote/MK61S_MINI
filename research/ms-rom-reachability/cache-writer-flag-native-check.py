#!/usr/bin/env python3
"""Independent ALL5 checks of the source-directed C0/C1 interventions.

The detached ring receives the actual native state, never a repaired flag,
byte, address or return. Each selected consecutive boundary and complete
reader/suffix end compares all five chips, physical wires and phase.
Period skipping requires an executed complete state/tags/phase recurrence.
"""
import json
from pathlib import Path
import runpy
import subprocess
import sys

root = Path(__file__).resolve().parent
source = runpy.run_path(str(root / 'cache-writer-flag-repair.py'))
r, w, q = source['r'], source['w'], source['q']
early = runpy.run_path(str(root / 'cache-input-mask-early-exit.py'))
engine = early['engine']
mapping = {'П→X': (8, 9), '9': (11, 1), 'K': (10, 9),
           '0': (2, 1), 'ПП': (5, 9), '8': (10, 1)}


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
            if not reader and command == report['firstD3']:
                a = state['ik1302']
                assert [r['number'](a.r[j]) for j in (2, 23, 26)] == [5, 0, 0]
                assert r['number'](a.st[22]) == report['C']
            if not reader and command == report['firstD3']+1:
                assert r['number'](w['ip'](state['ik1302'])) == 0xD5
            if not reader and report.get('lateWriterFields') and command == 1198:
                assert r['number'](w['ip'](state['ik1302'])) == 0xE4
                assert [r['number'](state['ik1302'].r[j]) for j in (2, 23, 26)] == [5, 1, 0]
        if command == following: continue
        pins = dict(initial_pins); index, offset = divmod(command, 1120)
        pins['ik1302'] = mapping[keys[index]] if index < len(keys) and offset < 560 else (0, 0)
        if following == command+1 and command in checkpoints and following in checkpoints:
            phase, _ = engine['step'](state, tags, phase, pins); command += 1; selected += 1
        else:
            phase, command = early['advance_fixed'](state, tags, phase, command,
                following, pins, losses=[], label=report['name']+('_reader' if reader else '_suffix'))
    assert command == end['command']
    expected = 438 if reader else (194 if report['kind'] == 'nop' else 240)
    assert selected == expected, (report['name'], reader, selected, expected)
    early['snapshot_matches'](state, phase, end['state'])
    assert r['inlet']['match_controller'](state['ik1302'])
    return selected


def validate(native):
    report = native['report']
    assert report['nativeKeyboardOnly'] and report['observerIndependent']
    assert report['all105Programme56Ms15OrdinaryHeld']
    assert not report['nativeFlagRepair'] and not report['persistentMsCopy'] and not report['partialK2']
    reader_count = replay(native, reader=True)
    suffix_count = replay(native, reader=False)
    print(f'PASS {report["name"]}: reader{reader_count} + suffix{suffix_count} consecutive '
          f'ALL5 transitions, complete6720/{report["end"]} ends, all fields/wires/phase; '
          'fresh completely unobserved reader+suffix mirror. First D3→D5, not63.', flush=True)
    return reader_count+suffix_count


if __name__ == '__main__':
    r['inlet']['immutable_reference']()
    joint = '--joint' in sys.argv
    controls = json.loads(subprocess.check_output([
        'node', str(root / 'cache-writer-flag-native.cjs'), '--proof-input',
        *(['--joint'] if joint else [])], text=True))
    assert len(controls) == (1 if joint else 4)
    count = sum(validate(native) for native in controls)
    assert count == (632 if joint else 2620)
    source['preserving_clearers']()
    source['independent_writer_interface']()
    source['nop_flag_barrier']()
    source['late_joint_return']()
    # The new prefix interface composes with this existing universal
    # writer specification; neither creates a native Ms-byte source.
    source['source']['opaque_page_families']()
    r['inlet']['immutable_reference']()
    print(f'PASS {len(controls)} fresh native controls,{count} consecutive ALL5 transitions, '
          f'{len(controls)*2} complete reader/suffix ends. Conditional independent-byte/address '
          'writer interface is proved; no native writer inlet or partialK2.', flush=True)
