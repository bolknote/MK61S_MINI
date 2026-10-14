#!/usr/bin/env python3
"""Closed no-EE cuts from ALL reset-reachable program-reader contexts.

The cached controller is a complete conservative reset overapproximation,
including unlimited C8 and C9. Not a bounded path search or a payload proof.
Original program bytes / prior ring exports / other writers remain open.
"""
from collections import deque
import gzip
import json
from pathlib import Path
import runpy

root = Path(__file__).resolve().parent
audit = runpy.run_path(str(root / 'k1-formatter-entry-audit.py'))
with gzip.open(audit['cache_path'], 'rt') as stream:
    graph = json.load(stream)
assert graph['schema'] == 'mk61-reset-control-graph-v1'
assert graph['metadata']['sourceSha256'] == audit['fingerprints']()
assert graph['metadata']['argv'] == audit['argv']
assert graph['metadata']['complete'] and graph['metadata']['pending'] == 0
assert graph['metadata']['terminal'] is None
states, edges = graph['states'], graph['successors']
assert len(states) == len(edges) == len(graph['parents'])
assert all(0 <= j < len(states) for row in edges for j in row)


def closed_cut(code, expected_starts, expected_reached):
    starts = [j for j, st in enumerate(states) if st[0] == code]
    assert len(starts) == expected_starts
    reached = set(starts)
    queue = deque(starts)
    while queue:
        index = queue.popleft()
        if states[index][0] == 0xEE:
            continue
        for nxt in edges[index]:
            if nxt not in reached:
                reached.add(nxt)
                queue.append(nxt)
    assert len(reached) == expected_reached
    targets = [j for j in reached if states[j][0] == 0xE4]
    assert not targets
    print('PASS: ALL reset-reachable', f'{code:02X}', 'contexts', len(starts),
          '; closed noEE reachable', len(reached), '; E4 contexts0; pending0.', flush=True)


if __name__ == '__main__':
    print('PASS cache provenance:', len(states), 'states;',
          sum(map(len, edges)), 'edges; complete.', flush=True)
    for code, starts, reached in ((0xC9, 146, 10695), (0xC8, 19, 10571),
                                  (0x06, 273, 41129), (0x67, 61, 10503),
                                  (0x0A, 21, 11039)):
        closed_cut(code, starts, reached)
    print('PASS: any C9-to-E4 controller path after digital reset crosses EE; '
          'another C9 caller/reader exit alone cannot remove this barrier.', flush=True)
    print('LIMIT: not absence of a C9-to-different-writer route, a prior ring '
          'reserve read by EE, or partial K2; arbitrary injected entries are '
          'not claimed to be reset-reachable.', flush=True)
