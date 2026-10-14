#!/usr/bin/env python3
"""Exact sign feed of the recorded D6→DA path; not a native constructor.

Fresh keyboard-only P2/P8 controls provide primary and ALL5 baselines.
The separate local symbolic experiment replaces the initial pointer word
only in Z3, conditions on the recorded P8 macro path and admits arbitrary
future serial inputs and key pins. Its SAT pointers are NOT key recipes,
nor an ALL5-ring reachability or persistence witness.
"""
import json
from pathlib import Path
import runpy
import subprocess

from z3 import And, BitVec, Solver, sat, simplify

root = Path(__file__).resolve().parent
w = runpy.run_path(str(root / 'cache-writer-contract.py'))
q = w['q']
engine = runpy.run_path(str(root / 'cache-stack-lift-ring.py'))
cases = json.loads(subprocess.check_output(
    ['node', str(root / 'cache-da-sign-geometry-native.cjs'), '--proof-input'], text=True))


def native_replays():
    for case in cases:
        events = case['sourceEvents']
        a = w['constant'](events[0])
        for event, following in zip(events, events[1:]):
            assert w['number'](w['address'](a)) == event['ip']
            a = w['ex'](a, event['ip'], event['keyX'], event['keyY'],
                        serial_inputs=[q['N4'](v) for v in following['m']])
            for field in ('r', 'm', 'st'):
                assert [w['number'](v) for v in getattr(a, field)] == following[field]
            for field in ('s', 's1', 'l', 't', 'carry'):
                assert w['number'](getattr(a, field)) == following[field]
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
                    assert simplify(state['_wire'][name][field]).as_long() == target[field]
                if name.startswith('ir'):
                    assert [simplify(v).as_long() for v in state[name]] == target['m']
                    assert phase == target['tick']
                else:
                    for field in ('r', 'm', 'st'):
                        assert [w['number'](v) for v in getattr(state[name], field)] == target[field]
                    for field in ('s', 's1', 'l', 't', 'carry'):
                        assert w['number'](getattr(state[name], field)) == target[field]
        print('PASS native pointer P%d: %d source transitions ALL primary fields; '
              '64 ALL5-chip transitions/scalars/wires/phase; no sign F.' %
              (case['report']['register'], len(events) - 1), flush=True)


def conditional_pointer_sources():
    case = next(c for c in cases if c['report']['register'] == 8)
    events = case['sourceEvents']
    a = w['constant'](events[0])
    pointer = [BitVec('da_sign_pointer_%d' % i, 4) for i in range(12)]
    for i, value in enumerate(pointer):
        a.m[3*i] = value
    p = Solver(); p.set(timeout=20000)
    writes, inlet = [], None
    for index, (event, following) in enumerate(zip(events, events[1:])):
        p.add(w['address'](a) == event['ip'])
        if event['ip'] == 0x73:
            inlet = a
        output = []
        a = w['ex'](a, event['ip'], *q['arbitrary_keys']('da_sign_keys_%d' % index),
                    serial_inputs=q['State']('da_sign_serial_%d' % index).m,
                    emitted_outputs=output)
        if event['ip'] == 0xD4:
            writes.append((event['slot'], output))
    p.add(w['address'](a) == events[-1]['ip'])
    assert [slot for slot, _ in writes] == ['marker', 'Q', 'P8']
    w['prove'](p, And(writes[0][1][24] == pointer[8],
                      writes[1][1][24] == pointer[9],
                      writes[2][1][24] == 0,
                      inlet.r[33] == pointer[1], inlet.r[27] == pointer[11],
                      inlet.r[30] == pointer[0]),
               'Recorded D6→DA path: first DA sign←pointer exponent-unit A9; '
               'earlier normalization sign←A8; second DA sign0; selector←A1')
    # Pin every original pointer field except the identified feed. This
    # makes the conditional possibility more precise than an arbitrary SAT
    # solution, but it is still NOT a native exponent-F construction.
    original = [int(v, 16) for v in reversed(case['report']['pointer'])]
    p.push()
    p.add(*[pointer[i] == (15 if i == 9 else original[i]) for i in range(12)])
    assert p.check() == sat, 'the isolated order-unit F hypothesis must be feasible'
    w['prove'](p, writes[1][1][24] == 15,
               'CONDITIONAL pointer 99F0FFFFFFF0 writes ordinary P3 sign F')
    p.pop()
    print('LIMIT: arbitrary future pages/keys are a LOCAL overapproximation under '
          'the fixed P8 path. The actual keys construct 9990FFFFFFF0, sign9 in P3, '
          'not 99F0FFFFFFF0. No pointer relocation to PC, native sign maker, '
          'reader stitch, Ms transfer or partial K2.', flush=True)


if __name__ == '__main__':
    native_replays()
    conditional_pointer_sources()
