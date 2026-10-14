#!/usr/bin/env python3
"""Forward saved-mode domains on a complete control/return-stack cover.

This joins individual nibble domains, so a retained tuple may be spurious.
Copied fields and constants are universally proved; unsupported arithmetic
is TOP. Numeric stack slots are tracked through their exact movements.
All R2-dependent branch masks are computed from the exact ROM semantics.
"""
import runpy
from collections import deque
from pathlib import Path

from z3 import And, Or, UGE, sat, unsat

root = Path(__file__).resolve().parent
if 'cover' not in globals():
    cover = runpy.run_path(str(root / 'analyze_dd0_inputs.py'))
m, q = cover['m'], cover['q']
states, edges = cover['parents'], cover['successors']
R_FIELDS = tuple(range(6))
ST_FIELDS = tuple(range(6))
NAMES = tuple(f'R{i}' for i in R_FIELDS)+tuple(f'ST{i}' for i in ST_FIELDS)
TOP = (1 << 16)-1
INDEX2 = R_FIELDS.index(2)


def fields(a):
    return [a.r[i] for i in R_FIELDS]+[a.st[i] for i in ST_FIELDS]


def bit_values(mask):
    return [i for i in range(16) if mask & (1 << i)]


specs = {}
for ip, t in m['templates'].items():
    a = t[0]
    b = q['execute_command'](a, ip, *q['arbitrary_keys'](f'saved_mode_keys_{ip}'))
    if ip == 0x93:
        b = q['execute_command'](b, 0x94, *q['arbitrary_keys']('saved_mode_93_94'))
    if ip == 0x12:
        b = q['execute_command'](b, 0xC6, *q['arbitrary_keys']('saved_mode_12_C6'))
    old, new = fields(a), fields(b)
    operations = []
    for index, expr in enumerate(new):
        copied = next((j for j, source in enumerate(old) if expr.eq(source)), None)
        if copied is not None:
            operations.append(('copy', copied))
            continue
        p = q['base_solver'](a, ip)
        assert p.check() == sat
        value = p.model().eval(expr, model_completion=True).as_long()
        p.push()
        p.add(expr != value)
        constant = p.check() == unsat
        p.pop()
        if constant:
            operations.append(('constant', value))
            continue
        found = None
        for label, source, expression in (
                ('xor8', INDEX2, a.r[2] ^ 8),
                ('inc', R_FIELDS.index(5), a.r[5]+1),
                ('s1inc', -1, a.s1+1)):
            p.push()
            p.add(expr != expression)
            valid = p.check() == unsat
            p.pop()
            if valid:
                found = label, source
                break
        operations.append(found or ('top', -1))
    specs[ip] = tuple(operations)
    if ip % 64 == 63:
        print(f'compiled {ip+1}/256 saved-mode transfers', flush=True)

# Filter only by R2; leaving other dependencies unconstrained is safe.
branch_ips = cover['branch_dependent']
masks, mask_cache = {}, {}
for state, following in edges.items():
    ip, sp, vector, selector, delta, r38, dr38, r26, types = state
    if ip not in branch_ips:
        masks[state] = {target[0]: TOP for target in following}
        continue
    t = m['templates'][ip]
    key = (ip, tuple(sp[i] for i in t[10]), vector, selector, delta, r38, dr38, r26, types)
    if key not in mask_cache:
        a, p = cover['entry_solver'](state)
        allowed = {}
        for target in {nxt[0] for nxt in following}:
            p.push()
            p.add(t[1] == target)
            p.push()
            values = q['possible_values'](a.r[2], p, 17)
            p.pop()
            allowed[target] = sum(1 << v for v in values)
            p.pop()
        mask_cache[key] = allowed
    masks[state] = mask_cache[key]
print(f'compiled {len(mask_cache)} R2-sensitive branch masks', flush=True)


def transfer(state, incoming, target):
    ip = state[0]
    allowed = incoming[INDEX2] & masks[state][target[0]]
    if not allowed:
        return None
    narrowed = list(incoming)
    narrowed[INDEX2] = allowed
    out = []
    for operation, source in specs[ip]:
        if operation == 'copy':
            value = narrowed[source]
        elif operation == 'constant':
            value = 1 << source
        elif operation == 'xor8':
            value = ((narrowed[source] & 255) << 8) | (narrowed[source] >> 8)
        elif operation == 'inc':
            value = ((narrowed[source] << 1) & TOP) | (narrowed[source] >> 15)
        elif operation == 's1inc':
            value = sum(1 << ((n+1) % 16) for n in state[3])
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
    for target in edges[state]:
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
assert domains[start] == (1,)*len(NAMES)
checked = 0
for state, incoming in domains.items():
    for target in edges[state]:
        out = transfer(state, incoming, target)
        if out is not None:
            assert target in domains
            assert all((x & ~y) == 0 for x, y in zip(out, domains[target]))
        checked += 1
print(f'PASS: saved-mode fixpoint: {updates} transfers, {len(domains)} states, '
      f'{checked} checked cover edges; queue empty.', flush=True)
dd_modes = {}
for state in states:
    if state[0] != 0xDD:
        continue
    a, p = cover['entry_solver'](state)
    p.add(cover['read_context'](a), a.r[35] == 5, a.r[38] == 13,
          Or(*[a.r[32] == v for v in range(4)]))
    if p.check() != sat:
        continue
    values = domains.get(state)
    dd_modes.setdefault(state[1], set()).update([] if values is None else bit_values(values[INDEX2]))
for sp, values in sorted(dd_modes.items()):
    print('DD '+ '/'.join(f'{n:02X}' for n in sp)+': R2='+
          ','.join(f'{v:X}' for v in sorted(values)), flush=True)
print('Domains are independent nibble sets; retained high modes still '
      'require joint numeric/control feasibility and native preparation.', flush=True)
