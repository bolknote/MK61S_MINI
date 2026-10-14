#!/usr/bin/env python3
"""Native real-marker source and exact local sign/payload loss at EE.

Only the native driver uses the calculator, through keys and frames. All
paired experiments below are detached Z3 states with common arbitrary key
pins/future serial inputs. They are not alternate native marker recipes.
"""
import json
from pathlib import Path
import runpy
import subprocess

from z3 import And, Solver, simplify

root = Path(__file__).resolve().parent
w = runpy.run_path(str(root / 'cache-writer-contract.py'))
q = w['q']
engine = runpy.run_path(str(root / 'cache-stack-lift-ring.py'))


def equal(left, right):
    return And(*[x == y for field in ('r', 'st', 'm')
                 for x, y in zip(getattr(left, field), getattr(right, field))],
               *[getattr(left, field) == getattr(right, field)
                 for field in ('s', 's1', 'l', 't', 'carry')])


def ee_loss():
    a = q['State']('real_marker_ee_left');other = q['State']('real_marker_ee_other')
    b = a.copy()
    # Old A9/R27 can influence L. Do not claim that EE forgets ALL12
    # fields. The sign and ALL6 cache payload positions are in the other11.
    for k in range(0, 36, 3):
        if k != 27:
            b.r[k] = other.r[k]
    p = w['base'](a, 0xEE)
    keys = q['arbitrary_keys']('real_marker_ee_keys')
    serial = q['State']('real_marker_ee_serial').m
    outputs, results = [], []
    for entry in (a, b):
        output = []
        results.append(w['ex'](entry, 0xEE, *keys, serial_inputs=serial,
                               emitted_outputs=output))
        outputs.append(output)
    w['prove'](p, And(equal(*results),
                      *[x == y for x, y in zip(*outputs)],
                      *[outputs[0][k] == a.m[k] for k in range(42)]),
               'EE forgets ALL11 old A fields other than A9 in ALL primary '
               'fields/output: sign A8 and ALL6 cached raw tetras lost; no new ring copy')
    print('EXCEPTION: old A9/R27 can affect scalar L; a total ALL12-state-loss '
          'claim would be false. Earlier external copies are not excluded.', flush=True)


def native_replay(case):
    events = case['sourceEvents'];a = w['constant'](events[0])
    for event, following in zip(events, events[1:]):
        assert w['number'](w['address'](a)) == event['ip']
        a = w['ex'](a, event['ip'], event['keyX'], event['keyY'],
                    serial_inputs=[q['N4'](v) for v in following['m']])
        for field in ('r', 'm', 'st'):
            assert [w['number'](v) for v in getattr(a, field)] == following[field]
        for field in ('s', 's1', 'l', 't', 'carry'):
            assert w['number'](getattr(a, field)) == following[field]
    state, tags, phase = engine['make'](case['prefix'][0])
    for current, following in zip(case['prefix'], case['prefix'][1:]):
        assert engine['boundary_ip'](state['ik1302']) == current['ip']
        pins = {name: (current['state'][name]['keyX'], current['state'][name]['keyY'])
                for name in engine['models']}
        phase, _ = engine['step'](state, tags, phase, pins)
        for name in engine['names']:
            target = following['state'][name]
            for field in ('input', 'output'):
                assert simplify(state['_wire'][name][field]).as_long() == target[field]
            if name.startswith('ir'):
                assert [w['number'](v) for v in state[name]] == target['m']
                assert phase == target['tick']
            else:
                for field in ('r', 'm', 'st'):
                    assert [w['number'](v) for v in getattr(state[name], field)] == target[field]
                for field in ('s', 's1', 'l', 't', 'carry'):
                    assert w['number'](getattr(state[name], field)) == target[field]
    print('PASS native A9→AC→E2→marker wait→EE/E3: eight ALL primary and '
          'ALL5-chip transitions/scalars/wires/phase. Real marker signF exists '
          'only transiently; ordinary PC and ST25 do not acquire it.', flush=True)


def sign_cut(case):
    events = case['sourceEvents']
    left = w['constant'](events[0]);right = left.copy()
    left.r[24] = q['BitVec']('real_marker_sign_left', 4)
    right.r[24] = q['BitVec']('real_marker_sign_right', 4)
    p = Solver();p.set(timeout=20000)
    for index, event in enumerate(events[:-1]):
        p.add(w['address'](left) == event['ip'], w['address'](right) == event['ip'])
        keys = q['arbitrary_keys']('real_marker_cutkeys_%d' % index)
        serial = q['State']('real_marker_cutserial_%d' % index).m
        output = []
        pair = []
        for entry in (left, right):
            out = []
            pair.append(w['ex'](entry, event['ip'], *keys,
                                serial_inputs=serial, emitted_outputs=out))
            output.append(out)
        w['prove'](p, And(*[x == y for x, y in zip(*output)],
                          *[output[0][k] == left.m[k] for k in range(42)]),
                   'real-marker source prefix no new primary ring copy %d' % index, False)
        left, right = pair
    p.add(w['address'](left) == events[-1]['ip'], w['address'](right) == events[-1]['ip'])
    w['prove'](p, equal(left, right),
               'CONDITIONAL recorded A9→EE/E3 tail forgets ANY original '
               'marker sign0..F in ALL primary fields, with no primary ring write')
    print('SCOPE: fixed native entry metadata and recorded path, arbitrary common '
          'future pages/keys. Other upper-push returns, marker geometries or '
          'earlier reserves are not excluded; no global sign-F impossibility.', flush=True)


if __name__ == '__main__':
    ee_loss()
    case = json.loads(subprocess.check_output(
        ['node', str(root / 'cache-real-marker-sign-source-native.cjs'), '--proof-input'], text=True))
    native_replay(case)
    sign_cut(case)
