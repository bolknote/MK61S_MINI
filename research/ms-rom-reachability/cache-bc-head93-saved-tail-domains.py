#!/usr/bin/env python3
"""Conservative saved-tail dataflow on the frozen COMPLETE reset cover.

All transfer aliases/constants are checked on the original arbitrary-key /
serial word semantics. Unknown operations yield TOP, never a guessed value.
Independent nibble domains do NOT prove joint/native packet reachability.
No old eager graph generator, emulator initialization, keys search or ROM /
state / return / IP repair. Both frozen word fusions are expanded.
"""
from collections import deque
from functools import reduce
from functools import lru_cache
from pathlib import Path
import runpy

from z3 import is_bv_value, sat, simplify, unsat

root = Path(__file__).resolve().parent
m = runpy.run_path(str(root / 'cache-bc-a3-cc-inlet-cut.py'))
r, w, q, states, edges = (m[n] for n in ('r', 'w', 'q', 'states', 'edges'))
positions = tuple(range(30, 36))
names = tuple(f'{group}{j}' for group in ('R', 'ST') for j in positions)
index = {name: j for j, name in enumerate(names)}
TOP = (1 << 16)-1


def fields(a):
    return [a.r[j] for j in positions]+[a.st[j] for j in positions]


def dependencies(expr):
    seen, leaves, todo = set(), set(), [expr]
    while todo:
        node = todo.pop(); ident = node.get_id()
        if ident in seen: continue
        seen.add(ident)
        if node.children(): todo.extend(node.children())
        else: leaves.add(str(node))
    return leaves


def values(p, expr):
    p.push(); out = q['possible_values'](expr, p, 17); p.pop()
    return sum(1 << n for n in out)


def bit_values(mask):
    return [n for n in range(16) if mask & (1 << n)]


def rotate(mask, n):
    n %= 16
    return ((mask << n) & TOP) | (mask >> (16-n))


def kind_domain(state):
    masks = []
    for selectors, delta in ((state[3], state[4]), (state[5], state[6])):
        if delta is not None: masks.append(sum(1 << ((n-delta) % 16) for n in selectors))
    result = TOP
    for mask in masks: result &= mask
    return result


def compile_transfers():
    destinations = {}
    for i, row in enumerate(edges):
        destinations.setdefault(states[i][0], set()).update(states[j][0] for j in row)
    specs, branches, checked, branch_bottom = {}, {}, 0, 0
    for code in range(256):
        label = f'head93_saved_tail_{code:02X}'
        a = q['State'](label); p = w['base'](a, code)
        b = m['original'](a, code, label)
        before, after = fields(a), fields(b); ops = []
        for expr in after:
            if is_bv_value(simplify(expr)):
                ops.append(('const', simplify(expr).as_long(), 0)); continue
            found = next((('copy', j, 0) for j, old in enumerate(before) if expr.eq(old)), None)
            if found is not None: ops.append(found); continue
            deps = dependencies(expr)
            candidates = [('copy', j, 0, old) for j, old in enumerate(before) if str(old) in deps]
            candidates += [('add', j, n, old+n) for j, old in enumerate(before)
                if str(old) in deps for n in (1, 15, 8)]
            candidates += [('s1', -1, n, a.s1+n) for n in (0, 1, 15)]
            # Constants not reduced by the expression simplifier are also
            # proved universally before they are used as domain transfers.
            assert p.check() == sat
            value = p.model().eval(expr, model_completion=True).as_long()
            candidates.append(('const', value, 0, q['N4'](value)))
            for name, source, amount, expected in candidates:
                p.push(); p.add(expr != expected); outcome = p.check(); p.pop()
                assert outcome in (sat, unsat)
                if outcome == unsat:
                    found = (name, source, amount); checked += 1; break
            ops.append(found or ('top', -1, 0))
        specs[code] = tuple(ops)
        deps = dependencies(w['ip'](b))
        relevant = [j for j, expr in enumerate(before) if str(expr) in deps]
        for destination in destinations.get(code, ()):
            local = w['base'](a, code); local.add(w['ip'](b) == destination)
            outcome = local.check(); assert outcome in (sat, unsat)
            if outcome == unsat:
                branches[code, destination] = (0,)*len(names); branch_bottom += 1
            else:
                masks = [TOP]*len(names)
                for j in relevant: masks[j] = values(local, before[j])
                branches[code, destination] = tuple(masks)
        if code % 64 == 63:
            print(f'PASS compiled original saved-tail transfers/branch masks through{code:02X}', flush=True)
    print('PASS universally checked nontrivial aliases/constants:', checked,
          '; explicit universally impossible IP branches:', branch_bottom, flush=True)
    return specs, branches


def fixed_point(specs, branches, blocked=frozenset()):
    graph = r['inlet']['g']['graph']
    assert len(states) == 52416 and sum(map(len, edges)) == 95731
    assert graph['metadata']['complete'] and graph['metadata']['pending'] == 0
    assert graph['metadata']['terminal'] is None and graph['indexes']['roots'] == [0]
    assert graph['metadata']['fusedCommands'] == {'93': ['93', '94'], '12': ['12', 'C6']}
    assert states[0][0] == 0 and all(a[8] is None for a in states)
    assert 0 not in blocked
    def transfer(i, incoming, j):
        if j in blocked: return None  # Independently proved COMPLETE bootstrap bottoms.
        narrowed = [x & y for x, y in zip(incoming, branches[states[i][0], states[j][0]])]
        narrowed[index['R35']] &= kind_domain(states[i])
        if not all(narrowed): return None
        result = []
        for operation, source, amount in specs[states[i][0]]:
            if operation == 'copy': value = narrowed[source]
            elif operation == 'add': value = rotate(narrowed[source], amount)
            elif operation == 'const': value = 1 << source
            elif operation == 's1': value = sum(1 << ((n+amount) % 16) for n in states[i][3])
            else:
                assert operation == 'top'; value = TOP
            result.append(value)
        result[index['R35']] &= kind_domain(states[j])
        return tuple(result) if all(result) else None
    domains = {0: (1,)*len(names)}  # Literal digital-reset R/ST tail fields.
    todo, pending = deque([0]), {0}; updates = 0
    while todo:
        i = todo.popleft(); pending.remove(i)
        for j in edges[i]:
            out = transfer(i, domains[i], j)
            if out is None: continue
            before = domains.get(j)
            joined = out if before is None else tuple(x | y for x, y in zip(before, out))
            if joined == before: continue
            domains[j] = joined
            if j not in pending: todo.append(j); pending.add(j)
        updates += 1
        if updates % 100000 == 0:
            print('dataflow updates', updates, 'classes', len(domains), 'pending', len(todo), flush=True)
    checked = 0
    for i, row in enumerate(edges):
        for j in row:
            checked += 1
            if i not in domains: continue  # Explicit bottom input, no execution.
            out = transfer(i, domains[i], j)
            if out is not None:
                assert j in domains and all(not (x & ~y) for x, y in zip(out, domains[j]))
    assert checked == 95731
    print('PASS saved-tail fixpoint:', updates, 'updates,', len(domains),
          'nonbottom classes, all95731 edges checked; queue empty.', flush=True)
    return domains, transfer


def report(domains):
    region = m['basis']['backward']({11376, 17324}, {0xE3})
    gateways = sorted(i for i in region if states[i][0] == 0xE3)
    assert len(gateways) == 41
    remaining = [i for i in gateways if i in domains
        and domains[i][index['ST31']] & ((1 << 2) | (1 << 3))
        and domains[i][index['ST34']] & (1 << 13)]
    print('E3 saved header admitted independently in', len(remaining), 'of41 source classes:', remaining)
    for code in (0xAC, 0xE3, 0xE4, 0xA3):
        selected = [i for i in domains if states[i][0] == code]
        print(f'ALL{code:02X} tail unary domains:', {name: bit_values(
            reduce(int.__or__, (domains[i][index[name]] for i in selected), 0))
            for name in ('ST31', 'ST32', 'ST34', 'ST35')})
    for i in (11376, 17324):
        print('A3 target', i, None if i not in domains else {name: bit_values(domains[i][index[name]])
            for name in ('R32', 'R35', 'ST31', 'ST34')})
    print('NOTE independent unary admission is NOT a joint SAT/native witness. '
          'Only a missing value/class would be a negative reachability theorem. '
          'No saved-counter25, Ms data origin, physical marker phase or safe '
          'exchange claim is made.', flush=True)
    return remaining


pairs = tuple((i, j) for i in range(len(names)) for j in range(i+1, len(names)))
pair_index = {pair: i for i, pair in enumerate(pairs)}
PAIR_TOP = (1 << 256)-1


@lru_cache(maxsize=100000)
def rectangle(rows, columns):
    return sum(columns << (16*n) for n in bit_values(rows))


@lru_cache(maxsize=100000)
def projections(mask):
    rows = sum(1 << n for n in range(16) if (mask >> (16*n)) & TOP)
    columns = mask | (mask >> 128)
    columns |= columns >> 64; columns |= columns >> 32; columns |= columns >> 16
    return rows, columns & TOP


@lru_cache(maxsize=100000)
def transpose(mask):
    rows, columns = projections(mask)
    if mask == rectangle(rows, columns): return rectangle(columns, rows)
    return sum(1 << (16*j+i) for i in range(16) for j in range(16)
               if mask & (1 << (16*i+j)))


@lru_cache(maxsize=100000)
def shifted(mask, rows, columns):
    rows %= 16; columns %= 16
    if rows:
        bits = 16*rows
        mask = ((mask << bits) & PAIR_TOP) | (mask >> (256-bits))
    if columns:
        low = rectangle(TOP, (1 << (16-columns))-1)
        mask = ((mask & low) << columns) | ((mask & (PAIR_TOP ^ low)) >> (16-columns))
    return mask


def pair_bitops_check():
    # Every singleton (all256 ordered pairs) and all independent rectangles
    # of the representative unary masks validate the transport orientation.
    for i in range(16):
        for j in range(16):
            mask = 1 << (16*i+j)
            assert transpose(mask) == 1 << (16*j+i)
            for x, y in ((0, 0), (1, 15), (8, 8), (15, 1)):
                assert shifted(mask, x, y) == 1 << (16*((i+x) % 16)+(j+y) % 16)
    for rows in (0, 1, 7, 31, 255, 256, TOP):
        for columns in (0, 1, 7, 31, 255, 256, TOP):
            mask = rectangle(rows, columns)
            assert projections(mask) == ((rows, columns) if rows and columns else (0, 0))
            assert transpose(mask) == rectangle(columns, rows)
    print('PASS pair bitset transpose/projections/mod16 transport unit checks.', flush=True)


def pair_fixed_point(specs, branches, unary):
    def alias(operation, state):
        name, source, amount = operation
        if name in ('copy', 'add'): return source, amount
        if name == 's1' and state[4] is not None:
            # Literal core relation: S1=R35+delta mod16. It permits an
            # exact alias here, not an independent selector Cartesian set.
            return index['R35'], (amount+state[4]) % 16
        return None
    def transfer(i, incoming, j):
        narrowed = [x & y for x, y in zip(unary[i], branches[states[i][0], states[j][0]])]
        narrowed[index['R35']] &= kind_domain(states[i])
        if not all(narrowed): return None
        current = list(incoming); changed = True
        while changed:
            changed = False
            for k, (x, y) in enumerate(pairs):
                mask = current[k] & rectangle(narrowed[x], narrowed[y])
                if not mask: return None
                current[k] = mask
                rows, columns = projections(mask)
                if rows != narrowed[x] or columns != narrowed[y]:
                    narrowed[x], narrowed[y] = rows, columns; changed = True
        ops = specs[states[i][0]]; out_unary = []
        for name, source, amount in ops:
            if name == 'copy': value = narrowed[source]
            elif name == 'add': value = rotate(narrowed[source], amount)
            elif name == 'const': value = 1 << source
            elif name == 's1':
                if states[i][4] is not None:
                    value = rotate(narrowed[index['R35']], amount+states[i][4])
                else: value = sum(1 << ((n+amount) % 16) for n in states[i][3])
            else:
                assert name == 'top'; value = TOP
            out_unary.append(value)
        out_unary = [x & y for x, y in zip(out_unary, unary[j])]
        if not all(out_unary): return None
        aliases = [alias(op, states[i]) for op in ops]; output = []
        for x, y in pairs:
            left, right = aliases[x], aliases[y]
            if left is None or right is None:
                mask = rectangle(out_unary[x], out_unary[y])
            elif left[0] == right[0]:
                mask = sum(1 << (16*((n+left[1]) % 16)+(n+right[1]) % 16)
                    for n in bit_values(narrowed[left[0]]))
            else:
                key = (left[0], right[0])
                mask = (current[pair_index[key]] if key in pair_index else
                        transpose(current[pair_index[key[::-1]]]))
                mask = shifted(mask, left[1], right[1])
            mask &= rectangle(out_unary[x], out_unary[y])
            if not mask: return None
            output.append(mask)
        return tuple(output)
    domains = {0: (1,)*len(pairs)}
    todo, pending = deque([0]), {0}; updates = 0
    while todo:
        i = todo.popleft(); pending.remove(i)
        for j in edges[i]:
            if j not in unary: continue
            out = transfer(i, domains[i], j)
            if out is None: continue
            before = domains.get(j)
            joined = out if before is None else tuple(x | y for x, y in zip(before, out))
            if joined == before: continue
            domains[j] = joined
            if j not in pending: todo.append(j); pending.add(j)
        updates += 1
        if updates % 50000 == 0:
            print('pair updates', updates, 'classes', len(domains), 'pending', len(todo), flush=True)
    checked = 0
    for i, row in enumerate(edges):
        for j in row:
            checked += 1
            if i not in domains or j not in unary: continue
            out = transfer(i, domains[i], j)
            if out is not None:
                assert j in domains and all(not (x & ~y) for x, y in zip(out, domains[j]))
    assert checked == 95731
    print('PASS saved-tail66-pair fixpoint:', updates, 'updates,', len(domains),
          'nonbottom classes, all95731 edges checked; queue empty.', flush=True)
    return domains


def pair_report(domains):
    region = m['basis']['backward']({11376, 17324}, {0xE3})
    gateways = sorted(i for i in region if states[i][0] == 0xE3)
    wanted = (1 << (16*2+13)) | (1 << (16*3+13))
    k = pair_index[index['ST31'], index['ST34']]
    remaining = [i for i in gateways if i in domains and domains[i][k] & wanted]
    print('PAIR savedTYPE2/3-KINDD admitted in', len(remaining), 'of41 E3 source classes:', remaining)
    for i in (11376, 17324):
        k = pair_index[index['R32'], index['R35']]
        mask = domains[i][k] if i in domains else 0
        print('PAIR A3 target', i, 'allowed TYPE2/3-KINDD:',
            [typ for typ in (2, 3) if mask & (1 << (16*typ+13))])
    print('NOTE pair admission is still a conservative candidate, NOT a '
          'joint full-packet SAT/native key witness. TOP arithmetic and '
          'untracked saved-counter25 remain explicit.', flush=True)
    return remaining


if __name__ == '__main__':
    r['inlet']['immutable_reference']()
    _, blocked = m['bootstrap_cut']()
    assert len(blocked) == 57
    print('PASS dependency: all57 COMPLETE headDD bootstrap bottoms rechecked; '
          'joined into the saved-tail dataflow, never guessed from its positive candidates.', flush=True)
    specs, branches = compile_transfers()
    domains, _ = fixed_point(specs, branches, frozenset(blocked))
    report(domains)
    pair_bitops_check()
    pair_report(pair_fixed_point(specs, branches, domains))
    r['inlet']['immutable_reference']()
    print('PASS frozen-cover saved-tail audit; no native experiment or reference edits.', flush=True)
