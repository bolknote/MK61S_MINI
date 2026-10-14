#!/usr/bin/env python3
"""Exact conditional B-source store through the natural formatter exit.

This is a primary-chip ROM contract, NOT a keyboard entry or complete-ring
witness. Every incoming page and per-tick key signal is arbitrary, except
released keys at final33. Only the listed entry requirements and eventual
marker arrival restrict the solver. No calculator state or ROM is changed.
In particular, B and A are independent sources: recovering old A is not
confused with recovering the written B. The three zero-normalization cases
cover all six raw tetras of the reader format, not just a selected example.
"""
import json
from pathlib import Path
import runpy
import subprocess
import sys

from z3 import And, If, Or, Solver, unsat

root = Path(__file__).resolve().parent
w = runpy.run_path(str(root / 'cache46-writer-contracts.py'))
State, ex, base, keys, ip, A, B, stack, eq, prove = (
    w[name] for name in
    ('State', 'ex', 'base', 'keys', 'ip', 'A', 'B', 'stack', 'eq', 'prove'))


raw_indices = (0, 1, 3, 4, 6, 7)


def decode_raw_tetras(stored, tag_lo):
    """Symbolic stored-word contract, not calculator keyboard decoding."""
    def unshift(index, count):
        return stored[index+count] if index+count < 8 else w['q']['N4'](0)
    return [If(stored[9] == tag_lo, unshift(k, 0),
               If(stored[9] == tag_lo-1, unshift(k, 1), unshift(k, 2)))
            for k in raw_indices]


def run(header, shifts, tag_lo=8, tag_hi=7):
    assert header in (0, 9) and shifts in (0, 1, 2)
    assert 2 <= tag_lo <= 15 and 0 <= tag_hi <= 15
    label = f'h{header}_tag{tag_lo:X}{tag_hi:X}_shift{shifts}'
    a = State(f'bsource_closed_{label}')
    p = base(a, 0xDC)
    p.add(a.r[34] == header, a.st[22] == 0,
          a.r[7] == 15, a.r[16] == 15, a.r[25] == 15,
          a.r[28] == tag_lo, a.r[31] == tag_hi)
    if shifts == 0:
        p.add(a.r[22] != 0)
    elif shifts == 1:
        p.add(a.r[22] == 0, a.r[19] != 0)
    else:
        p.add(a.r[22] == 0, a.r[19] == 0)
    source = B(a)[:12]
    sequence = (
        0xDC, 0xEA, 0xEC, 0x40, 0x41, 0x42)
    sequence += (0x44, 0x42) * shifts
    sequence += (
        0x46,
        0xE5, 0xE5, 0xE6, 0xE8, 0xE7, 0x47, 0x49, 0xBD,
        0x91, 0x92, 0x93, 0x94, 0x95, 0x98, 0x9A,
        0x93, 0x94, 0x95, 0x98, 0x9A, 0xBE, 0xB0, 0x33)
    pages = [State(f'bsource_{label}_page{j}').m
             for j in range(len(sequence) + 1)]
    a.m = pages[0]
    b = a
    for j, code in enumerate(sequence):
        if code == 0xE5:
            p.add(pages[j][22] == (0 if sequence[j+1] == 0xE5 else 15))
        prove(p, ip(b) == code,
              f'{label} natural command{j} {code:02X} forced', False)
        if code == 0xBE:
            prove(p, b.r[23] == a.st[22],
                  f'{label}: exit opcode flag comes from original ST22')
        out = []
        pins = (0, 0) if code == 0x33 else keys(f'bsource_{label}_keys{j}')
        b = ex(b, code, *pins,
               serial_inputs=pages[j+1], emitted_outputs=out)
        if code == 0xE7:
            stored = out[1:36:3]
            normalized = [w['q']['N4'](0)] * shifts + source[:8-shifts]
            expected = normalized + [w['q']['N4'](value)
                                     for value in (15, tag_lo-shifts, tag_hi, header)]
            prove(p, And(eq(stored, expected),
                         eq(A(b), pages[j][1:36:3]),
                         *[out[t] == pages[j][t] for t in range(42)
                           if t % 3 != 1 or t >= 37]),
                  f'{label}: one exactly normalized12-tetra M2 write; other lanes held')
            decoded = decode_raw_tetras(stored, tag_lo)
            prove(p, And(Or(stored[9] == tag_lo, stored[9] == tag_lo-1,
                            stored[9] == tag_lo-2),
                         eq(decoded, [source[k] for k in raw_indices])),
                  f'{label}: same stored-word decoder recovers all six raw tetras')
        else:
            prove(p, eq(out, pages[j]),
                  f'{label} {code:02X} no outgoing write', False)
        if code == 0x47:
            prove(p, eq(A(b), source),
                  f'{label}: 47 recovers original unnormalized B12 from numeric ST')
        if code == 0x49:
            prove(p, eq(B(b)[:12], source),
                  f'{label}: 49 parks original unnormalized B12 in B')
    prove(p, And(ip(b) == 0x35, eq(b.st[0:27:3], source[:9])),
          f'{label}: quiet33 reaches idle35; ST lane0 retains original lower9 including all raw6')
    print('CONDITIONAL CLOSED STORE, not native:',
          label, ' '.join(f'{c:02X}' for c in sequence), '->35', flush=True)
    return a, b, p


def replay_native():
    """Check semantics on a genuine writer tail, not invented payload entry."""
    data = json.loads(subprocess.check_output(
        ['node', str(root / 'cache-writer-native.cjs'), '--proof-input'], text=True))
    events = data['events']
    start = next(j for j, e in enumerate(events) if e['ip'] == 0xDC)
    writer = next(j for j in range(start, len(events)) if events[j]['ip'] == 0xE7)
    stop = next(j for j in range(writer+1, len(events)) if events[j]['ip'] == 0x35)
    assert all(events[writer]['r'][j] == 0 for j in w['raw']), (
        'native semantic-control writer unexpectedly contains a raw cache')
    baseline = runpy.run_path(str(root / 'cache-writer-contract.py'))
    b = baseline['constant'](events[start])
    for j in range(start, stop):
        e, nxt = events[j:j+2]
        assert nxt['command'] == e['command'] + 1
        assert baseline['number'](ip(b)) == e['ip']
        b = ex(b, e['ip'], e['keyX'], e['keyY'],
               serial_inputs=[w['q']['N4'](v) for v in nxt['m']])
        for field in ('r', 'st', 'm'):
            assert [baseline['number'](v) for v in getattr(b, field)] == nxt[field], (j, field)
        for field in ('s', 's1', 'l', 't', 'carry'):
            assert baseline['number'](getattr(b, field)) == nxt[field], (j, field)
    print(f'PASS: exact passive native DC-to-E7-to35 replay, {stop-start} commands; '
          'all primary fields. Native raw cache was erased BEFORE this writer; '
          'this is only a semantics regression, not native partial K2.', flush=True)


if __name__ == '__main__':
    a = State('bsource_case_cover')
    p = Solver()
    p.add(~Or(a.r[22] != 0, And(a.r[22] == 0, a.r[19] != 0),
              And(a.r[22] == 0, a.r[19] == 0)))
    assert p.check() == unsat
    print('PASS: three source-data cases are exhaustive.', flush=True)
    for header in (0, 9):
        for shifts in (0, 1, 2):
            run(header, shifts)
    for shifts in (0, 1, 2):
        run(9, shifts, tag_lo=10, tag_hi=9)
    print('PASS: three conditional header/tag combinations; exhaustive three '
          'zero-normalization cases; all 16^6 opaque raw payloads covered per '
          'combination; same parameterized decoder.', flush=True)
    print('LIMIT: no native cache-to-B/header adapter, physical Ms slot '
          'alignment, old-Ms backup, reverse program write, or K2 proved.',
          flush=True)
    if '--native-replay' in sys.argv:
        replay_native()
