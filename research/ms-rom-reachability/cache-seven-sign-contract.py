#!/usr/bin/env python3
"""Native seven mask plus a CONDITIONAL arithmetic57 signF constructor.

All reference actions are public keys/frames. Local57/58 entries below are
detached ROM hypotheses. Native7/X→П does prepare the required data/flags
at48, but does not enter57. The separate cache-seven-57-entry-invariant.py
now proves ALL reset57 entries L0; these local L1 constructors are not
reachable keyboard protocols. This is metadata preparation, not cache export.
"""
import json
from pathlib import Path
import runpy
import subprocess

from z3 import And, simplify

root = Path(__file__).resolve().parent
early = runpy.run_path(str(root / 'cache-input-mask-early-exit.py'))
engine, w, q = (early[name] for name in ('engine', 'w', 'q'))
native = json.loads(subprocess.check_output([
    'node', str(root / 'cache-seven-sign-source-native.cjs'), '--proof-input'], text=True))


def validate_native():
    assert native['report']['observerIndependent'] is True
    state, tags, phase = engine['make'](native['entry'])
    early['snapshot_matches'](state, phase, native['prefix'][0]['state'])
    for current, following in zip(native['prefix'], native['prefix'][1:]):
        assert engine['boundary_ip'](state['ik1302']) == current['ip']
        pins = {name: (current['state'][name]['keyX'], current['state'][name]['keyY'])
                for name in engine['models']}
        phase, _ = engine['step'](state, tags, phase, pins)
        early['snapshot_matches'](state, phase, following['state'])
    command = native['prefix'][-1]['command']
    released = {name: (native['entry']['state'][name]['keyX'],
                       native['entry']['state'][name]['keyY']) for name in engine['models']}
    assert released['ik1302'] == (0, 0)
    phase, command = early['advance_fixed'](
        state, tags, phase, command, native['end']['command'], released,
        label='native seven quiet')
    early['snapshot_matches'](state, phase, native['end']['state'])
    assert tags == engine['make'](native['end'])[1]
    assert command == 1680
    print('PASS native seven: ALL64 consecutive five-chip transitions plus '
          'complete1680-macro end/wires/phase/tags and fresh mirror.', flush=True)
    entries = native['storePrefix']
    state, tags, phase = engine['make'](native['storeEntry'])
    early['snapshot_matches'](state, phase, entries[0]['state'])
    for current, following in zip(entries, entries[1:]):
        pins = {name: (current['state'][name]['keyX'], current['state'][name]['keyY'])
                for name in engine['models']}
        phase, _ = engine['step'](state, tags, phase, pins)
        early['snapshot_matches'](state, phase, following['state'])
    command = entries[-1]['command']
    held = {name: (entries[0]['state'][name]['keyX'], entries[0]['state'][name]['keyY'])
            for name in engine['models']}
    assert held['ik1302'] == (6, 9)
    phase, command = early['advance_fixed'](state, tags, phase, command, 560, held,
                                           label='native seven STORE-prefix held')
    released = dict(held); released['ik1302'] = (0, 0)
    phase, command = early['advance_fixed'](state, tags, phase, command, 3360, released,
                                           label='native seven STORE-prefix released')
    early['snapshot_matches'](state, phase, native['storeEnd']['state'])
    assert tags == engine['make'](native['storeEnd'])[1]
    assert native['report']['native57Called'] is False
    print('PASS native7/X→П: additional64 ALL5 transitions and complete3360 end; '
          'true mask7/C1..6=8/L1 at48, no57 or signF claimed.', flush=True)


def constructor57():
    a = q['State']('seven_arithmetic57')
    p = w['base'](a, 0x57)
    p.add(a.r[21] == 7, a.l == 1,
          *[a.r[3*index] == 15 for index in range(7)],
          *[a.r[3*index+2] == 8 for index in range(1, 7)])
    outputs = []
    b = w['ex'](a, 0x57, *q['arbitrary_keys']('seven_arithmetic57_keys'),
                emitted_outputs=outputs)
    w['prove'](p, And(b.r[21] == 15, w['ip'](b) == 0x55, w['eq'](outputs, a.m)),
               'CONDITIONAL57 makes F from native-shaped A7=7/leadingF, '
               'with L1/C1..6=8; no write, exits55, arbitrary keys/future pages')

    # Compare the actual native seven fields with the precise sufficient flags.
    # Setting an IP here is ONLY the hypothetical primary entry57.
    state, _, _ = engine['make'](native['entry'])
    actual = state['ik1302']
    for change_c1, change_l, expected in (
        (False, False, 7), (True, False, 7), (False, True, 7), (True, True, 15)):
        before = actual.copy()
        before.r[36], before.r[39] = q['N4'](7), q['N4'](5)
        if change_c1:
            before.r[5] = q['N4'](8)
        if change_l:
            before.l = q['N1'](1)
        p = w['base'](before, 0x57)
        outputs = []
        after = w['ex'](before, 0x57,
                       *q['arbitrary_keys'](f'seven_flags_{change_c1}_{change_l}'),
                       emitted_outputs=outputs)
        w['prove'](p, And(after.r[21] == expected, w['ip'](after) == 0x55,
                         w['eq'](outputs, before.m)),
                   f'CONDITIONAL57 native seven flags C1repair={change_c1}/'
                   f'Lrepair={change_l} => A7={expected:X}')
    print('BARE native7 lacks C1=8/L1 at35. The additional native X→П '
          'prefix below prepares them at48, but neither reference control '
          'calls57 or creates signF.', flush=True)


def native_ready48():
    entry = next(value for value in native['storePrefix'] if value['ip'] == 0x48)
    state, _, _ = engine['make'](entry)
    a = state['ik1302']
    assert entry['command'] == 8
    assert all(simplify(a.r[3*index]).as_long() == 15 for index in range(7))
    assert simplify(a.r[21]).as_long() == 7
    assert all(simplify(a.r[3*index+2]).as_long() == 8 for index in range(1, 7))
    assert simplify(a.l).as_long() == 1
    # SOLE counterfactual for this actual native inlet: entering57 instead of48.
    # No numeric or flag field changes, and nothing enters the reference.
    b = a.copy()
    b.r[36], b.r[39] = q['N4'](7), q['N4'](5)
    p = w['base'](b, 0x57)
    outputs = []
    c = w['ex'](b, 0x57, *q['arbitrary_keys']('seven_native48_to57_keys'),
                emitted_outputs=outputs)
    w['prove'](p, And(c.r[21] == 15, w['ip'](c) == 0x55,
                     w['eq'](outputs, b.m)),
               'CONDITIONAL native prepared48→57: ONLY address hypothesis, '
               'no data/flag repair; produces A7=F, no write, exits55')
    print('NATIVE DATA ONLY: public7/X→П naturally prepares ALL DATA/FLAGS of57 '
          'at real48. The separate reset57/L0 invariant closes the native '
          'L1 inlet, despite the successful detached address hypothesis. '
          'No native signF or cache export is claimed.', flush=True)


def setup58():
    a = q['State']('seven_setup58')
    p = w['base'](a, 0x58); p.add(a.r[2] == 8, a.r[5] == 0)
    outputs = []
    b = w['ex'](a, 0x58, *q['arbitrary_keys']('seven_setup58_keys'),
                emitted_outputs=outputs)
    w['prove'](p, And(b.r[2] == 0,
                     *[b.r[3*index+2] == 8 for index in range(1, 7)],
                     w['eq'](b.r[0:27:3], a.r[0:27:3]), w['ip'](b) == 0x4E,
                     w['eq'](outputs, a.m)),
               'CONDITIONAL58 from native C0=8/C1=0 fills C1..6=8, '
               'holds A0..8 only, exits4E; not entry58/57 or a proof of L1')
    state, _, _ = engine['make'](native['entry'])
    actual = state['ik1302'].copy()
    actual.r[36], actual.r[39] = q['N4'](8), q['N4'](5)
    p = w['base'](actual, 0x58)
    b = w['ex'](actual, 0x58, *q['arbitrary_keys']('seven_concrete58_keys'))
    w['prove'](p, And(b.l == 1, b.r[21] == 7,
                     *[b.r[3*index] == 15 for index in range(7)],
                     *[b.r[3*index+2] == 8 for index in range(1, 7)]),
               'CONDITIONAL entry58 from exact native seven fills C1..6=8 '
               'and naturally sets L1 while keeping lower7 maskF/A7=7; '
               'all DATA prerequisites of57, but exits4E not57')
    a = q['State']('seven_exit55')
    p = w['base'](a, 0x55)
    outputs = []
    b = w['ex'](a, 0x55, *q['arbitrary_keys']('seven_exit55_keys'),
                emitted_outputs=outputs)
    w['prove'](p, And(w['ip'](b) == 0x06, w['eq'](b.r[0:27:3], a.r[0:27:3]),
                     w['eq'](outputs, a.m)),
               '55 exits06 and holds A0..8 incl A7/F; no write. '
               '57→55 is not an endless counter loop or a direct D4 call')


if __name__ == '__main__':
    validate_native()
    constructor57()
    setup58()
    native_ready48()
