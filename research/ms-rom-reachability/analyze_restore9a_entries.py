#!/usr/bin/env python3
"""Project sources of the particular high 9A restore roots, including returns."""
import runpy
from collections import defaultdict
from pathlib import Path

from z3 import And, Or, UGE, sat, unsat, substitute

root = Path(__file__).resolve().parent
if 'slice9a' not in globals():
    slice9a = runpy.run_path(str(root / 'analyze_restore9a_slice.py'))
cover = slice9a['cover']
m, q = cover['m'], cover['q']
address, stack, byte = (cover[n] for n in ('address', 'stack', 'byte'))
TARGETS = (0x9A, 0x98, 0x95, 0x93)
rows = {target: defaultdict(lambda: {'sp': set(), 'states': [], 'vectors': set()})
        for target in TARGETS}
executions = {}
contexts = {}


def context_at(state, b):
    """Keep the complete target context, not only its return-stack bytes."""
    if state not in contexts:
        a, p = cover['entry_solver'](state)
        contexts[state] = a, And(*p.assertions())
    a, expression = contexts[state]
    replacements = [(x, y) for name in ('r', 'm', 'st')
                    for x, y in zip(getattr(a, name), getattr(b, name))]
    replacements += [(getattr(a, name), getattr(b, name))
                     for name in ('s', 's1', 'l', 't', 'carry')]
    return substitute(expression, *replacements)


wanted = {0x9A: {state for state, _ in slice9a['roots'][0x9A]}}
for target in TARGETS:
    for state, following in cover['successors'].items():
        relevant = set(following) & wanted[target]
        if not relevant:
            continue
        ip = state[0]
        a, p = cover['entry_solver'](state)
        if ip not in executions:
            b = q['execute_command'](a, ip, *q['arbitrary_keys'](f'restore_entry_keys_{ip}'))
            if ip == 0x93:
                b = q['execute_command'](b, 0x94, *q['arbitrary_keys']('restore_entry_93_94'))
            if ip == 0x12:
                b = q['execute_command'](b, 0xC6, *q['arbitrary_keys']('restore_entry_12_C6'))
            executions[ip] = b
        b = executions[ip]
        high = {0x9A: b.r[1], 0x98: b.r[0], 0x95: b.st[0], 0x93: b.st[0]}[target]
        p.add(Or(*[context_at(nxt, b) for nxt in relevant]), UGE(high, 5))
        outcome = p.check()
        assert outcome in (sat, unsat)
        if outcome == sat:
            row = rows[target][ip]
            # Every output has the same stack transform for a given source.
            output_stacks = {nxt[1] for nxt in relevant}
            assert len(output_stacks) == 1
            row['sp'].update(output_stacks)
            row['states'].append(state)
            row['vectors'].add(state[2])
    sources = rows[target]
    print(f'Restore input {target:02X}:', flush=True)
    for ip, row in sorted(sources.items()):
        print(f'  {ip:02X} ({m["templates"][ip][4]}), {len(row["states"])} source states; '+
              'SP='+','.join('/'.join(f'{n:02X}' for n in sp) for sp in sorted(row['sp']))+
              '; input vectors='+','.join(str(v) for v in sorted(row['vectors'], key=str)), flush=True)
    if target != 0x93:
        predecessor = {0x9A: 0x98, 0x98: 0x95, 0x95: 0x93}[target]
        assert set(sources) == {predecessor}, (target, set(sources))
        wanted[predecessor] = set(sources[predecessor]['states'])
print('Positive entries are conservative local projections, not native states.', flush=True)
