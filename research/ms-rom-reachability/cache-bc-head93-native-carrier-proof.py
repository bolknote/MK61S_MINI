#!/usr/bin/env python3
"""Native carrier binding plus strict122-word PRIMARY replay and data source.

Carrier tags are observer-owned labels, never emulator contents. Fixed native
inputs are used only in symbolic replay; no observed/hypothesized state is
loaded into a calculator. Universal EE/E3/E4 equations distinguish a data
source from a carrier merely passing through the primary chip at that time.
"""
from pathlib import Path
import json
import runpy
import subprocess

from z3 import And

root = Path(__file__).resolve().parent
replay = runpy.run_path(str(root / 'cache-bc-head93-native-replay.py'))
m, r, w, q, eq = (replay[n] for n in ('m', 'r', 'w', 'q', 'eq'))
A, B = m['A'], m['B']


def universal_sources():
    for code in (0xEE, 0xE4):
        label = f'carrier_source_{code:02X}'
        a = q['State'](label); p = w['base'](a, code)
        output = []
        b = w['ex'](a, code, *q['arbitrary_keys'](label+'_keys'),
            serial_inputs=q['State'](label+'_serial').m, emitted_outputs=output)
        source = eq(A(b), a.m[1:36:3]) if code == 0xEE else eq(B(b), A(a))
        w['prove'](p, And(source, eq(output, a.m)),
            'GLOBAL EE loads numericM2 into A/ring held' if code == 0xEE
            else 'GLOBAL E4 copies OLD A into B, NOT current numericM2/ring held')
    m['m']['restore_origin']()


def run():
    r['inlet']['immutable_reference']()
    universal_sources()
    native = json.loads(subprocess.check_output(['node',
        str(root / 'cache-bc-head93-native-carriers.cjs'), '--proof-input'], text=True))
    report, records = native['report'], native['records']
    assert report['ALL5mirror'] and report['onlyPublicKeys']
    assert report['carrierTagsNeverLoaded'] and report['bb'] == report['bc'] == 1
    assert report['sourceReadOwner'] == 'stack:Y'
    assert report['BCtargetOwner'] == 'stack:Z' and report['zeroE7targetOwner'] == 'stack:Y'
    assert len(records) == 122 and records[0]['ip'] == 0xEE and records[-1]['ip'] == 0xBE
    state = replay['observed'](records[0]['before'], 'carrier_NATIVE_INITIAL')
    source = A(replay['observed'](records[1]['before'], 'carrier_E3_source'))
    seen_a3 = False
    for i, record in enumerate(records):
        code = record['ip']; label = f'carrier_native_{i}_{code:02X}'
        p = w['base'](state, code)
        w['prove'](p, w['same'](state, replay['observed'](record['before'], label+'_before')),
            'continuous calculated/native before', False)
        if record['word'] == 1228:
            w['prove'](p, eq(A(state), source), 'native realE4 keeps early EE/Y source', False)
        if code == 0xA3:
            w['prove'](p, m['m']['match'](state, 11376), 'native whole A3 frozen class11376')
            seen_a3 = True
        if code == 0xBB:
            w['prove'](p, eq(B(state), source), 'native BB input numericB equals EARLY EE/Y read')
        output = []
        after = w['ex'](state, code, [q['N4'](v) for v in record['keysX']],
            [q['N4'](v) for v in record['keysY']],
            serial_inputs=[q['N4'](v) for v in record['serial']], emitted_outputs=output)
        w['prove'](p, And(w['same'](after, replay['observed'](record['after'], label+'_after')),
            eq(output, [q['N4'](v) for v in record['emitted']])),
            'all515 native working bits and42 outgoing tetras', False)
        if code == 0xBC:
            w['prove'](p, eq(output[1:36:3], source), 'native BC writes EARLY EE/Y numeric source')
        state = replay['literal_calculated'](after)
    assert seen_a3
    r['inlet']['immutable_reference']()
    print('PASS122 consecutive native ORIGINAL PRIMARY transitions, all515 bits/42 outgoing; '
          'fresh native ALL5 mirror; every282240 ring ticks checked against real five-cell routing.')
    print('PASS actual EE1214 reads Y; E3 holds A; E4 copies OLD A intoB while X carrier passes. '
          'BC1260 writes Z; E71319 clears Y. This witness is Y->Z, NOT X->Z or Ms/programme.')
    print('LIMIT fixed native fixture/carrier identity + universal source equations; '
          'not a general native payload family, fullK2, hardware experiment or ALL5 symbolic count.')


if __name__ == '__main__': run()
