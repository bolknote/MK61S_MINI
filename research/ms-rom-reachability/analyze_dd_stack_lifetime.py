#!/usr/bin/env python3
"""Last-DD lifetime with exact three-byte return stacks in every state key.

Numeric domains are still joined, so a candidate needs exact validation.
All execution uses unchanged IK1302 ROM and arbitrary per-tick keys/ring.
Prior first-entry facts are explicit below; this is not a reset search.
"""
import argparse
import runpy
from collections import deque
from pathlib import Path

from z3 import And, Not, Or, UGE, ULT, ZeroExt, sat, unsat

OPEN_STACKS = tuple((0x2F, int(a, 16), int(b, 16)) for a, b in
    (item.split('/') for item in
     '6E/08 6E/78 93/E5 AC/72 AC/93 AC/9A AC/AC AC/D6 AC/DD DD/E5'.split()))
_MODEL = None


def model():
    global _MODEL
    if _MODEL is None:
        _MODEL = runpy.run_path(str(Path(__file__).with_name('analyze_1f_lifetime.py')))
    return _MODEL


def byte(lo, hi):
    return ZeroExt(4, lo) | (ZeroExt(4, hi) << 4)


def address(a):
    return byte(a.r[36], a.r[39])


def stack(a):
    return [byte(a.st[36+i], a.st[39+i]) for i in range(3)]


def prior(p, a, ip, type7, selector_value=4, selector9_gate=False):
    m = model()
    p.add(a.r[38] == selector_value, Or(a.r[41] == 0, a.r[41] == 15))
    if selector9_gate and selector_value == 9 and ip == 0x77:
        # Independent complete incoming-edge proof in
        # analyze_selector9_bootstrap.py --check-invariants.
        p.add(False)
    if ip in m['PRIOR_SELECTOR_DOMAINS']:
        p.add(Or(*[a.r[38] == n for n in m['PRIOR_SELECTOR_DOMAINS'][ip]]))
    if ip == 0xA3:
        p.add(Or(a.r[37] == a.r[40], *[byte(a.r[37], a.r[40]) == n
                 for n in (0x90, 0x93, 0xCC, 0xD3, 0xD8)]))
    if type7 and ip == 0x7E:
        # Independent, completed 258285-state reset proof, not a result of
        # the lifetime analysis being performed here.
        p.add(Or(a.r[35] != 7, a.r[26] == 0))


def seed_solver(a, sp, mode, selector_value=4, exit_ip=0xD6, vectors=(0xFF,)):
    assert exit_ip in (0xD4, 0xD6)
    p = model()['base'](a, 0xDD)
    p.add(a.s1 == exit_ip-0xD0, a.r[0] == (selector_value-1)%16,
          Or(a.r[41] == 0, a.r[41] == 15),
          *[v == n for v, n in zip(stack(a), sp)])
    if None not in vectors:
        p.add(Or(*[a.r[37] == a.r[40] if value == 'diagonal'
                   else byte(a.r[37], a.r[40]) == value for value in vectors]))
    if mode == 'low':
        p.add(ULT(a.r[2], 5))
    elif mode == 'high':
        p.add(UGE(a.r[2], 5))
    return p


def seed_specs(starts, seed_contexts):
    return ([(0xD6, tuple(sp), (0xFF,)) for sp in starts]
            if seed_contexts is None else list(seed_contexts))


def bootstrap_condition(a):
    return And(a.r[38] == 9, a.r[26] == 1, UGE(a.r[2], 5),
               a.r[25] == a.r[31])


def run(mode='low', limit=10000, complete=False, type7=True, starts=OPEN_STACKS,
        verbose=True, selector_value=4, bootstrap=False, seed_contexts=None,
        selector9_gate=False):
    assert selector_value in (4, 9)
    assert not bootstrap or selector_value == 9
    m = model()
    templates, _ = m['compile_templates']()
    domains, edges, roots = {}, {}, set()
    queue, pending = deque(), set()
    terminals = set()
    found = None

    def merge(key, values):
        old = domains.get(key)
        joined = values if old is None else tuple(a | b for a, b in zip(old, values))
        if old == joined:
            return
        domains[key] = joined
        if key not in pending:
            pending.add(key)
            queue.append(key)

    specs = seed_specs(starts, seed_contexts)
    for number, (exit_ip, sp, vectors) in enumerate(specs):
        a = m['State'](f'stack_seed_{number}')
        p = seed_solver(a, sp, mode, selector_value, exit_ip, vectors)
        assert p.check() == sat, ('empty seed', sp, mode)
        b = m['execute'](a, 0xDD, *m['keys'](f'stack_seed_keys_{number}'))
        p.push()
        p.add(~And(address(b) == exit_ip, b.r[38] == selector_value,
                   *[v == n for v, n in zip(stack(b), sp)]))
        assert p.check() == unsat, 'DD seed must enter its specified exit with its stack intact'
        p.pop()
        key = (exit_ip, tuple(sp))
        roots.add(key)
        merge(key, tuple(m['domain'](p, expr) for expr in m['fields'](b)[:-3]))

    updates = 0
    while queue and updates < limit:
        key = queue.popleft()
        pending.remove(key)
        ip, sp = key
        if ip in m['WRITERS'] or ip in (0xC7, 0xC8):
            terminals.add(ip)
            if ip in (0xC7, 0xC8):
                found = found or key
                if not complete:
                    break
            continue
        a, b, old, new, addr, copies, kind, pushed = templates[ip]
        p = m['base'](a, ip)
        prior(p, a, ip, type7, selector_value, selector9_gate)
        values = domains[key] + tuple(frozenset([n]) for n in sp)
        m['constrain'](p, old, values)
        # Independently proved first-entry source restriction.
        p.add(addr != 0xC7)
        if ip != 0x60:
            p.add(addr != 0xC8)
        if bootstrap and ip == 0x60:
            p.push()
            p.add(bootstrap_condition(a))
            outcome = p.check()
            assert outcome in (sat, unsat)
            if outcome == sat:
                found = found or key
            p.pop()
            if found and not complete:
                break
        next_sp = (sp if kind == 'same' else sp[1:]+sp[:1] if kind == 'rotate'
                   else (pushed,)+sp[:2])
        for nxt in sorted(m['domain'](p, addr)):
            p.push()
            p.add(addr == nxt)
            result = tuple(values[j] if j is not None and len(values[j]) == 1
                           else m['domain'](p, expr) for expr, j in zip(new[:-3], copies))
            p.pop()
            target = (nxt, next_sp)
            edges.setdefault(key, set()).add(target)
            merge(target, result)
        updates += 1
        if verbose and updates % 100 == 0:
            print(f'{updates} transfers; {len(domains)} exact-stack contexts; '
                  f'{len(queue)} pending', flush=True)

    path = None
    if found is not None:
        predecessors = {root: None for root in sorted(roots)}
        search = deque(sorted(roots))
        while search and found not in predecessors:
            source = search.popleft()
            for target in sorted(edges.get(source, ())):
                if target not in predecessors:
                    predecessors[target] = source
                    search.append(target)
        assert found in predecessors
        path = []
        cursor = found
        while cursor is not None:
            path.append(cursor)
            cursor = predecessors[cursor]
        path.reverse()
    finished = not queue and found is None
    excluded = finished and not ({0xC7, 0xC8} & terminals)
    print(f'selector={selector_value:X}, bootstrap={bootstrap}, mode={mode}, '
          f'type7={type7}, selector9_gate={selector9_gate}: '
          f'{updates} transfers, {len(domains)} contexts, '
          f'{len({key[0] for key in domains})} ROM addresses, {len(queue)} pending', flush=True)
    print('terminals:', ' '.join(f'{ip:02X}' for ip in sorted(terminals)), flush=True)
    print('FIXPOINT: excluded for these DD seeds' if excluded else
          'CANDIDATE: return-stack consistent, numeric data not validated' if found else
          'INCOMPLETE: transfer limit reached', flush=True)
    if path:
        sequence = [0xDD]
        for ip, _ in path:
            sequence.append(ip)
            if ip == 0x93:
                sequence.append(0x94)
        print('candidate path:', ' '.join(f'{ip:02X}' for ip in sequence), flush=True)
        print('initial stack:', '/'.join(f'{n:02X}' for n in path[0][1]), flush=True)
    return {'excluded': excluded, 'finished': finished, 'path': path,
            'domains': domains, 'edges': edges, 'roots': roots,
            'updates': updates, 'pending': len(queue), 'terminals': terminals,
            'seed_contexts': specs, 'selector_value': selector_value,
            'bootstrap': bootstrap, 'selector9_gate': selector9_gate}


def check_certificate(report, mode='low', type7=True, starts=OPEN_STACKS):
    """Check the final inductive cover without rerunning the worklist.

    This deliberately does not use the projection/copy/merge implementation:
    each exact ROM transition must land in the reported cover as a whole.
    The same independently proved first-entry bounds remain assumptions.
    """
    assert report['excluded'] and report['finished'] and report['pending'] == 0
    m = model()
    templates, _ = m['compile_templates']()
    domains, edges = report['domains'], report['edges']
    specs = report.get('seed_contexts', seed_specs(starts, None))
    selector_value = report.get('selector_value', 4)
    bootstrap = report.get('bootstrap', False)
    selector9_gate = report.get('selector9_gate', False)

    def member(a, key):
        ip, sp = key
        return And(address(a) == ip,
                   *[v == n for v, n in zip(stack(a), sp)],
                   *[Or(*[expr == n for n in values]) for expr, values in
                     zip(m['fields'](a)[:-3], domains[key])])

    assert report['roots'] == {(ip, tuple(sp)) for ip, sp, _ in specs}
    for number, (exit_ip, sp, vectors) in enumerate(specs):
        a = m['State'](f'certificate_seed_{number}')
        p = seed_solver(a, sp, mode, selector_value, exit_ip, vectors)
        assert p.check() == sat, ('vacuous seed', sp)
        b = m['execute'](a, 0xDD, *m['keys'](f'certificate_seed_keys_{number}'))
        p.add(Not(And(b.r[38] == selector_value, member(b, (exit_ip, tuple(sp))))))
        assert p.check() == unsat, ('uncovered initial DD', sp)

    checked = 0
    returns = 0
    for key in sorted(domains):
        ip, sp = key
        assert ip not in (0xC7, 0xC8), 'primitive in a negative certificate'
        if ip in m['WRITERS']:
            continue
        a, b, _, _, addr, _, _, _ = templates[ip]
        p = m['base'](a, ip)
        prior(p, a, ip, type7, selector_value, selector9_gate)
        p.add(member(a, key), addr != 0xC7)
        if ip != 0x60:
            p.add(addr != 0xC8)
        if bootstrap and ip == 0x60:
            p.push()
            p.add(bootstrap_condition(a))
            assert p.check() == unsat, ('bootstrap target in negative cover', key)
            p.pop()
        successors = edges.get(key, ())
        cover = Or(*[member(b, target) for target in successors])
        p.add(Not(And(b.r[38] == selector_value, cover)))
        assert p.check() == unsat, ('non-inductive cover', key)
        checked += 1
        if ip in (0xD4, 0xD6):
            assert all(target == (sp[0], sp[1:]+sp[:1]) for target in successors)
            returns += 1
    for root in report['roots']:
        ip, sp = root
        assert edges[root] == {(sp[0], sp[1:]+sp[:1])}, ('bad first return', root)
    print(f'PASS: {len(specs)} nonempty DD seed covers; {checked} inductive '
          f'transition covers; {returns} exact D4/D6 return contexts. '
          'Projection/merge code is not used by this check.', flush=True)
    return checked


def verify(path, mode='low', type7=True, selector_value=4, bootstrap=False,
           vectors=(0xFF,), selector9_gate=False):
    m = model()
    sequence = [0xDD]
    for ip, _ in path:
        sequence.append(ip)
        if ip == 0x93:
            sequence.append(0x94)
    a = m['State']('stack_candidate')
    p = seed_solver(a, path[0][1], mode, selector_value, path[0][0], vectors)
    b = a
    for index, (ip, nxt) in enumerate(zip(sequence, sequence[1:])):
        if ip != 0xDD:
            prior(p, b, ip, type7, selector_value, selector9_gate)
        b = m['execute'](b, ip, *m['keys'](f'stack_candidate_keys_{index}'))
        p.assert_and_track(address(b) == nxt, f'edge_{index}_{ip:02X}_{nxt:02X}')
    if bootstrap and sequence[-1] == 0x60:
        p.assert_and_track(bootstrap_condition(b), 'final_bootstrap_gate')
    result = p.check()
    assert result in (sat, unsat)
    print('exact candidate check:', result, flush=True)
    if result == unsat:
        print('transition core:', p.unsat_core(), flush=True)
    else:
        print('SAT only with an artificial initial state/arbitrary ring. '
              'This is not a keyboard protocol or a reset reachability result.', flush=True)
    return str(result)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=['low', 'high', 'all'], default='low')
    parser.add_argument('--limit', type=int, default=10000)
    parser.add_argument('--complete', action='store_true', help='continue after an abstract C8 candidate')
    parser.add_argument('--no-type7-lemma', action='store_true')
    parser.add_argument('--verify-candidate', action='store_true')
    parser.add_argument('--check-certificate', action='store_true',
                        help='check the completed exclusion as an inductive cover')
    parser.add_argument('--expect-excluded', action='store_true')
    args = parser.parse_args()
    report = run(args.mode, args.limit, args.complete, not args.no_type7_lemma)
    if args.verify_candidate and report['path']:
        verify(report['path'], args.mode, not args.no_type7_lemma)
    if args.check_certificate:
        check_certificate(report, args.mode, not args.no_type7_lemma)
    if args.expect_excluded:
        assert report['excluded'], 'the exact-stack lifetime has not excluded C8'
