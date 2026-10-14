#!/usr/bin/env python3
"""Exact full-ring cycle and keyboard quotient of the signF/type6 branch.

The entry is detached: ST25=F, arbitrary raw6 and matching program fields.
--physical-sign additionally puts F in physical ordinary C.M1[24]; this
checks consistency of the saved sign hypothesis, not a key constructor.
No native setter/ROM mutation. A quiet90-macro full-state period is tested
after378 macros, not guessed from a controller suffix. Optional local
equivalence admits arbitrary primary keys and primary T at every macro;
T is ignored only when every observable/control/data field is proved equal.
This is scoped to this inlet, fixed ring and the secondary chips' rad pins.
"""
import json
from pathlib import Path
import runpy
import subprocess
import sys

from z3 import And, BitVec

root = Path(__file__).resolve().parent
e = runpy.run_path(str(root / 'cache-stack-lift-ring.py'))
w, q = e['w'], e['q']
cases = json.loads(subprocess.check_output(
    ['node', str(root / 'cache-digit-call-native.cjs'), '--proof-input'], text=True))
entry = cases[2]['completePrefix'][0]
raw, program = (0, 3, 9, 12, 18, 21), (14, 17, 20, 23, 26, 29)


def capture(state, tags, phase):
    return ({name: list(state[name]) if name.startswith('ir') else state[name]
             for name in e['names']}, state['_wire'],
            {name: list(tags[name]) for name in e['names']}, phase)


def state_equality(state, tags, phase, saved):
    old, wires, old_tags, old_phase = saved
    assert phase == old_phase and tags == old_tags
    claims = []
    for name in e['names']:
        if name.startswith('ir'):
            claims.append(w['eq'](state[name], old[name]))
        else:
            for field in ('r', 'm', 'st'):
                claims.append(w['eq'](getattr(state[name], field), getattr(old[name], field)))
            claims.extend(getattr(state[name], field) == getattr(old[name], field)
                          for field in ('s', 's1', 'l', 't', 'carry'))
        claims.extend(state['_wire'][name][field] == wires[name][field]
                      for field in ('input', 'output'))
    return And(*claims)


def run(audit_keys=True, physical_sign=False):
    state, tags, j = e['make'](entry)
    a = state['ik1302']
    a.st[25] = q['N4'](15)
    payload = [BitVec(f'digit_cycle_raw{k}', 4) for k in range(6)]
    for pos, value in zip(raw, payload):
        a.r[pos] = value
    for name in e['names']:
        memory = state[name] if name.startswith('ir') else state[name].m
        for k, (slot, nibble) in enumerate(tags[name]):
            if slot == 'Y' and nibble in program:
                memory[k] = payload[program.index(nibble)]
            if physical_sign and (slot, nibble) == ('Y', 24):
                memory[k] = q['N4'](15)
    initial = e['ring'](state, tags)
    p = q['base_solver'](a, 0x8C)
    pins = {name: (entry['state'][name]['keyX'], entry['state'][name]['keyY'])
            for name in e['models']}
    pins['ik1302'] = (0, 0)
    saved, sequence, key_steps = None, [], 0
    for count in range(468):
        code = e['boundary_ip'](state['ik1302'], p)
        sequence.append(code)
        assert code not in (0x33, 0x35)
        if count == 378:
            assert code == 0xE2
            saved = capture(state, tags, j)
        before = state['ik1302']
        incoming = list(state['ir2b'][j:j+42])
        j, emitted = e['step'](state, tags, j, pins, p)
        if audit_keys:
            paired = before.copy()
            paired.t = BitVec(f'digit_cycle_any_T{count}', 1)
            other_out = []
            other = q['execute_command'](
                paired, code, *q['arbitrary_keys'](f'digit_cycle_keys{count}'),
                serial_inputs=incoming, emitted_outputs=other_out)
            target = state['ik1302']
            claim = And(*[w['eq'](getattr(other, field), getattr(target, field))
                          for field in ('r', 'm', 'st')],
                        *[getattr(other, field) == getattr(target, field)
                          for field in ('s', 's1', 'l', 'carry')],
                        w['eq'](other_out, emitted['ik1302']))
            w['prove'](p, claim,
                       f'Keyboard/T quotient at macro{count}/{code:02X}', False)
            key_steps += 1
        if count % 90 == 0:
            print('CONDITIONAL cycle progress', count, f'{code:02X}',
                  'key-equivalence steps', key_steps, flush=True)
    assert saved is not None and len(sequence[378:]) == 90
    assert e['boundary_ip'](state['ik1302'], p) == 0xE2
    w['prove'](p, state_equality(state, tags, j, saved),
               'SignF/type6: ALL5-chip fields/wires/phase/tags repeat after '
               '90 quiet macros at378→468, for ALL256^3 payloads')
    after = e['ring'](state, tags)
    for slot, offset in (('Q', 3), ('P8', 0)):
        w['prove'](p, w['eq']([after[slot][k+offset] for k in raw], payload),
                   'Periodic type6 branch retains exact raw6 in ordinaryP'+
                   cases[2]['mapping']['registerPages'][slot])
    held = [(slot, k) for slot in e['slots'] for k in range(42)
            if k % 3 == 2 or (k % 3 == 0 and k < 36 and slot not in ('Q', 'P8'))]
    held += [(slot, k) for slot, indices in cases[2]['mapping']['hidden'].items()
             for k in indices]
    w['prove'](p, w['eq']([after[slot][k] for slot, k in held],
                         [initial[slot][k] for slot, k in held]),
               'Periodic type6 branch holds ALL105 program/56Ms/other13 registers')
    if audit_keys:
        assert key_steps == 468
        print('PASS keyboard quotient: every macro from8C through the whole '
              'cycle ignores arbitrary per-tick primary keys and arbitrary '
              'primary T in ALL R/ST/M/S/S1/L/carry and emitted42 cells. '
              'Only T may differ. Other chips receive identical outputs; '
              'the quotient cycle excludes key escape for this inlet.', flush=True)
    print('Physical C-sign hypothesis:', 'F' if physical_sign else 'native0', flush=True)
    print('SCOPE: a genuine full-state QUIET period, not just a repeated '
          'controller word. ST25=F is still detached; this is not a native '
          'constructor, all-inlet/global K2 impossibility, or exclusion of '
          'changed ring/type/marker preparations.', flush=True)


if __name__ == '__main__':
    run(audit_keys='--quiet-only' not in sys.argv,
        physical_sign='--physical-sign' in sys.argv)
