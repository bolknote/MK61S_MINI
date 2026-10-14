#!/usr/bin/env python3
"""Short-A8 return93 sign reserve, not a native marker displacement recipe.

The actual keys only displace X/sign0. Local identities admit arbitrary
tick keys and future serial pages. The ALL5 experiment adds ONE late P8
marker tetra to a detached copy, not to the native calculator. Earlier
marker preparation and compatibility with the C8 reader remain unproved.
"""
import json
from pathlib import Path
import runpy
import subprocess

from z3 import And

root = Path(__file__).resolve().parent
w = runpy.run_path(str(root / 'cache-writer-contract.py'))
q = w['q']
engine = runpy.run_path(str(root / 'cache-stack-lift-ring.py'))


def eq(xs, ys):
    return And(*[x == y for x, y in zip(xs, ys)])


def local_return():
    a = q['State']('marker_return93_source')
    p = w['base'](a, 0xEE)
    p.add(a.s1 == 14,
          *[v == k for v, k in zip(w['stack'](a), (0xA8, 0x93, 0xE5))])
    page = q['State']('marker_return93_displaced_page').m
    b = a
    sequence = (0xEE, 0xA8, 0xA9, 0x93, 0x94, 0x95, 0x98, 0x9A)
    result = {}
    for index, code in enumerate(sequence):
        w['prove'](p, w['address'](b) == code,
                   f'short-return93 forced edge {code:02X}', False)
        before = b
        output = []
        b = w['ex'](b, code, *q['arbitrary_keys'](f'marker_return93_keys{index}'),
                    serial_inputs=page if code == 0xEE else None,
                    emitted_outputs=output)
        # The only write is A8's numeric M2 copy, never M1 or M3.
        if code == 0xA8:
            w['prove'](p, And(eq(output[1:36:3], a.m[1:36:3]),
                              eq([output[k] for k in range(42) if k % 3 != 1 or k >= 37],
                                 [before.m[k] for k in range(42) if k % 3 != 1 or k >= 37])),
                       'single A8 writes only the source M2 number, no M1/M3', False)
        else:
            w['prove'](p, eq(output, before.m), f'{code:02X} no outgoing write', False)
        result[code] = b
    sign = page[25]
    w['prove'](p, And(result[0xA8].r[24] == sign,
                      result[0xA9].r[24] == sign,
                      result[0x93].st[24] == sign,
                      result[0x94].st[26] == sign,
                      result[0x95].st[25] == sign,
                      result[0x98].st[25] == sign,
                      result[0x9A].st[25] == sign,
                      w['address'](b) == 0xE5, b.s1 == 0),
               'short A8→A9→93/94/95/98/9A saves ANY displaced sign0..F '
               'via A8→ST24→ST26→ST25; returns E5/S1=0')
    p.add(sign == 15)
    w['prove'](p, b.st[25] == 15,
               'CONDITIONAL real-marker signF survives in ST25, unlike the AC→EE tail')


def replay(case, label):
    entries = case['prefix']
    state, tags, phase = engine['make'](entries[0])
    for current, following in zip(entries, entries[1:]):
        assert engine['boundary_ip'](state['ik1302']) == current['ip']
        pins = {name: (current['state'][name]['keyX'], current['state'][name]['keyY'])
                for name in engine['models']}
        phase, _ = engine['step'](state, tags, phase, pins)
        for name in engine['names']:
            target = following['state'][name]
            for field in ('input', 'output'):
                assert w['number'](state['_wire'][name][field]) == target[field]
            if name.startswith('ir'):
                assert [w['number'](v) for v in state[name]] == target['m']
                assert phase == target['tick']
            else:
                for field in ('r', 'm', 'st'):
                    assert [w['number'](v) for v in getattr(state[name], field)] == target[field]
                for field in ('s', 's1', 'l', 't', 'carry'):
                    assert w['number'](getattr(state[name], field)) == target[field]
    print(f'PASS native {label}:{len(entries)-1} consecutive ALL5 transitions, '
          'ALL R/ST/M/scalars/wires/phase.', flush=True)


def fixed_pins(case, command):
    entries = [e for e in case['keySchedule'] if e['command'] <= command]
    assert entries
    return entries[-1]['pins']


def conditional_marker(case, *, boundary_hook=None, return_context=False, log=True):
    entry = case['prefix'][0]
    state, tags, phase = engine['make'](entry)
    for name in engine['names']:
        memory = state[name] if name.startswith('ir') else state[name].m
        for index, (slot, tetra) in enumerate(tags[name]):
            if (slot, tetra) == ('P8', 22):
                assert w['number'](memory[index]) == 0
                memory[index] = q['N4'](15)
    initial = engine['ring'](state, tags)
    changes, writes = [], []
    first_a8 = None
    displaced_word = None
    end = None
    for index in range(512):
        code = engine['boundary_ip'](state['ik1302'])
        slot = tags['ik1302'][1][0]
        pins = fixed_pins(case, entry['command'] + index)
        if boundary_hook is not None:
            boundary_hook(index, code, slot, state, tags, phase)
        if code == 0x35 and pins['ik1302'] == [0, 0]:
            end = index
            break
        before_sign = w['number'](state['ik1302'].st[25])
        if code == 0xA8 and first_a8 is None:
            first_a8 = slot
            displaced_word = ''.join(f'{w["number"](v):X}'
                                     for v in reversed(state['ik1302'].m[1:36:3]))
        phase, emitted = engine['step'](state, tags, phase, pins)
        after_sign = w['number'](state['ik1302'].st[25])
        if before_sign != after_sign:
            changes.append({'offset': index, 'ip': f'{code:02X}', 'slot': slot,
                            'from': before_sign, 'to': after_sign})
        if code == 0xD4:
            writes.append({'offset': index, 'slot': slot,
                           'sign': w['number'](emitted['ik1302'][24])})
    final = engine['ring'](state, tags)
    assert first_a8 == 'marker'
    assert displaced_word == '000FFFFFFFFF'
    assert changes[0] == {'offset': 14, 'ip': '95', 'slot': 'Y', 'from': 0, 'to': 15}
    assert end == 430, 'same fixed key schedule, first released35 boundary'
    assert writes == [], 'this whole continuation never executes D4'
    assert w['number'](final['Y'][24]) == 0
    program_changes = sum(w['number'](final[s][k]) != w['number'](initial[s][k])
                          for s in engine['slots'] for k in range(2, 42, 3))
    assert program_changes == 0
    report = {'hypothesis': 'ONE late detached P8.M2[22]=F before final E5',
              'nativeRecipe': False, 'firstA8Target': first_a8,
              'displacedWord': displaced_word,
              'savedSignChanges': changes, 'D4Writes': writes,
              'CSignBefore': w['number'](initial['Y'][24]),
              'CSignAfter': w['number'](final['Y'][24]),
              'released35At': end, 'bound': 512,
              'programTetraChanges': program_changes}
    if log:
        print('CONDITIONAL ALL5 late-marker continuation:', json.dumps(report), flush=True)
        print('SCOPE: complete CONSTANT late-entry counterfactual, fixed native key '
              'schedule. The marker is NOT prepared by keys; no earlier-reader '
              'stitch, native C-signF, Ms exchange or partial K2.', flush=True)
    if return_context:
        return {'report': report, 'state': state, 'tags': tags, 'phase': phase,
                'initialRing': initial, 'entry': entry}
    return report


def odd_compensation():
    a = q['State']('marker_return93_odd_compensation')
    p = w['base'](a, 0xA8)
    p.add((a.s1 & 1) == 1)
    b = w['ex'](a, 0xA8, *q['arbitrary_keys']('marker_return93_odd_keys'))
    w['prove'](p, And(w['address'](b) == 0xA8,
                      b.s1 == a.s1 + q['N4'](2), b.st[25] == a.st[25]),
               'odd A8 is invariant for ANY future keys/pages: no A9/93, '
               'ST25 held. Induction closes the native early-X compensation')


if __name__ == '__main__':
    local_return()
    odd_compensation()
    case = json.loads(subprocess.check_output(
        ['node', str(root / 'cache-marker-return93-native.cjs'), '--proof-input'], text=True))
    replay(case, 'short-return93:target X/sign0, NOT marker')
    replay(case['compensation'], 'early-X compensation:odd A8, NOT a finite shift')
    conditional_marker(case)
