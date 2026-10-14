#!/usr/bin/env python3
"""Exact CF/C3 constructor and native inlets, with a finite CONDITIONAL exit.

Real0/ВП entersC3 but makes1. Real7/ВП and cache7/F/Сx/ВП enterCF
but NOT C3. Only the detached full ring has native idle7's address35
replaced by CF; no data/flag repair, reference setter or ROM change.
That sole address hypothesis makes a stable workingF, NOT ordinary C-signF
or a program/Ms exchange. The joint native zero-B/A7=7 inlet remains open.
"""
from collections import Counter
import hashlib
import json
from pathlib import Path
import runpy
import subprocess

from z3 import And, BitVecVal, If, Or, UGE, ULE

root = Path(__file__).resolve().parent
seven = runpy.run_path(str(root / 'cache-seven-sign-contract.py'))
w, q, engine, early = (seven[name] for name in ('w', 'q', 'engine', 'early'))
number, word = early['number'], early['word']
controls = json.loads(subprocess.check_output([
    'node', str(root / 'cache-cf-constructor-native.cjs'), '--proof-input'], text=True))
restore = (0x8C, 0x91, 0x92, 0x93, 0x94, 0x95, 0x98, 0x9A,
           0x93, 0x94, 0x95, 0x98, 0x9A, 0x8D, 0x4F)


def immutable_reference():
    for name, expected in (
        ('mk61.cjs', 'b15bc586ac3804eb5622b8072e88f35bcd2081abbe2195fcefa5a718e56ece0c'),
        ('rom.cjs', '6c3f85b3e942cdd4d4191e46e98a50829eb850011b8b7a3cc01b12e5e2a31a33')):
        assert hashlib.sha256((q['ROM_PATH'].parent / name).read_bytes()).hexdigest() == expected


def cf_formula():
    a = q['State']('cf_constructor_formula'); p = w['base'](a, 0xCF)
    out = []
    b = w['ex'](a, 0xCF, *q['arbitrary_keys']('cf_constructor_formula_keys'),
                emitted_outputs=out)
    zero = And(*[a.r[1+3*i] == 0 for i in range(8)])
    w['prove'](p, And(w['ip'](b) == If(zero, BitVecVal(0xC3, 8), BitVecVal(0xC2, 8)),
                     b.r[21] == a.r[21], b.r[34] == a.r[34], b.s1 == 4,
                     w['eq'](out, a.m)),
               'CF entersC3 IFF oldB0..7 allzero, otherwiseC2; '
               'holds A7/header, sets S1=4 and writes nothing')
    p.add(zero)
    w['prove'](p, b.r[22] == a.r[21]+1,
               'CF zero-B branch makes B7=A7+1 modulo16, no carry/key premise')
    c = w['ex'](b, 0xC3, *q['arbitrary_keys']('cf_constructor_c3_keys'))
    w['prove'](p, And(c.r[21] == a.r[21]*2+1, w['ip'](c) == 0xC2,
                     (c.r[21] == 15) == Or(a.r[21] == 7, a.r[21] == 15)),
               'CF→C3 zero-B gives A7=2*oldA7+1 modulo16; '
               'F IFF oldA7=7/F, NOT F for every zero-B entry')


def exact_inlet():
    a = q['State']('cf_constructor_8c_inlet'); p = w['base'](a, 0x8C)
    p.add(a.s1 == 12); b = a
    for index, code in enumerate(restore):
        w['prove'](p, w['ip'](b) == code, f'8C/C forced inlet stage{index}', False)
        out = []; before = b
        b = w['ex'](b, code, *q['arbitrary_keys'](f'cf_constructor_inlet_keys{index}'),
                    emitted_outputs=out)
        w['prove'](p, w['eq'](out, before.m), 'CF inlet no outgoing write', False)
    w['prove'](p, And(w['ip'](b) == 0xCF, b.r[21] == a.r[21],
                     w['eq'](b.r[1:24:3], a.st[0:24:3]), b.r[34] == a.st[34]),
               '8C/S1=C forced fifteen-word route reachesCF; A7held, '
               'B0..7 from oldST0, header from oldST34 (not oldST33)')
    c = w['ex'](b, 0xCF, *q['arbitrary_keys']('cf_constructor_after_inlet_keys'))
    w['prove'](p, (w['ip'](c) == 0xC3) == And(*[a.st[3*i] == 0 for i in range(8)]),
               '8C/C→CF→C3 IFF ORIGINAL ST0 lower8 allzero; '
               'zero ordinaryC in another ST lane does not suffice')
    for code in (0x9E, 0x9F):
        a = q['State'](f'cf_constructor_dispatch_{code:02X}')
        p = w['base'](a, code)
        b = w['ex'](a, code, *q['arbitrary_keys'](f'cf_constructor_dispatch_keys{code:02X}'))
        claim = (And(w['ip'](b) == If(a.r[33] == 0, BitVecVal(0x8C, 8),
                                    BitVecVal(0x9F, 8)), b.s1 == a.s1)
                 if code == 0x9E else b.s1 == a.r[33]+12)
        w['prove'](p, claim, f'{code:02X} exact dispatch dependency')
    g = runpy.run_path(str(root / 'cache-numeric-export-gates.py'))
    expected = {0xCF: {0x4F: 30, 0xD4: 9, 0xD6: 6},
                0x4F: {0x8D: 30}, 0x8D: {0x9A: 30}, 0x8C: {0x9E: 208}}
    found = {code: Counter() for code in expected}
    for index, row in enumerate(g['edges']):
        for child in row:
            code = g['states'][child][0]
            if code in found: found[code][g['states'][index][0]] += 1
    assert found == expected
    print('PASS complete52416/95731 incoming inventory: CF←4F/D4/D6; '
          '4F←8D←9A;8C←9E. Positive graph edges are NOT keyboard witnesses.', flush=True)


def header_exits():
    for code in (0xDC, 0xDE):
        a = q['State'](f'cf_constructor_header_{code:02X}')
        p = w['base'](a, code); out = []
        b = w['ex'](a, code, *q['arbitrary_keys'](f'cf_constructor_header_keys{code:02X}'),
                    emitted_outputs=out)
        claim = (w['ip'](b) == If(And(UGE(a.r[34], 1), ULE(a.r[34], 8)),
                                 BitVecVal(0xDE, 8), BitVecVal(0xEA, 8))
                 if code == 0xDC else And(w['ip'](b) == w['byte'](a.r[34], q['N4'](13)),
                                         b.s1 == a.r[34]))
        w['prove'](p, And(claim, b.r[21] == a.r[21], b.r[34] == a.r[34],
                         w['eq'](out, a.m)), f'{code:02X} exact header dispatch, A7held/no write')
    a = q['State']('cf_constructor_header6_reader'); p = w['base'](a, 0xC3)
    p.add(a.r[34] == 6); b = a
    for index, code in enumerate((0xC3, 0xC2, 0xDC, 0xDE, 0xD6)):
        w['prove'](p, w['ip'](b) == code, 'header6 forced reader stage', False)
        out = []; before = b
        b = w['ex'](b, code, *q['arbitrary_keys'](f'cf_constructor_header6_keys{index}'),
                    emitted_outputs=out)
        w['prove'](p, w['eq'](out, before.m), 'header6 no outgoing write', False)
    w['prove'](p, w['eq'](w['A'](b), before.m[0:36:3]),
               'C3/header6 forces D6, which imports ALL12 A from its current M1; '
               'workingF is not preserved independently of that page')


def validate_native_controls():
    for native in controls:
        assert native['report']['observerIndependent'] is True
        assert native['report']['nativeCF_C3NewF'] is False
        entries = native['prefix']; state, tags, phase = engine['make'](entries[0])
        early['snapshot_matches'](state, phase, entries[0]['state'])
        for current, following in zip(entries, entries[1:]):
            assert engine['boundary_ip'](state['ik1302']) == current['ip']
            pins = {name: (current['state'][name]['keyX'], current['state'][name]['keyY'])
                    for name in engine['models']}
            phase, _ = engine['step'](state, tags, phase, pins)
            early['snapshot_matches'](state, phase, following['state'])
        command = entries[-1]['command']
        held = {name: (entries[0]['state'][name]['keyX'], entries[0]['state'][name]['keyY'])
                for name in engine['models']}
        assert held['ik1302'] == (9, 8)
        release = (entries[0]['command']//1120)*1120+560
        assert command < release
        phase, command = early['advance_fixed'](
            state, tags, phase, command, release, held, label=native['report']['name']+' ВП held')
        released = dict(held); released['ik1302'] = (0, 0)
        phase, command = early['advance_fixed'](
            state, tags, phase, command, native['end']['command'], released,
            label=native['report']['name']+' ВП released')
        early['snapshot_matches'](state, phase, native['end']['state'])
        assert tags == engine['make'](native['end'])[1]
        print('PASS native', native['report']['name'],
              ':64 ALL5 transitions/full end/wires/phase/tags/fresh mirror;',
              json.dumps(native['report'], ensure_ascii=False), flush=True)


def conditional_finite_cf():
    entry = seven['native']['entry']; state, tags, phase = engine['make'](entry)
    a = state['ik1302']
    assert engine['boundary_ip'](a) == 0x35 and number(a.r[21]) == 7
    assert all(number(v) == 0 for v in a.r[1:24:3]) and number(a.r[34]) == 0
    initial_ring = engine['ring'](state, tags)
    # SOLE counterfactual: primary controller35→CF in the detached model.
    # All other working fields, ALL5 memories/wires, phase and tags are native.
    a.r[36], a.r[39] = q['N4'](15), q['N4'](12)
    pins = {name: (entry['state'][name]['keyX'], entry['state'][name]['keyY'])
            for name in engine['models']}
    assert pins['ik1302'] == (0, 0)
    seen, sequence, changes = {}, [], []
    first_idle = None
    for command in range(200):
        signature = early['complete_fingerprint'](state, tags, phase)
        if signature in seen:
            assert (command, seen[signature], command-seen[signature]) == (64, 34, 30)
            break
        seen[signature] = command
        a = state['ik1302']; code = engine['boundary_ip'](a); sequence.append(code)
        if code == 0x35:
            if first_idle is None: first_idle = command
            assert number(a.r[21]) == 15
        assert code != 0xD4
        before = engine['ring'](state, tags)
        phase, _ = engine['step'](state, tags, phase, pins)
        after = engine['ring'](state, tags)
        delta = [(slot, k, number(before[slot][k]), number(after[slot][k]))
                 for slot in engine['slots'] for k in range(42)
                 if number(before[slot][k]) != number(after[slot][k])]
        if delta: changes.append((command, code, delta))
    else: raise AssertionError('conditional constructor did not reach a complete period')
    assert first_idle == 33
    assert sequence[:6] == [0xCF, 0xC3, 0xC2, 0xDC, 0xEA, 0xEC]
    assert changes == [(14, 0xE7, [('X', 22, 7, 8)])]
    final_ring = engine['ring'](state, tags)
    assert [(slot, k, number(initial_ring[slot][k]), number(final_ring[slot][k]))
            for slot in engine['slots'] for k in range(42)
            if number(initial_ring[slot][k]) != number(final_ring[slot][k])] == [('X', 22, 7, 8)]
    print('PASS CONDITIONAL native idle7/address35→CF ONLY: workingF made, '
          'return35 at33, full ALL5/wires/phase/tags period30. Sole ring change '
          'X22:7→8; all other629 tetras held. NoD4, ordinaryC-signF or Ms exchange.', flush=True)
    print('CONDITIONAL finite route:', ' '.join(f'{v:02X}' for v in sequence[:33]), '→35', flush=True)
    return state, tags, phase, command, pins


def conditional_store_control(state, tags, phase, command, released):
    # A subsequent conventional fixed STORE/C schedule is a separate test,
    # NOT presumed to preserve the artificial F or even take a normal route.
    phase, command = early['advance_fixed'](
        state, tags, phase, command, 90, released, label='conditional CF before STORE')
    assert engine['boundary_ip'](state['ik1302']) == 0x35
    assert number(state['ik1302'].r[21]) == 15
    events, losses = [], []
    for name, physical in (('STORE', (6, 9)), ('C', (9, 8))):
        end = command+3360; held = dict(released); held['ik1302'] = physical
        phase, command = early['advance_fixed'](
            state, tags, phase, command, command+560, held,
            events=events, losses=losses, label='conditional CF '+name+' held')
        phase, command = early['advance_fixed'](
            state, tags, phase, command, end, released,
            events=events, losses=losses, label='conditional CF '+name+' released')
        if name == 'STORE': assert number(state['ik1302'].r[21]) == 15
    assert events == [], 'a new numeric writer needs a separate analysis'
    assert losses and (losses[0]['command'], losses[0]['ip']) == (3652, '60')
    assert word(engine['ring'](state, tags)['Y']) == '000000000000'
    print('PASS CONDITIONAL CF then fixed STORE/C: noD4; first A7F positional '
          'loss at3652/60, ordinaryC stillzero. No ordinary saved signF. '
          'This rejects this suffix ONLY, not other exports/reserves.', flush=True)
    print('OPEN: native joint A7=7/zeroB inlet, preserving export with usable '
          'control metadata, reader compatibility and later Ms transport; '
          'partialK2 NOT obtained.', flush=True)


if __name__ == '__main__':
    immutable_reference()
    cf_formula()
    exact_inlet()
    header_exits()
    seven['validate_native']()
    validate_native_controls()
    conditional_store_control(*conditional_finite_cf())
    immutable_reference()
