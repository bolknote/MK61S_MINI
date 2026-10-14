#!/usr/bin/env python3
"""Candidate-only word transport through the previously computed ROM graph.

Run with runpy and a completed `cover` dictionary from analyze_dd0_inputs.py.
This reuses its control graph, which does NOT establish post-C8 reachability.
No negative conclusion follows from exhausting this candidate generator.
Only proved exact nibble copies are followed; arithmetic is not a copy.
Every printed route needs a separate exact path and keyboard check.
The now-working 12/C6/06 mantissa reader uses an increment, so this
unchanged-copy search cannot by itself describe its decoded output.
"""
from collections import deque
import json
from pathlib import Path
import subprocess
import runpy
from z3 import And, Or, sat, unsat

assert 'cover' in globals(), 'supply the existing completed control graph'
q = runpy.run_path(str(Path(__file__).with_name('ik1302_symbolic.py')))
State, execute, base, keys = (q[n] for n in
    ('State', 'execute_command', 'base_solver', 'arbitrary_keys'))
root = Path(__file__).resolve().parent


def variables(expr, cache):
    ident = expr.get_id()
    if ident not in cache:
        children = expr.children()
        cache[ident] = (frozenset((str(expr),)) if not children else
                       frozenset().union(*(variables(v, cache) for v in children)))
    return cache[ident]


transfers = {}
for ip in range(256):
    a = State(f'recovery_transport_{ip}')
    out = []
    b = execute(a, ip, *keys(f'recovery_transport_keys_{ip}'), emitted_outputs=out)
    if ip == 0x93:
        b = execute(b, 0x94, *keys('recovery_transport_93_94'))
    if ip == 0x12:
        b = execute(b, 0xC6, *keys('recovery_transport_12_C6'))
    sources = a.r[:36] + a.st[:36]
    targets = b.r[:36] + b.st[:36] + out
    by_name = {str(v): i for i, v in enumerate(sources)}
    p = base(a, ip)
    mapping = [[] for _ in sources]
    cache = {}
    for j, value in enumerate(targets):
        # Source support is only a speed-up; the solver proves each copy.
        for name in variables(value, cache) & by_name.keys():
            i = by_name[name]
            if value.eq(sources[i]):
                valid = True
            else:
                p.push()
                p.add(value != sources[i])
                valid = p.check() == unsat
                p.pop()
            if valid:
                mapping[i].append(j)
    transfers[ip] = mapping
    if ip % 32 == 31:
        print(f'proved transport copies for {ip+1}/256 ROM commands', flush=True)

native = json.loads(subprocess.check_output(['node', '-e',
    "const {run}=require('./tmp/ms-rom-reachability/probe_c8_payload.cjs');"
    "const {snapshot}=require('./tmp/ms-rom-reachability/paused_keyboard_state.cjs');"
    "console.log(JSON.stringify(snapshot(run('1.0234567E30').calc.ik1302)))"],
    cwd=root.parents[1], text=True))
starts = []
for st in cover['parents']:
    if st[0] != 0x35:
        continue
    a, p = cover['entry_solver'](st)
    for name in ('r', 'm', 'st'):
        p.add(*[v == n for v, n in zip(getattr(a, name), native[name])])
    p.add(*[getattr(a, name) == native[name]
            for name in ('s', 's1', 'l', 't', 'carry')])
    if p.check() == sat:
        starts.append(st)
print(f'{len(starts)} native-compatible scanner control contexts', flush=True)

def find_candidate(blocked=(), blocked_triples=(), blocked_patterns=(),
                   start_position=13, target='numeric-write'):
    # Remember only suffixes that are prefixes of a forbidden ROM path.
    # A single parent per control state is otherwise insufficient: it merges
    # keyboard-prefix correlations which the exact chip model rejects.
    patterns = {tuple(v) for v in (*blocked, *blocked_triples, *blocked_patterns)}
    prefixes = {()}
    for pattern in patterns:
        prefixes.update(pattern[:i] for i in range(1, len(pattern)))

    def advance(history, ip):
        extended = history + (ip,)
        if any(len(p) <= len(extended) and extended[-len(p):] == p for p in patterns):
            return None
        return max((p for p in prefixes if not p or extended[-len(p):] == p), key=len)

    # Original mantissa digit 2 is in R13 after the verified two shifts.
    # 0x100 is a beginning-of-path marker, never a ROM address. Prefix-only
    # filters must not exclude the same sequence after a later preparation.
    parents = {(st, start_position, advance(advance((), 0x100), st[0])): None for st in starts}
    pending = deque(parents)
    terminal = None
    while pending:
        node = pending.popleft()
        st, pos, history = node
        ip = st[0]
        dests = transfers[ip][pos]
        # Ignore the already understood, paired C9 program-buffer exchanges.
        reached = (ip == 0x35 and pos in (31,34)) if target == 'scanner-pc' else (
            ip in (0xD4, 0xE7, 0xBC) and any(j >= 72 for j in dests))
        if reached:
            terminal = node
            break
        for following in cover['successors'][st]:
            next_history = advance(history, following[0])
            if next_history is None:
                continue
            for dest in (j for j in dests if j < 72):
                nxt = (following, dest, next_history)
                if nxt not in parents:
                    parents[nxt] = node
                    pending.append(nxt)
        if len(parents) > 1500000:
            print('candidate budget reached, no exclusion claim', flush=True)
            break
    path = []
    if terminal is None:
        print(f'No pure-copy candidate in this reused graph: {len(parents)} nodes. '
              'NOT a proof of recovery impossibility.', flush=True)
    else:
        node = terminal
        while node is not None:
            path.append(node[:2])
            node = parents[node]
        path.reverse()
        print('CANDIDATE, not a keyboard protocol:', flush=True)
        print(' '.join(f'{st[0]:02X}[{"R" if pos < 36 else "ST"}{pos%36}]'
                       for st, pos in path), flush=True)
        print('Output nibble(s):', [j-72 for j in transfers[terminal[0][0]][terminal[1]]
                                    if j >= 72], flush=True)
    return path


candidate = find_candidate()
