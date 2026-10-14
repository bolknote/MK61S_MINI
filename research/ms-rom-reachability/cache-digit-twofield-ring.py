#!/usr/bin/env python3
"""Audit whether an early C-signF/X-markerF needs the extra T-type7.

Detached hypotheses are prepared BEFORE the native last AC, never in the
reference. The complete fixed-key source and later release are replayed on
all five chips. All256^3 program triples vary jointly. Differences, including
ones outside raw6, are reported; controller idle is not enough for success.
"""
from pathlib import Path
import runpy

from z3 import And, BitVec, Concat, simplify

root = Path(__file__).resolve().parent
r = runpy.run_path(str(root / 'cache-digit-redirect-ring.py'))
e, q, w, data = (r[name] for name in ('e', 'q', 'w', 'data'))
raw, program = r['raw'], r['program']


def holds(p, claim):
    return r['repeated'](p, claim)


def report_changes(p, before, after, label):
    groups = {
        'program105': [(s, k) for s in e['slots'] for k in range(42) if k % 3 == 2],
        'Ms56': [(s, k) for s, indices in data['mapping']['hidden'].items() for k in indices],
        'ordinary13': [(s, k) for s in e['slots'] if s not in ('Q', 'P8')
                       for k in range(0, 36, 3)],
    }
    okay = True
    for name, cells in groups.items():
        claim = w['eq']([after[s][k] for s, k in cells], [before[s][k] for s, k in cells])
        clean = holds(p, claim)
        if name != 'program105':
            assert clean, (label, name, 'unexpected additional damage')
        okay &= clean
        if clean:
            print('PASS', label, name, 'held', flush=True)
        else:
            changed = [(s, k, str(simplify(before[s][k])), str(simplify(after[s][k])))
                       for s, k in cells if not holds(p, after[s][k] == before[s][k])]
            print('DIFFERENCE', label, name, changed, flush=True)
    return okay


def audit():
    state, tags, phase = e['make'](data['source'][0])
    payload = [BitVec(f'twofield_raw{k}', 4) for k in range(6)]
    for k, value in zip(program, payload):
        r['set_physical'](state, tags, 'Y', k, value)
    r['set_physical'](state, tags, 'Y', 24, q['N4'](15))
    r['set_physical'](state, tags, 'X', 22, q['N4'](15))
    before = e['ring'](state, tags)
    assert simplify(before['T'][34]).as_long() == 0
    p = q['base_solver'](state['ik1302'], 0xAC)
    phase, inlet_at = r['source_run'](state, tags, phase, p, 'TWO-FIELD')
    inlet = e['ring'](state, tags)
    w['prove'](p, And(state['ik1302'].st[25] == 15,
                     state['ik1302'].r[41] == 0,
                     w['eq']([state['ik1302'].r[k] for k in raw], payload),
                     inlet['X'][22] == 15, inlet['X'][34] == 6,
                     inlet['T'][34] == 0),
               'Two early physical fields survive the whole AC→first8C source')
    pins = {name: (data['prefix'][0]['state'][name]['keyX'],
                   data['prefix'][0]['state'][name]['keyY']) for name in e['models']}
    release_at = data['report']['sourceToInletMacros']+data['report']['releaseCount']-inlet_at
    sequence, reads, writes, hits = [], [], [], []
    first_idle = None
    for count in range(release_at+360):
        if count >= release_at:
            pins['ik1302'] = (0, 0)
        code = e['boundary_ip'](state['ik1302'], p)
        sequence.append(code)
        if code == 0xEE:
            reads.append((count, tags['ik1302'][34], str(simplify(state['ik1302'].m[34]))))
        if code == 0xD4:
            writes.append((count, tags['ik1302'][0][0]))
        if code == 0xE5 and holds(p, state['ik1302'].m[22] == 15):
            hits.append((count, tags['ik1302'][22][0]))
        if code == 0x35 and first_idle is None:
            first_idle = count
        phase, _ = e['step'](state, tags, phase, pins, p)
        if count % 180 == 0:
            print('TWO-FIELD writer macro', count, f'{code:02X}', flush=True)
    after = e['ring'](state, tags)
    for slot, offset in (('Q', 3), ('P8', 0)):
        w['prove'](p, w['eq']([after[slot][k+offset] for k in raw], payload),
                   'Two-field ALL256^3 exact raw triples retained in '+slot)
    clean = report_changes(p, before, after, 'TWO-FIELD')
    expected = {('P9', k): value for k, value in
                ((5, 8), (8, 8), (11, 8), (14, 8), (17, 8), (20, 8),
                 (29, 9), (32, 6), (35, 4), (38, 2), (41, 5))}
    expected[('X1', 38)] = 0
    all_program = [(s, k) for s in e['slots'] for k in range(42) if k % 3 == 2]
    w['prove'](p, w['eq']([after[s][k] for s, k in all_program],
                         [q['N4'](expected[(s, k)]) if (s, k) in expected else before[s][k]
                          for s, k in all_program]),
               'Two-field exact program damage: 12 tetras/8 bytes, not arbitrary corruption')
    assert not clean
    byte_changes = []
    for slot in e['slots']:
        for rest in range(7):
            high = 41 if rest == 0 else 6*rest-1
            low = high-3
            if (slot, high) in expected or (slot, low) in expected:
                address = 7*int(data['mapping']['registerPages'][slot], 16)+rest
                byte_changes.append((address,
                    str(simplify(Concat(before[slot][high], before[slot][low]))),
                    str(simplify(Concat(after[slot][high], after[slot][low])))))
    assert sorted(a for a, _, _ in byte_changes) == [42, 43, 44, 45, 46, 47, 48, 70]
    print('TWO-FIELD changed program bytes', sorted(byte_changes), flush=True)
    print('TWO-FIELD EE', reads, 'D4', writes, 'E5 hits', hits,
          'first35', first_idle, 'finalIP', f'{e["boundary_ip"](state["ik1302"], p):02X}',
          'preservation', clean, 'prefix', ' '.join(f'{v:02X}' for v in sequence[:180]),
          flush=True)
    saved = r['capture'](state, tags, phase)
    tail = []
    for _ in range(30):
        tail.append(e['boundary_ip'](state['ik1302'], p))
        phase, _ = e['step'](state, tags, phase, pins, p)
    w['prove'](p, r['equality'](state, tags, phase, saved),
               'Two-field quiet30 ALL5 full-state period despite program damage')
    assert tail == [0x35]*30
    print('SCOPE: conditional early two-field audit only; no native constructor, '
          'no Ms/program exchange or partial K2.', flush=True)


if __name__ == '__main__':
    audit()
