#!/usr/bin/env python3
"""Exact first-use/first-loss frontier of an isolated working A7 source.

All256 primary words receive arbitrary other state, common per-tick keys and
common future serial input. The complete reset-controller graph is a sound
overapproximation, NOT a positive native keyboard/data witness.
"""
from collections import Counter, deque
import json
from pathlib import Path
import runpy

from z3 import And, BitVec, sat, unsat

root = Path(__file__).resolve().parent
w = runpy.run_path(str(root / 'cache46-writer-contracts.py'))
q = w['q']


def differs(p, claim):
    assert p.check() == sat
    p.push(); p.add(~claim); result = p.check(); p.pop()
    assert result in (sat, unsat)
    return result == sat


def inventory():
    observed, killed, isolated = [], [], []
    direct, transforms = {}, {}
    for code in range(256):
        a = q['State'](f'input_sign_{code:02X}')
        other = a.copy()
        other.r[21] = BitVec(f'input_sign_other_{code:02X}', 4)
        keys = q['arbitrary_keys'](f'input_sign_keys_{code:02X}')
        serial = q['State'](f'input_sign_serial_{code:02X}').m
        results, outputs = [], []
        for before in (a, other):
            out = []
            results.append(w['ex'](before, code, *keys, serial_inputs=serial,
                                    emitted_outputs=out))
            outputs.append(out)
        b, c = results
        common = [w['eq'](getattr(b, field), getattr(c, field)) for field in ('m', 'st')]
        common += [getattr(b, field) == getattr(c, field)
                   for field in ('s', 's1', 'l', 't', 'carry')]
        common += [w['eq'](*outputs)]
        outside = And(*common, *[b.r[index] == c.r[index] for index in range(42)
                                if index != 21])
        whole = And(outside, b.r[21] == c.r[21])
        p = w['base'](a, code)
        if differs(p, outside):
            observed.append(code)
            candidates = [(f'R{index}', b.r[index]) for index in range(42) if index != 21]
            candidates += [(f'ST{index}', b.st[index]) for index in range(42)]
            candidates += [(f'out{index}', value) for index, value in enumerate(outputs[0])]
            copies = [label for label, value in candidates
                      if not differs(p, value == a.r[21])]
            if copies:
                direct[f'{code:02X}'] = copies
        elif differs(p, whole):
            isolated.append(code)
            if differs(p, b.r[21] == a.r[21]):
                p.push(); p.add(a.r[21] == 15)
                values = q['possible_values'](b.r[21], p, 17); p.pop()
                transforms[f'{code:02X}'] = values
        else:
            killed.append(code)
        if code % 64 == 63:
            print(f'A7 audit through{code:02X}: observers{len(observed)}, '
                  f'killers{len(killed)}, isolated{len(isolated)}', flush=True)
    assert len(observed)+len(killed)+len(isolated) == 256
    assert observed == [0x08, 0x12, 0x16, 0x17, 0x1E, 0x20, 0x22, 0x24, 0x26,
                        0x30, 0x32, 0x37, 0x3A, 0x3F, 0x40, 0x41, 0x42, 0x49,
                        0x60, 0x61, 0x91, 0x93, 0x98, 0xA8, 0xAF, 0xC6, 0xC7,
                        0xCF, 0xD4, 0xD7, 0xDD, 0xE1, 0xE4, 0xE7, 0xE9, 0xEB,
                        0xEC, 0xF6, 0xF7, 0xFE]
    assert killed == [0x00, 0x43, 0x44, 0x47, 0x6E, 0x94, 0x95, 0xD2, 0xD6, 0xEE]
    assert len(isolated) == 206
    assert direct['D4'] == ['out24']
    assert direct['40'] == direct['93'] == ['ST21']
    assert direct['FE'] == ['R18']
    assert set(transforms) == {'0B', '0C', '0D', '0E', '3B', '3C', '3D', '3E', '57', 'C3'}
    assert all(set(values) == set(range(16)) for values in transforms.values())
    report = {'observers': observed, 'killers': killed, 'isolated': isolated,
              'exactCopies': direct, 'isolatedTransformsWithF': transforms}
    print('ALL256 A7-source inventory:', json.dumps({
        'observers': [f'{v:02X}' for v in observed],
        'killers': [f'{v:02X}' for v in killed], 'isolatedCount': len(isolated),
        'exactCopies': direct, 'isolatedTransformsWithF': transforms}), flush=True)
    return report


def first_frontier(report):
    graph = runpy.run_path(str(root / 'cache-numeric-export-gates.py'))
    states, edges, metadata = graph['states'], graph['edges'], graph['graph']['metadata']
    reached = {index for index, state in enumerate(states) if state[0] == 0x35}
    starts = len(reached)
    todo = deque(sorted(reached))
    parent = {index: None for index in reached}
    observers, killers, transforms = [], [], []
    while todo:
        index = todo.popleft()
        code = states[index][0]
        words = [int(value, 16) for value in metadata['fusedCommands'].get(
            f'{code:02X}', [f'{code:02X}'])]
        stop = False
        for word in words:
            if word in report['observers']:
                observers.append((index, word)); stop = True; break
            if word in report['killers']:
                killers.append((index, word)); stop = True; break
            assert word in report['isolated']
            if f'{word:02X}' in report['isolatedTransformsWithF']:
                transforms.append((index, word))
        if stop:
            continue
        for child in edges[index]:
            if child not in reached:
                reached.add(child); todo.append(child); parent[child] = index
    def counts(events):
        return {f'{code:02X}': count for code, count in sorted(Counter(
            code for _, code in events).items())}
    paths = {}
    for index, word in observers:
        key = f'{word:02X}'
        if key in paths:
            continue
        chain = []
        while index is not None:
            chain.append(index); index = parent[index]
        paths[key] = [f'{states[index][0]:02X}' for index in reversed(chain)]
    result = {'starts35': starts, 'contexts': len(reached),
              'firstObservers': counts(observers), 'firstKillers': counts(killers),
              'isolatedTransformsBeforeStop': counts(transforms),
              'shortestConservativePaths': paths}
    assert (starts, len(reached)) == (806, 15737)
    assert result['firstObservers'] == {'49': 3, '60': 11, '91': 35, 'D4': 4,
                                       'D7': 4, 'DD': 5, 'EC': 5, 'F6': 7,
                                       'F7': 7, 'FE': 22}
    assert result['firstKillers'] == {'6E': 4, 'D2': 34, 'D6': 4, 'EE': 40}
    assert result['isolatedTransformsBeforeStop'] == {'57': 18}
    print('COMPLETE A7 first-use/loss frontier:', json.dumps(result), flush=True)
    print('SCOPE: positive first-observer paths are conditional controller candidates, '
          'not native key recipes, data preservation or signF constructors. Earlier '
          'independent sources/reserves, literalF construction and partialK2 remain open.',
          flush=True)
    return result


def exact_path_filters(frontier):
    """Test conservative shortest paths; a rejection closes that path ONLY."""
    results = {}
    for sink, labels in frontier['shortestConservativePaths'].items():
        sequence = [int(label, 16) for label in labels]
        a = q['State'](f'input_sign_exact_{sink}')
        p = w['base'](a, sequence[0]); p.add(a.r[21] == 15)
        before = a
        failure = None
        for index, code in enumerate(sequence):
            p.add(w['ip'](before) == code)
            status = p.check(); assert status in (sat, unsat)
            if status == unsat:
                failure = {'index': index, 'ip': f'{code:02X}'}
                break
            if sink == 'FE' and index == len(sequence)-1:
                w['prove'](p, before.r[21] == 15,
                           'conditional shortest FE candidate actually retains initial A7=F')
            serial = q['State'](f'input_sign_exact_serial_{sink}_{index}').m
            before = w['ex'](before, code,
                             *q['arbitrary_keys'](f'input_sign_exact_keys_{sink}_{index}'),
                             serial_inputs=serial)
        results[sink] = {'result': 'unsat' if failure is not None else 'sat',
                         'failure': failure}
        print('EXACT shortest A7 frontier filter:', sink, json.dumps(results[sink]),
              ' '.join(labels), flush=True)
    for sink in ('49', '91', 'D4', 'D7', 'DD', 'EC', 'F7', 'F6'):
        assert results[sink] == {'result': 'unsat', 'failure': {'index': 4, 'ip': 'B1'}}
    assert results['60'] == {'result': 'unsat', 'failure': {'index': 25, 'ip': 'FC'}}
    assert results['FE'] == {'result': 'sat', 'failure': None}
    print('LIMIT: SAT still permits arbitrary initial metadata/future pages and '
          'potakt keys. UNSAT does not reject longer or other controller paths.', flush=True)
    return results


def concrete_idle_fe_filter(initial):
    """Only the reported conditional early-mask idle, all its sources fixed to F."""
    labels = ('35 45 8B 48 4A 4C 4E 97 63 64 66 01 02 03 04 BA CC CD C9 '
              '67 6A 6B 6C 69 FB FD FE').split()
    sequence = [int(label, 16) for label in labels]
    before = initial.copy()
    p = w['base'](before, 0x35)
    p.add(*[before.r[3*index] == 15 for index in range(8)])
    assert p.check() == sat
    failure = None
    for index, code in enumerate(sequence):
        p.add(w['ip'](before) == code)
        outcome = p.check(); assert outcome in (sat, unsat)
        if outcome == unsat:
            failure = {'index': index, 'ip': f'{code:02X}'}
            break
        before = w['ex'](
            before, code, *q['arbitrary_keys'](f'concrete_mask_fe_keys_{index}'),
            serial_inputs=q['State'](f'concrete_mask_fe_serial_{index}').m)
    report = {'native': False, 'input': 'first conditional released35; original A0..A7=F',
              'result': 'unsat' if failure is not None else 'sat', 'failure': failure,
              'sequence': labels}
    assert report['result'] == 'unsat'
    assert failure == {'index': 8, 'ip': '63'}
    print('EXACT conditional mask/FE filter:', json.dumps(report), flush=True)
    print('LIMIT: this tests one FE route and a NON-NATIVE early-counter inlet, '
          'not all FE routes, full physical-ring feasibility or partialK2.', flush=True)
    return report


def fe_source_contract():
    a = q['State']('input_sign_FE_contract')
    p = w['base'](a, 0xFE)
    outputs = []
    b = w['ex'](a, 0xFE, *q['arbitrary_keys']('input_sign_FE_contract_keys'),
                emitted_outputs=outputs)
    w['prove'](p, And(w['ip'](b) == 0xFC,
                     w['eq'](b.r[0:33:3], a.r[3:36:3]),
                     b.r[33] == 14, w['eq'](outputs, a.m)),
               'FE linearly shifts A1..11 into A0..10, inserts E in A11, '
               'moves oldA7 to A6, exitsFC and writes no outgoing ring')
    print('LIMIT: FE is NOT a circular12-tetra rotation, numeric writer or '
          'native inlet. OldA7 is not the next A7/D4-sign feed.', flush=True)


if __name__ == '__main__':
    exact_path_filters(first_frontier(inventory()))
    fe_source_contract()
