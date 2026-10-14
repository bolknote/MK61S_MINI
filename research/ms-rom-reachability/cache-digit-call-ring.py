#!/usr/bin/env python3
"""Digit/signF CONDITIONAL complete-ring continuation, not keyboard success.

Only a detached primary ST25 is changed toF; it is0 in the native reference.
Raw6 and corresponding program tetras vary jointly. This does not construct
signF before C8. Optional second counterfactual: the physical M2 X[34] is7,
not its native6, before8C. Neither field is injected into the reference.
Fixed digit-key release and one further frame, no feedback.
The native ALL5 baselines are observed and left untouched.
"""
from collections import Counter
import json
from pathlib import Path
import runpy
import subprocess
import sys

from z3 import And, BitVec, simplify

root = Path(__file__).resolve().parent
engine = runpy.run_path(str(root / 'cache-stack-lift-ring.py'))
w, q = engine['w'], engine['q']
models, names, slots = (engine[n] for n in ('models', 'names', 'slots'))
make, step, ring, boundary_ip = (engine[n] for n in
                               ('make', 'step', 'ring', 'boundary_ip'))
cases = json.loads(subprocess.check_output(
    ['node', str(root / 'cache-digit-call-native.cjs'), '--proof-input'], text=True))
raw = (0, 3, 9, 12, 18, 21)
program = (14, 17, 20, 23, 26, 29)


def validate_baseline():
    for case in cases:
        entries = case['completePrefix']
        state, tags, j = make(entries[0])
        for current, following in zip(entries, entries[1:]):
            assert boundary_ip(state['ik1302']) == current['ip']
            pins = {name: (current['state'][name]['keyX'], current['state'][name]['keyY'])
                    for name in models}
            j, _ = step(state, tags, j, pins)
            for name in names:
                target = following['state'][name]
                for field in ('input', 'output'):
                    assert simplify(state['_wire'][name][field]).as_long() == target[field], (name, field)
                if name.startswith('ir'):
                    assert [simplify(v).as_long() for v in state[name]] == target['m'], name
                    assert j == target['tick']
                else:
                    for field in ('r', 'm', 'st'):
                        assert [simplify(v).as_long() for v in getattr(state[name], field)] == target[field], (name, field)
                    for field in ('s', 's1', 'l', 't', 'carry'):
                        assert simplify(getattr(state[name], field)).as_long() == target[field], (name, field)
        report = case['report']
        print('PASS digit engine native baseline:', report['fixture'], 'C sign',
              report['nativeST25'], 'ALL5 chips/R/ST/M/scalars/phase/wires '
              'at64 consecutive boundaries.', flush=True)


def conditional(cleanup_type7=False):
    case = cases[2]  # raw_hex, ordinary C=0.
    entry = case['completePrefix'][0]
    state, tags, j = make(entry)
    primary = state['ik1302']
    assert boundary_ip(primary) == 0x8C
    assert [simplify(primary.st[k]).as_long() for k in (25, 33, 35)] == [0, 10, 5]
    assert simplify(primary.r[41]).as_long() == 0
    # Counterfactual model only. No native state/ROM setter is called.
    primary.st[25] = q['N4'](15)
    payload = [BitVec(f'digit_ring_raw{k}', 4) for k in range(6)]
    for pos, value in zip(raw, payload):
        primary.r[pos] = value
    for name in names:
        memory = state[name] if name.startswith('ir') else state[name].m
        for k, (slot, nibble) in enumerate(tags[name]):
            if slot == 'Y' and nibble in program:
                index = program.index(nibble)
                assert simplify(memory[k]).as_long() == (3, 10, 4, 13, 5, 11)[index]
                memory[k] = payload[index]
            if cleanup_type7 and slot == 'X' and nibble == 34:
                assert simplify(memory[k]).as_long() == 6
                memory[k] = q['N4'](7)
    before = ring(state, tags)
    p = q['base_solver'](primary, 0x8C)
    pins = {name: (entry['state'][name]['keyX'], entry['state'][name]['keyY'])
            for name in models}
    release_at, finish_at = 5*560, 7*560
    assert 4*560 <= entry['command'] < release_at
    sequence, writes = [], []
    first_idle = None
    first_any_idle = None
    rereads = []
    for count in range(finish_at-entry['command']):
        released = entry['command']+count >= release_at
        if released:
            pins['ik1302'] = (0, 0)
        code = boundary_ip(state['ik1302'], p)
        sequence.append(code)
        if code == 0xEE:
            tag = tags['ik1302'][34]
            value = state['ik1302'].m[34]
            rereads.append((count, tag, str(simplify(value))))
            if cleanup_type7 and len(rereads) == 1:
                assert tag == ('X', 34)
                w['prove'](p, value == 7,
                           'Counterfactual physical X[34]=7 reaches the first cleanup EE')
        if code == 0x35 and first_any_idle is None:
            first_any_idle = count
        if code == 0x35 and released and first_idle is None:
            first_idle = count
        original = state['ik1302']
        dest = tags['ik1302'][0][0]
        j, emitted = step(state, tags, j, pins, p)
        p.push()
        p.add(~w['eq'](emitted['ik1302'], original.m))
        answer = p.check()
        p.pop()
        assert answer in (q['sat'], q['unsat'])
        if answer == q['sat']:
            writes.append((count, code, dest))
            print('CONDITIONAL digit primary write:', count, f'{code:02X}', dest, flush=True)
    print('CONDITIONAL digit bounded tail:',
          ' '.join(f'{code:02X}' for code in sequence[-30:]),
          '; counts', {f'{code:02X}': n for code, n in Counter(sequence).items()},
          '; first any/released idle', first_any_idle, first_idle,
          '; EE source first4', rereads[:4], flush=True)
    if first_idle is not None:
        w['prove'](p, w['ip'](state['ik1302']) == 0x35,
                   'Digit/signF conditional fixed release plus one frame ends at35')
    expected = [0x8C, 0x91, 0x92, 0x93, 0x94, 0x95, 0x98, 0x9A,
                0x93, 0x94, 0x95, 0x98, 0x9A, 0x8D, 0x8F, 0x82, 0x84,
                0x75, 0xCA, 0xDB, 0xDC, 0xDE, 0xD4, 0xDD, 0xD4, 0x76]
    assert sequence[:len(expected)] == expected
    assert len(writes) >= 2 and [code for _, code, _ in writes[:2]] == [0xD4, 0xD4]
    first_slot, second_slot = (row[2] for row in writes[:2])
    assert first_slot != second_slot
    after = ring(state, tags)
    for slot, offset in ((first_slot, 3), (second_slot, 0)):
        w['prove'](p, w['eq']([after[slot][k+offset] for k in raw], payload),
                   'Digit raw6 physically retained at bounded end in ordinaryP'+
                   case['mapping']['registerPages'][slot])
    w['prove'](p, w['eq']([after[slot][k] for slot in slots for k in range(42) if k % 3 == 2],
                        [before[slot][k] for slot in slots for k in range(42) if k % 3 == 2]),
               'Digit ALL105 original program bytes held after76/EE/fixed release')
    hidden = case['mapping']['hidden']
    w['prove'](p, w['eq']([after[slot][k] for slot, positions in hidden.items() for k in positions],
                        [before[slot][k] for slot, positions in hidden.items() for k in positions]),
               'Digit ALL56 Ms bytes held; NOT an Ms copy')
    w['prove'](p, w['eq']([after[slot][k] for slot in slots if slot not in (first_slot, second_slot)
                         for k in range(0, 36, 3)],
                        [before[slot][k] for slot in slots if slot not in (first_slot, second_slot)
                         for k in range(0, 36, 3)]),
               'Digit other13 ordinary registers held; destinations overwritten, NOT exchanged')
    print('CONDITIONAL digit complete-ring bounded run:', len(sequence), 'fixed macros; '
          'first released idle', first_idle, '; all256^3 synthetic triples; writes', writes,
          flush=True)
    if cleanup_type7:
        assert first_idle is not None
        assert 0xD7 in sequence and 0x7F in sequence
        # The symbolic chips are immutable after each macro; the IR2 lists
        # are edited in place, so retain their values explicitly. A full
        # 30-macro state equality proves repeatable quiet idle, not merely
        # absence of controller events in a bounded window.
        quiet_state = {name: (list(state[name]) if name.startswith('ir') else state[name])
                       for name in names}
        quiet_wire, quiet_phase = state['_wire'], j
        for count in range(30):
            assert boundary_ip(state['ik1302'], p) == 0x35
            j, _ = step(state, tags, j, pins, p)
        claims = []
        for name in names:
            if name.startswith('ir'):
                claims.append(w['eq'](state[name], quiet_state[name]))
            else:
                for field in ('r', 'm', 'st'):
                    claims.append(w['eq'](getattr(state[name], field),
                                          getattr(quiet_state[name], field)))
                claims.extend(getattr(state[name], field) == getattr(quiet_state[name], field)
                              for field in ('s', 's1', 'l', 't', 'carry'))
            claims.extend(state['_wire'][name][field] == quiet_wire[name][field]
                          for field in ('input', 'output'))
        assert j == quiet_phase
        w['prove'](p, And(*claims),
                   'Counterfactual type7 exit: ALL5-chip state/wires/phase '
                   'repeat after30 quiet macros, for all256^3 payloads; stable idle by induction')
        print('LIMIT: both primary ST25=F and physical X[34]=7 are detached '
              'hypotheses, not a native simultaneous constructor. The '
              'conditional full-ring writer has a working exit with retained '
              'all256^3 reserve, but no keyboard recipe, Ms transfer, exchange '
              'or partialK2 is established.', flush=True)
    else:
        assert first_idle is None, 'this bounded control is a retained reserve, not a working exit'
        print('LIMIT: primary ST25=F is detached, not a native C-sign constructor. '
              'The all256^3 reserve is retained at this bounded end but35 is not '
              'reached. Neither a sole E5 sink nor a full-state periodic cycle '
              'is asserted. Need the sign constructor AND cleanup repair/readback. '
              'No Ms transfer or partialK2.', flush=True)


if __name__ == '__main__':
    if '--baseline-only' in sys.argv:
        validate_baseline()
    elif '--conditional-only' in sys.argv:
        conditional()
    elif '--type7-only' in sys.argv:
        conditional(cleanup_type7=True)
    else:
        validate_baseline()
        conditional()
        conditional(cleanup_type7=True)
