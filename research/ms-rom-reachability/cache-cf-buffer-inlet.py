#!/usr/bin/env python3
"""Exact CF-buffer writer cut and native DATA readiness for one restore93.

The complete reset-controller graph is a conservative control model, not a
keyboard witness. The real two payload protocols prepare B7=6/7 and zeroST1,
but neither supplies a joint7/zeroST0 inlet. A separate ALL5 continuation
changes ONLY primary35→93. It returns70, fails9E→8C and loses7 atEE;
neither that detached entry nor a repaired return is a native recipe.
"""
from collections import Counter, deque
import hashlib
import json
from pathlib import Path
import runpy
import subprocess

from z3 import And, Or, sat, simplify, unsat

root = Path(__file__).resolve().parent
w = runpy.run_path(str(root / 'cache46-writer-contracts.py'))
q = w['q']
g = runpy.run_path(str(root / 'cache-numeric-export-gates.py'))
states, edges = g['states'], g['edges']
pushers, rotators = (0x40, 0x93), (0x47, 0x94, 0x95)
single = (0x93, 0x94, 0x95, 0x98, 0x9A)
double = (0x91, 0x92, *single, *single)
number = lambda v: simplify(v).as_long()
lower_st = lambda a, lane=0: a.st[lane:24:3]
lower_r = lambda a, lane=0: a.r[lane:24:3]
zero = lambda values: And(*[v == 0 for v in values])


def immutable_reference():
    expected = {
        q['ROM_PATH'].parent / 'mk61.cjs':
            'b15bc586ac3804eb5622b8072e88f35bcd2081abbe2195fcefa5a718e56ece0c',
        q['ROM_PATH']:
            '6c3f85b3e942cdd4d4191e46e98a50829eb850011b8b7a3cc01b12e5e2a31a33',
        root / 'ik1302_symbolic.py':
            '1f54d40447a5899199707abe4a42900ab758b21ef836e041ce76bd3e0faa4155',
        root / 'analyze_gates.py':
            '893e844a2d9448c3af956da11fad27498be913178b5d1b5668ffe516e7d8f1b0',
        root / 'audit_ms_rom_control.py':
            '7dc5ce13a58988cd45e4b0625aa7b3d962c94df3f1634ad83fcb53e3829af271',
        root / 'k1-formatter-entry-audit.py':
            'fb548129e96636ccea8878c65079847b60c4bbf1d3b299d8b64c3b2a4f6c3a3f',
    }
    for path, fingerprint in expected.items():
        assert hashlib.sha256(path.read_bytes()).hexdigest() == fingerprint, path


def buffer_writer_inventory():
    writers, joint_clearers = [], []
    for code in range(256):
        a = q['State'](f'cf_buffer_word_{code:02X}')
        p = w['base'](a, code)
        b = w['ex'](a, code, *q['arbitrary_keys'](f'cf_buffer_keys_{code:02X}'))
        p.push(); p.add(~w['eq'](lower_st(b), lower_st(a)))
        answer = p.check(); p.pop(); assert answer in (sat, unsat)
        if answer == sat:
            writers.append(code)
            p.push(); p.add(a.r[21] == 7, Or(*[v != 0 for v in lower_st(a)]),
                            b.r[21] == 7, zero(lower_st(b)))
            possible = p.check(); p.pop(); assert possible in (sat, unsat)
            if possible == sat: joint_clearers.append(code)
    assert writers == [0x40, 0x47, 0x93, 0x94, 0x95]
    assert joint_clearers == list(rotators)
    for code in writers:
        a = q['State'](f'cf_buffer_mapping_{code:02X}')
        p = w['base'](a, code); out = []
        b = w['ex'](a, code, *q['arbitrary_keys'](f'cf_buffer_mapping_keys_{code:02X}'),
                    emitted_outputs=out)
        claim = (w['eq'](lower_st(b), lower_r(a)) if code in pushers else
                 And(w['eq'](lower_st(b), lower_st(a, 1)), b.r[21] == a.st[21]))
        w['prove'](p, And(claim, w['eq'](out, a.m)),
                   f'{code:02X} exact lowerST0 source/no outgoing write')
    a = q['State']('cf_buffer_fused93'); p = w['base'](a, 0x93)
    b = a
    for index, code in enumerate((0x93, 0x94)):
        w['prove'](p, w['ip'](b) == code, 'forced93/94 stage', False)
        b = w['ex'](b, code, *q['arbitrary_keys'](f'cf_buffer_fused_keys{index}'))
    w['prove'](p, And(w['ip'](b) == 0x95, b.r[21] == a.r[21],
                     w['eq'](lower_st(b), lower_st(a))),
               'fused93→94 preserves A7/lowerST0; 94 is not an independent clear here')
    for code in (0x35, 0x45, 0x8B, 0x48, 0x4A, 0x4B, 0x4C,
                 0x4E, 0x97, 0x99, 0x9B, 0x9C, 0x9E):
        a = q['State'](f'cf_buffer_scanner_{code:02X}'); p = w['base'](a, code)
        b = w['ex'](a, code, *q['arbitrary_keys'](f'cf_buffer_scanner_keys_{code:02X}'))
        w['prove'](p, And(b.r[21] == a.r[21], w['eq'](lower_st(b), lower_st(a))),
                   'scanner buffer/A7 preservation', False)
    print('PASS ALL256:251 hold lowerST0; only40/47/93/94/95 change it. '
          'Only47/94/95 locally clear nonzeroST0 while keeping7. '
          'Thirteen scanner/ВП words hold both7 and the buffer.', flush=True)
    return writers


def packet_contracts():
    for name, sequence in (('single93', single), ('double91', double)):
        a = q['State']('cf_buffer_'+name); p = w['base'](a, sequence[0]); b = a
        for index, code in enumerate(sequence):
            w['prove'](p, w['ip'](b) == code, name+' forced stage', False)
            before, out = b, []
            b = w['ex'](b, code, *q['arbitrary_keys'](f'cf_buffer_{name}_keys{index}'),
                        emitted_outputs=out)
            w['prove'](p, w['eq'](out, before.m), name+' no outgoing write', False)
        sources = ((lower_r(a, 1), lower_r(a, 2), lower_st(a), lower_st(a, 1), lower_r(a))
                   if name == 'single93' else
                   (lower_r(a), lower_st(a), lower_st(a, 1), lower_r(a, 1), lower_r(a, 2)))
        targets = (lower_r(b), lower_r(b, 1), lower_r(b, 2), lower_st(b), lower_st(b, 1))
        w['prove'](p, And(*[w['eq'](dst, src) for dst, src in zip(targets, sources)],
                         w['ip'](b) == w['stack'](a)[0]),
                   name+' exact lower8 five-buffer mapping and ORIGINAL return head')
        if name == 'single93':
            w['prove'](p, And(b.r[21] == 7, zero(lower_st(b))) ==
                       And(a.r[22] == 7, zero(lower_st(a, 1))),
                       'single93 gives joint A7=7/zeroST0 IFF oldB7=7/zeroST1')
    print('LIMIT: data5-cycle/involution are not repeatable keyboard gadgets; '
          'no return tag or next address is inserted between packets.', flush=True)


def incoming_contracts():
    # These are PRIMARY ROM addresses, not the fixture's program opcodeA3.
    for code in (0x92, 0x9A, 0xA3, 0xA9, 0xBC, 0xD4, 0xD6, 0xEE):
        a = q['State'](f'cf_buffer_caller_{code:02X}'); p = w['base'](a, code)
        b = w['ex'](a, code, *q['arbitrary_keys'](f'cf_buffer_caller_keys_{code:02X}'))
        p.add(w['ip'](b) == 0x93)
        numeric = And(w['eq'](lower_st(b, 1), lower_st(a, 1)),
                      b.r[22] == a.r[23] if code in (0x92, 0x9A) else b.r[22] == a.r[22])
        if code == 0xA3:
            control = And(w['byte'](a.r[37], a.r[40]) == 0x93,
                          w['eq'](w['stack'](b), w['stack'](a)))
        elif code == 0x92:
            control = w['stack'](b)[0] == 0x93
        else:
            control = And(w['stack'](a)[0] == 0x93,
                          w['eq'](w['stack'](b), [w['stack'](a)[1],
                                                w['stack'](a)[2], w['stack'](a)[0]]))
        w['prove'](p, And(numeric, control), f'{code:02X} exact numeric/control inlet93')
    print('PASS incoming93 split: A3 dispatches old service vector93 and '
          'HOLDS return stack/B7/ST1; A9/BC/D4/D6/EE return through old top93, '
          'rotating original second into the new head while holding B7/ST1. '
          '92/9A instead import B7 from C7. These are local contracts, '
          'NOT simultaneous native data/control or harmless physical writes.', flush=True)


def controller_cut(writers):
    assert len(states) == 52416 and sum(map(len, edges)) == 95731
    starts = [i for i, s in enumerate(states) if s[0] == 0x35]
    assert len(starts) == 806
    reached, todo = set(starts), deque(starts)
    while todo:
        index = todo.popleft()
        if states[index][0] in pushers: continue
        for child in edges[index]:
            if child not in reached: reached.add(child); todo.append(child)
    counts = Counter(states[i][0] for i in reached)
    assert len(reached) == 38189 and counts[0x8C] == 159 and counts[0xCF] == 0
    assert counts[0x47] == counts[0x95] == 0
    assert not any(s[0] == 0x94 or 0x94 in s[1] or 0x95 in s[1] for s in states)
    assert not set(writers)-set(pushers)-{0x94} & set(counts)
    expected = {
        0x8C: {0x9E: 208}, 0x9E: {0x9C: 208}, 0x9C: {0x9B: 208},
        0x9B: {0x99: 168, 0x9B: 208, 0xD5: 292},
        0x99: {0x09: 190, 0x97: 536, 0xA3: 1},
        0x97: {0x4E: 417, 0x9D: 208},
        0x40: {0xEC: 378}, 0x47: {0xE7: 47},
        0x93: {0x92: 326, 0x9A: 98, 0xA3: 22, 0xA9: 5,
               0xBC: 1, 0xD4: 13, 0xD6: 9, 0xEE: 1},
        0x95: {0x93: 247},
    }
    found = {code: Counter() for code in expected}
    for index, row in enumerate(edges):
        for child in row:
            code = states[child][0]
            if code in found: found[code][states[index][0]] += 1
    assert found == expected
    heads = Counter(s[1][0] for s in states if s[0] == 0x93)
    assert heads == {0x8D: 30, 0x93: 98, 0xAC: 22, 0xBE: 18, 0xD2: 14,
                     0xDD: 13, 0xE2: 18, 0xE4: 18, 0xE5: 16}
    assert not {0x35, 0x70, 0x8C, 0xCF} & set(heads)
    a3_callers = [states[i] for i, row in enumerate(edges) if states[i][0] == 0xA3
                  and any(states[child][0] == 0x93 for child in row)]
    assert len(a3_callers) == 22
    assert all(s[1][0] == 0xAC and s[2] == 0x93 and s[3] == [9]
               and s[7] == [0] for s in a3_callers)
    print('PASS complete806→38189 cut, stopping BEFORE40/93:159 first8C, '
          'noCF/47/95. Every executed word before the cut holds lowerST0; '
          'internal94 is accounted for in fused93.', flush=True)
    print('PASS ALL93 heads:', {f'{k:02X}': v for k, v in sorted(heads.items())}, flush=True)
    print('LIMIT: no shortcut from a nonzero native idleST0 to CF/C3 without '
          'a preceding40/93. Earlier packets/other preparation remain OPEN. '
          'No93 return35/70/8C/CF exists in the complete reset control graph.', flush=True)
    print('NEXT conditional control target: all22 A3→93 contexts have vector93, '
          'original returnAC, S1=9 and R26=0. This is a compatible CALLER candidate, '
          'not a proven joint B7=7/zeroST1 inlet.', flush=True)


def match_controller(a):
    ip = number(w['ip'](a)); sp = [number(v) for v in w['stack'](a)]
    vector = number(w['byte'](a.r[37], a.r[40])); s1 = number(a.s1)
    r35, r38, r26 = (number(a.r[k]) for k in (35, 38, 26))
    matches = []
    for index, (code, tags, vec, selectors, delta, r38s, dr38, r26s, types) in enumerate(states):
        if code != ip or tags != sp or s1 not in selectors: continue
        if vec == 'diagonal' and number(a.r[37]) != number(a.r[40]): continue
        if vec not in (None, 'diagonal') and vec != vector: continue
        if delta is not None and delta != (s1-r35) % 16: continue
        if r38s is not None and r38 not in r38s: continue
        if dr38 is not None and dr38 != (r38-r35) % 16: continue
        if r26s is not None and r26 not in r26s: continue
        assert types is None
        matches.append(index)
    assert matches, 'actual native controller is not covered by the reset graph'
    return matches


def validate_native(early, fixtures):
    engine = early['engine']
    for native in fixtures:
        assert native['report']['observerIndependent'] is True
        state, tags, phase = engine['make'](native['initial'])
        command = 0
        first = native['origin']; second = native['prefix']
        held = {name: (first[0]['state'][name]['keyX'], first[0]['state'][name]['keyY'])
                for name in engine['models']}
        released = dict(held); released['ik1302'] = (0, 0)
        digit = dict(released); digit['ik1302'] = (
            second[0]['state']['ik1302']['keyX'], second[0]['state']['ik1302']['keyY'])
        assert held['ik1302'] == (8, 9) and digit['ik1302'] == (11, 1)
        for entries, pins in ((first, held), (second, digit)):
            if entries[0]['command'] > command:
                phase, command = early['advance_fixed'](state, tags, phase, command,
                    560, held, label='native buffer П→X held')
                phase, command = early['advance_fixed'](state, tags, phase, command,
                    1120, released, label='native buffer П→X released')
                phase, command = early['advance_fixed'](state, tags, phase, command,
                    entries[0]['command'], digit, label='native buffer digit9 toAC')
            early['snapshot_matches'](state, phase, entries[0]['state'])
            for current, following in zip(entries, entries[1:]):
                assert command == current['command']
                assert engine['boundary_ip'](state['ik1302']) == current['ip']
                phase, _ = engine['step'](state, tags, phase, pins); command += 1
                early['snapshot_matches'](state, phase, following['state'])
        phase, command = early['advance_fixed'](state, tags, phase, command,
            1680, digit, label='native buffer digit9 held')
        phase, command = early['advance_fixed'](state, tags, phase, command,
            6720, released, label='native buffer reader released')
        early['snapshot_matches'](state, phase, native['end']['state'])
        assert tags == engine['make'](native['end'])[1]
        matches = match_controller(state['ik1302'])
        assert any(number(v) != 0 for v in lower_st(state['ik1302']))
        print('PASS native', native['report']['name'], ':', len(first)+len(second)-2,
              'consecutive ALL5 keyed transitions/full6720 end/wires/phase/tags/',
              len(matches), 'reset graph match(es)/fresh whole mirror.', flush=True)


def conditional_single93(early, native):
    engine = early['engine']; word = early['word']
    state, tags, phase = engine['make'](native['end'])
    a = state['ik1302']; assert engine['boundary_ip'](a) == 0x35
    match_controller(a)
    assert number(a.r[22]) == native['report']['B7']
    assert all(number(v) == 0 for v in lower_st(a, 1))
    assert number(w['stack'](a)[0]) == 0x70
    initial_ring = engine['ring'](state, tags)
    raw = (0, 3, 9, 12, 18, 21)
    original_cache = [number(a.r[k]) for k in raw]
    # ONLY counterfactual: primary35→93 in the detached ALL5 model.
    # No numeric/flag/return/ring repair and no reference state setter.
    a.r[36], a.r[39] = q['N4'](3), q['N4'](9)
    pins = {name: (native['end']['state'][name]['keyX'],
                   native['end']['state'][name]['keyY']) for name in engine['models']}
    assert pins['ik1302'] == (0, 0)
    sequence = []; ready, dispatched = None, None
    expected = [0x93, 0x94, 0x95, 0x98, 0x9A, 0x70, 0x72, 0x74, 0x86,
                0xD3, 0xD5, 0x9B, 0x9C, 0x9E, 0x9F, 0xAA, 0xAC, 0xE2,
                *([0xE5]*9), 0xE6, 0xED, 0xEE, 0xE3]
    for command in range(30):
        a = state['ik1302']; code = engine['boundary_ip'](a); sequence.append(code)
        assert code == expected[command]
        if command == 5:
            ready = {'A': word(a.r), 'ST0': word(a.st),
                     'A7': number(a.r[21]), 'lowerST0Zero': True, 'return': '70'}
            assert number(a.r[21]) == native['report']['B7']
            assert all(number(v) == 0 for v in lower_st(a))
        if command == 13:
            dispatched = {'at9E_R33': number(a.r[33]), 'S1': number(a.s1),
                          'next': '9F', 'A7': number(a.r[21])}
            assert dispatched == {'at9E_R33': 15, 'S1': 9, 'next': '9F',
                                  'A7': native['report']['B7']}
        if command == 29:
            assert word(a.m, 1) == '300000010006', 'actual current M2, not assumed zeroX'
        phase, _ = engine['step'](state, tags, phase, pins)
        if command >= 4:
            assert [number(state['ik1302'].st[k+1]) for k in raw] == original_cache, \
                'original program raw6 still lives in ST1, not a global cache loss'
        current_ring = engine['ring'](state, tags)
        assert all(number(v) == number(initial_ring[slot][i])
                   for slot, values in current_ring.items() for i, v in enumerate(values))
    assert engine['boundary_ip'](state['ik1302']) == 0xE3
    assert word(state['ik1302'].r) == '300000010006'
    assert number(state['ik1302'].r[21]) == 1, 'firstEE imports actual M2/sign-feed1'
    assert not set(sequence) & {0x35, 0x8C, 0xCF, 0xC3, 0xD4}
    print('PASS CONDITIONAL ONLY', native['report']['name'], ':sole35→93 makes', ready,
          '; native return metadata routes', dispatched,
          '; firstEE29 imports actualM2=300000010006/A7=1. ALL630 ring tetras held through30; '
          'original raw6 held in ST1 throughEE; noCF/C3/D4 or ordinaryC-signF. '
          'Later paths are NOT excluded.', flush=True)
    print('CONDITIONAL30 route:', ' '.join(f'{code:02X}' for code in sequence), '→E3', flush=True)


if __name__ == '__main__':
    immutable_reference()
    writers = buffer_writer_inventory()
    packet_contracts()
    incoming_contracts()
    controller_cut(writers)
    early = runpy.run_path(str(root / 'cache-input-mask-early-exit.py'))
    fixtures = json.loads(subprocess.check_output([
        'node', str(root / 'cache-cf-buffer-native.cjs'), '--proof-input'], text=True))
    validate_native(early, fixtures)
    for native in fixtures: conditional_single93(early, native)
    immutable_reference()
    print('PASS buffer inlet audit; native DATA preparation only. OPEN: '
          'compatible93 inlet/return, CF joint7/zeroST0, preserving numeric '
          'export, Ms transport and reverse exchange. No partialK2.', flush=True)
