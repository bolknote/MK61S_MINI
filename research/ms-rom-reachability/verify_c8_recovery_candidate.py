#!/usr/bin/env python3
"""Exact IK1302 path filter; arbitrary future ring, physical keyboard rows.

This is a candidate filter, never a claim of a real complete-ring execution.
Provide `transport` from analyze_c8_recovery_transport.py when using runpy.
"""
from z3 import And, Or, UGE, ULE, ZeroExt, sat, unsat

assert 'transport' in globals()
q = transport['q']
address = lambda a: ZeroExt(4, a.r[36]) | (ZeroExt(4, a.r[39]) << 4)


def verify(candidate):
    sequence = []
    for st, _ in candidate:
        sequence.append(st[0])
        if st[0] == 0x93:
            sequence.append(0x94)
        elif st[0] == 0x12:
            sequence.append(0xC6)
    return verify_sequence(sequence, transport['native'])


def verify_sequence(sequence, native=None, constraints=None):
    """Filter a ROM path from either a native snapshot or arbitrary chip state.

    UNSAT without a native snapshot excludes that path for physical key pins
    even with arbitrary serial ring inputs. SAT alone establishes no recipe.
    """
    a = q['State']('recovery_candidate_native')
    p = q['base_solver'](a, sequence[0])
    if native is not None:
        for group in ('r', 'm', 'st'):
            p.add(*[v == n for v, n in zip(getattr(a, group), native[group])])
        for field in ('s', 's1', 'l', 't', 'carry'):
            p.add(getattr(a, field) == native[field])
    if constraints is not None:
        p.add(*constraints(a))
    b = a
    states, key_pins = [], []
    for i, ip in enumerate(sequence):
        p.add(address(b) == ip)
        result = p.check()
        if result != sat:
            print(f'{result}: exact {"native" if native is not None else "arbitrary-state"} prefix fails at {i}, '
                  + ' '.join(f'{v:02X}' for v in sequence[max(0, i-6):i+1]), flush=True)
            return {'result': result, 'index': i, 'sequence': sequence}
        b = b.copy()
        b.r[36], b.r[39] = q['N4'](ip), q['N4'](ip >> 4)
        states.append(b)
        kx, ky = q['arbitrary_keys'](f'recovery_candidate_keys_{i}')
        key_pins.append((kx, ky))
        for x, y in zip(kx, ky):
            p.add(Or(And(x == 0, y == 0),
                     And(UGE(x, 2), ULE(x, 11), Or(y == 1, y == 8, y == 9))))
        b = q['execute_command'](b, ip, kx, ky)
    print('SAT in the IK1302 overapproximation; full ring and timed keys still required.', flush=True)
    return {'result': sat, 'sequence': sequence, 'initial': a, 'final': b,
            'solver': p, 'states': states, 'key_pins': key_pins}
