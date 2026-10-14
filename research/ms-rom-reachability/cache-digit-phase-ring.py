#!/usr/bin/env python3
"""Exact phase/topology test of a conditional signF writer's cleanup.

All native controls are keyboard-only negatives. ST25=F and raw6 changes
occur only in separate symbolic states. Genuine phase offsets are inside
the native trace. No false marker or type7 is inserted in this audit.
"""
import json
from pathlib import Path
import runpy
import subprocess

from z3 import And, BitVec, simplify

root = Path(__file__).resolve().parent
e = runpy.run_path(str(root / 'cache-stack-lift-ring.py'))
w, q = e['w'], e['q']
cases = json.loads(subprocess.check_output(
    ['node', str(root / 'cache-digit-phase-native.cjs'), '--proof-input'], text=True))
raw = (0, 3, 9, 12, 18, 21)
program = (14, 17, 20, 23, 26, 29)


def pins(entry):
    return {name: (entry['state'][name]['keyX'], entry['state'][name]['keyY'])
            for name in e['models']}


def baselines():
    for case in cases:
        state, tags, j = e['make'](case['entries'][0])
        for current, following in zip(case['entries'], case['entries'][1:]):
            assert e['boundary_ip'](state['ik1302']) == current['ip']
            j, _ = e['step'](state, tags, j, pins(current))
            for name in e['names']:
                target = following['state'][name]
                assert all(simplify(state['_wire'][name][field]).as_long() == target[field]
                           for field in ('input', 'output'))
                if name.startswith('ir'):
                    assert [simplify(v).as_long() for v in state[name]] == target['m']
                    assert j == target['tick']
                else:
                    for field in ('r', 'm', 'st'):
                        assert [simplify(v).as_long() for v in getattr(state[name], field)] == target[field]
                    for field in ('s', 's1', 'l', 't', 'carry'):
                        assert simplify(getattr(state[name], field)).as_long() == target[field]
        print('PASS phase baseline', case['report']['phaseOffset'],
              ': ALL5 state/wires/phase at64 native transitions.', flush=True)


def phase_conjugacy():
    # At a macro boundary the IK13 tick is0. All phase dependence of step()
    # is the IR2 position j. In canonical orientation the update is exactly:
    # A' = A[42:] + emitted1306; B' = B[42:] + oldA[:42].
    # Check this index identity for ALL six possible IR2 macro phases using
    # distinct cell labels. It holds for arbitrary values, not just this
    # fixture. The wire formula also uses the same canonical42-cell pieces.
    for j in range(0, 252, 42):
        aa, bb = [('a', k) for k in range(252)], [('b', k) for k in range(252)]
        output = [('out', k) for k in range(42)]
        ca, cb = aa[j:]+aa[:j], bb[j:]+bb[:j]
        aa[j:j+42], bb[j:j+42] = output, aa[j:j+42]
        next_j = (j+42) % 252
        assert aa[next_j:]+aa[:next_j] == ca[42:]+output
        assert bb[next_j:]+bb[:next_j] == cb[42:]+ca[:42]
    saved = None
    for case in cases:
        state, tags, j = e['make'](case['entries'][0])
        oriented = {name: state[name][j:]+state[name][:j]
                    for name in e['names'] if name.startswith('ir')}
        oriented_tags = {name: (tags[name][j:]+tags[name][:j]
                               if name.startswith('ir') else tags[name])
                         for name in e['names']}
        if saved is None:
            saved = state, oriented, oriented_tags, pins(case['entries'][0])
            continue
        old, old_oriented, old_tags, old_pins = saved
        assert oriented_tags == old_tags
        assert pins(case['entries'][0]) == old_pins
        claims = []
        for name in e['names']:
            if name.startswith('ir'):
                claims.append(w['eq'](oriented[name], old_oriented[name]))
            else:
                claims.extend(w['eq'](getattr(state[name], field), getattr(old[name], field))
                              for field in ('r', 'm', 'st'))
                claims.extend(getattr(state[name], field) == getattr(old[name], field)
                              for field in ('s', 's1', 'l', 't', 'carry'))
            claims.extend(state['_wire'][name][field] == old['_wire'][name][field]
                          for field in ('input', 'output'))
        p = q['base_solver'](state['ik1302'], 0x8C)
        w['prove'](p, And(*claims),
                   f'Phase{case["report"]["phaseOffset"]} native inlet is '
                   'EXACTLY phase-conjugate to phase0 in ALL5 states/wires/physical tags')
    print('PASS phase conjugacy: same primary/secondary key pins and '
          'canonical initial state; each42-tick step is independent of IR '
          'phase after canonical rotation. Identical symbolic raw6/program '
          'and C-sign substitutions preserve this relation. The separate '
          '90-macro/keyboard quotient proof transfers to these three inlets.',
          flush=True)


def first_cleanup(case):
    phase = case['report']['phaseOffset']
    entry = case['entries'][0]
    state, tags, j = e['make'](entry)
    state['ik1302'].st[25] = q['N4'](15)
    payload = [BitVec(f'digit_phase{phase}_raw{k}', 4) for k in range(6)]
    for pos, value in zip(raw, payload):
        state['ik1302'].r[pos] = value
    for name in e['names']:
        memory = state[name] if name.startswith('ir') else state[name].m
        for k, (slot, nibble) in enumerate(tags[name]):
            if slot == 'Y' and nibble in program:
                index = program.index(nibble)
                assert simplify(memory[k]).as_long() == (3, 10, 4, 13, 5, 11)[index]
                memory[k] = payload[index]
    before = e['ring'](state, tags)
    p = q['base_solver'](state['ik1302'], 0x8C)
    writes, scans, sequence = [], [], []
    for count in range(70):
        code = e['boundary_ip'](state['ik1302'], p)
        sequence.append(code)
        if code == 0xE5:
            scans.append((count, tags['ik1302'][22], str(simplify(state['ik1302'].m[22]))))
        if code == 0xEE:
            assert tags['ik1302'][34] == ('X', 34)
            w['prove'](p, state['ik1302'].m[34] == 6,
                       f'Phase{phase} first cleanup still reads physical X type6')
            break
        if code == 0xD4:
            writes.append((count, tags['ik1302'][0][0]))
        j, _ = e['step'](state, tags, j, pins(entry), p)
    else:
        raise AssertionError('expected first cleanup EE within70 macros')
    assert sequence[:26] == [0x8C, 0x91, 0x92, 0x93, 0x94, 0x95, 0x98, 0x9A,
                             0x93, 0x94, 0x95, 0x98, 0x9A, 0x8D, 0x8F, 0x82,
                             0x84, 0x75, 0xCA, 0xDB, 0xDC, 0xDE, 0xD4, 0xDD,
                             0xD4, 0x76]
    assert scans == [(27, ('marker', 22), '15')]
    assert len(writes) == 2
    after = e['ring'](state, tags)
    destinations = [slot for _, slot in writes]
    assert destinations[0] != destinations[1]
    for slot, offset in zip(destinations, (3, 0)):
        w['prove'](p, w['eq']([after[slot][k+offset] for k in raw], payload),
                   f'Phase{phase} all256^3 raw triples retained in '
                   f'ordinaryP{case["mapping"]["registerPages"][slot]} before cleanup EE')
    held = [(slot, k) for slot in e['slots'] for k in range(42)
            if k % 3 == 2 or (k % 3 == 0 and k < 36 and slot not in destinations)]
    held += [(slot, k) for slot, indices in case['mapping']['hidden'].items() for k in indices]
    w['prove'](p, w['eq']([after[slot][k] for slot, k in held],
                         [before[slot][k] for slot, k in held]),
               f'Phase{phase} first cleanup holds ALL105 program/56Ms/other13 ordinary registers')
    print('CONDITIONAL phase', phase, 'entry', entry['command'],
          'D4 destinations', destinations, 'E5 scan', scans, flush=True)


if __name__ == '__main__':
    baselines()
    phase_conjugacy()
    for case in cases:
        first_cleanup(case)
    print('PASS three-phase first-cleanup topology: offsets do not bypass '
          'the immediate true marker or change the X/type6 source. '
          'LIMIT: native signF/marker relocation/other timing constructions '
          'and partialK2 are NOT established or globally excluded.', flush=True)
