#!/usr/bin/env python3
"""Physical sign/type sources before the RECORDED AC→C8 reader.

Native reference: keys and passive snapshots only. Symbolic variants modify
ordinary C.M1[24] and/or X.M2[34] in a detached full-ring model. They are NOT
keyboard constructors. This checks a concrete native inlet and its exact
121-macro source route, not every reachable C8 preparation.
"""
import json
from pathlib import Path
import runpy
import subprocess

from z3 import And, BitVec, simplify

root = Path(__file__).resolve().parent
engine = runpy.run_path(str(root / 'cache-stack-lift-ring.py'))
w, q = engine['w'], engine['q']
names, models = engine['names'], engine['models']
make, step, ring, boundary_ip = (engine[n] for n in
                               ('make', 'step', 'ring', 'boundary_ip'))
script = """
const {prepareReader}=require(process.argv[1]);
const {fixtures}=require(process.argv[2]);
const r=prepareReader({fixture:fixtures[1],selector:10,carrier:'0',fullSource:true});
const {layout}=require(process.argv[3]);
console.log(JSON.stringify({entries:r.completeSource,mapping:layout()}));
"""
data = json.loads(subprocess.check_output(
    ['node', '-e', script, str(root / 'cache-da-sign-native.cjs'),
     str(root / 'check_partial_k2_program_scan.cjs'),
     str(root / 'cache-d4-native-topology.cjs')], text=True))
entries, mapping = data['entries'], data['mapping']
assert len(entries) == 122 and entries[0]['ip'] == 0xAC and entries[-1]['ip'] == 0xC8


def pins(entry):
    return {name: (entry['state'][name]['keyX'], entry['state'][name]['keyY'])
            for name in models}


def set_physical(state, tags, slot, nibble, value):
    matches = 0
    for name in names:
        memory = state[name] if name.startswith('ir') else state[name].m
        for k, tag in enumerate(tags[name]):
            if tag == (slot, nibble):
                memory[k] = value
                matches += 1
    assert matches == 1


def baseline():
    state, tags, j = make(entries[0])
    for current, following in zip(entries, entries[1:]):
        assert boundary_ip(state['ik1302']) == current['ip']
        j, _ = step(state, tags, j, pins(current))
        for name in names:
            target = following['state'][name]
            for field in ('input', 'output'):
                assert simplify(state['_wire'][name][field]).as_long() == target[field]
            if name.startswith('ir'):
                assert [simplify(v).as_long() for v in state[name]] == target['m']
                assert j == target['tick']
            else:
                for field in ('r', 'm', 'st'):
                    assert [simplify(v).as_long() for v in getattr(state[name], field)] == target[field]
                for field in ('s', 's1', 'l', 't', 'carry'):
                    assert simplify(getattr(state[name], field)).as_long() == target[field]
    print('PASS recorded reader source ALL5 chips/R/ST/M/scalars/wires/phase: '
          '121 consecutive native AC→C8 transitions.', flush=True)


def arbitrary_C_sign():
    state, tags, j = make(entries[0])
    original = ring(state, tags)
    assert simplify(original['Y'][24]).as_long() == 0
    assert simplify(original['X'][34]).as_long() == 6
    sign = BitVec('digit_reader_ordinary_C_sign', 4)
    set_physical(state, tags, 'Y', 24, sign)
    before = ring(state, tags)
    p = q['base_solver'](state['ik1302'], 0xAC)
    first_load = True
    for count, current in enumerate(entries[:-1]):
        assert boundary_ip(state['ik1302'], p) == current['ip']
        if current['ip'] == 0xD6 and first_load:
            assert count == 26 and tags['ik1302'][24] == ('Y', 24)
            w['prove'](p, state['ik1302'].m[24] == sign,
                       'Physical ordinary C.M1[24] reaches the first D6 exactly')
            first_load = False
        j, _ = step(state, tags, j, pins(current), p)
    after = ring(state, tags)
    assert boundary_ip(state['ik1302'], p) == 0xC8
    w['prove'](p, And(state['ik1302'].st[25] == sign,
                     after['Y'][24] == sign, after['X'][34] == 6),
               'All16 detached physical C signs preserve the recorded '
               'AC→C8 controller route; ST25 receives the sign, X type remains6')
    # The working numeric stack changes: this is NOT a whole-ring no-write
    # claim. Only the original program, Ms and ordinary register words are
    # checked. The initial sign substitution is included in before.
    positions = [(slot, k) for slot in engine['slots'] for k in range(42)
                 if k % 3 == 2 or (k % 3 == 0 and k < 36)]
    positions += [(slot, k) for slot, indices in mapping['hidden'].items() for k in indices]
    w['prove'](p, w['eq']([after[slot][k] for slot, k in positions],
                         [before[slot][k] for slot, k in positions]),
               'All16 C-sign variants hold ALL105 program/56Ms/15 ordinary '
               'register words relative to the modified input; working stack may change')
    p.add(sign == 15)
    w['prove'](p, state['ik1302'].st[25] == 15,
               'CONDITIONAL actual source C-signF reaches C8 with ST25=F; '
               'no saved-ST assignment is needed, but X is still type6')


def early_type7_cut():
    state, tags, j = make(entries[0])
    set_physical(state, tags, 'Y', 24, q['N4'](15))
    set_physical(state, tags, 'X', 34, q['N4'](7))
    observed = []
    for count, current in enumerate(entries[:-1]):
        code = boundary_ip(state['ik1302'])
        if count == 26:
            assert current['ip'] == 0xD6 and code == 0xD7
            break
        assert code == current['ip']
        observed.append(code)
        j, _ = step(state, tags, j, pins(current))
    else:
        raise AssertionError('expected early type7 reader cut')
    assert 0xC8 not in observed and 0xD6 not in observed
    # The changed header exits before even loading the sign source in C.
    for code in (0xD7, 0x7F):
        assert boundary_ip(state['ik1302']) == code
        j, _ = step(state, tags, j, pins(entries[26]))
    assert boundary_ip(state['ik1302']) == 0x33
    print('PASS early type7 cut: changing both physical sources before the '
          'recorded AC takes D7/7F→33 at step26, before first C-sign D6 '
          'and before C8. Simply pre-seeding both fields does NOT splice '
          'the conditional writer to this native reader.', flush=True)
    print('SCOPE: only this recorded inlet/construction is cut. Another '
          'reader preparation, a post-reader type7 repair, redirected '
          'cleanup source, or an earlier code reserve remain open. '
          'No native signF constructor or partialK2.', flush=True)


if __name__ == '__main__':
    baseline()
    arbitrary_C_sign()
    early_type7_cut()
