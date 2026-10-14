#!/usr/bin/env python3
"""CONDITIONAL earlier A2 marker sites, exact writes and native carrier calendar.

The native record is read-only evidence for the initial A2 working/control
packet and carrier calendar. Hypothetical ring words/serial remain purely
symbolic and are NEVER loaded into any emulator. Every original IP/return is
derived; marker pinning describes a missing constructor, not native success.
Other-chip numeric movement, marker survival, E7/inverse/safe exit are open.
"""
from pathlib import Path
import json
import runpy
import subprocess

from z3 import And, BitVecVal, If, sat

root = Path(__file__).resolve().parent
replay = runpy.run_path(str(root / 'cache-bc-head93-native-replay.py'))
m, r, w, q, eq = (replay[n] for n in ('m', 'r', 'w', 'q', 'eq'))
A, B, C = m['A'], m['B'], m['C']


def gate():
    a = q['State']('A2_marker_gate'); p = w['base'](a, 0xA2)
    output = []
    b = w['ex'](a, 0xA2, *q['arbitrary_keys']('A2_marker_gate_keys'),
        serial_inputs=q['State']('A2_marker_gate_serial').m, emitted_outputs=output)
    w['prove'](p, And(w['ip'](b) == If(a.m[22] == 15,
        BitVecVal(0xA3, 8), BitVecVal(0xA2, 8)), eq(B(b), B(a)),
        eq(C(b), C(a)), eq(b.st[:36], a.st[:36]), eq(A(b)[:10], A(a)[:10]),
        b.r[30] == a.r[32], b.r[33] == a.r[35], eq(output, a.m)),
        'GLOBAL A2 exits iff numericM2[22]=F; sourceB/control/cache lower10 held, ring neutral')


def conditional_waits(native, waits):
    records, calendar = native['records'], native['report']['carrierCycle']
    entry = next(e for e in records if e['ip'] == 0xA2)
    # Working/control fields are observed constants. The ring data is a
    # separate symbolic hypothesis, not a repaired/loaded calculator state.
    a = replay['observed'](entry['before'], f'marker_A2_native_working_w{waits}')
    a.m = q['State'](f'marker_symbolic_initial_ring_w{waits}').m
    origin = a; b = a; p = w['base'](a, 0xA2)
    sequence = (0xA2,)*waits + (0xA3, 0xCC, 0xBB, 0xBC)
    last_output = None
    for i, code in enumerate(sequence):
        if code == 0xA2:
            p.add(b.m[22] == 15 if i == waits-1 else b.m[22] != 15)
        assert p.check() == sat
        w['prove'](p, w['ip'](b) == code, 'conditional actual nextIP', False)
        if code == 0xA3:
            w['prove'](p, m['m']['match'](b,11376), 'conditional true frozen A3class11376', False)
        before = b; output = []
        b = w['ex'](b, code, *q['arbitrary_keys'](f'marker_w{waits}_keys{i}'),
            serial_inputs=q['State'](f'marker_w{waits}_serial{i}').m, emitted_outputs=output)
        if code == 0xA3:
            w['prove'](p, And(eq(output[28:35:3], A(before)[9:]),
                *[output[j] == before.m[j] for j in range(42) if j not in (28,31,34)]),
                'conditional preliminary A3 upper3 write must be protected', False)
        elif code == 0xBC:
            w['prove'](p, And(w['ip'](b) == 0x93,
                eq(output[1:42:3], [*B(origin),q['N4'](3),q['N4'](10)]),
                *[output[j] == before.m[j] for j in range(42) if j%3!=1]),
                'conditional BC14 writes full original source +3/A, true93', False)
            last_output = output
        else:
            w['prove'](p, eq(output,before.m), 'conditional wait/CC/BB ring neutral', False)
    assert last_output is not None
    marker_word = entry['word'] + waits - 1
    row = {'waits':waits,'markerWord':marker_word,
        'markerOwner':calendar[marker_word%15],
        'preliminaryA3Owner':calendar[(marker_word+1)%15],
        'BCtargetOwner':calendar[(marker_word+4)%15],
        'markerFieldLSBfirst':7,'markerFieldMSBfirst':4,
        'BCsourceRaw12':''.join(f'{v.as_long():X}' for v in reversed(B(origin))),
        'nativeMarkerConstructed':False,'conditionalOnly':True}
    print(json.dumps(row,ensure_ascii=False),flush=True)
    return row


def run():
    r['inlet']['immutable_reference'](); gate()
    native = json.loads(subprocess.check_output(['node',
        str(root/'cache-bc-head93-native-carriers.cjs'),'--proof-input'],text=True))
    entry = next(e for e in native['records'] if e['ip'] == 0xA2)
    waits = [e for e in native['records'] if e['ip'] == 0xA2]
    assert entry['word'] == 1247 and len(waits) == 10
    assert all(e['before']['m'][22] != 15 for e in waits[:-1])
    assert waits[-1]['before']['m'][22] == 15
    assert waits[-1]['numericOwner'] == 'unclassified:aux0'
    rows = [conditional_waits(native,n) for n in range(1,11)]
    assert [e['BCtargetOwner'] for e in rows[:5]] == ['Ms:Q','Ms:P7','Ms:P8','Ms:P9','Ms:P10']
    assert rows[-1]['BCtargetOwner'] == 'stack:Z'
    r['inlet']['immutable_reference']()
    print('PASS native10 A2 words end at aux0 marker ->Z; conditional1..5 earlier exits '
          'target five Ms words, with exposed A3 upper3 side writes and true93.')
    print('LIMIT no native marker constructor/lifetime or Ms-write witness; '
          'symbolic ring hypotheses were NOT loaded. Other-chip moves/E7/inverse/safe exit remain open.')


if __name__ == '__main__': run()
