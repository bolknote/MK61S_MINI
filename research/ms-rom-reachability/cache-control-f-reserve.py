#!/usr/bin/env python3
"""Remaining late F in R23/R2/R5: exact ROM dependencies, not key recipes.

Paired states differ in ONE internal tetra only. Arbitrary other fields,
common per-tick keys and common future serial inputs overapproximate the
physical calculator. A positive dependency/graph route is not a native
keyboard witness. The existing late marker experiment remains conditional.
"""
from collections import Counter, deque
import json
from pathlib import Path
import runpy
import subprocess

from z3 import And, BitVec, UGE, sat, unsat

root = Path(__file__).resolve().parent
w = runpy.run_path(str(root / 'cache-writer-contract.py'))
q = w['q']


def equal(xs, ys):
    return And(*[x == y for x, y in zip(xs, ys)])


def pair(code, field, other_response_fields=()):
    a = q['State'](f'control_reserve_{field}_{code:02X}')
    b = a.copy();b.r[field] = BitVec(f'control_reserve_other_{field}_{code:02X}', 4)
    keys = q['arbitrary_keys'](f'control_reserve_keys_{field}_{code:02X}')
    serial = q['State'](f'control_reserve_serial_{field}_{code:02X}').m
    states, outputs = [], []
    for entry in (a, b):
        out = []
        states.append(w['ex'](entry, code, *keys,
                               serial_inputs=serial, emitted_outputs=out))
        outputs.append(out)
    left, right = states
    common = [equal(getattr(left, n), getattr(right, n)) for n in ('m', 'st')]
    common += [getattr(left, n) == getattr(right, n) for n in ('s', 's1', 'l', 't', 'carry')]
    common.append(equal(*outputs))
    outside = And(*common, *[left.r[k] == right.r[k] for k in range(42)
                            if k != field and k not in other_response_fields])
    whole = And(*common, equal(left.r, right.r))
    return a, left, outputs[0], w['base'](a, code), outside, whole


def possible_difference(p, claim):
    assert p.check() == sat
    p.push();p.add(~claim);answer = p.check();p.pop()
    assert answer in (sat, unsat)
    return answer == sat


def inventory(field):
    observed, killed, isolated = [], [], []
    direct_copies, numeric_copies, isolated_transforms = {}, {}, {}
    for code in range(256):
        a, b, out, p, outside, whole = pair(code, field)
        if possible_difference(p, outside):
            observed.append(code)
            destinations = []
            for label, value in [(f'R{k}', b.r[k]) for k in (21, 22, 24, 25, 26)] + [('outM1-sign', out[24])]:
                if not possible_difference(p, value == a.r[field]):
                    destinations.append(label)
            if destinations:
                direct_copies[f'{code:02X}'] = destinations
            destinations = []
            for k in range(36):
                if k % 3 != 2 and not possible_difference(p, b.r[k] == a.r[field]):
                    destinations.append(f'R{k}')
            if destinations:
                numeric_copies[f'{code:02X}'] = destinations
        elif possible_difference(p, whole):
            isolated.append(code)
            if possible_difference(p, b.r[field] == a.r[field]):
                p.push();p.add(a.r[field] == 15)
                values = q['possible_values'](b.r[field], p, 17);p.pop()
                isolated_transforms[f'{code:02X}'] = values
        else:
            killed.append(code)
        if code % 64 == 63:
            print(f'R{field} through{code:02X}: observers{len(observed)}, '
                  f'killers{len(killed)}, isolated{len(isolated)}', flush=True)
    assert len(observed)+len(killed)+len(isolated) == 256
    result = {'field': field, 'observers': observed, 'killers': killed,
              'isolated': isolated, 'directCopiesToWriterFields': direct_copies,
              'directCopiesToNumericAB': numeric_copies,
              'isolatedTransformsWithFInput': isolated_transforms}
    if field == 23:
        assert observed == [0x44, 0x4A, 0x4B, 0x4D, 0x92, 0x9A, 0xB2, 0xBE,
                            0xD3, 0xF1, 0xF3, 0xF4]
        assert len(killed) == 21 and len(isolated) == 223
        assert direct_copies == {'92': ['R22'], '9A': ['R22']}
        assert numeric_copies == {'92': ['R22'], '9A': ['R22']}
        assert set(isolated_transforms) == {'50', 'B8', 'F6', 'F7'}
    elif field == 2:
        assert len(observed) == 22 and len(killed) == 9
        assert 0x35 in observed and direct_copies == {}
        assert numeric_copies == {'92': ['R1'], '9A': ['R1']}
    else:
        assert field == 5 and len(observed) == 11 and len(killed) == 9
        assert len(isolated) == 236 and direct_copies == {}
        assert numeric_copies == {'92': ['R4'], '9A': ['R4']}
        assert set(isolated_transforms) == {'F6', 'F7'}
    printed = {k: v for k, v in result.items() if k != 'isolated'}
    printed['isolatedCount'] = len(isolated)
    print('ROM DEPENDENCY inventory:', json.dumps(printed), flush=True)
    return result


def first_observer_cut(data, after54=False):
    graph = runpy.run_path(str(root / 'cache-numeric-export-gates.py'))
    states, edges = graph['states'], graph['edges']
    starts = [i for i, s in enumerate(states) if s[0] == 0x35]
    if after54:
        assert data['field'] == 5
        starts = sorted({child for i, s in enumerate(states) if s[0] == 0x54
                         for child in edges[i]})
    reached = set(starts);todo = deque(starts);first_observers = [];first_killers = []
    passed_transforms = []
    # A graph vertex can stand for two original ROM words. Stop before
    # its FIRST observer or killer, never jump over an internal fused word.
    fused = graph['graph']['metadata']['fusedCommands']
    observer = set(data['observers']);killer = set(data['killers'])
    if data['field'] == 23:
        assert 0x35 in data['isolated']
    # R2 already has observers inside35. Do not apply the R23 isolation
    # premise to it merely because one fixed held key preserved R2.
    while todo:
        i = todo.popleft();code = states[i][0]
        sequence = [int(s, 16) for s in fused.get(f'{code:02X}', [f'{code:02X}'])]
        stopped = False
        for word in sequence:
            if word in observer:
                first_observers.append((i, word));stopped = True;break
            if word in killer:
                first_killers.append((i, word));stopped = True;break
            assert word in data['isolated']
            if f'{word:02X}' in data['isolatedTransformsWithFInput']:
                passed_transforms.append(word)
        if stopped:
            continue
        for child in edges[i]:
            if child not in reached:
                reached.add(child);todo.append(child)
    report = {'field': data['field'], 'starts': len(starts), 'contexts': len(reached),
              'startKind': 'successors54' if after54 else 'idle35',
              'firstObserverCounts': {f'{c:02X}': n for c, n in sorted(Counter(c for _, c in first_observers).items())},
              'firstKillerCounts': {f'{c:02X}': n for c, n in sorted(Counter(c for _, c in first_killers).items())},
              'isolatedTransformsBeforeFirstStop': {f'{c:02X}': n for c, n in sorted(Counter(passed_transforms).items())}}
    # In particular no 50/B8 decrement or F6/F7 clear can encode a high
    # R23 into the low class before its first gate. R5 also holds EXACTLY.
    assert report['isolatedTransformsBeforeFirstStop'] == {}
    if data['field'] == 23:
        assert report['starts'] == 806 and report['contexts'] == 5171
        assert report['firstObserverCounts'] == {'4A': 126, 'B2': 21}
        assert report['firstKillerCounts'] == {'B3': 21}
    elif data['field'] == 2:
        assert report['starts'] == 806 and report['contexts'] == 806
        assert report['firstObserverCounts'] == {'35': 806}
        assert report['firstKillerCounts'] == {}
    elif after54:
        assert report['starts'] == 288 and report['contexts'] == 1263
        assert report['firstObserverCounts'] == {'58': 130, '8B': 234}
        assert report['firstKillerCounts'] == {}
    else:
        assert report['starts'] == 806 and report['contexts'] == 4464
        assert report['firstObserverCounts'] == {'8B': 685}
        assert report['firstKillerCounts'] == {}
    print('COMPLETE controller first-observer cut:', json.dumps(report), flush=True)
    print('SCOPE: universal local dependencies and a complete conservative control cut. '
          'Positive observer contexts are NOT a native F transfer, C writer or partial K2.', flush=True)
    return report


def high_r23_tail(sequence):
    """ALL5..F have identical non-R23 state until the final original word.

    This is a PRIMARY ROM identity with arbitrary common future pages/keys,
    not an injection into the reference or a concrete native entry.
    """
    a = q['State'](f'highR23_{sequence[0]:02X}')
    b = a.copy();b.r[23] = BitVec(f'highR23_other_{sequence[0]:02X}', 4)
    p = w['base'](a, sequence[0]);p.add(UGE(a.r[23], 5), UGE(b.r[23], 5))
    pairs = (a, b)
    for index, code in enumerate(sequence):
        keys = q['arbitrary_keys'](f'highR23_keys{code:02X}_{index}')
        serial = q['State'](f'highR23_serial{code:02X}_{index}').m
        fresh = []
        for before in pairs:
            w['prove'](p, w['address'](before) == code,
                       f'highR23 forces{code:02X}', False)
            out = []
            after = w['ex'](before, code, *keys, serial_inputs=serial, emitted_outputs=out)
            w['prove'](p, equal(out, before.m), f'{code:02X} no outgoing write', False)
            fresh.append(after)
        left, right = fresh
        outside = And(*[left.r[k] == right.r[k] for k in range(42) if k != 23],
                      equal(left.m, right.m), equal(left.st, right.st),
                      *[getattr(left, n) == getattr(right, n)
                        for n in ('s', 's1', 'l', 't', 'carry')])
        w['prove'](p, outside, f'{code:02X} ALL5..F indistinguishable outside R23', False)
        pairs = fresh
    w['prove'](p, equal(left.r, right.r),
               'HIGH R23 first-observer tail forgets original5..F in ALL primary '
               'fields/outputs, arbitrary common keys/pages')
    print('PASS highR23 forced loss tail:', ' '.join(f'{code:02X}' for code in sequence), flush=True)
    print('SCOPE: only the high-class predicate may select the tail. ALL5..F are '
          'identical outside R23 and fully forgotten by the final word. Other '
          'copies, predicate effects, literal F constructors and earlier entries '
          'are NOT excluded.', flush=True)


def mode_reserve_contracts():
    a = q['State']('control54_shift');p = w['base'](a, 0x54);out = []
    b = w['ex'](a, 0x54, *q['arbitrary_keys']('control54_keys'),
                emitted_outputs=out)
    w['prove'](p, And(b.r[2] == 0, b.r[23] == 0,
                     *[b.r[k] == a.r[k-3] for k in (5, 8, 11, 14, 17, 20)],
                     *[b.r[k] == a.r[k] for k in range(36) if k % 3 != 2],
                     equal(out, a.m)),
               '54 saves oldR2 in R5, shifts C1..C6, clears R2/R23; '
               'ALL numeric A/B and outgoing ring held, arbitrary keys/pages')
    for code in (0x58, 0x8B):
        a, b, out, p, outside, _ = pair(code, 5, other_response_fields=(2,))
        claim = And(b.r[2] == a.r[5], b.r[5] == a.r[2], equal(out, a.m))
        if code == 0x58:
            claim = And(claim, *[b.r[k] == a.r[2] for k in (8, 11, 14, 17, 20)])
        w['prove'](p, claim,
                   f'{code:02X} returns EXACT oldR5 into R2, no outgoing ring write')
        w['prove'](p, outside,
                   f'{code:02X} changing oldR5 affects ONLY R2, not numeric '
                   'A/B, other primary fields or outgoing stream')
    print('SCOPE: R5 survives as a mode reserve, not a proved numeric/sign source. '
          'R2 paths after restoration, other copies and native literal77=F remain open. '
          'The conditional marker fixture is NOT a native keyboard witness.', flush=True)


def native_marker_mode_control():
    # Existing public-key fixture, passive observation plus a fresh ALL5
    # mirror. Do not confuse its genuine numeric signF with mode flagsF.
    fixture = json.dumps(str(root / 'cache-real-marker-sign-source-native.cjs'))
    script = (f'const n=require({fixture}).capture({{mirror:true,log:false}});'
              'process.stdout.write(JSON.stringify({mirror:n.report.observerIndependent,'
              'events:n.sourceEvents.map(e=>({ip:e.ip,R2:e.r[2],R5:e.r[5],R23:e.r[23]}))}));')
    result = subprocess.run(['node', '-e', script], cwd=root,
                            check=True, capture_output=True, text=True)
    data = json.loads(result.stdout)
    assert data['mirror'] is True and len(data['events']) == 9
    assert all((e['R2'], e['R5'], e['R23']) == (0, 8, 0) for e in data['events'])
    print('PASS native real-marker signF/fresh ALL5 mirror: ALL9 source events '
          'have R2=0,R5=8,R23=0. This separate K1 geometry does NOT '
          'construct a mode/control reserveF.', flush=True)


if __name__ == '__main__':
    for field in (23, 2, 5):
        data = inventory(field)
        first_observer_cut(data)
        if field == 5:
            first_observer_cut(data, after54=True)
    high_r23_tail((0x4A, 0x4B, 0x4D, 0x54))
    high_r23_tail((0xB2, 0x8E, 0x5E, 0x5D))
    mode_reserve_contracts()
    native_marker_mode_control()
