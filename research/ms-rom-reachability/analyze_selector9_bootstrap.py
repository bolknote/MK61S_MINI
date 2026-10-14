#!/usr/bin/env python3
"""Project the remaining selector-9 bootstrap into 77/6F from reset.

The source is a complete control-stack/vector/selector overapproximation.
R2 and numeric data are not tracked, so positive contexts are only candidates.
"""
import argparse
import runpy
import sys
from pathlib import Path

from z3 import And, Or, sat, unsat

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--verbose',action='store_true')
parser.add_argument('--check-invariants',action='store_true',
                    help='check the new zero-marker exclusion and 77 incoming edges; '
                    'the latter uses the independently completed type7 theorem')
args = parser.parse_args()
sys.argv = ['analyze_gates.py','--target','cd','--r38','--first-entry-lemmas']
m = runpy.run_path(str(Path(__file__).with_name('analyze_gates.py')))
assert not m['queue'] and m['terminal'] is None, 'complete reset cover required'


def entry_solver(state):
    ip,sp,vector,selector,delta,r38,dr38,r26,types = state
    a,addr,av,old = m['templates'][ip][:4]
    p = m['state_solver'](a,ip)
    if vector == 'diagonal':
        p.add(a.r[37]==a.r[40])
    elif vector is not None:
        p.add(av==vector)
    p.add(Or(*[a.s1==n for n in selector]),Or(*[a.r[38]==n for n in r38]),
          Or(*[a.r[26]==n for n in r26]),*[v==n for v,n in zip(old,sp)])
    if delta is not None:
        p.add(a.s1-a.r[35]==delta)
    if dr38 is not None:
        p.add(a.r[38]-a.r[35]==dr38)
    return a,p


def domain(p,expr):
    p.push()
    values = tuple(m['q']['possible_values'](expr,p,17))
    p.pop()
    return values


queries = {
    '7E with type 7': (0x7E,lambda a:a.r[35]==7),
    '7E with type 7 / selector 9': (0x7E,lambda a:And(a.r[35]==7,a.r[38]==9)),
    '7D with selector 9': (0x7D,lambda a:a.r[38]==9),
    '77 with selector 9': (0x77,lambda a:a.r[38]==9),
    '6D with selector 9 / marker 0': (0x6D,lambda a:And(a.r[38]==9,a.r[26]==0)),
    '6F with selector 9': (0x6F,lambda a:a.r[38]==9),
    '60 with selector 9 / marker 1': (0x60,lambda a:And(a.r[38]==9,a.r[26]==1)),
}
results = {}
for name,(wanted,condition) in queries.items():
    rows = []
    for state in m['parents']:
        if state[0] != wanted:
            continue
        a,p = entry_solver(state)
        p.add(condition(a))
        outcome = p.check()
        assert outcome in (sat,unsat)
        if outcome == unsat:
            continue
        row = {'state':state,'sp':state[1],'vector':state[2]}
        for field in (26,32,35,38):
            row[f'R{field}'] = domain(p,a.r[field])
        row['S1'] = domain(p,a.s1)
        rows.append(row)
    results[name] = rows
    print(name+': '+str(len(rows))+' contexts',flush=True)
    for field in ('R26','R32','R35','R38','S1'):
        print('  '+field+': '+','.join(f'{n:X}' for n in
              sorted({n for row in rows for n in row[field]})),flush=True)
    print('  stacks: '+' '.join('/'.join(f'{n:02X}' for n in sp)
          for sp in sorted({row['sp'] for row in rows})),flush=True)
    if args.verbose:
        for row in rows:
            print(' ',{k:v for k,v in row.items() if k!='state'},flush=True)

if args.check_invariants:
    for name in ('7E with type 7 / selector 9','77 with selector 9'):
        assert results[name], ('nonempty coarse family expected',name)
        assert all(0 not in row['R26'] for row in results[name]),name
    print('PASS: neither type7/selector9 at 7E nor selector9 at 77 can have '
          'R26=0, even in the untyped completed reset cover.',flush=True)
    # Complete source coverage in check_selector9_bootstrap.py establishes
    # that only 7E, A3, or a genuine stack return can enter 77 with selector 9.
    # We inspect the OUTPUT of each such edge, not just source input fields.
    admitted = []
    checked = 0
    for state in m['parents']:
        ip,sp = state[:2]
        t = m['templates'][ip]
        if ip not in (0x7E,0xA3) and not (sp[0]==0x77 and t[4]=='rotate'):
            continue
        a,p = entry_solver(state)
        p.add(t[1]==0x77,t[11]==9)
        if ip==0x7E:
            # Existing 258285-state complete proof; not inferred from this
            # new projection and not asserted for states after a C8 call.
            p.add(Or(a.r[35]!=7,a.r[26]==0))
        outcome = p.check()
        assert outcome in (sat,unsat)
        checked += 1
        if outcome==sat:
            admitted.append(state)
    assert not admitted,admitted
    print(f'PASS: {checked} possible 77 incoming contexts checked on output; '
          'none can enter 77 with selector 9, using the prior type7 theorem. '
          'Hence the hypothetical selector9/77 checkpoint has no reset path.',flush=True)

print('Projection completed. Positive rows are not native paths; all negative '
      'rows include arbitrary R2 and numeric data.',flush=True)
