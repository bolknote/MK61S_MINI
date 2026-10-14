#!/usr/bin/env python3
"""Find candidate live-tag returns to 77 before the first C7/C8.

This scans the completed conservative reset fixpoint, then checks each
candidate return edge in the exact symbolic command model. A printed prefix
through abstract states is not necessarily a feasible concrete path.
"""
import argparse
import runpy
import sys
from pathlib import Path

from z3 import And, Or, ZeroExt, sat, unsat

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--selector', type=lambda s:int(s,16),action='append',
                    help='output R38 value to inspect; defaults to 4 and 9')
parser.add_argument('--expect-excluded', action='store_true',
                    help='assert no requested selector can return with nonzero R26')
parser.add_argument('--expect-zero-marker', action='store_true',
                    help='assert every actual return to 77 has output R26=0, for all R38')
parser.add_argument('--first-entry-lemmas', action='store_true',
                    help='apply independently proved E6 and A2/A3 input invariants')
parser.add_argument('--expect-selector-cd', action='store_true',
                    help='assert every actual return to 77 has output R38 in {C,D}')
parser.add_argument('--expect-a3-cd', action='store_true',
                    help='assert every A3->77 has output R38 in {C,D} and R26=0')
args = parser.parse_args()
requested = args.selector or [4,9]
assert all(0 <= n < 16 for n in requested)
sys.argv = ['analyze_gates.py','--target','cd','--r38']
if args.first_entry_lemmas:sys.argv.append('--first-entry-lemmas')
m = runpy.run_path(str(Path(__file__).with_name('analyze_gates.py')))
assert not m['queue'] and m['terminal'] is None
parents,templates,q = m['parents'],m['templates'],m['q']


def byte(lo,hi):
    return ZeroExt(4,lo)|(ZeroExt(4,hi)<<4)


matches = {n:[] for n in requested}
return_domains = {}
a3_domains = {}
scanned = 0
for state in parents:
    ip,sp,vector,selector,delta,r38,dr38,r26,types = state
    template = templates[ip]
    is_return = sp[0] == 0x77 and template[4] == 'rotate'
    if not is_return and ip != 0xA3:
        continue
    if is_return:scanned += 1
    a,addr,av,old = template[:4]
    p = m['state_solver'](a,ip)
    if vector == 'diagonal':p.add(a.r[37] == a.r[40])
    elif vector is not None:p.add(av == vector)
    p.add(Or(*[a.s1 == n for n in selector]),Or(*[a.r[38] == n for n in r38]))
    if delta is not None:p.add(a.s1-a.r[35] == delta)
    if dr38 is not None:p.add(a.r[38]-a.r[35] == dr38)
    p.add(Or(*[a.r[26] == n for n in r26]),*[v == n for v,n in zip(old,sp)])
    if types is not None:
        for index,values in zip((32,35),types):
            p.add(Or(*[a.r[index] == n for n in values]))
    # Restrict the OUTPUT only: a returning command may write R38 or R26.
    # Merely seeing 77 in the bottom stack slot at entry 77 is not evidence
    # of a return; ordinary 7E->77 can coexist with such a stored tag.
    p.add(addr == 0x77)
    result = p.check()
    assert result in (sat,unsat), result
    if result == unsat:
        continue
    p.push();selectors = q['possible_values'](template[11],p,17);p.pop()
    for value in selectors:
        p.push();p.add(template[11] == value)
        p.push();markers = q['possible_values'](template[14],p,17);p.pop()
        domain_store = return_domains if is_return else a3_domains
        domain_store.setdefault(ip,{}).setdefault(value,set()).update(markers)
        if is_return and value in requested:
            p.push();p.add(template[14] != 0)
            result = p.check()
            assert result in (sat,unsat),result
            if result == sat:matches[value].append(state)
            p.pop()
        p.pop()
print(f'Checked {scanned} abstract states with an actual top-77 return operation',flush=True)
print('All return domains: source -> output R38 : output R26',flush=True)
for ip,domain in sorted(return_domains.items()):
    print(f'  {ip:02X}: '+', '.join(f'{selector:X}:{{'+','.join(f'{n:X}' for n in sorted(markers))+'}'
                                for selector,markers in sorted(domain.items())),flush=True)
print('A3->77 domains: output R38 : output R26',flush=True)
for ip,domain in sorted(a3_domains.items()):
    print(f'  {ip:02X}: '+', '.join(f'{selector:X}:{{'+','.join(f'{n:X}' for n in sorted(markers))+'}'
                                for selector,markers in sorted(domain.items())),flush=True)
for value,candidates in matches.items():
    print(f'return-77 candidates with selector {value:X} and nonzero R26: {len(candidates)}',flush=True)
    print('return sites:',sorted({f'{st[0]:02X}' for st in candidates}),flush=True)
    if not candidates:
        continue
    def lineage(state):
        path=[]
        while state is not None:
            path.append(state);state=parents[state]
        return list(reversed(path))
    chosen=min(candidates,key=lambda st:len(lineage(st)))
    path=lineage(chosen)
    expanded=[]
    for st in path:
        expanded.append(st[0])
        if st[0] == 0x93:expanded.append(0x94)
        if st[0] == 0x12:expanded.append(0xC6)
    expanded.append(0x77)
    print('abstract prefix (not a physical protocol):',
          ' '.join(f'{ip:02X}' for ip in expanded),flush=True)
    print('return state:',chosen,flush=True)
if args.expect_excluded:
    assert all(not candidates for candidates in matches.values()),matches
    print('PASS: no actual return to 77 has a requested selector and nonzero R26',flush=True)
if args.expect_zero_marker:
    assert return_domains, 'must include actual returns, not an empty scan'
    assert all(markers == {0} for domain in return_domains.values() for markers in domain.values()),return_domains
    print('PASS: every admitted actual return to 77 has R26=0, for every selector',flush=True)
if args.expect_selector_cd:
    assert return_domains, 'must include actual returns, not an empty scan'
    assert all(set(domain) <= {12,13} for domain in return_domains.values()),return_domains
    print('PASS: every admitted actual return to 77 has R38 in {C,D}, never 4 or 9',flush=True)
if args.expect_a3_cd:
    assert a3_domains, 'must include an admitted A3->77, not an empty scan'
    assert all(set(domain) <= {12,13} and all(markers == {0} for markers in domain.values())
               for domain in a3_domains.values()),a3_domains
    print('PASS: every admitted A3->77 has R38 in {C,D} and R26=0',flush=True)
