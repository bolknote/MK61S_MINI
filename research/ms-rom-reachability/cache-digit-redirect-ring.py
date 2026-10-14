#!/usr/bin/env python3
"""Physical early preparations for a CONDITIONAL reader→DB reserve.

The reference uses only keys/passive snapshots. Its continuous lastAC→8C
trace is replayed against ALL5 fields/wires/phase at every segment boundary;
long constant-IP/key runs are shortened only after exact full-state periods
are proved. In the detached variant, ALL changes precede AC: ordinary C's
sign F, an extra working M2 marker F, and a different M2 header7. No saved
ST25 assignment, post-reader repair, controller patch or native injection.
All256^3 program triples vary jointly. This is NOT a key constructor or K2.
"""
import json
from pathlib import Path
import runpy
import subprocess
import sys

from z3 import And, BitVec, simplify

root = Path(__file__).resolve().parent
e = runpy.run_path(str(root / 'cache-stack-lift-ring.py'))
w, q = e['w'], e['q']
data = json.loads(subprocess.check_output(
    ['node', str(root / 'cache-digit-redirect-native.cjs'), '--proof-input'], text=True))
raw, program = (0, 3, 9, 12, 18, 21), (14, 17, 20, 23, 26, 29)


def capture(state, tags, phase):
    return ({name: list(state[name]) if name.startswith('ir') else state[name]
             for name in e['names']}, state['_wire'],
            {name: list(tags[name]) for name in e['names']}, phase)


def equality(state, tags, phase, saved):
    old, wires, old_tags, old_phase = saved
    assert phase == old_phase and tags == old_tags
    claims = []
    for name in e['names']:
        if name.startswith('ir'):
            claims.append(w['eq'](state[name], old[name]))
        else:
            claims.extend(w['eq'](getattr(state[name], field), getattr(old[name], field))
                          for field in ('r', 'm', 'st'))
            claims.extend(getattr(state[name], field) == getattr(old[name], field)
                          for field in ('s', 's1', 'l', 't', 'carry'))
        claims.extend(state['_wire'][name][field] == wires[name][field]
                      for field in ('input', 'output'))
    return And(*claims)


def native_equal(state, tags, phase, entry, p):
    target, target_tags, target_phase = e['make'](entry)
    w['prove'](p, equality(state, tags, phase, capture(target, target_tags, target_phase)),
               f'Native continuous boundary at{entry["command"]}/{entry["ip"]:02X}', False)


def set_physical(state, tags, slot, nibble, value):
    matches = 0
    for name in e['names']:
        memory = state[name] if name.startswith('ir') else state[name].m
        for k, tag in enumerate(tags[name]):
            if tag == (slot, nibble):
                memory[k] = value
                matches += 1
    assert matches == 1


def repeated(p, claim):
    p.push()
    p.add(~claim)
    answer = p.check()
    p.pop()
    assert answer in (q['sat'], q['unsat'])
    return answer == q['unsat']


def segment_run(state, tags, phase, segment, p, label):
    code, steps, pins = segment['ip'], segment['steps'], segment['pins']
    elapsed, skipped, period_found = 0, 0, False
    while elapsed < steps:
        if steps-elapsed >= 60 and not period_found:
            # Warm up for one full30, then prove a second30 repeats ALL
            # state/wires/phase/tags. A controller self-edge is not enough.
            for _ in range(30):
                assert e['boundary_ip'](state['ik1302'], p) == code, (label, code, elapsed)
                phase, _ = e['step'](state, tags, phase, pins, p)
                elapsed += 1
            saved = capture(state, tags, phase)
            for _ in range(30):
                assert e['boundary_ip'](state['ik1302'], p) == code, (label, code, elapsed)
                phase, _ = e['step'](state, tags, phase, pins, p)
                elapsed += 1
            if repeated(p, equality(state, tags, phase, saved)):
                skip = (steps-elapsed)//30*30
                elapsed += skip
                skipped += skip
                period_found = True
        else:
            assert e['boundary_ip'](state['ik1302'], p) == code, (label, code, elapsed)
            phase, _ = e['step'](state, tags, phase, pins, p)
            elapsed += 1
    return phase, skipped


def source_run(state, tags, phase, p, label, baseline=False):
    skipped, elapsed, differences = 0, 0, []
    for index, segment in enumerate(data['segments']):
        if baseline:
            native_equal(state, tags, phase, segment['start'], p)
        if not baseline and segment['steps'] < 60:
            for local in range(segment['steps']):
                code = e['boundary_ip'](state['ik1302'], p)
                if code == 0x8C:
                    inlet_pins = {name: (data['prefix'][0]['state'][name]['keyX'],
                                         data['prefix'][0]['state'][name]['keyY'])
                                  for name in e['models']}
                    assert all(tuple(s['pins'][name]) == inlet_pins[name]
                               for s in data['segments'][index:] for name in e['models'])
                    print(label, 'first8C at fixed source macro', elapsed,
                          'native-length delta', elapsed-data['report']['sourceToInletMacros'],
                          'short-segment route differences', differences, flush=True)
                    return phase, elapsed
                if code != segment['ip']:
                    differences.append((elapsed, segment['ip'], code))
                phase, _ = e['step'](state, tags, phase, segment['pins'], p)
                elapsed += 1
            n = 0
        else:
            phase, n = segment_run(state, tags, phase, segment, p, label)
            elapsed += segment['steps']
        skipped += n
        if index % 100 == 0:
            print(label, 'source segment', index, f'{segment["ip"]:02X}',
                  'proved-period skipped macros', skipped, flush=True)
    assert e['boundary_ip'](state['ik1302'], p) == 0x8C
    if baseline:
        native_equal(state, tags, phase, data['prefix'][0], p)
    print(label, 'continuous AC→8C:', data['report']['sourceToInletMacros'],
          'fixed macros /', len(data['segments']), 'segments; skipped only',
          skipped, 'proved full-state-period macros; short-segment route differences',
          [(n, f'{old:02X}', f'{new:02X}') for n, old, new in differences], flush=True)
    return phase, elapsed


def baseline():
    state, tags, phase = e['make'](data['source'][0])
    p = q['base_solver'](state['ik1302'], 0xAC)
    phase, _ = source_run(state, tags, phase, p, 'BASELINE', baseline=True)
    for current, following in zip(data['prefix'], data['prefix'][1:]):
        pins = {name: (current['state'][name]['keyX'], current['state'][name]['keyY'])
                for name in e['models']}
        phase, _ = e['step'](state, tags, phase, pins, p)
        native_equal(state, tags, phase, following, p)
    print('PASS continuous baseline: ALL5 R/ST/M/scalars/wires/phase/tags '
          'at321 segment boundaries +64 consecutive native writer-prefix transitions.',
          flush=True)


def conditional(marker, header, prepare_header=True):
    label = (f'CONDITIONAL extra{marker}/header{header}' if prepare_header else
             f'CONDITIONAL native{header}7/extra{marker}')
    state, tags, phase = e['make'](data['source'][0])
    payload = [BitVec(f'digit_redirect_{marker}_raw{k}', 4) for k in range(6)]
    original = e['ring'](state, tags)
    assert [simplify(original['Y'][k]).as_long() for k in program] == [3, 10, 4, 13, 5, 11]
    for k, value in zip(program, payload):
        set_physical(state, tags, 'Y', k, value)
    # Every counterfactual precedes AC, rather than being injected at8C.
    set_physical(state, tags, 'Y', 24, q['N4'](15))
    set_physical(state, tags, marker, 22, q['N4'](15))
    if prepare_header:
        set_physical(state, tags, header, 34, q['N4'](7))
    else:
        assert data['report']['nativeEarlyT7'] and header == 'T'
        assert simplify(e['ring'](state, tags)[header][34]).as_long() == 7
    before = e['ring'](state, tags)
    p = q['base_solver'](state['ik1302'], 0xAC)
    phase, inlet_at = source_run(state, tags, phase, p, label)
    inlet_ring = e['ring'](state, tags)
    w['prove'](p, And(state['ik1302'].st[25] == 15,
                     state['ik1302'].r[41] == 0,
                     w['eq']([state['ik1302'].r[k] for k in raw], payload),
                     inlet_ring[marker][22] == 15,
                     inlet_ring[header][34] == 7,
                     inlet_ring['X'][34] == 6),
               label+f' early physical preparation survives {inlet_at} fixed '
               'AC→first8C macros with ST25=F, fresh raw6, R41=0, X stilltype6')
    pins = {name: (data['prefix'][0]['state'][name]['keyX'],
                   data['prefix'][0]['state'][name]['keyY']) for name in e['models']}
    sequence, reads, hits, d4 = [], [], [], []
    release_at = (data['report']['sourceToInletMacros']+
                  data['report']['releaseCount']-inlet_at)
    finish_at = release_at+360
    first_idle = None
    for count in range(finish_at):
        if count >= release_at:
            pins['ik1302'] = (0, 0)
        code = e['boundary_ip'](state['ik1302'], p)
        sequence.append(code)
        if code == 0xE5 and repeated(p, state['ik1302'].m[22] == 15):
            hits.append((count, tags['ik1302'][22][0]))
        if code == 0xEE:
            tag, value = tags['ik1302'][34], state['ik1302'].m[34]
            expected = 6 if not reads else 7
            w['prove'](p, value == expected,
                       label+f' EE source{len(reads)} at{count} physically {tag} type{expected}')
            reads.append((count, tag))
        if code == 0xD4:
            d4.append((count, tags['ik1302'][0][0]))
        if code == 0x35 and first_idle is None:
            first_idle = count
        phase, _ = e['step'](state, tags, phase, pins, p)
        if count % 180 == 0:
            print(label, 'writer macro', count, f'{code:02X}', flush=True)
    assert reads == [(30, ('X', 34)),
                     (64 if marker == 'Y' else 63, (header, 34)),
                     (105, ('X', 34))]
    assert d4 == [(22, 'Q'), (24, 'P8')]
    assert first_idle == release_at+1
    assert e['boundary_ip'](state['ik1302'], p) == 0x35
    after = e['ring'](state, tags)
    for slot, offset in (('Q', 3), ('P8', 0)):
        w['prove'](p, w['eq']([after[slot][k+offset] for k in raw], payload),
                   label+' ALL256^3 raw triples retained at released idle in ordinaryP'+
                   data['mapping']['registerPages'][slot])
    held = [(slot, k) for slot in e['slots'] for k in range(42)
            if k % 3 == 2 or (k % 3 == 0 and k < 36 and slot not in ('Q', 'P8'))]
    held += [(slot, k) for slot, indices in data['mapping']['hidden'].items() for k in indices]
    w['prove'](p, w['eq']([after[slot][k] for slot, k in held],
                         [before[slot][k] for slot, k in held]),
               label+' ALL105 program/56Ms/other13 registers held relative '
               'to the early prepared input; destinations are overwritten')
    saved = capture(state, tags, phase)
    for _ in range(30):
        assert e['boundary_ip'](state['ik1302'], p) == 0x35
        phase, _ = e['step'](state, tags, phase, pins, p)
    w['prove'](p, equality(state, tags, phase, saved),
               label+' ALL5 state/wires/phase/tags repeat after30 quiet macros')
    print(label, 'E5 hits', hits, 'EE reads', reads,
          'first released35', first_idle, 'pre-idle route',
          ' '.join(f'{ip:02X}' for ip in sequence[:124]), flush=True)
    bank_note = ('Both extra fields are working M2, not Ms.' if header == 'T'
                 else 'The extra U header is Ms: held relative to the changed input only.')
    prepared_note = ('Three early physical hypotheses are not a native maker.' if prepare_header
                     else 'T-type7 is native; ONLY C-signF and X-markerF are hypothetical.')
    print('SCOPE:', label, prepared_note, bank_note, 'Ordinary C signF is prepared. '
          'Not arbitrary Ms geometry, readback, Ms/program exchange or partialK2.', flush=True)


if __name__ == '__main__':
    if '--conditional-only' not in sys.argv:
        baseline()
    if '--baseline-only' not in sys.argv:
        if '--y-only' not in sys.argv:
            conditional('X', 'T')
        if '--x-only' not in sys.argv:
            conditional('Y', 'U')
