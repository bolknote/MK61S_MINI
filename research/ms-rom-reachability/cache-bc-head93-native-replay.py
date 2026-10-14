#!/usr/bin/env python3
"""Strict primary replay of a keyboard-only, ALL5-mirrored native witness.

Only the INITIAL recorded primary snapshot is supplied to the symbolic
analysis. Every later state is the calculated original42-tick output,
compared with the next native checkpoint and reduced to literal constants.
Native serial inputs/key signals/emitted outputs are recorded per tick.
No hypotheses are loaded into the reference; no IP/return/state repair.
This is primary replay plus fresh native ALL5 mirrors, NOT an ALL5 symbolic
transition count or a complete/inverse K2 proof.
"""
from pathlib import Path
import json
import runpy
import subprocess

from z3 import And, is_bv_value, simplify

root = Path(__file__).resolve().parent
m = runpy.run_path(str(root / 'cache-bc-head93-d8-reserve.py'))
r, w, q, eq = (m[n] for n in ('r', 'w', 'q', 'eq'))


def observed(row, label):
    a = q['State'](label)
    for group in ('r', 'st', 'm'):
        assert len(row[group]) == 42
        setattr(a, group, [q['N4'](v) for v in row[group]])
    for name in ('s', 's1'): setattr(a, name, q['N4'](row[name]))
    for name in ('l', 't', 'carry'): setattr(a, name, q['N1'](row[name]))
    return a


def literal_calculated(a):
    b = a.copy()
    for group in ('r', 'st', 'm'):
        values = [simplify(v) for v in getattr(a, group)]
        assert all(is_bv_value(v) for v in values), ('nonliteral calculated', group)
        setattr(b, group, values)
    for name in ('s', 's1', 'l', 't', 'carry'):
        value = simplify(getattr(a, name)); assert is_bv_value(value), name
        setattr(b, name, value)
    return b


def run():
    r['inlet']['immutable_reference']()
    native = json.loads(subprocess.check_output([
        'node', str(root / 'cache-bc-head93-native-witness.cjs'), '--proof-input'], text=True))
    report, records = native['report'], native['records']
    assert report['observerIndependentALL5'] and report['nativeOnlyPublicKeys']
    assert report['nativeBB'] == report['nativeBC'] == 1
    assert report['seedState']['ST2'] == [0, 2, 13]
    assert records[0]['ip'] == 0xA3 and records[-1]['ip'] == 0xBE
    state = observed(records[0]['before'], 'native_keyboard_INITIAL')
    w['prove'](w['base'](state, 0xA3), m['m']['match'](state, 11376),
        'recorded native A3 is the COMPLETE constantCC/head93 class11376')
    writers = []
    for i, record in enumerate(records):
        code = record['ip']; label = f'native_keyboard_replay_{i}_{code:02X}'
        p = w['base'](state, code)
        expected_before = observed(record['before'], label+'_before_check')
        w['prove'](p, w['same'](state, expected_before), 'calculated/native continuous BEFORE', False)
        assert all(len(record[n]) == 42 for n in ('keysX', 'keysY', 'serial', 'emitted'))
        output = []
        after = w['ex'](state, code, [q['N4'](v) for v in record['keysX']],
            [q['N4'](v) for v in record['keysY']],
            serial_inputs=[q['N4'](v) for v in record['serial']], emitted_outputs=output)
        expected_after = observed(record['after'], label+'_after_check')
        w['prove'](p, And(w['same'](after, expected_after),
            eq(output, [q['N4'](v) for v in record['emitted']])),
            'original calculated/native AFTER/all515 working bits/all42 emitted tetras', False)
        if record['emitted'] != record['before']['m']:
            writers.append({'ip': f'{code:02X}', 'word': record['word'],
                'positions': [j for j in range(42)
                    if record['emitted'][j] != record['before']['m'][j]]})
        state = literal_calculated(after)  # Calculated values, not the next checkpoint.
    r['inlet']['immutable_reference']()
    print('PASS', len(records), 'consecutive strict PRIMARY original-word transitions, '
          'all515 working-state bits and all42 outgoing tetras; native per-tick keys/serial.')
    print('PASS fresh unobserved native ALL5 mirrors after setup, seed and full second read; '
          'saved0/2/D constructed ONLY by public keys.')
    print('Actual primary outgoing changes:', json.dumps(writers))
    print('Native report:', json.dumps(report, ensure_ascii=False))
    print('LIMIT no ALL5 symbolic transition claim, hardware test, inverse/programme exchange '
          'or restored fullK2. Initial observation is not an injected emulator state.')


if __name__ == '__main__': run()
