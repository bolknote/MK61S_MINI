#!/usr/bin/env python3
"""Conditional secondary geometry after the preserving deep NOP.

No keyboard search and no native-state injection. The primary producer
and concurrent primary writes are outside this local ROM contract.
"""
import runpy
from pathlib import Path
from z3 import And, Or, sat, unsat

q = runpy.run_path(str(Path(__file__).with_name('analyze_ms_pending_opcodes.py')))
State, ex, base, keys, addr = (q[n] for n in ('State', 'ex', 'base', 'keys', 'address'))
slots = q['slots']


def prove(p, claim, name):
    assert p.check() == sat, ('empty premise', name)
    p.push(); p.add(~claim)
    assert p.check() == unsat, name
    p.pop()


def check(start, opcode, keep_t):
    tag = 'nop_secondary_' + start + '_' + str(opcode) + '_' + str(keep_t)
    pages = {n: State(tag + n).m for n in slots}
    original = dict(pages)
    a = State(tag); a.m = pages[start]
    p = base(a, 0x6E); p.add(a.r[29] == 0)
    if opcode == 0x25:
        p.add(a.st[36] == 10, a.st[39] == 3,
              a.st[37] == 10, a.st[40] == 3)
    markers = {'marker', 'V'} | ({'T'} if keep_t else set())
    for n in slots:
        p.add(pages[n][22] == 15 if n in markers else pages[n][22] != 15)
    request = 'control' if start == 'marker' else 'W'
    p.add(pages[request][31] == opcode % 16, pages[request][34] == opcode // 16)
    if start == 'marker':
        ack = 'control'
        expected = [('X', 'Y'), ('Y', 'X')] if opcode == 0x14 else [
            ('X', 'Y'), ('Y', 'Z'), ('Z', 'T'), ('T', 'X')]
    elif keep_t:
        ack = 'U'
        expected = [('W', 'P8'), ('Q', 'W')] if opcode == 0x14 else [
            ('W', 'P8'), ('Q', 'P7'), ('P7', 'P8'), ('P8', 'P7')]
    else:
        ack = 'W'
        expected = [('P7', 'P8'), ('P8', 'P7')] if opcode == 0x14 else [
            ('P7', 'P8'), ('P8', 'P9'), ('P9', 'P10'), ('P10', 'P7')]
    route, writes, acknowledgements = [], [], []
    for step in range(80):
        p.push(); ips = q['q']['possible_values'](addr(a), p, 257); p.pop()
        assert len(ips) == 1, ('not forced', route, ips)
        ip = ips[0]
        here = slots[(slots.index(start) + step) % 15]
        nxt = slots[(slots.index(start) + step + 1) % 15]
        route.append('%02X(%s)' % (ip, here))
        before = pages[here]; out = []
        a = ex(a, ip, *keys(tag + str(step)), serial_inputs=pages[nxt], emitted_outputs=out)
        if ip in (0x4E, 0x2A, 0x3A):
            target, source = expected[len(writes)]; assert here == target
            prove(p, And(*[out[1 + 3*j] == original[source][1 + 3*j] for j in range(12)],
                         *[out[j] == before[j] for j in range(42) if j % 3 != 1 or j >= 37]),
                  'exact full-word copy at ' + route[-1])
            writes.append((target, source))
        elif ip == 0x27:
            assert here == ack
            prove(p, And(out[31] == 15,
                         *[out[j] == before[j] for j in range(42) if j != 31]),
                  'exact acknowledgement at ' + route[-1])
            acknowledgements.append(here)
        else:
            prove(p, And(*[x == y for x, y in zip(out, before)]),
                  'no other writes at ' + route[-1])
        pages[here] = out
        if ip == 0x39:
            prove(p, And(addr(a) == 0x6E, a.r[29] == 0), 'finite scanner return')
            break
    else:
        raise AssertionError('no bounded return')
    assert writes == expected
    assert len(acknowledgements) == (1 if opcode == 0x14 else 2)
    print('PASS', 'request=' + request, '%02X' % opcode, 'T-marker=' + str(keep_t), flush=True)
    print('PATH', ' -> '.join(route), flush=True)
    print('COPIES', writes, 'ACK', acknowledgements, flush=True)


def visible_drop_t():
    """Sufficient primary suffix: begin A7 at V, skip both false markers."""
    from z3 import ZeroExt
    primary = runpy.run_path(str(Path(__file__).with_name('ik1302_symbolic.py')))
    addr2 = lambda a: ZeroExt(4, a.r[36]) | (ZeroExt(4, a.r[39]) << 4)
    pages = {n: primary['State']('drop_t_' + n).m for n in slots}
    a = primary['State']('drop_t_entry'); a.m = pages['V']
    p = primary['base_solver'](a, 0xA7)
    p.add(a.st[36] == 12, a.st[39] == 10)
    for n in slots:
        p.add(pages[n][22] == 15 if n in ('marker', 'T', 'V') else pages[n][22] != 15)
    seq = [0xA7] + [0xE5]*7 + [0xE6, 0xE8, 0xE7, 0xA8, 0xA8, 0xA8, 0xA9]
    names = [slots[(8+i) % 15] for i in range(len(seq)+1)]
    carried = [a.r[3*j] for j in range(12)]
    written = []
    for i, ip in enumerate(seq):
        here = names[i]; label = '%02X(%s)' % (ip, here)
        prove(p, addr2(a) == ip, 'forced primary ' + label)
        out = []
        a = primary['execute_command'](a, ip, *primary['arbitrary_keys']('drop_t_key_' + str(i)),
                                       serial_inputs=pages[names[i+1]], emitted_outputs=out)
        if ip in (0xE7, 0xA8):
            prove(p, And(*[out[1+3*j] == carried[j] for j in range(12)],
                         *[out[j] == pages[here][j] for j in range(42) if j % 3 != 1 or j >= 37]),
                  'exact visible push ' + label)
            written.append(here)
            carried = [pages[here][1+3*j] for j in range(12)]
        else:
            prove(p, And(*[x == y for x, y in zip(out, pages[here])]), 'no ring writes ' + label)
    assert written == ['X', 'Y', 'Z', 'T']
    prove(p, addr2(a) == 0xAC, 'finite requested return')
    print('PASS A7(V) -> E5(W/Q/P7/P8/P9/P10/marker) -> E6(control) -> E8(X1) '
          '-> E7(X) -> A8(Y/Z/T) -> A9(U) -> AC(V): '
          'incoming/oldX/u/q; only old T marker is displaced.', flush=True)


if __name__ == '__main__':
    for start, keep_t in [('marker', True), ('V', True), ('V', False)]:
        for opcode in (0x14, 0x25):
            check(start, opcode, keep_t)
    visible_drop_t()
    print('LIMIT: local connected secondary contracts; no proof of keyboard producer, '
          'primary numeric return, or safe cleanup after a useful upper permutation.', flush=True)
