#!/usr/bin/env python3
"""Conservative lifetime of a selector 4 or 9 assigned by 1F or DD.

This is a control/data-flow fixpoint, not a search through user programs.
Stop BEFORE every following R38 assignment, even when it would assign 4 again.
Joined per-address nibble/stack-byte domains deliberately lose correlations.
An exclusion is conditional on the specified entry and prior reset/first-entry
invariants; a reported candidate is not a calculator-side protocol.
Selector4 is the unchanged default. The selector9/bootstrap option checks
60 with marker1, high R2, and equal counter digits before the next writer.
"""
import argparse
import runpy
from collections import deque
from pathlib import Path

from z3 import And, Or, UGE, ULT, ZeroExt, sat, unsat

q = runpy.run_path(str(Path(__file__).with_name('ik1302_symbolic.py')))
State, execute, base, keys = (q[n] for n in
    ('State', 'execute_command', 'base_solver', 'arbitrary_keys'))
WRITERS = {0x1F, 0x59, 0x5C, 0x5F, 0x6C, 0x7C,
           0x85, 0xB3, 0xCD, 0xDD, 0xDE, 0xE6}
# Full reset/first-entry fixpoint in analyze_gates.py, not local assumptions
# about arbitrary chip states. Check with --check-1f-invariants there.
PRIOR_SELECTOR_DOMAINS = {0xF8: (7,8), 0xFC: (7,8,14), 0x68: (7,8,14)}
R_FIELDS = (2, 25, 26, 29, 31, 32, 34, 35)
NAMES = tuple(f'R{i}' for i in R_FIELDS) + (
    'S', 'S1', 'vector', 'S1-R35', 'stack0', 'stack1', 'stack2')


def byte(lo, hi):
    return ZeroExt(4, lo) | (ZeroExt(4, hi) << 4)


def fields(a):
    return ([a.r[i] for i in R_FIELDS] + [a.s, a.s1,
            byte(a.r[37], a.r[40]), a.s1-a.r[35]]
            + [byte(a.st[36+i], a.st[39+i]) for i in range(3)])


def constrain(p, expressions, domains):
    for expr, values in zip(expressions, domains):
        if len(values) < 2**expr.size():
            p.add(Or(*[expr == v for v in values]))


def domain(p, expression):
    p.push()
    result = frozenset(q['possible_values'](expression, p, 2**expression.size()+1))
    p.pop()
    return result


_TEMPLATE_CACHE = None


def compile_templates():
    global _TEMPLATE_CACHE
    if _TEMPLATE_CACHE is not None:
        return _TEMPLATE_CACHE
    templates = {}
    pushed_values = {0}
    for ip in range(256):
        a = State(f'lifetime_{ip}')
        b = execute(a, ip, *keys(f'lifetime_keys_{ip}'))
        old, new = fields(a), fields(b)
        p = base(a, ip)
        if ip == 0x93:
            p.push()
            p.add(byte(b.r[36], b.r[39]) != 0x94)
            assert p.check() == unsat
            p.pop()
            # Preserve the relation S=old R40 across this unconditional pair.
            # Original 93 leaves the address stack unchanged.
            p.push()
            p.add(~And(*[x == y for x, y in zip(new[-3:], old[-3:])]))
            assert p.check() == unsat
            p.pop()
            b = execute(b, 0x94, *keys('lifetime_keys_93_94'))
            new = fields(b)
        pushed = (ip & 0xF0) | ((ip+1) & 15)
        stack_forms = [('same', old[-3:]), ('rotate', old[-2:]+old[-3:-2]),
                       ('push', [pushed]+old[-3:-1])]
        for label, expected in stack_forms:
            p.push()
            p.add(~And(*[x == y for x, y in zip(new[-3:], expected)]))
            valid = p.check() == unsat
            p.pop()
            if valid:
                if label == 'push':
                    pushed_values.add(pushed)
                break
        else:
            raise AssertionError(f'unclassified stack at {ip:02X}')
        copies = []
        for index, expr in enumerate(new[:-3]):
            # Syntactic matches need no solver calls. Other dependencies are
            # projected by Z3 rather than guessed from the source formula.
            copies.append(next((j for j, source in enumerate(old)
                                if expr.eq(source)), None))
        addr = byte(b.r[36], b.r[39])
        templates[ip] = a, b, old, new, addr, copies, label, pushed
        if ip % 64 == 63:
            print(f'compiled {ip+1}/256', flush=True)

    assert not ({0x1F, 0x60, 0x6D, 0xC8} & pushed_values)
    _TEMPLATE_CACHE = templates, pushed_values
    return _TEMPLATE_CACHE


def run(entry, low_mode=False, limit=5000, details=False, seed_constraints=None,
        proved_type7_gate=False, selector_value=4, bootstrap=False):
    assert selector_value in (4,9)
    assert not bootstrap or selector_value==9
    templates, pushed_values = compile_templates()
    # The store entry constrains only the A5 state
    # supplied by the X->P helper, not the rest of the chip or ring contents.
    sequence = ([0xDD] if entry.startswith('dd') else
                [int(entry[3:], 16)] if entry.startswith('at-') else
                {'ab': [0xAB, 0xA5, 0x1F], 'store': [0xA5, 0x1F],
                 'format': [0x4F, 0x1F], 'arbitrary': [0x1F]}[entry])
    if entry == 'dd-1':
        # Exact forced double pass. Expanding it before projection preserves
        # the nested return 93 and prevents a false jump to an unrelated tag.
        # Every edge is re-proved below, not assumed as a path restriction.
        sequence = [int(v,16) for v in
                    'DD D1 91 92 93 94 95 98 9A 93 94 95 98 9A'.split()]
    a = State('lifetime_entry')
    p = base(a, sequence[0])
    p.add(Or(a.r[41] == 0, a.r[41] == 15))
    constrain(p, fields(a)[-3:], [pushed_values]*3)
    if low_mode:
        p.add(ULT(a.r[2], 5))
    if entry.startswith('at-'):
        p.add(a.r[38] == selector_value)
    elif entry.startswith('dd'):
        p.add(a.r[0] == (selector_value-1)%16)
        if entry != 'dd':
            p.add(a.s1 == int(entry.split('-')[1],16))
    elif entry == 'ab':
        p.add(a.r[32] == (selector_value-8)%16, UGE(a.r[35], 7))
    elif entry == 'store':
        p.add(a.r[32] == (selector_value-8)%16, a.r[35] == 4)
    else:
        p.add(a.r[35] == (selector_value-8)%16)
    if seed_constraints is not None:
        p.add(seed_constraints(a))
    b = a
    for i, ip in enumerate(sequence):
        b = execute(b, ip, *keys(f'lifetime_entry_keys_{i}'))
        if entry == 'dd-1':
            expected = sequence[i+1] if i+1 < len(sequence) else 0xD2
            p.push()
            p.add(~And(byte(b.r[36],b.r[39]) == expected,b.r[38] == selector_value))
            assert p.check() == unsat, f'DD-1 prefix is not forced at {ip:02X}'
            p.pop()
        if i+1 < len(sequence):
            p.add(byte(b.r[36], b.r[39]) == sequence[i+1])
    p.add(b.r[38] == selector_value)
    assert p.check() == sat, 'empty seed'

    states, parents = {}, {}
    queue, pending = deque(), set()
    terminals = set()
    bootstrap_hits = set()
    starts = []

    def merge(ip, incoming, parent):
        old = states.get(ip)
        joined = incoming if old is None else tuple(x | y for x, y in zip(old, incoming))
        if old == joined:
            return
        states[ip] = joined
        if ip not in parents:
            parents[ip] = parent
        if ip not in pending:
            queue.append(ip)
            pending.add(ip)

    final_addr = byte(b.r[36], b.r[39])
    for ip in domain(p, final_addr):
        starts.append(ip)
        p.push()
        p.add(final_addr == ip)
        merge(ip, tuple(domain(p, expr) for expr in fields(b)), None)
        p.pop()

    updates = 0
    edges = set()
    while queue and updates < limit:
        ip = queue.popleft()
        pending.remove(ip)
        values = states[ip]
        if ip in WRITERS or ip in (0xC7, 0xC8):
            terminals.add(ip)
            continue
        a, b, old, new, addr, copies, kind, pushed = templates[ip]
        p = base(a, ip)
        p.add(a.r[38] == selector_value, Or(a.r[41] == 0, a.r[41] == 15))
        if ip in PRIOR_SELECTOR_DOMAINS:
            p.add(Or(*[a.r[38] == n for n in PRIOR_SELECTOR_DOMAINS[ip]]))
        constrain(p, old, values)
        # Prior reset/first-C7/C8 fixpoint: A3's vector class and the only
        # possible first entry into either primitive (60->C8).
        if ip == 0xA3:
            p.add(Or(a.r[37] == a.r[40], *[
                byte(a.r[37], a.r[40]) == v for v in (0x90, 0x93, 0xCC, 0xD3, 0xD8)]))
        if proved_type7_gate and ip == 0x7E:
            # Independent completed reset proof: analyze_gates.py --target
            # type7 --r38 --types --first-entry-lemmas --limit 400000:
            # 258285 states, empty queue. Never use the new lifetime result
            # to justify the same invariant in its own source analysis.
            p.add(Or(a.r[35] != 7, a.r[26] == 0))
        p.add(addr != 0xC7)
        if ip != 0x60:
            p.add(addr != 0xC8)
        if bootstrap and ip==0x60:
            p.push()
            p.add(a.r[26]==1,UGE(a.r[2],5),a.r[25]==a.r[31])
            outcome = p.check()
            assert outcome in (sat,unsat)
            if outcome==sat:
                bootstrap_hits.add(ip)
            p.pop()
        for nxt in domain(p, addr):
            p.push()
            p.add(addr == nxt)
            # A preserving assignment can still be narrowed by the selected
            # branch (e.g. 8D->4F implies S1>=A). Reusing its entire input
            # domain here creates avoidable, incompatible 4F exits.
            result = [values[j] if j is not None and len(values[j])==1 else domain(p, expr)
                      for expr, j in zip(new[:-3], copies)]
            stack = (values[-3:] if kind == 'same' else values[-2:]+values[-3:-2]
                     if kind == 'rotate' else (frozenset([pushed]),)+values[-3:-1])
            if kind == 'rotate':
                stack = tuple(v if len(v)==1 else domain(p, expr)
                              for v,expr in zip(stack,new[-3:]))
            merge(nxt, tuple(result)+stack, ip)
            edges.add((ip, nxt))
            p.pop()
        updates += 1
        if updates % 100 == 0:
            print(f'{updates} transfers; {len(states)} addresses; {len(queue)} pending', flush=True)

    print(f'{entry}, selector={selector_value:X}, low_mode={low_mode}: {updates} transfers, {len(states)} addresses, '
          f'{len(queue)} pending', flush=True)
    print('terminals:', ' '.join(f'{ip:02X}' for ip in sorted(terminals)), flush=True)
    # This path is through the joined control-flow graph. It may combine
    # incompatible data domains and must be checked by exact path execution.
    if 0xC8 in terminals:
        predecessors = {ip: None for ip in starts}
        path_queue = deque(starts)
        while path_queue and 0xC8 not in predecessors:
            ip = path_queue.popleft()
            for nxt in sorted(y for x,y in edges if x==ip):
                if nxt not in predecessors:
                    predecessors[nxt] = ip
                    path_queue.append(nxt)
        route = []
        ip = 0xC8
        while ip is not None:
            route.append(ip)
            ip = predecessors[ip]
        expanded = []
        for ip in sequence+list(reversed(route)):
            expanded.append(ip)
            if ip == 0x93:
                expanded.append(0x94)
        print('joined-graph candidate (not an exact path):',
              ' '.join(f'{ip:02X}' for ip in expanded), flush=True)
    for ip in (0x07, 0x77, 0x6D, 0x60, 0xC8):
        if ip in states and details:
            print(f'{ip:02X}:', {name: sorted(v) for name, v in zip(NAMES, states[ip])
                                 if not name.startswith('stack')}, flush=True)
    complete = not queue
    excluded = complete and not ({0xC7, 0xC8} & terminals) and not bootstrap_hits
    if bootstrap:
        print('selector9/60 with marker1, high R2, and equal counters: '+
              ('CANDIDATE' if bootstrap_hits else 'absent'),flush=True)
    print('INCOMPLETE' if not complete else 'FIXPOINT: excluded for this entry family'
          if excluded else 'FIXPOINT: abstract candidate, not a physical protocol', flush=True)
    return {'complete': complete, 'excluded': excluded, 'states': states,
            'terminals': terminals, 'edges': edges, 'updates': updates,
            'bootstrap_hits': bootstrap_hits}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--entry', choices=['ab', 'store', 'format', 'arbitrary','dd','at-d2','at-dc']+
                        [f'dd-{n:x}' for n in range(16)], default='ab')
    parser.add_argument('--low-mode', action='store_true', help='require R2<5 at the specified entry')
    parser.add_argument('--proved-type7-gate', action='store_true',
                        help='use the independently completed first-entry type7 exclusion at 7E')
    parser.add_argument('--limit', type=int, default=5000)
    parser.add_argument('--expect-excluded', action='store_true')
    parser.add_argument('--details', action='store_true', help='print projected gate domains')
    parser.add_argument('--selector',type=lambda s:int(s,16),choices=(4,9),default=4,
                        help='assigned R38 selector; 4 preserves the original proof setup')
    parser.add_argument('--bootstrap',action='store_true',
                        help='with selector9, also search for 60/R26=1/R2>=5/R25=R31')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--all-dd', action='store_true', help='classify all sixteen DD exit selectors')
    group.add_argument('--closed-dd', action='store_true',
                       help='check the fourteen closed DD exit selectors, excluding D4/D6')
    args = parser.parse_args()
    if args.bootstrap and args.selector!=9:
        parser.error('--bootstrap requires --selector 9')
    entries = ([f'dd-{n:x}' for n in range(16) if not args.closed_dd or n not in (4,6)]
               if args.all_dd or args.closed_dd else [args.entry])
    for entry in entries:
        report = run(entry, args.low_mode, args.limit, args.details,
                     proved_type7_gate=args.proved_type7_gate,
                     selector_value=args.selector,bootstrap=args.bootstrap)
        if args.expect_excluded:
            assert report['excluded'], 'entry family was not excluded'
