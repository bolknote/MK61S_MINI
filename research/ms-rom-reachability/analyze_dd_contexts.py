#!/usr/bin/env python3
"""Project last-DD return contexts from a completed reset overapproximation.

The source fixpoint does not track R2: its absence from this report is not
evidence that a high or low mode is physically reachable in a context.
Only a DD assigning the requested R38 (4 by default) and continuing to
D4/D6 is considered. Selector9 supports inventory only, not the old
selector4-specific suffix/lifetime assertions.
"""
import argparse
import runpy
import sys
from pathlib import Path

from z3 import And, Or, ZeroExt, sat, unsat

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--selector', type=lambda s:int(s,16), choices=(4,9), default=4)
parser.add_argument('--check-marker-classes', action='store_true',
                    help='verify the marker0/1/F partition of D6/2F contexts')
parser.add_argument('--check-suffixes', action='store_true',
                    help='verify the exact return fragments and the closed DC/write lifetimes')
parser.add_argument('--probe-read-mode', action='store_true',
                    help='also explore the remaining D6/2F family with initial R2<5; a candidate is inconclusive')
parser.add_argument('--verbose', action='store_true', help='print each of the 113 projected contexts')
args = parser.parse_args()
if args.selector != 4 and (args.check_suffixes or args.probe_read_mode):
    parser.error('selector9 supports inventory only; use its separate lifetime checks')
sys.argv = ['analyze_gates.py', '--target', 'cd', '--r38', '--first-entry-lemmas']
m = runpy.run_path(str(Path(__file__).with_name('analyze_gates.py')))
assert not m['queue'] and m['terminal'] is None, 'a complete source fixpoint is required'
contexts = {}
for state in m['parents']:
    ip, sp, vector, selector, delta, r38, dr38, r26, types = state
    if ip != 0xDD:
        continue
    t = m['templates'][ip]
    a, addr, av, old = t[:4]
    p = m['state_solver'](a, ip)
    if vector == 'diagonal':
        p.add(a.r[37] == a.r[40])
    elif vector is not None:
        p.add(av == vector)
    p.add(Or(*[a.s1 == n for n in selector]), Or(*[a.r[38] == n for n in r38]))
    if delta is not None:
        p.add(a.s1-a.r[35] == delta)
    if dr38 is not None:
        p.add(a.r[38]-a.r[35] == dr38)
    p.add(Or(*[a.r[26] == n for n in r26]), *[v == n for v, n in zip(old, sp)])
    p.add(t[11] == args.selector)
    for exit_ip in (0xD4, 0xD6):
        p.push()
        p.add(addr == exit_ip)
        result = p.check()
        assert result in (sat, unsat)
        if result == sat:
            record = contexts.setdefault((exit_ip, sp), {'r26': set(), 'r35': set(), 'vectors': set()})
            for name, expr in [('r26', t[14]), ('r35', t[16][1])]:
                p.push()
                record[name].update(m['q']['possible_values'](expr, p, 17))
                p.pop()
            record['vectors'].add(vector)
        p.pop()
print(f'Projected {len(contexts)} DD/selector{args.selector:X} return contexts '
      'from the complete reset fixpoint', flush=True)
if args.verbose:
    for (exit_ip, sp), record in sorted(contexts.items()):
        print(f'{exit_ip:02X} stack='+','.join(f'{n:02X}' for n in sp)
              +' R26='+','.join(f'{n:X}' for n in sorted(record['r26']))
              +' R35='+','.join(f'{n:X}' for n in sorted(record['r35']))
              +' vectors='+','.join(sorted(str(v) if not isinstance(v, int) else f'{v:02X}'
                                          for v in record['vectors'])), flush=True)

families = {}
open_contexts = []
for (exit_ip, sp), record in contexts.items():
    top = sp[0]
    if exit_ip == 0xD6 and top == 0x2F:
        assert record['vectors'] == {0xFF}
        open_contexts.append((exit_ip, sp))
        label = 'open D6/2F'
    elif exit_ip == 0xD4 and top == 0x26:
        assert record['vectors'] == {0xFF}
        label = 'write D4/26'
    elif top == 0xDD:
        label = 'direct next DD'
    elif top == 0x93:
        assert sp[1] in (0xDD, 0xE5), (exit_ip, sp)
        label = '93 restoration then DD/E5'
    elif top in (0xAF, 0xC3, 0xCF):
        label = 'AF/C3/CF then DC'
    elif top in (0x76, 0xE5):
        label = '76/E5 then E6'
    elif exit_ip == 0xD4 and top == 0xA5:
        label = 'A5 then 1F'
    elif exit_ip == 0xD6 and top == 0xA7:
        label = 'A7 then E6'
    else:
        raise AssertionError(('unclassified DD return context', exit_ip, sp, record))
    families[label] = families.get(label, 0)+1
print('Context families:', dict(sorted(families.items())), flush=True)
expected_stacks = runpy.run_path(str(Path(__file__).with_name('analyze_dd_stack_lifetime.py')))['OPEN_STACKS']
if args.selector == 4:
    assert len(contexts) == 113 and len(open_contexts) == 10
    assert {sp for _, sp in open_contexts} == set(expected_stacks), 'last-DD stack seeds changed'

if args.check_marker_classes:
    read = {sp: contexts[(ip, sp)] for ip, sp in open_contexts}
    assert len(read) == 10
    assert all(record['r26'] <= {0, 1, 15} for record in read.values())
    ready = {sp for sp, record in read.items() if 1 in record['r26']}
    assert ready == {(0x2F, 0x6E, 0x08), (0x2F, 0x6E, 0x78)}
    for marker in (0, 1, 15):
        admitted = sorted(sp for sp, record in read.items() if marker in record['r26'])
        print(f'R26={marker:X} at DD/selector{args.selector:X}/D6/2F: '
              + ' '.join('/'.join(f'{v:02X}' for v in sp) for sp in admitted), flush=True)
    print('PASS: the ten D6/2F contexts have only marker0/1/F; marker1 '
          'requires stack 2F/6E/08 or 2F/6E/78. R2 is not tracked, '
          'so a high-mode seed is not asserted reachable.', flush=True)

if args.check_suffixes or args.probe_read_mode:
    root = Path(__file__).resolve().parent
    runpy.run_path(str(root / 'check_dd_return_suffixes.py'))
    lifetime = runpy.run_path(str(root / 'analyze_1f_lifetime.py'))
    dc = lifetime['run']('at-dc')
    assert dc['excluded'] and dc['terminals'] == {0xDE, 0xE6}
    byte = lambda lo, hi: ZeroExt(4, lo) | (ZeroExt(4, hi) << 4)
    write = lifetime['run']('dd-4', proved_type7_gate=True,
        seed_constraints=lambda a: And(byte(a.st[36], a.st[39]) == 0x26,
                                      byte(a.r[37], a.r[40]) == 0xFF))
    assert write['excluded'], 'D4/26 has not been excluded'
    print('PASS: all 103 other contexts close before the next R38 assignment. '
          'Any first C8 must have last-DD continuation DD->D6->2F, with '
          'vector FF at DD; no restriction on initial R2 was used.', flush=True)
    if args.probe_read_mode:
        # Keep the projected return triples, not merely top=2F. Otherwise
        # the seed invents old tags such as 77 that are absent from every
        # admitted last-DD/2F context. Later joins may still lose correlations.
        read = lifetime['run']('dd-6', low_mode=True, proved_type7_gate=True,
            seed_constraints=lambda a: And(byte(a.r[37], a.r[40]) == 0xFF,
                Or(*[And(*[byte(a.st[36+i], a.st[39+i]) == value
                            for i, value in enumerate(sp)]) for _, sp in open_contexts])))
        if read['excluded']:
            print('PASS: the remaining last DD must already have R2>=5; the '
                  'D6/2F continuation cannot raise a low mode and reach C8 '
                  'before another selector assignment.', flush=True)
        else:
            print('INCONCLUSIVE: low-mode D6/2F has not been excluded. Joined '
                  'per-address stack domains can combine different return '
                  'contexts; a printed graph path is not an exact execution.', flush=True)
elif args.selector == 4:
    print('Inventory only: run --check-suffixes to verify closure of the 103 '
          'non-D6/2F contexts; their number alone is not a reachability proof.', flush=True)
else:
    print('Inventory only. Selector4 lifetime exclusions are not automatically '
          'valid for selector9. R2 was not tracked in the source cover.', flush=True)
