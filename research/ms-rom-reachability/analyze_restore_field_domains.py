#!/usr/bin/env python3
"""Joined saved numeric/control nibbles on the completed reset cover.

This adds the tail fields to the saved-mode transfer. Independent domains
are a conservative data-flow analysis, not a reachable tuple or keyboard
search. In particular the exact D5->AA opcode transport can now filter
the false AA->E5 branch instead of silently forgetting the FF value.
"""
import runpy
from collections import deque
from pathlib import Path

from z3 import Or, sat, unsat

root = Path(__file__).resolve().parent
if 'cover' not in globals():
    cover = runpy.run_path(str(root / 'analyze_dd0_inputs.py'))
m, q = cover['m'], cover['q']
R_FIELDS = tuple(range(6))+tuple(range(30, 36))
ST_FIELDS = R_FIELDS
NAMES = tuple(f'R{i}' for i in R_FIELDS)+tuple(f'ST{i}' for i in ST_FIELDS)
TOP = (1 << 16)-1
INDEX2, INDEX35 = R_FIELDS.index(2), R_FIELDS.index(35)


def fields(a):
    return [a.r[i] for i in R_FIELDS]+[a.st[i] for i in ST_FIELDS]


def bit_values(mask):
    return [i for i in range(16) if mask & (1 << i)]


def rotate(mask, n):
    n %= 16
    return ((mask << n) & TOP) | (mask >> (16-n))


def values(p, expr):
    p.push()
    out = q['possible_values'](expr, p, 2**expr.size()+1)
    p.pop()
    return out


specs, branch_masks = {}, {}
destinations = {}
for state, following in cover['successors'].items():
    destinations.setdefault(state[0], set()).update(nxt[0] for nxt in following)
for ip, t in m['templates'].items():
    a = t[0]
    b = q['execute_command'](a, ip, *q['arbitrary_keys'](f'field_domain_keys_{ip}'))
    if ip == 0x93:
        b = q['execute_command'](b, 0x94, *q['arbitrary_keys']('field_domain_93_94'))
    if ip == 0x12:
        b = q['execute_command'](b, 0xC6, *q['arbitrary_keys']('field_domain_12_C6'))
    old, new = fields(a), fields(b)
    operations = []
    for expr in new:
        copied = next((j for j, source in enumerate(old) if expr.eq(source)), None)
        if copied is not None:
            operations.append(('copy', copied, 0))
            continue
        p = q['base_solver'](a, ip)
        assert p.check() == sat
        value = p.model().eval(expr, model_completion=True).as_long()
        p.push()
        p.add(expr != value)
        constant = p.check() == unsat
        p.pop()
        if constant:
            operations.append(('constant', value, 0))
            continue
        dependencies = m['expression_vars']([expr])
        found = None
        candidates = [('copy', j, 0, source) for j, source in enumerate(old)
                      if str(source) in dependencies]
        candidates += [('add', j, n, source+n) for j, source in enumerate(old)
                       if str(source) in dependencies for n in (1, 15, 8)]
        candidates += [('xor8', INDEX2, 0, a.r[2] ^ 8),
                       ('s1', -1, 0, a.s1), ('s1', -1, 1, a.s1+1),
                       ('s1', -1, 15, a.s1-1)]
        for label, source, amount, expected in candidates:
            p.push()
            p.add(expr != expected)
            valid = p.check() == unsat
            p.pop()
            if valid:
                found = label, source, amount
                break
        operations.append(found or ('top', -1, 0))
    specs[ip] = tuple(operations)
    # Universal one-command branch masks. Existing source-specific R2
    # masks below further narrow these, with all original core bounds.
    addr = cover['address'](b)
    dependencies = m['expression_vars']([addr])
    relevant = [j for j, expr in enumerate(old) if str(expr) in dependencies]
    for target in destinations.get(ip, ()):
        p = q['base_solver'](a, ip)
        p.add(addr == target)
        assert p.check() == sat
        masks = [TOP]*len(NAMES)
        for j in relevant:
            masks[j] = sum(1 << v for v in values(p, old[j]))
        branch_masks[ip, target] = tuple(masks)
    if ip % 64 == 63:
        print(f'compiled {ip+1}/256 numeric/tail transfers and branch masks', flush=True)

if 'saved_modes' not in globals():
    saved_modes = runpy.run_path(str(root / 'analyze_saved_mode_domains.py'),
                                init_globals={'cover': cover})


def transfer(state, incoming, target):
    narrowed = [x & y for x, y in zip(incoming, branch_masks[state[0], target[0]])]
    narrowed[INDEX2] &= saved_modes['masks'][state][target[0]]
    # These are literal constraints in the completed source context.
    if state[4] is not None:
        narrowed[INDEX35] &= sum(1 << ((v-state[4]) % 16) for v in state[3])
    if state[6] is not None:
        narrowed[INDEX35] &= sum(1 << ((v-state[6]) % 16) for v in state[5])
    if not all(narrowed):
        return None
    out = []
    for operation, source, amount in specs[state[0]]:
        if operation == 'copy':
            value = narrowed[source]
        elif operation == 'constant':
            value = 1 << source
        elif operation == 'add':
            value = rotate(narrowed[source], amount)
        elif operation == 'xor8':
            value = rotate(narrowed[source], 8)
        elif operation == 's1':
            value = sum(1 << ((n+amount) % 16) for n in state[3])
        else:
            assert operation == 'top'
            value = TOP
        out.append(value)
    return tuple(out)


start = m['start']
domains = {start: (1,)*len(NAMES)}
queue, pending = deque([start]), {start}
updates = 0
while queue:
    state = queue.popleft()
    pending.remove(state)
    for target in cover['successors'][state]:
        out = transfer(state, domains[state], target)
        if out is None:
            continue
        previous = domains.get(target)
        joined = out if previous is None else tuple(x | y for x, y in zip(previous, out))
        if previous == joined:
            continue
        domains[target] = joined
        if target not in pending:
            queue.append(target)
            pending.add(target)
    updates += 1
    if updates % 50000 == 0:
        print(f'{updates} transfers, {len(domains)} states, {len(queue)} pending', flush=True)
checked = 0
for state, incoming in domains.items():
    for target in cover['successors'][state]:
        out = transfer(state, incoming, target)
        if out is not None:
            assert target in domains
            assert all((x & ~y) == 0 for x, y in zip(out, domains[target]))
        checked += 1
print(f'PASS: numeric/tail fixpoint: {updates} transfers, {len(domains)} states, '
      f'{checked} checked edges; queue empty.', flush=True)
ac = [d for st, d in domains.items() if st[0] == 0xAC]
for name in ('R1', 'R31', 'R34', 'ST32', 'ST35'):
    mask = 0
    for d in ac:
        mask |= d[NAMES.index(name)]
    print('AC '+name+': '+','.join(f'{n:X}' for n in bit_values(mask)), flush=True)
signatures = [st for st, d in domains.items() if st[0] == 0xAC and
              d[NAMES.index('R1')] & (TOP ^ 31) and
              d[NAMES.index('R31')] & sum(1 << n for n in (8, 10, 11, 13)) and
              d[NAMES.index('R34')] & (1 << 5) and
              d[NAMES.index('ST32')] & sum(1 << n for n in range(12, 16)) and
              d[NAMES.index('ST35')] & (1 << 9)]
print(f'AC high-counter/cycle signature admitted in {len(signatures)} '
      'independent-domain contexts; this is not joint reachability.', flush=True)
