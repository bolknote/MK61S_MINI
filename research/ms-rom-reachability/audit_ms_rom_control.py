#!/usr/bin/env python3
"""Recover all edges of the completed, C8-inclusive controller abstraction.

Positive paths in this graph are candidates, not native keyboard protocols.
This helper can reuse a live analyze_gates namespace without recomputation.
"""
from collections import defaultdict, deque


def graph(m):
    assert not m['queue'] and m['terminal'] is None
    assert m['args'].target == 'c7' and not m['args'].first_entry_lemmas
    successors = {}
    predecessors = defaultdict(set)
    for state in m['parents']:
        ip, sp, vector, selector, delta, r38, dr38, r26, types = state
        t = m['templates'][ip]
        kind, pushed, new_vector, delta_op, sp_deps, dr38_op = (
            t[4], t[5], t[6], t[9], t[10], t[13])
        key = (ip, tuple(sp[i] for i in sp_deps), vector, selector, delta,
               r38, dr38, r26, types)
        next_sp = (sp if kind == 'same' else sp[1:]+sp[:1] if kind == 'rotate'
                   else (0xC7, 0x13, sp[0]) if kind == 'push2'
                   else (pushed, sp[0], sp[1]))
        next_vector = vector if new_vector == 'preserve' else new_vector
        next_delta = ((delta+delta_op[1]) % 16 if delta is not None else None) \
            if delta_op[0] == 'add' else delta_op[1]
        next_dr38 = ((dr38+dr38_op[1]) % 16 if dr38 is not None else None) \
            if dr38_op[0] == 'add' else dr38_op[1]
        following = []
        for nxt, sel, m38, m26, typ in m['cache'][key]:
            target = (nxt, next_sp, next_vector, sel, next_delta,
                      m38, next_dr38, m26, typ)
            assert target in m['parents']
            following.append(target)
            predecessors[target].add(state)
        successors[state] = tuple(following)
    return successors, predecessors


def walk(successors, starts, stop=(), allowed=None):
    parents = dict.fromkeys(starts)
    queue = deque(parents)
    while queue:
        state = queue.popleft()
        if state[0] in stop:
            continue
        for target in successors[state]:
            if target not in parents and (allowed is None or allowed(state, target)):
                parents[target] = state
                queue.append(target)
    return parents


def path(parents, target):
    out = []
    while target is not None:
        out.append(target)
        target = parents[target]
    return out[::-1]


def report(m):
    successors, predecessors = graph(m)
    print('Completed graph:', len(successors), 'states,',
          sum(map(len, successors.values())), 'edges', flush=True)
    for ip in (0xD4, 0xD6, 0xC7, 0xE7, 0xA8, 0xC8, 0xC9, 0xBB, 0xBC):
        states = [st for st in successors if st[0] == ip]
        sources = sorted({pred[0] for st in states for pred in predecessors[st]})
        targets = sorted({nxt[0] for st in states for nxt in successors[st]})
        print(f'{ip:02X}: predecessors='+' '.join(f'{x:02X}' for x in sources)
              +'; successors='+' '.join(f'{x:02X}' for x in targets), flush=True)
    starts = [st for st in successors if st[0] == 0xC8]
    epoch = walk(successors, starts, stop=(0x7F,))
    print('C8 -> before/at 7F:', len(epoch), 'states;',
          ' '.join(f'{x:02X}' for x in sorted({st[0] for st in epoch})), flush=True)
    for ip in (0xBB, 0xBC, 0xD4):
        targets = [st for st in epoch if st[0] == ip]
        if targets:
            print(f'CANDIDATE {ip:02X}:', ' '.join(f'{st[0]:02X}' for st in path(epoch, targets[0])), flush=True)
    return successors, predecessors, epoch


def refine_mode_epoch(m, successors):
    """Overapproximate a C8 continuation entered with R2 >= 5, until 7F.

    This is a conditional continuation theorem, not a proof that every reset
    C8 entry has that mode. Exact per-edge checks carry the mode forward.
    All untracked fields and serial inputs remain arbitrary at every step.
    """
    from z3 import Or, sat, unsat
    q = m['q']
    finals, preserves, cache = {}, {}, {}
    starts = [st for st in successors if st[0] == 0xC8]
    reached = {st: set(range(5, 16)) for st in starts}
    queue, pending = deque(starts), set(starts)
    updates = 0
    while queue:
        state = queue.popleft()
        pending.remove(state)
        ip, sp, vector, selector, delta, r38, dr38, r26, types = state
        if ip == 0x7F:
            continue
        modes = tuple(sorted(reached[state]))
        a, addr, av, old = m['templates'][ip][:4]
        if ip not in finals:
            b = q['execute_command'](a, ip, *q['arbitrary_keys'](f'audit_mode_{ip}'))
            if ip == 0x93:
                b = q['execute_command'](b, 0x94, *q['arbitrary_keys']('audit_mode_93_94'))
            if ip == 0x12:
                b = q['execute_command'](b, 0xC6, *q['arbitrary_keys']('audit_mode_12_C6'))
            finals[ip] = b
            p = q['base_solver'](a, ip)
            p.add(b.r[2] != a.r[2])
            preserves[ip] = p.check() == unsat
        b = finals[ip]
        assert types is None
        key = (state, modes)
        if key not in cache:
            p = m['state_solver'](a, ip)
            if vector == 'diagonal': p.add(a.r[37] == a.r[40])
            elif vector is not None: p.add(av == vector)
            p.add(Or(*[a.s1 == n for n in selector]),
                  Or(*[a.r[38] == n for n in r38]),
                  Or(*[a.r[26] == n for n in r26]),
                  Or(*[a.r[2] == n for n in modes]),
                  *[v == n for v, n in zip(old, sp)])
            if delta is not None: p.add(a.s1-a.r[35] == delta)
            if dr38 is not None: p.add(a.r[38]-a.r[35] == dr38)
            out = {}
            for nxt in {st[0] for st in successors[state]}:
                p.push(); p.add(addr == nxt)
                outcome = p.check()
                assert outcome in (sat, unsat)
                if outcome == sat:
                    out[nxt] = modes if preserves[ip] else tuple(q['possible_values'](b.r[2], p, 17))
                p.pop()
            cache[key] = out
        for target in successors[state]:
            extra = set(cache[key].get(target[0], ())) - reached.get(target, set())
            if extra:
                reached.setdefault(target, set()).update(extra)
                if target not in pending:
                    pending.add(target); queue.append(target)
        updates += 1
        if updates % 1000 == 0:
            print('mode epoch', updates, 'updates,', len(reached), 'states,', len(queue), 'pending', flush=True)
    ips = sorted({st[0] for st in reached})
    print('R2>=5 C8 epoch:', len(reached), 'states;',
          ' '.join(f'{x:02X}' for x in ips), flush=True)
    print('Mode-changing instructions:',
          ' '.join(f'{x:02X}' for x in ips if not preserves.get(x, True)), flush=True)
    print('Terminals:', {f'{ip:02X}':sum(st[0] == ip for st in reached)
                        for ip in (0x7F, 0xBB, 0xBC, 0xD4)}, flush=True)
    return reached, cache, preserves


if __name__ == '__main__':
    import argparse
    import runpy
    import sys
    from pathlib import Path
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode-epoch', action='store_true',
                        help='also refine the C8 continuation by R2; still an overapproximation')
    options = parser.parse_args()
    sys.argv = ['analyze_gates.py', '--target', 'c7', '--r38', '--check-c8-invariants']
    m = runpy.run_path(str(Path(__file__).with_name('analyze_gates.py')))
    successors, _, _ = report(m)
    if options.mode_epoch:
        refine_mode_epoch(m, successors)
