#!/usr/bin/env python3
"""Native ALL5 control + separately labelled TYPE3-only whole-ring test.

The stock reference is NEVER repaired. Only the detached ALL5 model gets
R32=3 at the actual54 snapshot; every other field/ROM/wire/page is native.
The positive test writes one programme byte and overwrites one Ms word;
it is NOT a native sequence, safe exchange, or opaque Ms-byte transfer.
"""
import json
from pathlib import Path
import runpy
import subprocess

root = Path(__file__).resolve().parent
source = runpy.run_path(str(root / 'cache-bc-writer-contract.py'))
r, w, q = source['r'], source['w'], source['q']
early = runpy.run_path(str(root / 'cache-input-mask-early-exit.py'))
engine = early['engine']
mapping = {'П→X': (8, 9), '9': (11, 1), 'K': (10, 9), '6': (8, 1)}


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
            if not reader and command == 1127:
                a = state['ik1302']
                assert r['number'](w['ip'](a)) == 0x54
                assert [r['number'](a.r[j]) for j in (29, 32)] == [report['operand'], 0]
        if command == following: continue
        pins = dict(initial_pins); index, offset = divmod(command, 1120)
        pins['ik1302'] = mapping[keys[index]] if index < len(keys) and offset < 560 else (0, 0)
        if following == command+1 and command in checkpoints and following in checkpoints:
            phase, _ = engine['step'](state, tags, phase, pins); command += 1; selected += 1
        else:
            phase, command = early['advance_fixed'](state, tags, phase, command,
                following, pins, losses=[], label=report['name']+('_reader' if reader else '_suffix'))
    expected_selected = 438 if reader else 64+report['last']-report['start']
    assert command == end['command'] and selected == expected_selected
    early['snapshot_matches'](state, phase, end['state'])
    assert r['inlet']['match_controller'](state['ik1302'])
    return selected


def physical_data(state, tags, native):
    ring = engine['ring'](state, tags)
    number = r['number']
    program = [16*number(ring[p['hi']['slot']][p['hi']['n']])+
               number(ring[p['lo']['slot']][p['lo']['n']]) for p in native['topology']['programMap']]
    ms = {slot: ''.join(f'{number(ring[slot][40-3*i]):X}' for i in range(14))
          for slot in native['before']['ms']}
    registers = [None]*15
    for slot, register in native['topology']['registerPages'].items():
        registers[int(register, 16)] = ''.join(f'{number(ring[slot][33-3*i]):X}' for i in range(12))
    assert all(v is not None for v in registers)
    return {'program': program, 'ms': ms, 'registers': registers}


def conditional_type3(native):
    source['matching_native_control'](native)
    state, tags, phase = engine['make'](native['gate'])
    before = physical_data(state, tags, native)
    assert before == native['before'], 'actual54 ring matches all105/56/15 original data'
    # The ONE and ONLY mutation, confined to the detached ALL5 model.
    assert r['number'](state['ik1302'].r[32]) == 0
    state['ik1302'].r[32] = q['N4'](3)
    expected_word = ''.join(f'{n:X}' for n in reversed([
        7, *native['gate']['state']['ik1302']['r'][1:36:3], 15]))
    initial_pins = {name: (native['gate']['state'][name]['keyX'], native['gate']['state'][name]['keyY'])
                    for name in engine['models']}
    command = native['gate']['command']; events = []
    assert command == 1127
    # Execute EVERY boundary until the first native-shaped idle35. No
    # feedback keys or guessed return/marker exit is inserted.
    while command < native['end']['command']:
        code = engine['boundary_ip'](state['ik1302'])
        if code in (0xBC, 0xBE, 0xC9, 0xF9, 0x35):
            a = state['ik1302']
            events.append({'command': command, 'ip': f'{code:02X}', 'slot': tags['ik1302'][34][0],
                'flags': [r['number'](a.r[j]) for j in (2, 23, 26)],
                'byte': r['number'](w['byte'](a.r[30], a.r[33])),
                'PC': r['number'](w['byte'](a.r[31], a.r[34]))})
        if code == 0x35: break
        pins = dict(initial_pins); pins['ik1302'] = (8, 1) if command < 1680 else (0, 0)
        phase, _ = engine['step'](state, tags, phase, pins); command += 1
    assert command < native['end']['command'], 'a real idle35 exit must be found, not assumed'
    first_idle = command
    assert [e for e in events if e['ip'] == 'BC'] == [
        {'command': 1134, 'ip': 'BC', 'slot': 'P9', 'flags': [5, 0, 0], 'byte': 0xF9, 'PC': 0x90}]
    be = next(e for e in events if e['ip'] == 'BE')
    assert be['command'] == 1149 and be['PC'] == 0x99 and be['byte'] == 0x90
    assert be['flags'] == ([5, 1, 0] if native['report']['numericJoint'] else [0, 0, 0])
    patches = [e for e in events if e['ip'] == 'F9']
    assert bool(patches) == native['report']['numericJoint']
    if patches: assert patches[0]['command'] == 1214 and patches[0]['byte'] == 0x90
    # Fixed physical key release, then full suffix end. Acceleration needs
    # an executed full ALL5/wires/phase/tags recurrence with constant pins.
    for end in sorted({1680, 2240, native['end']['command']}):
        if end <= command: continue
        pins = dict(initial_pins); pins['ik1302'] = (8, 1) if command < 1680 else (0, 0)
        phase, command = early['advance_fixed'](state, tags, phase, command, end, pins,
            losses=[], label=native['report']['name']+'_TYPE3_ONLY_HYPOTHESIS')
    assert phase == 84 and engine['boundary_ip'](state['ik1302']) == 0x35
    after = physical_data(state, tags, native)
    expected = list(before['program'])
    if native['report']['numericJoint']: expected[99] = 0x90
    assert after['program'] == expected
    assert after['registers'] == before['registers'], 'all15 ordinary words held in this conditional case'
    assert after['ms'] == {**before['ms'], 'P9': expected_word}, 'exactly one14-tetra Ms word overwritten'
    end_fingerprint = early['complete_fingerprint'](state, tags, phase)
    quiet_pins = dict(initial_pins); quiet_pins['ik1302'] = (0, 0)
    for _ in range(30): phase, _ = engine['step'](state, tags, phase, quiet_pins)
    assert early['complete_fingerprint'](state, tags, phase) == end_fingerprint
    result = {'label': 'TYPE3_ONLY_HYPOTHESIS_NOT_NATIVE', 'control': native['report']['name'],
        'onlyRepair': {'field': 'primary.R32 at54', 'native': 0, 'hypothesis': 3},
        'firstIdle35': first_idle, 'endCommand': command, 'stableFullPeriod': 30,
        'events': events, 'programme99': {'before': before['program'][99], 'after': after['program'][99]},
        'MsP9': {'before': before['ms']['P9'], 'after': after['ms']['P9']},
        'other104ProgrammeHeld': True, 'other7MsWordsHeld': True, 'all15OrdinaryHeld': True,
        'nativeType3Constructor': False, 'opaqueMsByteProvenance': False,
        'displacedMsWordSaved': False, 'exchange': False, 'partialK2': False}
    print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    r['inlet']['immutable_reference']()
    controls = json.loads(subprocess.check_output([
        'node', str(root / 'cache-bc-phase-native.cjs'), '--proof-input'], text=True))
    assert len(controls) == 2
    count = 0
    for native in controls:
        report = native['report']
        assert report['nativeKeyboardOnly'] and report['observerIndependent']
        assert report['all105Programme56Ms15OrdinaryHeld'] and not report['nativeBC']
        count += replay(native, reader=True)+replay(native, reader=False)
        print(f'PASS NATIVE {report["name"]}:682 consecutive ALL5 transitions, complete6720/3360 '
              'ends, all fields/wires/phase/fresh unobserved mirrors. Type0, no BC or writer.', flush=True)
        conditional_type3(native)
    assert count == 1364
    source['bc_writer_families']()
    r['inlet']['immutable_reference']()
    print('PASS1364 native ALL5 transitions/four COMPLETE ends + two separately labelled '
          'TYPE3-only whole-ring experiments/stable30 ends. No reference repair, '
          'native type3 inlet, arbitrary Ms-byte copy, exchange or partialK2.', flush=True)
