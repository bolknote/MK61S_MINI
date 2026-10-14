#!/usr/bin/env python3
"""Local ROM contracts for the eight-word allocation.

Native integration supplies the first D6 placement and entry fields. These
proofs allow arbitrary serial data and keyboard signals inside each suffix;
they do not prove that arbitrary keyboard states reach the assumed entry.
"""
import runpy
from pathlib import Path
from z3 import And, ZeroExt, sat, unsat

q = runpy.run_path(str(Path(__file__).with_name('ik1302_symbolic.py')))
State, ex, base, keys = (q[n] for n in ('State', 'execute_command', 'base_solver', 'arbitrary_keys'))
byte = lambda lo, hi: ZeroExt(4, lo) | (ZeroExt(4, hi) << 4)
address = lambda a: byte(a.r[36], a.r[39])
stack = lambda a: [byte(a.st[36+i], a.st[39+i]) for i in range(3)]
A = lambda a: [a.r[3*i] for i in range(12)]
same = lambda xs, ys: And(*[x == y for x, y in zip(xs, ys)])
tetras = lambda word: [int(c, 16) for c in reversed(word)]
slots = ['marker', 'control', 'X1', 'X', 'Y', 'Z', 'T', 'U', 'V', 'W', 'Q', 'P7', 'P8', 'P9', 'P10']


def prove(p, claim, label):
    assert p.check() == sat, ('empty premise', label)
    p.push()
    p.add(~claim)
    result = p.check()
    assert result == unsat, (label, p.model() if result == sat else result)
    p.pop()


def writer(source_index):
    pointer = source_index - 8
    tag = 'one_pointer_' + str(source_index)
    seq = [0xD6] + [ip for _ in range(7) for ip in (0x2F, 0x20)] + [0x2F, 0x21, 0x23, 0x25]
    slot = lambda: slots[(13 + len(seq)) % 15]
    markers = {'marker', 'V'}

    def helper(n, load=False):
        while slot() not in markers:
            seq.append(1)
        seq.extend([1] + [2]*(n+1) + [3, 4, 0xBA, 0xCB, 0xDD, 0xD6 if load else 0xD4])

    helper(13)
    seq.extend([0x26, 0x28, 0x7E, 0x70, 0xAB, 0xAD, 0xA6])
    helper(pointer, True)
    seq.append(0xA7)
    while slot() not in markers:
        seq.append(0xE5)
    seq.extend([0xE5, 0xE6, 0xE8, 0xE7, 0xA8, 0xA8, 0xA8, 0xA9])
    names = [slots[(13+i) % 15] for i in range(len(seq)+1)]
    pages = [State(tag + '_page_' + str(i)).m for i in range(len(seq)+1)]
    a = State(tag)
    a.m = pages[0]
    p = base(a, 0xD6)
    word = '0000%d0000000' % pointer
    p.add(a.r[29] == 14, a.r[32] == 13, a.r[35] == 0, a.r[26] == 15, a.s1 == 6,
          *[x == y for x, y in zip(stack(a), (0x2F, 0xAC, 0x9A))],
          *[a.m[3*i] == n for i, n in enumerate(tetras(word))])
    for i, ip in enumerate(seq):
        if ip in (1, 0xE5):
            p.add(pages[i][22] == 15 if names[i] in markers else pages[i][22] != 15)
    b, source, carried, writes = a, None, None, []
    for i, ip in enumerate(seq):
        label = '%s %d %02X(%s)' % (tag, i, ip, names[i])
        prove(p, address(b) == ip, label + ' forced next command')
        if ip == 0xD6 and i:
            assert names[i] == slots[(source_index+7) % 15]
            source = [pages[i][3*j] for j in range(12)]
        out = []
        b = ex(b, ip, *keys(label), serial_inputs=pages[i+1], emitted_outputs=out)
        if ip == 0xD4:
            writes.append(('M1', names[i]))
            prove(p, And(*[out[3*j] == n for j, n in enumerate(tetras('007%09d' % pointer))],
                         *[out[j] == pages[i][j] for j in range(42) if j % 3 != 0 or j >= 36]),
                  label + ' only P6 pointer normalization')
        elif ip in (0xE7, 0xA8):
            writes.append(('M2', names[i]))
            incoming = source if ip == 0xE7 else carried
            prove(p, And(*[out[1+3*j] == n for j, n in enumerate(incoming)],
                         *[out[j] == pages[i][j] for j in range(42) if j % 3 != 1 or j >= 37]),
                  label + ' full numeric swap, other lanes and service held')
            carried = [pages[i][1+3*j] for j in range(12)]
            prove(p, same(A(b), carried), label + ' displaced numeric word held')
        else:
            prove(p, same(out, pages[i]), label + ' no ring writes')
        if source is not None and carried is None:
            prove(p, same(A(b), source), label + ' twelve source tetras retained')
    assert writes == [('M1', 'P9')] + [('M2', n) for n in slots[11:]]
    prove(p, And(address(b) == 0xAC, b.s1 == 0), tag + ' finite return')
    print('PASS:', tag, len(seq), 'connected commands; sole M1 write P6, D/E untouched; upper 48-tetra push.', flush=True)


def marker_carrier(source_slot):
    tag = 'marker_carrier_' + source_slot
    seq = [0xD6, 0xA7] + [0xE5]*(2 if source_slot == 'control' else 1) + [0xE6, 0xE8, 0xE7, 0xA8, 0xA8, 0xA8, 0xA9]
    names = [slots[(slots.index(source_slot)+i) % 15] for i in range(len(seq)+1)]
    pages = [State(tag + '_page_' + str(i)).m for i in range(len(seq)+1)]
    a = State(tag)
    a.m = pages[0]
    p = base(a, 0xD6)
    p.add(stack(a)[0] == 0xA7, stack(a)[1] == 0xAC)
    for i, ip in enumerate(seq):
        if ip == 0xE5:
            p.add(pages[i][22] == 15 if names[i] == 'Y' else pages[i][22] != 15)
    b, carried = a, None
    source = [pages[0][3*j] for j in range(12)]
    writes = []
    for i, ip in enumerate(seq):
        label = '%s %d %02X(%s)' % (tag, i, ip, names[i])
        prove(p, address(b) == ip, label + ' forced next command')
        out = []
        b = ex(b, ip, *keys(label), serial_inputs=pages[i+1], emitted_outputs=out)
        if ip in (0xE7, 0xA8):
            writes.append(names[i])
            incoming = source if ip == 0xE7 else carried
            prove(p, And(*[out[1+3*j] == n for j, n in enumerate(incoming)],
                         *[out[j] == pages[i][j] for j in range(42) if j % 3 != 1 or j >= 37]),
                  label + ' same complete lower push')
            carried = [pages[i][1+3*j] for j in range(12)]
            prove(p, same(A(b), carried), label + ' displaced word held')
        else:
            prove(p, same(out, pages[i]), label + ' no ring writes')
        if carried is None:
            prove(p, same(A(b), source), label + ' source held')
    assert writes == ['U', 'V', 'W', 'Q']
    prove(p, And(address(b) == 0xAC, b.s1 == 0), tag + ' finite return')
    print('PASS:', tag, len(seq), 'connected commands; arbitrary full-word lower push; every ordinary word untouched.', flush=True)


if __name__ == '__main__':
    for source_index in range(8, 15):
        writer(source_index)
    for source_slot in ('control', 'X1'):
        marker_carrier(source_slot)
    print('LIMIT: local connected IK1302 suffixes, not universal keyboard entry, numeric-domain or hardware proof.', flush=True)
