#!/usr/bin/env python3
"""Reverse high-mode slice before a last DD in a cycle context.

May reuse the dictionary returned by analyze_dd0_inputs.py as `cover`.
The slice is over a completed conservative graph. Paths printed below are
structural candidates, not exact-state or keyboard witnesses.
"""
import runpy
from collections import defaultdict, deque
from pathlib import Path

from z3 import And, Or, UGE, sat, unsat

root = Path(__file__).resolve().parent
if 'cover' not in globals():
    cover = runpy.run_path(str(root / 'analyze_dd0_inputs.py'))
states = cover['parents']
edges = cover['high_edges']
writers = cover['writers']
entry_solver = cover['entry_solver']
byte, address, stack = (cover[n] for n in ('byte', 'address', 'stack'))
q = cover['q']
templates = cover['templates']
reverse = defaultdict(list)
for state, following in edges.items():
    for nxt in following:
        reverse[nxt].append(state)
targets = set()
for state in states:
    if state[0] != 0xDD:
        continue
    a, p = entry_solver(state)
    p.add(cover['read_context'](a), a.r[35] == 5, a.r[38] == 13,
          Or(*[a.r[32] == i for i in range(4)]))
    outcome = p.check()
    assert outcome in (sat, unsat)
    if outcome == sat:
        targets.add(state)
next_step = {state: None for state in targets}
queue = deque(targets)
roots = defaultdict(list)
while queue:
    state = queue.popleft()
    for prev in reverse[state]:
        if prev[0] in writers:
            roots[prev[0]].append((prev, state))
            continue
        if prev not in next_step:
            next_step[prev] = state
            queue.append(prev)
print(f'{len(targets)} necessary DD contexts; {len(next_step)} states in '
      'the reverse high-mode/non-writer slice', flush=True)
for ip, entries in sorted(roots.items()):
    print(f'writer {ip:02X}: {len(entries)} root edges; destinations '+
          ','.join(f'{v:02X}' for v in sorted({nxt[0] for _, nxt in entries})), flush=True)


def vals(p, expression):
    p.push()
    result = set(q['possible_values'](expression, p, 2**expression.size()+1))
    p.pop()
    return result


summaries = {}
for state, nxt in roots[0x9A]:
    a, p = entry_solver(state)
    b = q['execute_command'](a, 0x9A, *q['arbitrary_keys']('restore9a_slice_keys'))
    p.add(address(b) == nxt[0], UGE(b.r[2], 5))
    outcome = p.check()
    assert outcome in (sat, unsat)
    if outcome == unsat:
        continue
    key = nxt[0], state[1], state[2]
    row = summaries.setdefault(key, {'count': 0, 'R32': set(), 'R35': set(),
                                    'R38': set(), 'R26': set(), 'S1': set(), 'example': (state, nxt)})
    row['count'] += 1
    for name, expr in (('R32', b.r[32]), ('R35', b.r[35]),
                       ('R38', b.r[38]), ('R26', b.r[26]), ('S1', b.s1)):
        row[name].update(vals(p, expr))
for (dest, sp, vector), row in sorted(summaries.items(), key=str):
    print(f'9A->{dest:02X}, old SP='+ '/'.join(f'{v:02X}' for v in sp)+
          f', vector={vector}: '+ '; '.join(name+'='+','.join(f'{v:X}' for v in sorted(row[name]))
                                          for name in ('R32', 'R35', 'R38', 'R26', 'S1')), flush=True)
examples = {}
for key, row in summaries.items():
    dest = key[0]
    if dest in examples:
        continue
    start, nxt = row['example']
    sequence = [start]
    while nxt is not None:
        sequence.append(nxt)
        nxt = next_step[nxt]
    examples[dest] = sequence
    print('Candidate suffix for destination '+f'{dest:02X}'+': '+
          ' '.join(f'{st[0]:02X}' for st in sequence), flush=True)
print('These roots still omit the numeric ST/caller history and must not '
      'be treated as reachable high-mode states.', flush=True)
