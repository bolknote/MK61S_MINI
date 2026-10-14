#!/usr/bin/env python3
"""Relational saved-field pairs on the completed control cover.

Every value is a 256-bit set of ordered nibble pairs. Copy/add operations
use universally proved transfers from analyze_restore_field_domains.py;
unknown expressions use a Cartesian overapproximation. Arc consistency
only removes pair members contradicted by another tracked projection.
No user programs or key sequences are enumerated.
The default tracks 144 mode/tail pairs; all_pairs=True in runpy initial
globals tracks all 276 unordered pairs, with transpose/same-source rules.
"""
import runpy
from collections import deque
from functools import lru_cache
from pathlib import Path

root = Path(__file__).resolve().parent
if 'restore_fields' not in globals():
    restore_fields = runpy.run_path(str(root / 'analyze_restore_field_domains.py'))
f = restore_fields
cover, q = f['cover'], f['q']
TOP = f['TOP']
PAIR_TOP = (1 << 256)-1
MODE = tuple(f['NAMES'].index(f'{group}{i}') for group in ('R', 'ST') for i in range(6))
TAIL = tuple(f['NAMES'].index(f'{group}{i}') for group in ('R', 'ST') for i in range(30, 36))
PAIRS = (tuple((i,j) for i in range(len(f['NAMES'])) for j in range(i+1,len(f['NAMES'])))
         if globals().get('all_pairs', False) else
         tuple((i, j) for i in MODE for j in TAIL))
PAIR_INDEX = {pair: index for index, pair in enumerate(PAIRS)}


@lru_cache(maxsize=100000)
def rectangle(rows, columns):
    return sum(columns << (16*i) for i in range(16) if rows & (1 << i))


@lru_cache(maxsize=100000)
def projections(mask):
    rows = sum(1 << i for i in range(16) if (mask >> (16*i)) & TOP)
    columns = mask | (mask >> 128)
    columns |= columns >> 64
    columns |= columns >> 32
    columns |= columns >> 16
    return rows, columns & TOP


@lru_cache(maxsize=100000)
def shift_pair(mask, rows, columns):
    rows %= 16
    columns %= 16
    if rows:
        bits = 16*rows
        mask = ((mask << bits) & PAIR_TOP) | (mask >> (256-bits))
    if columns:
        low = rectangle(TOP, (1 << (16-columns))-1)
        mask = ((mask & low) << columns) | ((mask & (PAIR_TOP ^ low)) >> (16-columns))
    return mask


@lru_cache(maxsize=100000)
def transpose_pair(mask):
    rows, columns = projections(mask)
    if mask == rectangle(rows,columns):
        return rectangle(columns,rows)
    return sum(1 << (16*j+i) for i in range(16) for j in range(16)
               if mask & (1 << (16*i+j)))


@lru_cache(maxsize=10000)
def same_source(mask, rows, columns):
    return sum(1 << (16*((i+rows)%16)+(i+columns)%16)
               for i in range(16) if mask & (1 << i))


def copy_source(operation):
    label, source, amount = operation
    if label == 'copy':
        return source, 0
    if label == 'add':
        return source, amount
    if label == 'xor8':
        return source, 8
    return None


specs = {}
for ip, ops in f['specs'].items():
    result = []
    for i, j in PAIRS:
        left, right = copy_source(ops[i]), copy_source(ops[j])
        pair = None if left is None or right is None else (left[0], right[0])
        if pair in PAIR_INDEX:
            result.append(('direct',PAIR_INDEX[pair],left[1],right[1]))
        elif pair is not None and pair[::-1] in PAIR_INDEX:
            result.append(('transpose',PAIR_INDEX[pair[::-1]],left[1],right[1]))
        elif pair is not None and pair[0] == pair[1]:
            result.append(('same',pair[0],left[1],right[1]))
        else:
            result.append(None)
    specs[ip] = tuple(result)


def transfer(state, incoming, target):
    raw = f['domains'][state]
    unary = [x & y for x, y in zip(raw, f['branch_masks'][state[0], target[0]])]
    unary[f['INDEX2']] &= f['saved_modes']['masks'][state][target[0]]
    if state[4] is not None:
        unary[f['INDEX35']] &= sum(1 << ((v-state[4]) % 16) for v in state[3])
    if state[6] is not None:
        unary[f['INDEX35']] &= sum(1 << ((v-state[6]) % 16) for v in state[5])
    if not all(unary):
        return None
    # Propagate consequences of branch restrictions through the saved
    # pairs. Each projection narrows only a necessary input domain.
    narrowed = list(incoming)
    changed = True
    while changed:
        changed = False
        for k, (i, j) in enumerate(PAIRS):
            value = narrowed[k] & rectangle(unary[i], unary[j])
            if not value:
                return None
            narrowed[k] = value
            left, right = projections(value)
            if left != unary[i] or right != unary[j]:
                unary[i], unary[j] = left, right
                changed = True
    output_unary = []
    for label, source, amount in f['specs'][state[0]]:
        if label == 'copy':
            value = unary[source]
        elif label == 'constant':
            value = 1 << source
        elif label == 'add':
            value = f['rotate'](unary[source], amount)
        elif label == 'xor8':
            value = f['rotate'](unary[source], 8)
        elif label == 's1':
            value = sum(1 << ((n+amount) % 16) for n in state[3])
        else:
            assert label == 'top'
            value = TOP
        output_unary.append(value)
    out = []
    for (i, j), operation in zip(PAIRS, specs[state[0]]):
        if operation is None:
            value = rectangle(output_unary[i], output_unary[j])
        else:
            kind, source, rows, columns = operation
            if kind == 'same':
                value = same_source(unary[source],rows,columns)
            else:
                raw_pair=narrowed[source]
                if kind == 'transpose':
                    raw_pair=transpose_pair(raw_pair)
                else:
                    assert kind == 'direct'
                value = shift_pair(raw_pair, rows, columns)
        out.append(value)
    return tuple(out)


start = cover['m']['start']
domains = {start: (1,)*len(PAIRS)}
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
        if joined == previous:
            continue
        domains[target] = joined
        if target not in pending:
            queue.append(target)
            pending.add(target)
    updates += 1
    if updates % 10000 == 0:
        print(f'{updates} pair transfers, {len(domains)} states, {len(queue)} pending', flush=True)
checked = 0
for state, incoming in domains.items():
    for target in cover['successors'][state]:
        out = transfer(state, incoming, target)
        if out is not None:
            assert target in domains
            assert all((x & ~y) == 0 for x, y in zip(out, domains[target]))
        checked += 1
print(f'PASS: {len(PAIRS)} saved-pair fixpoint: {updates} transfers, {len(domains)} states, '
      f'{checked} checked edges; queue empty.', flush=True)
for mode, tail in (('R1', 'ST35'), ('R1', 'ST32'), ('R1', 'R34')):
    pair = PAIR_INDEX[f['NAMES'].index(mode), f['NAMES'].index(tail)]
    joined = 0
    for st, values in domains.items():
        if st[0] == 0xAC:
            joined |= values[pair]
    high = joined & rectangle(TOP ^ 31, TOP)
    print(f'AC {mode}>=5 paired {tail} values: '+
          ','.join(f'{n:X}' for n in f['bit_values'](projections(high)[1])), flush=True)
print('Positive pair members remain an overapproximation, not native preparation.', flush=True)
