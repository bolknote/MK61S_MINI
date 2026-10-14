#!/usr/bin/env python3
"""Conditional secondary rotation from the real/Z reserve geometry.

Independent symbolic words distinguish genuine source addresses from fixture
duplicates. This is a local ROM contract, not a keyboard-reachability proof.
"""
import runpy
from pathlib import Path
from z3 import And, sat, unsat

root = Path(__file__).resolve().parent
q = runpy.run_path(str(root / 'analyze_ms_pending_opcodes.py'))
State, ex, base, keys, address = (q[n] for n in ('State', 'ex', 'base', 'keys', 'address'))
slots = q['slots']


def holds(p, claim):
    assert p.check() == sat, 'empty premise'
    p.push(); p.add(~claim); answer = p.check(); p.pop()
    return answer == unsat


def secondary(start):
    tag = 'z_reserve_rotate_' + start
    pages = {n: State(tag + n).m for n in slots}
    original = dict(pages)
    a = State(tag); a.m = pages[start]; p = base(a, 0x6E)
    request = slots[(slots.index(start) + 1) % 15]
    p.add(a.r[29] == 0, pages[request][31] == 5, pages[request][34] == 2,
          a.st[36] == 10, a.st[39] == 3, a.st[37] == 10, a.st[40] == 3)
    extra = 'Y' if start == 'Y' else 'Z'
    for n in slots:
        p.add(pages[n][22] == 15 if n in ('marker', extra) else pages[n][22] != 15)
    route, copies, acks = [], [], []
    expected = {
        'marker': [('X', 'Y'), ('Y', 'Z'), ('Z', 'T'), ('T', 'X')],
        'Z': [('X', 'W'), ('Y', 'Z'), ('Z', 'T'), ('T', 'V')],
        'Y': [('X', 'V'), ('Y', 'Z'), ('Z', 'T'), ('T', 'U')],
    }[start]
    for step in range(100):
        p.push(); ips = q['q']['possible_values'](address(a), p, 257); p.pop()
        assert len(ips) == 1, ('unforced', route, ips)
        ip = ips[0]
        here = slots[(slots.index(start) + step) % 15]
        nxt = slots[(slots.index(start) + step + 1) % 15]
        route.append('%02X(%s)' % (ip, here)); old = pages[here]; out = []
        a = ex(a, ip, *keys(tag + str(step)), serial_inputs=pages[nxt], emitted_outputs=out)
        if ip in (0x3A, 0x2A):
            target, source = expected[len(copies)]
            assert here == target, (route, copies, expected)
            assert holds(p, And(*[out[1 + 3*j] == original[source][1 + 3*j] for j in range(12)],
                                *[out[j] == old[j] for j in range(42) if j % 3 != 1 or j >= 37])), (here, source)
            copies.append((target, source))
        elif ip == 0x27:
            assert here == 'control', route
            assert holds(p, And(out[31] == 15, *[out[j] == old[j] for j in range(42) if j != 31]))
            acks.append(here)
        else:
            assert holds(p, And(*[x == y for x, y in zip(out, old)])), route
        pages[here] = out
        if ip == 0x39:
            assert holds(p, And(address(a) == 0x6E, a.r[29] == 0))
            break
    else:
        raise AssertionError('unclosed route')
    assert copies == expected and acks == ['control', 'control']
    if start == 'Z':
        assert holds(p, And(pages['Y'][22] == 15, pages['Z'][31] == 5, pages['Z'][34] == 2))
        print('PASS marker and unacknowledged request relocate Z/T -> Y/Z.', flush=True)
    print('PASS real/' + extra + ' request', request, 'copies', copies, flush=True)
    print('PATH', ' -> '.join(route), flush=True)


if __name__ == '__main__':
    for start in ('marker', 'Z', 'Y'):
        secondary(start)
    producer = runpy.run_path(str(root / 'k1-y-t-rotate-path-check.py'))['next_request']
    for start in ('control', 'T'):
        producer(start, 0x25)
    formatter = runpy.run_path(str(root / 'k1-q-formatter-check.py'))['check']
    # Only canonical decimal class 1 is claimed here. The native journal must
    # establish that the E5 scan still sees Y before the second output removes it.
    formatter(0, 0, True, source_slot='X', marker_slots=('marker', 'Y'),
              target_by_class=['U'] * 9)
    print('LIMIT: separate local ROM contracts; native inter-chip timing is checked by k1-z-reserve-restored-check.cjs, not implied here.', flush=True)
