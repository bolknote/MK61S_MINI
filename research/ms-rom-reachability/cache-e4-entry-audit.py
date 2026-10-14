#!/usr/bin/env python3
"""Complete cached reset-controller cuts from actual P9 reader/DC metadata.

Absence is conclusive in this conservative controller. Positive shortest
paths are only controller candidates: no payload or timed-key claim follows.
The exact IK1302 prefix filter further rejects joint impossible candidates.
"""
from collections import deque
import gzip
import json
from pathlib import Path
import runpy
import subprocess

root = Path(__file__).resolve().parent
audit = runpy.run_path(str(root / 'k1-formatter-entry-audit.py'))
with gzip.open(audit['cache_path'], 'rt') as stream:
    graph = json.load(stream)
assert graph['metadata']['sourceSha256'] == audit['fingerprints']()
assert graph['metadata']['argv'] == audit['argv']
assert graph['metadata']['complete'] and graph['metadata']['pending'] == 0
assert graph['metadata']['terminal'] is None
states, edges = graph['states'], graph['successors']
native = json.loads(subprocess.check_output(
    ['node', str(root / 'cache46-bsource-selector.cjs'), '--proof-input'], text=True))
q = runpy.run_path(str(root / 'ik1302_symbolic.py'))
checker = runpy.run_path(str(root / 'verify_c8_recovery_candidate.py'),
                       init_globals={'transport': {'q': q}})


def compatible(st, actual):
    ip, sp, vector, selector, delta, r38, dr38, r26, types = st
    r = actual['r']
    if ip != r[36]+16*r[39]:
        return False
    if sp != [actual['st'][36+j]+16*actual['st'][39+j] for j in range(3)]:
        return False
    if vector == 'diagonal' and r[37] != r[40]:
        return False
    if isinstance(vector, int) and vector != r[37]+16*r[40]:
        return False
    if selector is not None and actual['s1'] not in selector:
        return False
    if delta is not None and delta != (actual['s1']-r[35]) % 16:
        return False
    if r38 is not None and r[38] not in r38:
        return False
    if dr38 is not None and dr38 != (r[38]-r[35]) % 16:
        return False
    if r26 is not None and r[26] not in r26:
        return False
    assert types is None
    return True


def walk(actual, blocked, target):
    starts = [j for j, st in enumerate(states) if compatible(st, actual)]
    assert starts, 'native metadata must match the cached reset graph'
    previous = dict.fromkeys(starts)
    queue = deque(starts)
    while queue:
        index = queue.popleft()
        if states[index][0] in blocked:
            continue
        for nxt in edges[index]:
            if nxt not in previous:
                previous[nxt] = index
                queue.append(nxt)
    targets = [j for j in previous if states[j][0] == target]
    path = []
    if targets:
        j = targets[0]
        while j is not None:
            path.append(j)
            j = previous[j]
    sequence = []
    for index in reversed(path):
        code = states[index][0]
        sequence.append(code)
        if code == 0x93:
            sequence.append(0x94)
        if code == 0x12:
            sequence.append(0xC6)
    return starts, previous, targets, sequence


def report():
    print('PASS: cached graph provenance,', len(states), 'states;',
          sum(map(len, edges)), 'edges; no pending.', flush=True)
    writers = (0x32, 0x34, 0xA3, 0xA8, 0xBC, 0xC7, 0xE7, 0xE9)
    cuts = (('noEE', (0xEE,)), ('noEE/noC9', (0xEE, 0xC9)),
            ('noEE/noC9/noM2', (0xEE, 0xC9)+writers))
    for name, actual in (('P9 reader35', native['readerInitial']),
                         ('P9 rawDC', native['dc'])):
        for label, blocked in cuts:
            for target in (0xE4, 0xE3, 0x3F, 0x16):
                starts, reached, targets, sequence = walk(actual, blocked, target)
                print('CONTROLLER CUT', name, label, f'target{target:02X}',
                      'starts', len(starts), 'visited', len(reached),
                      'contexts', len(targets), 'pending0', flush=True)
                assert not targets, (name, label, target, len(targets))
                if sequence:
                    print('CONTROLLER CANDIDATE only:',
                          ' '.join(f'{code:02X}' for code in sequence), flush=True)
                    result = checker['verify_sequence'](sequence, actual)
                    print('EXACT native-prefix filter:', result['result'], flush=True)
    print('LIMIT: positive graph/filter result needs source survival, '
          'whole-ring timing and an actual keyboard protocol.', flush=True)


if __name__ == '__main__':
    report()
