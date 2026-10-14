#!/usr/bin/env python3
"""Original1D native controls + distinctly labelled FIVE-FIELD hypothesis.

The protected reference receives only the existing public reader keys. Its
original boundaries/full ends are independently replayed on ALL5. Only a
detached ALL5 model changes A0/R26/type/kind/B8 at the actual1D snapshot.
No head/IP/marker/phase/Ms/ROM is changed. This is NOT native partialK2:
the actual A source is the stored600 marker, not a programme/Ms cache.

LATER AUDIT: cache-bc-77-parity.py globally excludes the required native
odd typeB/operandC inlet. This five-field whole-ring experiment is retained
as a component test OUTSIDE reset reachability, not a candidate key recipe.
"""
import json
from pathlib import Path
import runpy
import subprocess

root = Path(__file__).resolve().parent
source = runpy.run_path(str(root / 'cache-bc-77-producer.py'))
r, w, q = (source[n] for n in ('r', 'w', 'q'))
prior = runpy.run_path(str(root / 'cache-bc-phase-check.py'))
early, engine, physical_data = (prior[n] for n in ('early', 'engine', 'physical_data'))
keymap = {'П→X': (8, 9), '9': (11, 1)}


def replay(native):
    initial, end = native['readerInitial'], native['readerEnd']
    checkpoints = {e['command']: e for group in ('readerOrigin', 'readerCore') for e in native[group]}
    state, tags, phase = engine['make'](initial)
    pins0 = {name: (initial['state'][name]['keyX'], initial['state'][name]['keyY'])
             for name in engine['models']}
    command = selected = 0
    boundaries = sorted({0, end['command'], *checkpoints, 560, 1120, 1680, 2240})
    for following in boundaries:
        if command in checkpoints:
            early['snapshot_matches'](state, phase, checkpoints[command]['state'])
        if following == command: continue
        pins = dict(pins0); index, offset = divmod(command, 1120)
        pins['ik1302'] = keymap[['П→X', '9'][index]] if index < 2 and offset < 560 else (0, 0)
        if following == command+1 and command in checkpoints and following in checkpoints:
            phase, _ = engine['step'](state, tags, phase, pins); command += 1; selected += 1
        else:
            phase, command = early['advance_fixed'](state, tags, phase, command,
                following, pins, losses=[], label=native['report']['name']+'_NATIVE')
    assert selected == 514 and command == 6720
    early['snapshot_matches'](state, phase, end['state'])
    assert r['inlet']['match_controller'](state['ik1302'])
    assert physical_data(state, tags, native) == native['before']
    gate_state, gate_tags, _ = engine['make'](native['gate'])
    actual_ring = {slot: [r['number'](v) for v in values]
                   for slot, values in engine['ring'](gate_state, gate_tags).items()}
    assert actual_ring == native['gateRing'], 'all630 physical tags/tetras agree at actual1D'
    return selected


def conditional_constructor(native):
    state, tags, phase = engine['make'](native['gate'])
    before = physical_data(state, tags, native)
    a = state['ik1302']
    repairs = [(0, 3, 11), (26, 0, 8), (32, 2, 11), (35, 5, 7), (25, 0, 9)]
    for field, old, new in repairs:
        assert r['number'](a.r[field]) == old
        a.r[field] = q['N4'](new)
    assert r['number'](a.r[31]) == 9
    original_a = [r['number'](v) for v in source['A'](a)]
    original_b = [r['number'](v) for v in source['B'](a)]
    expected_m1 = ''.join(f'{n:X}' for n in reversed(original_a))
    expected_ms = ''.join(f'{n:X}' for n in reversed([7, *original_b, 15]))
    pins0 = {name: (native['gate']['state'][name]['keyX'], native['gate']['state'][name]['keyY'])
             for name in engine['models']}
    command = native['gate']['command']; events = []; writes = []; first_c9_reserve = None
    tracked = {0x1D, 0x25, 0xDD, 0xD4, 0x26, 0x28, 0x7E, 0x77, 0x60,
               0x48, 0xBC, 0xBE, 0xC9, 0xF9}
    while command < 6720:
        code = engine['boundary_ip'](state['ik1302'])
        a = state['ik1302']
        if code in tracked:
            events.append({'command': command, 'ip': f'{code:02X}', 'slot': tags['ik1302'][34][0],
                'R26': r['number'](a.r[26]), 'type': r['number'](a.r[32]),
                'kind': r['number'](a.r[35]), 'selector': r['number'](a.r[38]),
                'flags': [r['number'](a.r[j]) for j in (2, 23, 26)],
                'byte': r['number'](w['byte'](a.r[30], a.r[33])),
                'PC': r['number'](w['byte'](a.r[31], a.r[34]))})
        if code == 0xC9 and first_c9_reserve is None:
            assert [r['number'](v) for v in source['A'](a)] == original_b
            assert [r['number'](v) for v in source['ST0'](a)[:9]] == original_a[3:]
            assert [r['number'](v) for v in source['ST1'](a)[9:12]] == original_a[:3]
            raw = [r['number'](a.st[j]) for j in (28, 31, 0, 3, 9, 12)]
            assert raw == [original_a[j//3] for j in w['raw']]
            first_c9_reserve = {'command': command, 'all12Preserved': True, 'raw6': raw}
        if code == 0x35 and command >= 1680: break
        before_ring = engine['ring'](state, tags)
        pins = dict(pins0); pins['ik1302'] = (11, 1) if command < 1680 else (0, 0)
        phase, emitted = engine['step'](state, tags, phase, pins)
        if code in (0xD4, 0xBC):
            after_ring = engine['ring'](state, tags)
            if code == 0xD4:
                assert command == 1289
                assert [r['number'](v) for v in after_ring['X'][0:36:3]] == original_a
            else:
                assert command == 1299
                assert [r['number'](v) for v in after_ring['P9'][1:42:3]] == [7, *original_b, 15]
            changed = {slot: [j for j in range(42)
                if r['number'](before_ring[slot][j]) != r['number'](after_ring[slot][j])]
                for slot in engine['slots']}
            writes.append({'command': command, 'ip': f'{code:02X}',
                'changed': {slot: values for slot, values in changed.items() if values}})
        command += 1
        if command % 150 == 0:
            print(f'{native["report"]["name"]} FIVE_FIELD_HYPOTHESIS: executed to{command:04d}, '
                  f'currentIP{engine["boundary_ip"](state["ik1302"]):02X}', flush=True)
    assert command < 6720, 'no guessed idle exit is allowed'
    first_idle = command
    for following in (2240, 6720):
        if following <= command: continue
        pins = dict(pins0); pins['ik1302'] = (0, 0)
        phase, command = early['advance_fixed'](state, tags, phase, command, following, pins,
            losses=[], label=native['report']['name']+'_FIVE_FIELD_HYPOTHESIS_NOT_NATIVE')
    after = physical_data(state, tags, native)
    assert first_idle == (1797 if native['report']['numericJoint'] else 1681)
    assert phase == 84 and engine['boundary_ip'](state['ik1302']) == 0x35
    assert expected_m1 == '60001000000B' and expected_ms == 'FF939788888887'
    expected_program = list(before['program'])
    if native['report']['numericJoint']: expected_program[99] = 0xF9
    assert before['program'][99] == 0 and after['program'] == expected_program
    assert after['ms'] == {**before['ms'], 'P9': expected_ms}
    expected_registers = list(before['registers']); expected_registers[11] = expected_m1
    assert after['registers'] == expected_registers
    assert [e['command'] for e in events if e['ip'] == 'F9'] == (
        [1379] if native['report']['numericJoint'] else [])
    assert bool(first_c9_reserve) == native['report']['numericJoint']
    assert writes == [
        {'command': 1289, 'ip': 'D4', 'changed': {'X': [0, 21, 33]}},
        {'command': 1299, 'ip': 'BC', 'changed': {'P9': list(range(1, 42, 3))}}]
    assert before == native['before'], 'the native1D gate precedes persistent reader changes'
    full_end = early['complete_fingerprint'](state, tags, phase)
    pins = dict(pins0); pins['ik1302'] = (0, 0)
    for _ in range(30): phase, _ = engine['step'](state, tags, phase, pins)
    assert early['complete_fingerprint'](state, tags, phase) == full_end
    print(json.dumps({'label': 'FIVE_FIELD_HYPOTHESIS_NOT_NATIVE',
        'control': native['report']['name'], 'repairs': repairs,
        'firstIdle35AfterRelease': first_idle, 'endIP': f'{engine["boundary_ip"](state["ik1302"]):02X}',
        'stableFullPeriod': 30, 'expectedM1': expected_m1, 'expectedMs': expected_ms,
        'firstC9SplitReserve': first_c9_reserve, 'events': events, 'writes': writes,
        'programmeChangesFromGate': [(j, old, new) for j, (old, new) in
            enumerate(zip(before['program'], after['program'])) if old != new],
        'MsChangesFromGate': {slot: [before['ms'][slot], word] for slot, word in after['ms'].items()
            if word != before['ms'][slot]},
        'ordinaryChangesFromGate': [(j, old, new) for j, (old, new) in
            enumerate(zip(before['registers'], after['registers'])) if old != new],
        'programmeChangesFromPreparation': [(j, old, new) for j, (old, new) in
            enumerate(zip(native['before']['program'], after['program'])) if old != new],
        'other104ProgrammeHeld': True, 'other7MsWordsHeld': True, 'other14OrdinaryWordsHeld': True,
        'nativeJointConstructor': False, 'MsByteProvenance': False, 'originalAIsProgrammeCache': False,
        'displacedWordsSaved': False, 'partialK2': False}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    r['inlet']['immutable_reference']()
    controls = json.loads(subprocess.check_output([
        'node', str(root / 'cache-bc-77-native.cjs'), '--proof-input'], text=True))
    count = 0
    for native in controls:
        assert native['report']['nativeKeyboardOnly'] and native['report']['observerIndependent']
        assert native['report']['all105Programme56Ms15OrdinaryHeld']
        count += replay(native)
        print(f'PASS NATIVE {native["report"]["name"]}:514 consecutive ALL5 transitions/full6720 '
              'end/fresh unobserved mirror. ORIGINAL1D has type2/kind5/R26zero/B unequal→2E, '
              'not25/77/BC. ActualA is stored600, not codecache.', flush=True)
        conditional_constructor(native)
    assert count == 1028
    r['inlet']['immutable_reference']()
    print('PASS1028 native ALL5 transitions/two complete ends/two fresh unobserved mirrors; '
          'two complete/stable30 FIVE-field whole-ring experiments ONLY in detached ALL5. '
          'Native joint entry, genuine Ms byte, displaced words and partialK2 are still missing.', flush=True)
