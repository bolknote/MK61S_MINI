#!/usr/bin/env python3
"""Oldest-ST reserve: local recovery gates, first-loss cut and STORE C.

Native controls use only public keys/frames. The signF reserve is still a
detached late-P8-marker hypothesis, NOT a key constructor. Whole-ring key
pulses start at public frame boundaries. Constant full-state periods may
shorten a pulse only after ALL5 R/ST/M/scalars/wires/tags/phase repeat.
"""
from collections import Counter, deque
import json
from pathlib import Path
import runpy
import subprocess

from z3 import And, BitVec, sat, unsat

root = Path(__file__).resolve().parent
source = runpy.run_path(str(root / 'cache-marker-return93-contract.py'))
w, q, engine = source['w'], source['q'], source['engine']
oldest = tuple(range(2, 36, 3))
payload = tuple(range(2, 29, 3))  # eight mantissa fields and their sign;
                               # ST29/32/35 also serve as decoder metadata.


def equal(xs, ys):
    return And(*[x == y for x, y in zip(xs, ys)])


def paired(code, fields=payload):
    a = q['State'](f'reserve_recovery_{code:02X}')
    b = a.copy()
    for k in fields:
        b.st[k] = BitVec(f'reserve_recovery_other_{code:02X}_{k}', 4)
    signals = q['arbitrary_keys'](f'reserve_recovery_keys_{code:02X}')
    serial = q['State'](f'reserve_recovery_serial_{code:02X}').m
    outputs, results = [], []
    for entry in (a, b):
        out = []
        results.append(w['ex'](entry, code, *signals, serial_inputs=serial,
                                emitted_outputs=out))
        outputs.append(out)
    left, right = results
    common = [equal(getattr(left, n), getattr(right, n)) for n in ('r', 'm')]
    common += [getattr(left, n) == getattr(right, n) for n in ('s', 's1', 'l', 't', 'carry')]
    common += [equal(*outputs)]
    outside = And(*common, *[left.st[k] == right.st[k] for k in range(42) if k not in fields])
    whole = And(*common, equal(left.st, right.st))
    return w['base'](a, code), outside, whole


def local_inventory():
    observers = []
    for code in range(256):
        p, outside, whole = paired(code)
        assert p.check() == sat
        p.push();p.add(~outside);answer = p.check();p.pop()
        assert answer in (sat, unsat)
        if answer == sat:
            observers.append(code)
        if code in (0x40, 0x93):
            full_p, _, full_whole = paired(code, oldest)
            w['prove'](full_p, full_whole,
                       f'{code:02X} forgets ALL12 oldest numericST fields '
                       'in ALL primary state/output; no new external copy')
        if code % 64 == 63:
            print(f'Checked through{code:02X}: oldest-ST observers outside itself',
                  [f'{v:02X}' for v in observers], flush=True)
    assert observers == [0x47, 0x94, 0x95]
    print('PASS ALL256 original primary ROM words: ONLY47/94/95 can move '
          'oldest-ST ALL9 mantissa/sign fields outside those nine positions, with arbitrary '
          'other fields, tick keys and future serial pages.', flush=True)
    for code in observers:
        a = q['State'](f'reserve_recovery_rotation_{code:02X}')
        p = w['base'](a, code);out = []
        b = w['ex'](a, code, *q['arbitrary_keys'](f'reserve_rotation_keys{code}'),
                    emitted_outputs=out)
        w['prove'](p, And(equal(b.r[0:36:3], a.st[0:36:3]),
                          *[b.st[j+i] == a.st[j+(i+1) % 3]
                            for j in range(0, 36, 3) for i in range(3)],
                          equal(out, a.m)),
                   f'{code:02X} reads oldST-lane0 into A12 and LEFT-rotates '
                   'all numericST trios, no primary outgoing write')
    # A legal LOCAL94→95 edge can recover lane1; entry94 itself is missing.
    a = q['State']('reserve_recovery_94_95')
    p = w['base'](a, 0x94);b = a
    for index, code in enumerate((0x94, 0x95)):
        w['prove'](p, w['address'](b) == code, 'local94/95 forced edge', False)
        b = w['ex'](b, code, *q['arbitrary_keys'](f'reserve94_95_keys{index}'))
    w['prove'](p, And(equal(b.r[0:36:3], a.st[1:36:3]), w['address'](b) == 0x98),
               'CONDITIONAL entry94→95 recovers ALL12 oldST-lane1 fields '
               'into A; not a native entry94 or oldest-lane2 recovery')
    exceptions = {}
    for code in (0x8C, 0xAC):
        fields = []
        for k in oldest:
            p, outside, _ = paired(code, (k,))
            p.add(~outside);answer = p.check();assert answer in (sat, unsat)
            if answer == sat:
                fields.append(k)
        assert fields and all(k not in payload for k in fields)
        exceptions[f'{code:02X}'] = fields
    print('EXCEPTION: a total ALL12 single-word-isolation claim would be false. '
          '8C/AC observe decoder/order tail fields:', exceptions,
          '; the exact ALL9 payload/sign inventory above excludes that overclaim.', flush=True)
    return observers


def controller_cut(observers):
    graph = runpy.run_path(str(root / 'cache-numeric-export-gates.py'))
    states, edges = graph['states'], graph['edges']
    assert graph['graph']['metadata']['fusedCommands']['93'] == ['93', '94']
    reached = {j for j, s in enumerate(states) if s[0] == 0x35}
    starts = len(reached);todo = deque(sorted(reached));blocked = {0x40, 0x93}
    while todo:
        j = todo.popleft()
        if states[j][0] in blocked:
            continue
        for k in edges[j]:
            if k not in reached:
                reached.add(k);todo.append(k)
    assert len(reached) == 38189
    assert not any(states[j][0] in observers for j in reached)
    assert not any(0x94 in s[1] or 0x95 in s[1] for s in states)
    print(f'PASS complete reset-controller ALL{starts} idle35 starts: '
          '38189 contexts before executing40/93; no47/95, and94 is fused '
          'inside blocked93, never a return tag. Provenance/completeness checked.', flush=True)
    print('FIRST-LOSS CUT: before40/93 no instruction can extract any of the '
          'nine oldest-ST mantissa/sign fields;40/93 erase ALL12 fields completely. Paired primary '
          'outputs are identical, so common downstream chips/ring also cannot '
          'acquire a new copy. Prior copies or unrelated F sources are NOT excluded.', flush=True)
    return states


def word(values):
    return ''.join(f'{w["number"](v):X}' for v in reversed(values))


def signature(state, tags, phase):
    values = [phase]
    for name in engine['names']:
        if name.startswith('ir'):
            values.extend(w['number'](v) for v in state[name])
        else:
            for field in ('r', 'm', 'st'):
                values.extend(w['number'](v) for v in getattr(state[name], field))
            values.extend(w['number'](getattr(state[name], n)) for n in ('s', 's1', 'l', 't', 'carry'))
        values.extend(w['number'](state['_wire'][name][n]) for n in ('input', 'output'))
        values.extend(tags[name])
    return tuple(values)


def native_equal(state, phase, entry):
    for name in engine['names']:
        target = entry['state'][name]
        for field in ('input', 'output'):
            assert w['number'](state['_wire'][name][field]) == target[field], (name, field)
        if name.startswith('ir'):
            assert [w['number'](v) for v in state[name]] == target['m'], name
            assert phase == target['tick']
        else:
            for field in ('r', 'm', 'st'):
                assert [w['number'](v) for v in getattr(state[name], field)] == target[field], (name, field)
            for field in ('s', 's1', 'l', 't', 'carry'):
                assert w['number'](getattr(state[name], field)) == target[field], (name, field)


def pulse(state, tags, phase, pins, steps, stats, label):
    seen = {};elapsed = 0;writes = [];first_loss = None
    while elapsed < steps:
        snap = signature(state, tags, phase)
        if snap in seen:
            before, event_count = seen[snap];period = elapsed-before
            count = (steps-elapsed)//period
            if count:
                repeated = writes[event_count:]
                stats['writes'].update({k: v*count for k, v in Counter(repeated).items()})
                jump = period*count;elapsed += jump;stats['skipped'] += jump
                stats['periods'].append({'segment': label, 'period': period, 'skipped': jump})
                # Same ALL5 state, physical tags and phase: no model mutation
                # implements the skip; only the elapsed fixed-pulse clock moves.
                if elapsed == steps:
                    break
        else:
            seen[snap] = (elapsed, len(writes))
        code = engine['boundary_ip'](state['ik1302'])
        slot = tags['ik1302'][0][0]
        if code in (0x40, 0x93) and first_loss is None:
            first_loss = {'segment': label, 'offset': elapsed, 'ip': f'{code:02X}',
                          'oldestWord': word(state['ik1302'].st[2:36:3])}
        phase, outputs = engine['step'](state, tags, phase, pins)
        if code == 0xD4:
            value = (slot, w['number'](outputs['ik1302'][24]))
            writes.append(value);stats['writes'][value] += 1
        elapsed += 1;stats['executed'] += 1
    stats['clock'] += steps
    if first_loss is not None:
        stats['firstLosses'].append(first_loss)
    return phase


def stats_new():
    return {'clock': 0, 'executed': 0, 'skipped': 0, 'writes': Counter(),
            'periods': [], 'firstLosses': []}


def store_c(state, tags, phase, pins, stats):
    for label, primary, steps in (('STORE held', (6, 9), 560),
                                  ('STORE release', (0, 0), 560),
                                  ('C held', (9, 8), 560),
                                  ('C release', (0, 0), 560),
                                  ('idle', (0, 0), 1120)):
        current = dict(pins);current['ik1302'] = primary
        phase = pulse(state, tags, phase, current, steps, stats, label)
    return phase


def auto_mode(state, tags, phase, pins, stats):
    for label, primary, steps in (('F held', (11, 9), 560),
                                  ('F release', (0, 0), 560),
                                  ('AUTO held', (8, 8), 560),
                                  ('AUTO release', (0, 0), 560),
                                  ('AUTO idle', (0, 0), 1120)):
        current = dict(pins);current['ik1302'] = primary
        phase = pulse(state, tags, phase, current, steps, stats, label)
    return phase


def baseline(native):
    state, tags, phase = engine['make'](native['entry'])
    pins = {name: (native['entry']['state'][name]['keyX'], native['entry']['state'][name]['keyY'])
            for name in engine['models']}
    # Check the first64 native keyed transitions independently of acceleration.
    copy_state, copy_tags, copy_phase = engine['make'](native['prefix'][0])
    for current, following in zip(native['prefix'], native['prefix'][1:]):
        actual = {name: (current['state'][name]['keyX'], current['state'][name]['keyY'])
                  for name in engine['models']}
        copy_phase, _ = engine['step'](copy_state, copy_tags, copy_phase, actual)
        native_equal(copy_state, copy_phase, following)
    stats = stats_new();phase = store_c(state, tags, phase, pins, stats)
    native_equal(state, phase, native['end'])
    expected_tags = engine['make'](native['end'])[1]
    assert tags == expected_tags
    assert stats['clock'] == native['end']['command'] == 3360
    print('PASS native STORE C:64 exact keyed ALL5 transitions and full3360-macro '
          'public pulse final state/wires/phase/tags; periods skipped', stats['skipped'], flush=True)
    control = native['modeControl']
    state, tags, phase = engine['make'](control['entry'])
    pins = {name: (control['entry']['state'][name]['keyX'],
                   control['entry']['state'][name]['keyY']) for name in engine['models']}
    stats = stats_new()
    for operation, target in ((store_c, control['programStoreEnd']),
                               (auto_mode, control['autoEnd']),
                               (store_c, control['end'])):
        phase = operation(state, tags, phase, pins, stats)
        native_equal(state, phase, target)
        assert tags == engine['make'](target)[1]
    assert stats['clock'] == control['end']['command'] == 10080
    print('PASS native PROGRAM STORE→F AUTO→STORE: all three ALL5 boundaries '
          'through10080 public macro pulses; no model-only mode bit repair.', flush=True)


def match_controller(a, states):
    ip = w['number'](w['address'](a));sp = [w['number'](v) for v in w['stack'](a)]
    vector = w['number'](w['byte'](a.r[37], a.r[40]));s1 = w['number'](a.s1)
    r35, r38, r26 = (w['number'](a.r[k]) for k in (35, 38, 26))
    matches = []
    for index, (code, tags, vec, selectors, delta, r38s, dr38, r26s, types) in enumerate(states):
        if code != ip or tags != sp or s1 not in selectors:
            continue
        if vec == 'diagonal' and w['number'](a.r[37]) != w['number'](a.r[40]):
            continue
        if vec not in (None, 'diagonal') and vec != vector:
            continue
        if delta is not None and delta != (s1-r35) % 16:
            continue
        if r38s is not None and r38 not in r38s:
            continue
        if dr38 is not None and dr38 != (r38-r35) % 16:
            continue
        if r26s is not None and r26 not in r26s:
            continue
        assert types is None
        matches.append(index)
    assert matches, 'the concrete controller must be covered by the complete abstract cut'
    return matches


def validate_commands(attempts):
    assert [a['operation'] for a in attempts] == [
        'STORE 1', 'STORE 2', 'F AUTO', 'STORE after AUTO']
    for a in attempts:
        assert a['D4Writes'] == []
        assert a['CBefore'] == a['CAfter'] == '000000000000'
        assert a['ordinaryNumericWordChanges'] == 0 and a['R23'] == 0
    for a in attempts[:2]:
        assert a['firstLosses'] == []
        assert a['oldestWordBefore'] == a['oldestWordAfter'] == '400FFFFFFFFF'
        assert a['R2'] == 15 and a['endIP'] == '35'
        assert a['programTetraChanges'] == 2 and a['MsTetraChanges'] == 0
    a = attempts[2]
    assert a['firstLosses'] == [{'segment': 'AUTO held', 'offset': 20, 'ip': '93',
                                'oldestWord': '400FFFFFFFFF'}]
    assert a['oldestWordBefore'] == '400FFFFFFFFF'
    assert a['oldestWordAfter'] == '000000000000'
    assert a['R2'] == 8 and a['endIP'] == '35'
    assert a['programTetraChanges'] == a['MsTetraChanges'] == 0
    a = attempts[3]
    assert a['firstLosses'] == []
    assert a['oldestWordBefore'] == a['oldestWordAfter'] == '000000000000'
    assert a['R2'] == 0 and a['endIP'] == '30'
    assert a['programTetraChanges'] == 0 and a['MsTetraChanges'] == 3
    print('PASS bounded conditional command regression: repeated STORE is not '
          'preserving; F AUTO kills the old reserve in93; later STORE still '
          'has noD4 and changes three Ms tetras. R2=8 alone is NOT recovery.', flush=True)


def conditional_store(case, states):
    eligible = {}
    def eligible_hook(index, code, slot, machine, physical_tags, phase):
        a = machine['ik1302']
        for group, values in [('A', a.r[0:36:3]), ('B', a.r[1:36:3]), ('C', a.r[2:36:3]),
                              ('ST0', a.st[0:36:3]), ('ST1', a.st[1:36:3]), ('ST2', a.st[2:36:3])]:
            if group not in eligible and word(values) == '400FFFFFFFFF':
                eligible[group] = {'offset': index, 'ip': f'{code:02X}', 'slot': slot}
    ctx = source['conditional_marker'](case, boundary_hook=eligible_hook,
                                       return_context=True, log=False)
    state, tags, phase = ctx['state'], ctx['tags'], ctx['phase']
    assert word(state['ik1302'].st[2:36:3]) == '400FFFFFFFFF'
    assert match_controller(state['ik1302'], states)
    now = ctx['entry']['command']+ctx['report']['released35At']
    end = case['finalEntry']['command']
    assert end % 560 == 0 and end >= now
    pins = source['fixed_pins'](case, now)
    assert list(pins['ik1302']) == [0, 0]
    stats = stats_new()
    phase = pulse(state, tags, phase, pins, end-now, stats, 'finish native idle frames')
    assert phase == 84 and word(state['ik1302'].st[2:36:3]) == '400FFFFFFFFF'
    assert match_controller(state['ik1302'], states)
    starting_ring = engine['ring'](state, tags)
    attempts = []
    # The first public STORE/C pulse repairs R23. Repeating that SAME
    # ordinary command is a decoder-repair control, not a key search.
    for label, operation in (('STORE 1', store_c), ('STORE 2', store_c),
                              ('F AUTO', auto_mode), ('STORE after AUTO', store_c)):
        before = engine['ring'](state, tags)
        earlier_writes = stats['writes'].copy()
        loss_index = len(stats['firstLosses'])
        oldest_before = word(state['ik1302'].st[2:36:3])
        phase = operation(state, tags, phase, pins, stats)
        assert phase == 84
        after = engine['ring'](state, tags)
        new_writes = stats['writes']-earlier_writes
        changes = {
            'programTetraChanges': sum(w['number'](after[s][k]) != w['number'](before[s][k])
                                       for s in engine['slots'] for k in range(2, 42, 3)),
            'MsTetraChanges': sum(w['number'](after[s][k]) != w['number'](before[s][k])
                                  for s in ('U', 'V', 'W', 'Q', 'P7', 'P8', 'P9', 'P10')
                                  for k in range(1, 42, 3)),
            'ordinaryNumericWordChanges': sum(word(after[s][0:36:3]) != word(before[s][0:36:3])
                                              for s in engine['slots']),
        }
        attempts.append({'operation': label, 'oldestWordBefore': oldest_before,
                         'firstLosses': stats['firstLosses'][loss_index:],
                         'D4Writes': [{'slot': s, 'sign': v, 'count': n}
                                      for (s, v), n in new_writes.items()],
                         'CBefore': word(before['Y'][0:36:3]),
                         'CAfter': word(after['Y'][0:36:3]),
                         'oldestWordAfter': word(state['ik1302'].st[2:36:3]),
                         'R2': w['number'](state['ik1302'].r[2]),
                         'R23': w['number'](state['ik1302'].r[23]),
                         'endIP': f'{engine["boundary_ip"](state["ik1302"]):02X}',
                         **changes})
        print('CONDITIONAL public command:', json.dumps(attempts[-1]), flush=True)
    validate_commands(attempts)
    assert stats['clock'] == end-now+4*3360 == 18964
    assert stats['executed']+stats['skipped'] == stats['clock']
    assert eligible == {'ST2': {'offset': 162, 'ip': '63', 'slot': 'X1'}}
    report = {'conditionalOnly': True, 'lateP8MarkerStillHypothetical': True,
              'startAtPublicFrame': end,
              'keys': [['X→П', 'ВП'], ['X→П', 'ВП'], ['F', '/-/'], ['X→П', 'ВП']],
              'oldestWordBeforeKeys': '400FFFFFFFFF',
              'firstEligibleWordByBuffer': eligible,
              'attempts': attempts,
              'firstLosses': stats['firstLosses'],
              'D4Writes': [{'slot': s, 'sign': v, 'count': n} for (s, v), n in stats['writes'].items()],
              'CBefore': word(starting_ring['Y'][0:36:3]), 'CAfter': word(after['Y'][0:36:3]),
              'oldestWordAfter': word(state['ik1302'].st[2:36:3]),
              'R2': w['number'](state['ik1302'].r[2]), 'R23': w['number'](state['ik1302'].r[23]),
              'endIP': f'{engine["boundary_ip"](state["ik1302"]):02X}',
              'executed': stats['executed'], 'skippedExactPeriod': stats['skipped']}
    print('CONDITIONAL frame-aligned STORE C:', json.dumps(report), flush=True)
    print('SCOPE: a CONSTANT late-marker fixture, not a native marker recipe '
          'or reader stitch. The first-loss theorem only closes extraction '
          'of the already-oldest ST word after35; earlier reserves, prior '
          'copies and other F constructors remain open.', flush=True)
    return report


if __name__ == '__main__':
    observers = local_inventory()
    states = controller_cut(observers)
    native = json.loads(subprocess.check_output(
        ['node', str(root / 'cache-marker-reserve-store-native.cjs'), '--proof-input'], text=True))
    baseline(native)
    case = json.loads(subprocess.check_output(
        ['node', str(root / 'cache-marker-return93-native.cjs'), '--proof-input'], text=True))
    conditional_store(case, states)
