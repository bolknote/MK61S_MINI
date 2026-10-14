#!/usr/bin/env python3
"""Apply proved saved-field domains to the last-high-mode reverse slice."""
import runpy
from pathlib import Path

from z3 import Or, UGE, sat, unsat

root = Path(__file__).resolve().parent
if 'restore_fields' not in globals():
    restore_fields = runpy.run_path(str(root / 'analyze_restore_field_domains.py'))
original = restore_fields['cover']
q, m = original['q'], original['m']
domains = restore_fields['domains']
TOP = restore_fields['TOP']


def entry_solver(state):
    a, p = original['entry_solver'](state)
    for expr, mask in zip(restore_fields['fields'](a), domains[state]):
        if mask != TOP:
            p.add(Or(*[expr == n for n in restore_fields['bit_values'](mask)]))
    return a, p


successors = {state: tuple(nxt for nxt in original['successors'][state]
                          if restore_fields['transfer'](state, incoming, nxt) is not None)
              for state, incoming in domains.items()}
assert all(nxt in domains for following in successors.values() for nxt in following)
executions, cache, high_edges = {}, {}, {}
for state, following in successors.items():
    ip, sp, vector, selector, delta, r38, dr38, r26, types = state
    if ip not in executions:
        a = original['templates'][ip][0]
        b = q['execute_command'](a, ip, *q['arbitrary_keys'](f'refined_high_keys_{ip}'))
        if ip == 0x93:
            b = q['execute_command'](b, 0x94, *q['arbitrary_keys']('refined_high_93_94'))
        if ip == 0x12:
            b = q['execute_command'](b, 0xC6, *q['arbitrary_keys']('refined_high_12_C6'))
        executions[ip] = b
    b = executions[ip]
    t = original['templates'][ip]
    key = (ip, tuple(sp[i] for i in t[10]), vector, selector, delta,
           r38, dr38, r26, types, domains[state], tuple(sorted({nxt[0] for nxt in following})))
    if key not in cache:
        a, p = entry_solver(state)
        # A last writer starts a high segment with its output. Other
        # commands must execute while high; all their R2 copies were proved.
        p.add(UGE(b.r[2] if ip in original['writers'] else a.r[2], 5))
        allowed = set()
        for dest in {nxt[0] for nxt in following}:
            p.push()
            p.add(original['address'](b) == dest)
            outcome = p.check()
            assert outcome in (sat, unsat)
            if outcome == sat:
                allowed.add(dest)
            p.pop()
        cache[key] = allowed
    high_edges[state] = tuple(nxt for nxt in following if nxt[0] in cache[key])
refined = dict(original)
refined.update(parents={state: original['parents'][state] for state in domains},
               successors=successors, high_edges=high_edges, entry_solver=entry_solver)
print(f'PASS: refined complete cover has {len(domains)} states, '
      f'{sum(map(len, successors.values()))} edges, '
      f'{sum(map(len, high_edges.values()))} admitted high-segment edges.', flush=True)
slice9a = runpy.run_path(str(root / 'analyze_restore9a_slice.py'),
                        init_globals={'cover': refined})
if slice9a['roots'][0x9A]:
    entries9a = runpy.run_path(str(root / 'analyze_restore9a_entries.py'),
                              init_globals={'slice9a': slice9a})
