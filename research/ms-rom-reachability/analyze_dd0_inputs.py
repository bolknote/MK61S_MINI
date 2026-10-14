#!/usr/bin/env python3
"""Incoming edges and mode-writer provenance for the remaining last DD.

The reset graph is complete but does not track R2 or R0. Exact local output
conditions refine each projected edge, not its entire history. A positive
edge/history label is only an overapproximation, never a native setup.
"""
import runpy
import sys
from collections import defaultdict, deque
from pathlib import Path

from z3 import And, Or, UGE, ZeroExt, sat, unsat

root = Path(__file__).resolve().parent
sys.argv = ['analyze_gates.py', '--target', 'cd', '--r38', '--first-entry-lemmas']
m = runpy.run_path(str(root / 'analyze_gates.py'))
assert not m['queue'] and m['terminal'] is None
parents, templates, cache = (m[n] for n in ('parents', 'templates', 'cache'))
q = m['q']
byte = lambda lo, hi: ZeroExt(4, lo) | (ZeroExt(4, hi) << 4)
address = lambda a: byte(a.r[36], a.r[39])
stack = lambda a: tuple(byte(a.st[36+i], a.st[39+i]) for i in range(3))
STACKS = ((0x2F, 0x93, 0xE5), (0x2F, 0xAC, 0x72),
          (0x2F, 0xAC, 0x93), (0x2F, 0xAC, 0x9A),
          (0x2F, 0xAC, 0xAC), (0x2F, 0xAC, 0xD6),
          (0x2F, 0xAC, 0xDD), (0x2F, 0xDD, 0xE5))
TARGETS = (0xDD, 0xCB, 0xBA, 0x04, 0x03, 0x02, 0x01)
PREFIX_TARGETS = (0x2E, 0x2C, 0x1D, 0x2D, 0x1C, 0x1F, 0xA5)


def entry_solver(state):
    ip, sp, vector, selector, delta, r38, dr38, r26, types = state
    a, _, av, old = templates[ip][:4]
    p = m['state_solver'](a, ip)
    if vector == 'diagonal':
        p.add(a.r[37] == a.r[40])
    elif vector is not None:
        p.add(av == vector)
    p.add(Or(*[a.s1 == n for n in selector]), Or(*[a.r[38] == n for n in r38]),
          Or(*[a.r[26] == n for n in r26]), *[v == n for v, n in zip(old, sp)])
    if delta is not None:
        p.add(a.s1-a.r[35] == delta)
    if dr38 is not None:
        p.add(a.r[38]-a.r[35] == dr38)
    assert types is None
    return a, p


successors = {}
for state in parents:
    ip, sp, vector, selector, delta, r38, dr38, r26, types = state
    t = templates[ip]
    kind, pushed, new_vector, delta_op, sp_deps, dr38_op = (
        t[4], t[5], t[6], t[9], t[10], t[13])
    key = (ip, tuple(sp[i] for i in sp_deps), vector, selector, delta,
           r38, dr38, r26, types)
    assert key in cache
    next_sp = (sp if kind == 'same' else sp[1:]+sp[:1] if kind == 'rotate' else
               (0xC7, 0x13, sp[0]) if kind == 'push2' else (pushed, sp[0], sp[1]))
    next_vector = vector if new_vector == 'preserve' else new_vector
    next_delta = ((delta+delta_op[1]) % 16 if delta is not None else None) \
        if delta_op[0] == 'add' else delta_op[1]
    next_dr38 = ((dr38+dr38_op[1]) % 16 if dr38 is not None else None) \
        if dr38_op[0] == 'add' else dr38_op[1]
    following = []
    for nxt, sel, m38, m26, typ in cache[key]:
        if nxt in (0xC7, 0xC8):
            continue
        target = (nxt, next_sp, next_vector, sel, next_delta, m38, next_dr38, m26, typ)
        assert target in parents
        following.append(target)
    successors[state] = tuple(following)

# Prove all 23 writer classifications again before using them as history labels.
r2 = runpy.run_path(str(root / 'check_r2_sources.py'))
writers = r2['labels']
origins = {state: set() for state in parents}
origins[m['start']].add('reset')
queue, pending = deque([m['start']]), {m['start']}
updates = 0
while queue:
    state = queue.popleft()
    pending.remove(state)
    ip = state[0]
    out = {ip} if ip in writers else origins[state]
    for target in successors[state]:
        extra = out-origins[target]
        if extra:
            origins[target].update(extra)
            if target not in pending:
                queue.append(target)
                pending.add(target)
    updates += 1
edges = 0
for state, targets in successors.items():
    out = {state[0]} if state[0] in writers else origins[state]
    for target in targets:
        assert out <= origins[target]
        edges += 1
assert all(origins.values())
print(f'PASS: R2 history cover: {len(parents)} states, {edges} edges, '
      f'{updates} updates; every edge covered, queue empty.', flush=True)


def read_context(a):
    return And(a.r[0] == 3, a.r[26] == 0, UGE(a.r[2], 5), a.s1 == 6,
               byte(a.r[37], a.r[40]) == 0xFF,
               Or(*[And(*[v == n for v, n in zip(stack(a), sp)]) for sp in STACKS]))


finals = {}
rows = {target: defaultdict(lambda: {'stacks': set(), 'origins': set(), 'count': 0})
        for target in TARGETS}
for state, following in successors.items():
    targets = {st[0] for st in following} & set(TARGETS)
    if not targets:
        continue
    ip = state[0]
    a, p = entry_solver(state)
    if ip not in finals:
        # All output constraints below refer to ONE execution, including the
        # branch address. No mixing of independent ring/keyboard witnesses.
        b = q['execute_command'](a, ip, *q['arbitrary_keys'](f'dd0_edge_keys_{ip}'))
        if ip == 0x93:
            b = q['execute_command'](b, 0x94, *q['arbitrary_keys']('dd0_edge_93_94'))
        if ip == 0x12:
            b = q['execute_command'](b, 0xC6, *q['arbitrary_keys']('dd0_edge_12_C6'))
        finals[ip] = b
    b = finals[ip]
    p.add(read_context(b))
    for target in targets:
        p.push()
        p.add(address(b) == target)
        outcome = p.check()
        assert outcome in (sat, unsat)
        if outcome == sat:
            row = rows[target][ip]
            row['count'] += 1
            row['origins'].update({ip} if ip in writers else origins[state])
            model = p.model()
            row['stacks'].add(tuple(model.eval(v).as_long() for v in stack(b)))
        p.pop()

fmt = lambda value: value if isinstance(value, str) else f'{value:02X}'
for target in TARGETS:
    print(f'Incoming {target:02X} / R0=3,R26=0,R2>=5,S1=6,vectorFF:', flush=True)
    for source, row in sorted(rows[target].items()):
        print(f'  {source:02X} ({templates[source][4]}), {row["count"]} contexts; '
              +'stacks='+','.join('/'.join(f'{v:02X}' for v in sp)
                                  for sp in sorted(row['stacks']))
              +'; last R2 writer='+','.join(fmt(v) for v in sorted(row['origins'], key=str)),
              flush=True)
print('Positive sources/history labels are overapproximations. R2 and R0 '
      'are only constrained at the projected local edge, not from reset.', flush=True)

expected = {0xDD: {0xCB}, 0xCB: {0xBA}, 0xBA: {0x04}, 0x04: {0x03},
            0x03: {0x02}, 0x02: {0x01, 0x02}, 0x01: {0x01, 0x2E}}
assert {target: set(sources) for target, sources in rows.items()} == expected
assert rows[0xDD][0xCB]['stacks'] == set(STACKS)
expected_writers = {0x58, 0x77, 0x8B, 0x9A, 0xAF, 0xB9, 0xC2, 0xCA, 0xEA}
assert rows[0xDD][0xCB]['origins'] == expected_writers
print('PASS: the remaining DD has the ordinary 2E read prefix, no old DD '
      'return; the last static R2 writer belongs to the nine listed sources.', flush=True)


def prefix_context(a):
    return And(a.r[0] == 3, a.r[26] == 0, UGE(a.r[2], 5),
               Or(*[And(stack(a)[0] == sp[1], stack(a)[1] == sp[2]) for sp in STACKS]))


def values(p, expression):
    p.push()
    result = set(q['possible_values'](expression, p, 2**expression.size()+1))
    p.pop()
    return result


prefix_rows = {target: defaultdict(lambda: {'count': 0, 'stacks': set(),
                'origins': set(), 's1': set(), 'r35': set(), 'vectors': set()})
               for target in PREFIX_TARGETS}
for state, following in successors.items():
    targets = {st[0] for st in following} & set(PREFIX_TARGETS)
    if not targets:
        continue
    ip = state[0]
    a, p = entry_solver(state)
    if ip not in finals:
        b = q['execute_command'](a, ip, *q['arbitrary_keys'](f'dd0_prefix_keys_{ip}'))
        if ip == 0x93:
            b = q['execute_command'](b, 0x94, *q['arbitrary_keys']('dd0_prefix_93_94'))
        if ip == 0x12:
            b = q['execute_command'](b, 0xC6, *q['arbitrary_keys']('dd0_prefix_12_C6'))
        finals[ip] = b
    b = finals[ip]
    p.add(prefix_context(b))
    for target in targets:
        p.push()
        p.add(address(b) == target)
        outcome = p.check()
        assert outcome in (sat, unsat)
        if outcome == sat:
            row = prefix_rows[target][ip]
            row['count'] += 1
            row['origins'].update({ip} if ip in writers else origins[state])
            model = p.model()
            row['stacks'].add(tuple(model.eval(v).as_long() for v in stack(b)))
            for name, expr in (('s1', b.s1), ('r35', b.r[35]),
                               ('vectors', byte(b.r[37], b.r[40]))):
                row[name].update(values(p, expr))
        p.pop()
for target in PREFIX_TARGETS:
    print(f'Prefix {target:02X} / R0=3,R26=0,R2>=5, matching top TWO stack bytes:', flush=True)
    for source, row in sorted(prefix_rows[target].items()):
        print(f'  {source:02X} ({templates[source][4]}), {row["count"]} contexts; '
              +'stacks='+','.join('/'.join(f'{v:02X}' for v in sp)
                                  for sp in sorted(row['stacks']))
              +'; '+ '; '.join(name+'='+','.join(f'{n:X}' for n in sorted(row[name]))
                               for name in ('s1', 'r35', 'vectors'))
              +'; last R2 writer='+','.join(fmt(v) for v in sorted(row['origins'], key=str)),
              flush=True)
print('Prefix rows still require backward context closure and exact numeric '
      'history checks before composing any candidate or exclusion.', flush=True)
assert not prefix_rows[0x2C], 'marker0/2C in the necessary read context is not excluded'
assert set(prefix_rows[0x2E]) == {0x1D}, 'an additional marker0 read source remains'
print('PASS: marker0 excludes 2C in the needed context; the preceding 2E '
      'must come from 1D. These are edge-cover exclusions, not selected paths.', flush=True)

# A second history cover carries a HIGH R2 throughout every non-writer
# segment. A fresh writer is conservatively seeded at every source state in
# the original reset cover: its numeric input history is NOT assumed valid.
# This can remove histories using a low-only branch after the last writer.
# The cache below filters only branch addresses. Other output correlations
# are deliberately left broad, so retained histories can still be spurious.
high_predicates = {}
branch_dependent = set()
for ip, t in templates.items():
    a = t[0]
    label = writers.get(ip, 'preserve')
    expression = {'zero': 0, 'eight': 8, 'fifteen': 15,
                  'copy_R5': a.r[5], 'copy_R1': a.r[1], 'copy_S1': a.s1,
                  'toggle_high_bit': a.r[2] ^ 8, 'preserve': a.r[2]}[label]
    high_predicates[ip] = expression >= 5 if isinstance(expression, int) else UGE(expression, 5)
    if str(a.r[2]) in m['expression_vars']([t[1]]):
        branch_dependent.add(ip)
print('Commands whose branch expression refers to R2: '+
      ','.join(f'{ip:02X}' for ip in sorted(branch_dependent)), flush=True)
high_edges, high_cache = {}, {}
for state, following in successors.items():
    ip, sp, vector, selector, delta, r38, dr38, r26, types = state
    t = templates[ip]
    if ip not in writers and ip not in branch_dependent:
        high_edges[state] = following
        continue
    key = (ip, tuple(sp[i] for i in t[10]), vector, selector, delta,
           r38, dr38, r26, types)
    if key not in high_cache:
        a, p = entry_solver(state)
        p.add(high_predicates[ip])
        admitted = set()
        for target in {st[0] for st in following}:
            p.push()
            p.add(t[1] == target)
            outcome = p.check()
            assert outcome in (sat, unsat)
            if outcome == sat:
                admitted.add(target)
            p.pop()
        high_cache[key] = admitted
    high_edges[state] = tuple(st for st in following if st[0] in high_cache[key])
high_origins = {state: set() for state in parents}
pending = set()
for state, following in high_edges.items():
    if state[0] not in writers:
        continue
    for target in following:
        high_origins[target].add(state[0])
        pending.add(target)
queue = deque(pending)
high_updates = 0
while queue:
    state = queue.popleft()
    pending.remove(state)
    if state[0] in writers:
        continue  # Every possible high-producing writer was seeded above.
    for target in high_edges[state]:
        extra = high_origins[state]-high_origins[target]
        if extra:
            high_origins[target].update(extra)
            if target not in pending:
                queue.append(target)
                pending.add(target)
    high_updates += 1
high_edge_count = 0
for state, following in high_edges.items():
    required = {state[0]} if state[0] in writers else high_origins[state]
    for target in following:
        assert required <= high_origins[target]
        high_edge_count += 1
assert not high_origins[m['start']], 'no high mode at zero reset'
print(f'PASS: high-mode history cover: {high_edge_count} admitted edges, '
      f'{high_updates} updates; all writer seeds and every edge covered.', flush=True)
high_dd_origins = set()
high_dd_stacks = defaultdict(set)
for state in parents:
    if state[0] != 0xDD:
        continue
    a, p = entry_solver(state)
    p.add(read_context(a))
    outcome = p.check()
    assert outcome in (sat, unsat)
    if outcome == sat:
        high_dd_origins.update(high_origins[state])
        high_dd_stacks[state[1]].update(high_origins[state])
print('Last HIGH R2 writers at the necessary DD:',
      ','.join(f'{ip:02X}' for ip in sorted(high_dd_origins)), flush=True)
for sp, labels in sorted(high_dd_stacks.items()):
    print('  '+'/'.join(f'{v:02X}' for v in sp)+': '+
          ','.join(f'{ip:02X}' for ip in sorted(labels)), flush=True)
assert high_dd_origins == expected_writers
restore_only = {(0x2F, 0x93, 0xE5), (0x2F, 0xAC, 0x93),
                (0x2F, 0xAC, 0xDD), (0x2F, 0xDD, 0xE5)}
assert {sp for sp, labels in high_dd_stacks.items() if labels == {0x9A}} == restore_only
print('A retained high writer still has arbitrary untracked input fields. '
      'This refined history cover is not a keyboard reachability proof.', flush=True)
