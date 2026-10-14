#!/usr/bin/env python3
"""Conditional raw writers and exact checks of cached candidate entry paths.

This does not construct keyboard sequences or modify an emulator. The cached
reset graph is an overapproximation; a listed state is not a native witness.
"""
import argparse
import gzip
import json
from pathlib import Path
import runpy
from z3 import And, If, Or, BitVecVal, ZeroExt, sat, unsat

root = Path(__file__).resolve().parent
q = runpy.run_path(str(root / 'ik1302_symbolic.py'))
State, ex, base, keys = (q[n] for n in
                       ('State', 'execute_command', 'base_solver', 'arbitrary_keys'))
byte = lambda lo, hi: ZeroExt(4, lo) | (ZeroExt(4, hi) << 4)
address = lambda a: byte(a.r[36], a.r[39])
stack = lambda a: [byte(a.st[36+i], a.st[39+i]) for i in range(3)]


def prove(p, claim, label):
    assert p.check() == sat, ('empty premise', label)
    p.push()
    p.add(~claim)
    outcome = p.check()
    assert outcome == unsat, (label, p.model() if outcome == sat else outcome)
    p.pop()
    print('PASS:', label, flush=True)


def local_contracts():
    a = State('de_dc')
    p = base(a, 0xDE)
    b = ex(a, 0xDE, *keys('de_dc_first'))
    p.add(address(b) == 0xDC)
    c = ex(b, 0xDC, *keys('de_dc_second'))
    prove(p, address(c) == 0xEA,
          'DE->DC universally exits EA, never the abstract candidate edge DE')
    for ip in (0xE5, 0xE6):
        a = State('s5_loop_%02X' % ip)
        p = base(a, ip)
        p.add(a.s1 == 5)
        out = []
        b = ex(a, ip, *keys('s5_loop_keys_%02X' % ip), emitted_outputs=out)
        permitted = [0xE5, 0xE6] if ip == 0xE5 else [0xE5]
        prove(p, And(b.s1 == 5, Or(*[address(b) == v for v in permitted]),
                     *[x == y for x, y in zip(out, a.m)]),
              'S1=5: %02X is trapped in read-only E5/E6, independent of keys' % ip)
    a = State('a8_dispatch')
    p = base(a, 0xA8)
    b = ex(a, 0xA8, *keys('a8_dispatch'))
    prove(p, And(b.s1 == a.s1 + 2,
                 address(b) == If(a.s1 == 14, BitVecVal(0xA9, 8),
                                  BitVecVal(0xA8, 8))),
          'A8 adds 2 modulo 16 and exits only from selector E')
    p.add((a.s1 & 1) == 1)
    prove(p, And((b.s1 & 1) == 1, address(b) == 0xA8),
          'odd A8 selector is invariant: an endless writer, not a finite lift')
    for selector, commands in ((14, (0xA8,)),
                               (12, (0xA8, 0xA8)),
                               (8, (0xA8,) * 4)):
        pages = [State('a8_%X_page_%d' % (selector, i)).m
                 for i in range(len(commands) + 1)]
        a = State('a8_%X' % selector)
        a.m = pages[0]
        p = base(a, 0xA8)
        p.add(a.s1 == selector)
        b = a
        previous = [a.r[3*j] for j in range(12)]
        for index, ip in enumerate(commands):
            prove(p, address(b) == ip,
                  'A8 selector %X: write %d is forced' % (selector, index+1))
            out = []
            b = ex(b, ip, *keys('a8_%X_%d' % (selector, index)),
                   serial_inputs=pages[index+1], emitted_outputs=out)
            prove(p, And(*[out[1+3*j] == previous[j] for j in range(12)],
                         *[out[j] == pages[index][j] for j in range(42)
                           if j % 3 != 1 or j >= 37],
                         *[b.r[3*j] == pages[index][1+3*j]
                           for j in range(12)]),
                  'A8 selector %X: exact 12-tetra swap, other fields held, write %d'
                  % (selector, index+1))
            previous = [pages[index][1+3*j] for j in range(12)]
        prove(p, address(b) == 0xA9,
              'A8 selector %X: exactly %d writes then A9' % (selector, len(commands)))

    for ret in (0x93, 0xDD):
        a = State('ee_a8_%02X' % ret)
        p = base(a, 0xEE)
        p.add(a.s1 == 14, stack(a)[0] == 0xA8, stack(a)[1] == ret)
        source = [a.m[1+3*j] for j in range(12)]
        b = a
        for index, ip in enumerate((0xEE, 0xA8, 0xA9)):
            prove(p, address(b) == ip, 'EE/A8/%02X: step %02X forced' % (ret, ip))
            before = b
            out = []
            b = ex(b, ip, *keys('ee_a8_%02X_%d' % (ret, index)), emitted_outputs=out)
            if ip == 0xA8:
                prove(p, And(*[out[1+3*j] == source[j] for j in range(12)],
                             *[out[j] == before.m[j] for j in range(42)
                               if j % 3 != 1 or j >= 37], b.s1 == 0),
                      'EE/A8/%02X: source copied exactly to next physical M2 word'
                      % ret)
            else:
                prove(p, And(*[x == y for x, y in zip(out, before.m)]),
                      'EE/A8/%02X: %02X writes no ring tetra' % (ret, ip))
        prove(p, And(address(b) == ret, b.s1 == 0),
              'EE/A8/%02X: A9 returns %02X with selector 0, not clean 47' % (ret, ret))
        if ret == 0xDD:
            out = []
            before = b
            b = ex(b, ret, *keys('ee_a8_dd_exit'), emitted_outputs=out)
            prove(p, And(address(b) == 0xD0,
                         *[x == y for x, y in zip(out, before.m)]),
                  'EE/A8/DD enters D0, not aligned M1 writer D4')


def constrain_abstract(p, a, state):
    ip, sp, vector, selector, delta, r38, dr38, r26, types = state
    assert types is None
    p.add(address(a) == ip,
          *[value == expected for value, expected in zip(stack(a), sp)],
          Or(*[a.s1 == value for value in selector]))
    if vector == 'diagonal':
        p.add(a.r[37] == a.r[40])
    elif vector is not None:
        p.add(byte(a.r[37], a.r[40]) == vector)
    if delta is not None:
        p.add(a.s1 - a.r[35] == delta)
    if r38 is not None:
        p.add(Or(*[a.r[38] == value for value in r38]))
    if dr38 is not None:
        p.add(a.r[38] - a.r[35] == dr38)
    if r26 is not None:
        p.add(Or(*[a.r[26] == value for value in r26]))


def cached_entry_paths(timeout_ms):
    audit = runpy.run_path(str(root / 'k1-formatter-entry-audit.py'))
    with gzip.open(audit['cache_path'], 'rt', encoding='utf8') as stream:
        data = json.load(stream)
    assert data['metadata']['complete'] and data['metadata']['pending'] == 0
    assert data['metadata']['sourceSha256'] == audit['fingerprints']()
    states = data['states']
    targets = [i for i in data['indexes']['byIp']['EE']
               if states[i][1][0] == 0xA8 and 14 in states[i][3]]
    assert targets == [51917, 52209, 52336]
    expected_rejections = {51917: (116, 5, 0xE5),
                           52209: (114, 12, 0xEA),
                           52336: (114, 12, 0xEA)}
    for target in targets:
        path = []
        index = target
        while index is not None:
            path.append(index)
            index = data['parents'][index]
        path.reverse()
        sequence = []
        for index in path:
            ip = states[index][0]
            sequence.append(ip)
            if ip == 0x93:
                sequence.append(0x94)
            if ip == 0x12:
                sequence.append(0xC6)
        print('CANDIDATE entry state', target, 'commands', len(sequence),
              ' '.join('%02X' % ip for ip in sequence), flush=True)
        a = State('raw_entry_%d_initial' % target)
        p = base(a, sequence[0])
        p.set(timeout=timeout_ms)
        # The initial abstract reset constraints are weaker than full zeroed
        # silicon. Rejection therefore does not rely on strengthening reset.
        constrain_abstract(p, a, states[path[0]])
        current = a
        result = sat
        for step, ip in enumerate(sequence[:-1]):
            b = ex(current, ip, *keys('raw_entry_%d_%d' % (target, step)))
            following = State('raw_entry_%d_state_%d' % (target, step+1))
            equalities = [x == y for field in ('r', 'm', 'st')
                          for x, y in zip(getattr(b, field), getattr(following, field))]
            equalities += [getattr(b, field) == getattr(following, field)
                           for field in ('s', 's1', 'l', 't', 'carry')]
            equalities.append(address(following) == sequence[step+1])
            p.push()
            p.assert_and_track(And(*equalities),
                               'path_%d_step_%d_%02X_%02X' %
                               (target, step, ip, sequence[step+1]))
            result = p.check()
            if result != sat:
                print('EXACT ENTRY', target, str(result), 'at', step,
                      '%02X->%02X' % (ip, sequence[step+1]), flush=True)
                if result == unsat:
                    print('UNSAT CORE clauses:', len(p.unsat_core()), flush=True)
                else:
                    print('REASON:', p.reason_unknown(), flush=True)
                p.pop()
                expected_step, expected_selector, expected_next = expected_rejections[target]
                assert result == unsat and step == expected_step
                for label, expression in [('entry selector', current.s1),
                                           ('actual next ip', address(b))]:
                    p.push()
                    values = q['possible_values'](expression, p, 257)
                    p.pop()
                    print('PREFIX', target, label,
                          ['%02X' % value for value in values], flush=True)
                    assert values == [expected_selector if label == 'entry selector'
                                      else expected_next]
                break
            current = following
            if step % 20 == 19:
                print('EXACT ENTRY', target, step+1, 'transitions SAT', flush=True)
        if result == sat:
            constrain_abstract(p, current, states[target])
            print('EXACT ENTRY', target, 'endpoint', p.check(), flush=True)
        assert result == unsat, 'the three recorded parent paths must stay rejected'
        del p, a, current
    print('LIMIT: these are exact checks of three selected cached parent paths, '
          'not an exclusion of all paths to their target abstract states. '
          'SAT still leaves physical ring circulation, secondary chips and '
          'public keyboard realizability unproved.', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--entry-paths', action='store_true')
    parser.add_argument('--timeout-ms', type=int, default=15000)
    args = parser.parse_args()
    local_contracts()
    if args.entry_paths:
        cached_entry_paths(args.timeout_ms)
    print('LIMIT: EE/topA8 with selector E supplies a conditional one-word '
          'writer, not a complete keyboard exchange or a safe output tail.', flush=True)
