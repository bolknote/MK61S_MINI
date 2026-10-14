#!/usr/bin/env python3
"""Independent ALL5 check of the source-selected native F/В↑ control.

Only public keys are sent to the stock reference. Whole-state period skipping
requires exact fields/wires/phase/tags at fixed pins. The lost readiness is a
negative result, not a native signF/exchange or a global reserve-erasure proof.
"""
import json
from pathlib import Path
import runpy
import subprocess

from z3 import And, BitVec, If, UGE, sat

root = Path(__file__).resolve().parent
r = runpy.run_path(str(root / 'cache-cf-ready-control.py'))
early = runpy.run_path(str(root / 'cache-input-mask-early-exit.py'))
engine = early['engine']


def zero_mode_exit_contract(native):
    w, q = r['w'], r['q']
    gate = q['State']('up_exit_8D_gate'); pg = w['base'](gate, 0x8D); out = []
    after = w['ex'](gate, 0x8D, *q['arbitrary_keys']('up_exit_8D_gate_keys'), emitted_outputs=out)
    w['prove'](pg, And(w['ip'](after) == If(UGE(gate.s1, 10),
        q['BitVecVal'](0x4F, 8), q['BitVecVal'](0x8F, 8)), after.s1 == gate.s1,
        *[after.r[i] == gate.r[i] for i in w['raw']],
        after.r[2] == gate.r[2], after.r[5] == gate.r[5], w['eq'](out, gate.m)),
        '8D chooses4F iff S1>=A, otherwise8F (NOT8E); raw6/mode held, no write')
    entry = next(e for e in native['decoder'] if e['command'] == 1152)
    assert entry['ip'] == 0x8D and entry['state']['ik1302']['s1'] == 15
    a = r['concrete_primary'](entry['state']['ik1302'])
    for i in w['raw']: a.r[i] = BitVec(f'up_zero_mode_raw_{i}', 4)
    a.m = q['State']('up_zero_mode_incoming').m
    other = a.copy()
    for i in w['raw']: other.r[i] = BitVec(f'up_zero_mode_other_raw_{i}', 4)
    b, c = a, other; p = w['base'](a, 0x8D)
    for index, code in enumerate((0x8D, 0x4F, 0xFF, 0xE5, 0xE6, 0xEE)):
        w['prove'](p, And(w['ip'](b) == code, w['ip'](c) == code),
                   f'native-shaped8D forced{code:02X}', False)
        if code == 0xE5: p.add(b.m[22] == 15)
        if code == 0xEE:
            w['prove'](p, And(b.r[2] == 0, b.r[5] == 0,
                *[b.r[i] == a.r[i] for i in w['raw']]),
                'native-shaped8D→firstEE holds ALL raw6/zero mode up to compulsory read')
        before_b, before_c = b, c; ob, oc = [], []
        pins = q['arbitrary_keys'](f'up_zero_mode_keys{index}')
        serial = q['State'](f'up_zero_mode_future{index}').m
        b = w['ex'](b, code, *pins, serial_inputs=serial, emitted_outputs=ob)
        c = w['ex'](c, code, *pins, serial_inputs=serial, emitted_outputs=oc)
        w['prove'](p, And(w['eq'](ob, before_b.m), w['eq'](oc, before_c.m)),
                   '8D→EE creates no outgoing cache copy', False)
    same = And(*[w['eq'](getattr(b, n), getattr(c, n)) for n in ('r', 'st', 'm')],
               *[getattr(b, n) == getattr(c, n) for n in ('s', 's1', 'l', 't', 'carry')])
    w['prove'](p, same, 'native-shaped8D→EE forgets independent ALL six raw tetras in primary/output')
    p.push(); p.add(And(*[a.r[i] != other.r[i] for i in w['raw']]))
    assert p.check() == sat; p.pop()
    wait = q['State']('up_zero_mode_wait'); pw = w['base'](wait, 0xE5)
    after = w['ex'](wait, 0xE5, *q['arbitrary_keys']('up_zero_mode_wait_keys'))
    w['prove'](pw, And(w['eq'](after.st, wait.st), after.s1 == wait.s1,
        *[after.r[i] == wait.r[i] for i in range(42) if i not in (36, 39)]),
        'any finite marker waits keep the same zero-mode/raw6 pre-read contract')
    print('LIMIT: exact local8D metadata, arbitrary ALL256^3 raw codes/keys/future pages; '
          'no pause can insert35 orCF beforeEE. Earlier correlated reserves '
          'and original physical program/other chips remain OPEN.', flush=True)


def validate(native):
    report = native['report']; assert report['observerIndependent'] is True
    assert (report['first79'], report['firstReadinessLoss'], report['lossCause']) == (1123, 1142, 0x92)
    assert report['programChanges'] == report['registerChanges'] == []
    assert report['all56MsBytesHeld'] is True
    state, tags, phase = engine['make'](native['initial']); command = 0; selected = 0
    checkpoints = {e['command']: e for field in ('origin', 'decoder') for e in native[field]}
    end = report['end']; keys = report['keys']
    pins0 = {name: (native['initial']['state'][name]['keyX'],
                    native['initial']['state'][name]['keyY']) for name in engine['models']}
    key_pins = {'F': (11, 9), 'В↑': (11, 8)}
    boundaries = sorted({0, end, *checkpoints,
        *(i*1120+offset for i in range(len(keys)) for offset in (0, 560, 1120))})
    for following in boundaries:
        if command in checkpoints:
            early['snapshot_matches'](state, phase, checkpoints[command]['state'])
        if following == command: continue
        pins = dict(pins0); index, offset = divmod(command, 1120)
        pins['ik1302'] = key_pins[keys[index]] if index < len(keys) and offset < 560 else (0, 0)
        if following == command+1 and command in checkpoints and following in checkpoints:
            phase, _ = engine['step'](state, tags, phase, pins); command += 1; selected += 1
        else:
            phase, command = early['advance_fixed'](state, tags, phase, command,
                following, pins, losses=[], label='native F/В↑')
    assert command == end == 3360 and selected == 223
    early['snapshot_matches'](state, phase, native['end']['state'])
    a = state['ik1302']; number = r['number']
    assert number(r['w']['ip'](a)) == 0xE5
    assert [number(a.r[j]) for j in (2, 5)] == [0, 0]
    assert all(number(v) == 0 for v in a.r[0:36:3])
    assert not (number(a.r[22]) == 7 and all(number(a.st[j]) == 0 for j in range(1, 24, 3)))
    assert r['inlet']['match_controller'](a)
    print('PASS native F/В↑:223 consecutive ALL5 transitions and complete3360 '
          'end; fields/wires/phase/tags; fresh whole unobserved mirror; '
          '105/56/15 held. Native79 is real; final mode0/0 lacks ready data. '
          'No global loss of all earlier reserves is inferred.', flush=True)


if __name__ == '__main__':
    r['inlet']['immutable_reference']()
    native = json.loads(subprocess.check_output([
        'node', str(root / 'cache-reader-mode-reset-native.cjs'), '--proof-input'], text=True))
    zero_mode_exit_contract(native)
    validate(native)
    r['inlet']['immutable_reference']()
