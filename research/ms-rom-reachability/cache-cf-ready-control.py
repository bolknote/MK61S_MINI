#!/usr/bin/env python3
"""Readiness-preserving source cut, exact callers and real mode-cycle limits.

No source/ROM/reference edits or calculator state setters. The reset graph is
an overapproximation, not a keyboard witness. Native internal7/zeroST0 states
are real but have forced packet exits. A hypothetical AB3 call has the right
data mapping and returnAC; its mandatory EE read still precedes any CF.
"""
from collections import Counter, deque
import json
from pathlib import Path
import runpy
import subprocess
import sys

from z3 import And, BitVec, sat, unsat

root = Path(__file__).resolve().parent
inlet = runpy.run_path(str(root / 'cache-cf-buffer-inlet.py'))
w, q = inlet['w'], inlet['q']
states, edges = inlet['states'], inlet['edges']
lower = inlet['lower_st']
zero = inlet['zero']
number = inlet['number']
ready = lambda a: And(a.r[22] == 7, zero(lower(a, 1)))
joint = lambda a: And(a.r[21] == 7, zero(lower(a)))
single = (0x93, 0x94, 0x95, 0x98, 0x9A)
double = (0x91, 0x92, *single, *single)
loop_words = {int(code, 16) for code in (
    'E1 91 92 93 94 95 98 9A E2 E5 E6 ED EE E3 E4 DE D6 EF E8 E7 A8 A9 E0 A7').split()}


def readiness_inventory():
    safe, unsafe = [], []
    for code in range(256):
        a = q['State'](f'cf_ready_word_{code:02X}')
        p = w['base'](a, code); p.add(ready(a))
        assert p.check() == sat, ('empty readiness premise', code)
        b = w['ex'](a, code, *q['arbitrary_keys'](f'cf_ready_keys_{code:02X}'))
        p.add(~ready(b))
        answer = p.check(); assert answer in (sat, unsat)
        (safe if answer == unsat else unsafe).append(code)
    assert unsafe == [int(s, 16) for s in (
        '08 12 13 16 3F 40 47 49 62 6A 6B 6F 88 91 92 93 94 95 98 9A '
        'BB C4 C6 C8 C9 CF D8 DF E1 E4 EB EC F6 F7').split()]
    assert len(safe) == 222
    print('PASS ALL256:222 universally hold B7=7/zeroST1;34 may change it. '
          'Arbitrary other metadata, future serial input and per-tick key pins.', flush=True)
    print('MAY CHANGE readiness:', ' '.join(f'{code:02X}' for code in unsafe), flush=True)
    print('LIMIT: a SAT word may preserve particular real data or recreate readiness '
          'later. This cut is NOT an all-path impossibility theorem.', flush=True)
    return set(safe)


def closure(starts, safe):
    reached, todo = set(starts), deque(starts)
    parents = {index: None for index in starts}
    while todo:
        index = todo.popleft()
        words = (states[index][0],)
        if words[0] == 0x93: words += (0x94,)
        if words[0] == 0x12: words += (0xC6,)
        if not all(code in safe for code in words): continue
        for child in edges[index]:
            if child not in reached:
                reached.add(child); todo.append(child); parents[child] = index
    return reached, parents


def controller_cut(safe, native):
    starts = [i for i, row in enumerate(states) if row[0] == 0x35]
    assert len(starts) == 806
    assert len(states) == 52416 and sum(map(len, edges)) == 95731
    targets = {i for i, row in enumerate(edges) if states[i][0] == 0xA3 and
               any(states[child][0] == 0x93 for child in row)}
    assert len(targets) == 22
    assert all(states[i][1][0] == 0xAC and states[i][2] == 0x93 and
               states[i][3] == [9] and states[i][7] == [0] for i in targets)
    reached, _ = closure(starts, safe)
    assert len(reached) == 20222 and len(targets & reached) == 13
    frontier = Counter(states[i][0] for i in reached if states[i][0] not in safe)
    assert frontier == {0x08: 4, 0x12: 26, 0x13: 26, 0x16: 26, 0x49: 3,
        0x6A: 8, 0x6F: 23, 0x88: 2, 0x91: 94, 0x93: 13, 0x98: 2,
        0xBB: 6, 0xC8: 2, 0xC9: 37, 0xD8: 56, 0xDF: 27,
        0xE4: 3, 0xEC: 27, 0xF6: 30, 0xF7: 28}
    predecessors = Counter()
    for i, row in enumerate(edges):
        for child in row:
            if child in targets: predecessors[states[i][0]] += 1
    assert predecessors == {0xAD: 52, 0xA2: 22}
    print('PASS complete reset cut806→20222, stopped BEFORE any nonholder; '
          '13/22 A3→93 control targets remain. All22 have original returnAC. '
          'Incoming target edges:52 AD and22 A2.', flush=True)
    # Match both actual states; the F/Сx prelude changes real return tags.
    for label, entry in [('reader35', native['initial']), ('cancelled35', native['end'])]:
        state = concrete_primary(entry['state']['ik1302'])
        matched = inlet['match_controller'](state)
        subset, parents = closure(matched, safe)
        eligible = sorted(targets & subset)
        assert len(eligible) == 13
        if label == 'reader35': assert len(subset) == 10528
        else: assert len(matched) == 2 and len(subset) == 10350
        print(f'PASS {label}: {len(matched)} native graph matches, '
              f'{len(subset)} reached,13 conditional A3→93 targets.', flush=True)
        print('CONDITIONAL target IDs:', eligible, flush=True)
        # Optional reproducible controller paths, never native claims.
        for index in eligible if '--paths' in sys.argv else ():
            path, current = [], index
            while current is not None:
                path.append(states[current][0]); current = parents[current]
            print('CANDIDATE', label, index,
                  ' '.join(f'{code:02X}' for code in reversed(path)), flush=True)
    print('LIMIT: individual graph edges discard untracked correlations. '
          'Shortest paths are not executable recipes and idle scans must not be omitted.', flush=True)


def concrete_primary(snapshot):
    a = q['State']('cf_ready_native')
    for field in ('r', 'm', 'st'):
        setattr(a, field, [q['N4'](n) for n in snapshot[field]])
    for field in ('s', 's1'):
        setattr(a, field, q['N4'](snapshot[field]))
    for field in ('l', 't', 'carry'):
        setattr(a, field, q['N1'](snapshot[field]))
    return a


def caller_and_exit_contracts():
    a = q['State']('cf_ready_AB3'); p = w['base'](a, 0xAB)
    p.add(a.r[35] == 3, ready(a)); b = a
    sequence = (0xAB, 0xAD, 0xA3, *single, 0xAC, 0xE2, 0xE5, 0xE6, 0xED, 0xEE)
    for index, code in enumerate(sequence):
        if code == 0xE5: p.add(b.m[22] == 15)
        w['prove'](p, w['ip'](b) == code, f'AB3 forced{code:02X}', False)
        before = b
        b = w['ex'](b, code, *q['arbitrary_keys'](f'cf_ready_AB3_keys{index}'))
        if code == 0xAB:
            w['prove'](p, And(w['ip'](b) == 0xAD,
                             w['byte'](b.r[37], b.r[40]) == 0x93,
                             w['stack'](b)[0] == 0xAC, ready(b)),
                       'AB/type3 constructs vector93/original returnAC and holds readiness')
        elif code == 0xAD:
            w['prove'](p, And(w['ip'](b) == 0xA3, b.r[32] == 3,
                             b.r[35] == a.r[32], b.r[26] == 0, b.s1 == 9, ready(b)),
                       'AD swaps type fields, sets S1=9 and dispatches actual type3 toA3')
        elif code == 0xA3:
            w['prove'](p, And(w['ip'](b) == 0x93, w['stack'](b)[0] == 0xAC, ready(b)),
                       'A3 dispatches to93 without changing B7/ST1 or returnAC')
        elif code == 0x9A:
            w['prove'](p, And(w['ip'](b) == 0xAC, joint(b),
                             w['eq'](lower(b, 1), a.r[0:24:3])),
                       'one93 returns naturallyAC with A7=7/zeroST0, oldA lower8 reserved inST1')
        elif code in (0xAC, 0xE2, 0xE5, 0xE6, 0xED):
            w['prove'](p, And(joint(b), w['eq'](lower(b, 1), a.r[0:24:3])),
                       'AC tail holds the joint pair and prior-A reserve beforeEE', False)
        elif code == 0xEE:
            w['prove'](p, And(b.r[21] == before.m[22],
                             w['eq'](lower(b, 1), a.r[0:24:3]), w['ip'](b) == 0xE3),
                       'firstEE rereads actual M2/sign-feed; oldA is still inST1, not globally lost')
    # The induction covers any finite physical marker wait, not just one E5.
    a = q['State']('cf_ready_AC_wait'); p = w['base'](a, 0xE5)
    b = w['ex'](a, 0xE5, *q['arbitrary_keys']('cf_ready_AC_wait_keys'))
    w['prove'](p, And(b.s1 == a.s1, w['eq'](b.st, a.st),
                     *[b.r[j] == a.r[j] for j in range(42) if j not in (36, 39)]),
               'arbitrary finite E5 repeats hold non-IP R/ST/S1')
    print('LIMIT: even a compatible A3→93/originalAC call must execute '
          'AC→E2→E5*→E6→ED→EE before anyCF. Per-tick keys cannot insertCF in that tail. '
          'Later approaches, a prepared M2/sign-feed7 and an earlier reserve remain open.', flush=True)


def internal_joint_contract():
    a = q['State']('cf_ready_E1_packet'); p = w['base'](a, 0xE1)
    p.add(zero(a.r[0:24:3]), a.r[22] == 1, a.r[23] == 7, zero(lower(a, 1)))
    b = a
    for index, code in enumerate((0xE1, *double)):
        w['prove'](p, w['ip'](b) == code, f'E1 forced{code:02X}', False)
        b = w['ex'](b, code, *q['arbitrary_keys'](f'cf_ready_E1_keys{index}'))
        if index == 6:
            w['prove'](p, And(w['ip'](b) == 0x9A, joint(b)),
                       'first98 exposes C7=7/zeroST0, but next is forced9A, notCF')
    targets = (b.r[0:24:3], b.r[1:24:3], b.r[2:24:3], lower(b), lower(b, 1))
    sources = (a.r[1:24:3], lower(a), lower(a, 1), a.r[0:24:3], a.r[2:24:3])
    w['prove'](p, And(w['ip'](b) == 0xE2, b.r[21] == 1, zero(lower(b)),
                     *[w['eq'](dst, src) for dst, src in zip(targets, sources)]),
               'E1/double91 exact mapping (B,ST0,ST1,A,C); returnsE2 with ONE, not7')
    print('PASS real-mode-shaped E1 inlet has an internal joint7/zeroST0, '
          'but all13 primary words are forced for arbitrary other metadata, '
          'keys and future serial input. No pause/next key redirects it toCF.', flush=True)


def keyboard_noninterference():
    # Two inputs differ in the keyboard and even in the old key latchT.
    # All other state and serial inputs agree. No physical timing restriction.
    for code in sorted(loop_words):
        a = q['State'](f'cf_ready_keyfree_{code:02X}')
        other = a.copy(); other.t = BitVec(f'cf_ready_other_T_{code:02X}', 1)
        p = w['base'](a, code)
        serial = q['State'](f'cf_ready_key_serial_{code:02X}').m
        outputs, other_outputs = [], []
        b = w['ex'](a, code, 0, 0, serial_inputs=serial, emitted_outputs=outputs)
        c = w['ex'](other, code, *q['arbitrary_keys'](f'cf_ready_keypins_{code:02X}'),
                    serial_inputs=serial, emitted_outputs=other_outputs)
        w['prove'](p, And(w['eq'](b.r, c.r), w['eq'](b.st, c.st), w['eq'](b.m, c.m),
                         w['eq'](outputs, other_outputs),
                         *[getattr(b, n) == getattr(c, n) for n in ('s', 's1', 'l', 'carry')]),
                   f'{code:02X} all primary state/output independent of keys and oldT, exceptT', False)
    print('PASS ALL24 loop words: arbitrary future per-tick keys/oldT cannot change '
          'R/ST/M/S/S1/L/carry or outgoing42 tetras; only key latchT may differ.', flush=True)


def closed_native_cycle(early, native):
    engine = early['engine']
    state, tags, phase = engine['make'](native['end'])
    signature = early['complete_fingerprint'](state, tags, phase)
    pins = {name: (native['end']['state'][name]['keyX'],
                   native['end']['state'][name]['keyY']) for name in engine['models']}
    assert pins['ik1302'] == (0, 0)
    sequence = []
    for command in range(90):
        code = engine['boundary_ip'](state['ik1302'])
        assert code in loop_words, ('new keyboard dependence requires audit', code)
        sequence.append(code)
        phase, _ = engine['step'](state, tags, phase, pins)
    assert early['complete_fingerprint'](state, tags, phase) == signature
    assert not set(sequence) & {0x35, 0xCF, 0xC3, 0xD4}
    print('PASS', native['report']['name'], ':exact full90-period of ALL5/wires/phase/tags; '
          'only24 independently key-free words, no35/CF/C3/D4. Future user keys cannot '
          'escape THIS cycle, with angle switch fixed and without reset/power-off.', flush=True)


def validate_native(early, fixtures):
    engine = early['engine']; total = 0
    for native in fixtures:
        assert native['report']['observerIndependent'] is True
        state, tags, phase = engine['make'](native['initial']); command = 0
        losses = []
        keys = native['report']['keys']; end = native['report']['macros']
        locations = {entries[0]['command']: entries for name in
                     ('origin', 'formatter', 'packet', 'decoder')
                     if (entries := native[name])}
        checkpoints = {entry['command']: entry for entries in locations.values() for entry in entries}
        pins0 = {name: (native['initial']['state'][name]['keyX'],
                        native['initial']['state'][name]['keyY']) for name in engine['models']}
        key_pins = {'F': (11, 9), 'Сx': (10, 8), 'K': (10, 9),
                    '5': (7, 1), 'ВП': (9, 8), '/-/': (8, 8)}
        boundaries = sorted({0, end, *checkpoints,
            *(index*1120+offset for index in range(len(keys)) for offset in (0, 560, 1120))})
        assert boundaries[-1] == end
        for following in boundaries:
            if command in checkpoints:
                early['snapshot_matches'](state, phase, checkpoints[command]['state'])
            if following == command: continue
            pins = dict(pins0)
            index, offset = divmod(command, 1120)
            pins['ik1302'] = key_pins[keys[index]] if index < len(keys) and offset < 560 else (0, 0)
            if following == command+1 and command in checkpoints and following in checkpoints:
                phase, _ = engine['step'](state, tags, phase, pins); command += 1; total += 1
            else:
                phase, command = early['advance_fixed'](state, tags, phase, command,
                    following, pins, losses=losses, label=native['report']['name'])
            if command in checkpoints:
                early['snapshot_matches'](state, phase, checkpoints[command]['state'])
        early['snapshot_matches'](state, phase, native['end']['state'])
        assert tags == engine['make'](native['end'])[1]
        matched = inlet['match_controller'](state['ik1302'])
        print('PASS native', native['report']['name'], ':',
              sum(len(entries)-1 for entries in locations.values()),
              f'consecutive ALL5 boundaries/full{end} end/wires/phase/tags/',
              len(matched), 'reset matches/fresh whole mirror.', flush=True)
        if native['report']['name'].startswith('mode_cycle'):
            closed_native_cycle(early, native)
    print('PASS total selected native ALL5 consecutive transitions:', total, flush=True)


if __name__ == '__main__':
    inlet['immutable_reference']()
    safe = readiness_inventory()
    caller_and_exit_contracts()
    internal_joint_contract()
    keyboard_noninterference()
    fixtures = json.loads(subprocess.check_output([
        'node', str(root / 'cache-cf-ready-control-native.cjs'), '--proof-input'], text=True))
    controller_cut(safe, fixtures[0])
    early = runpy.run_path(str(root / 'cache-input-mask-early-exit.py'))
    validate_native(early, fixtures)
    inlet['immutable_reference']()
    print('PASS readiness-control audit. Native cancel holds readiness; '
          'native mode cycles expose the joint pair only inside forced packets. '
          'No nativeCF/C3/C-signF or partialK2.', flush=True)
