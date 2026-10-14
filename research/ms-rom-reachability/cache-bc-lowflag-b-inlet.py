#!/usr/bin/env python3
"""A NEW conditional low-flag first28/BB path with a surviving raw cache.

Unlike the excluded type3/54 bridge, this begins at28 with TYPE2,
operand3, kindB and mode5. The first48 itself has TYPE5/operandB;
BB/BC/49 never needs54 or flag>=3. Necessary native source invariants
permit the packet, but do NOT establish it by public keys.

Eight detached PRIMARY contracts reach original F9 and a second C9.
Fresh serial M3 pages are NOT identified physical programme pages. The
source is F0..FF, NOT an established Ms byte. ALL12 original A tetras
survive in ST0lower9/ST1upper3. No native state/ROM/return repair.
"""
from pathlib import Path
import runpy

from z3 import And, Or, ULE, sat

root = Path(__file__).resolve().parent
source = runpy.run_path(str(root / 'cache-bc-direct-source-closure.py'))
r, w, q, loops, highkind, walk = (source[n] for n in
    ('r', 'w', 'q', 'loops', 'highkind', 'walk'))
A, B, eq = source['A'], source['B'], source['eq']
double = r['double']


def inlet_packet(a, address):
    return And(a.r[32] == 2, a.r[29] == 3, a.r[35] == 11,
        a.r[2] == 5, a.r[26] != 0, ULE(a.r[23], 2),
        a.st[1] == 5, a.st[22] == 1, a.st[25] == 0,
        a.st[30] == address % 10, a.st[33] == address // 10)


def compatible_with_necessary_source_bounds():
    for flag in (0, 1, 2):
        a = q['State'](f'lowflag_B_necessary_{flag}'); p = w['base'](a, 0x28)
        p.add(inlet_packet(a, 87), a.r[23] == flag,
            loops['inlet']['invariant'](a, 0x28),
            loops['ac_source_invariant'](a, 0x28),
            highkind['high_kind_origin_invariant'](a, 0x28))
        assert p.check() == sat
    print('PASS necessary-source compatibility for flags0/1/2: '
          '28/type2/operand3/kindB/mode5 does NOT violate the proved '
          'native type/number/mode/flag bounds. This is NOT a native '
          'witness, nor proof that public keys construct the joint packet.', flush=True)


def prefix_sequence(address):
    return (0x28, 0x7E, 0x7B, 0xB7, 0x45, 0x8B, 0x48,
        0xB1, 0xB3, 0xBB, 0xBC, 0x49, 0xBD, *double,
        0xBE, 0x63, *([0x64]*(address//7+1)), 0x66)


def marker_sequence(address):
    return (1, *([2]*(address//7+1)), 3, 4, 0xBA, 0xCC, 0xCD)


def complete_patch(a, entry, p, address, label):
    # All returns were made by28/45/8B/48/BD/66, not freely assigned.
    # This is a serial-lane composition; no claim that its visits hit
    # the same full-ring physical page is made.
    offset = address % 7
    page = list(entry.m[2:42:3]); assert len(page) == 14
    index = (2*offset+12) % 14
    patch = [a.r[34], q['N4'](15)]
    expected = list(page); expected[index:index+2] = patch
    output = []
    b = w['ex'](entry, 0xC9, *q['arbitrary_keys'](label+'_C9_first_keys'),
        serial_inputs=q['State'](label+'_C9_first_serial').m, emitted_outputs=output)
    w['prove'](p, And(w['ip'](b) == 0x67,
        eq(b.r[1:42:3], page), eq(output[2:42:3], entry.r[1:42:3]),
        *[output[j] == entry.m[j] for j in range(42) if j % 3 != 2]),
        f'{label} FIRST originalC9 swaps actual M3/B14 and returns constructed67')
    first = (0x6A, 0x6B, 0x6C, 0x69)*(offset+1)
    special = (0xFB, 0xFD, 0xF9, 0xFC, 0x68)
    rest = (0x69, 0x6A, 0x6B, 0x6C, 0x68)*(6-offset)
    b = walk(b, p, (0x67, *first, *special, *rest, 5), label+'_F9')
    w['prove'](p, And(w['ip'](b) == 1, w['stack'](b)[0] == 6,
        eq(b.r[1:42:3], expected), eq(b.st[0:27:3], A(a)[:9]),
        eq(b.st[28:36:3], A(a)[9:12]),
        *[b.st[j] == a.r[j] for j in w['raw']]),
        f'{label} originalF9 changes EXACTLY one local M3 byte toF-high; '
        'ALL other6 bytes and split oldA12 reserve survive')
    p.add(b.m[22] == 15)
    b = walk(b, p, marker_sequence(address), label+'_second_marker')
    w['prove'](p, And(w['ip'](b) == 0xC9, w['stack'](b)[0] == 6,
        eq(b.r[1:42:3], expected)), f'{label} original05/marker constructs secondC9/head06')
    before = b; output = []
    b = w['ex'](b, 0xC9, *q['arbitrary_keys'](label+'_C9_second_keys'),
        serial_inputs=q['State'](label+'_C9_second_serial').m, emitted_outputs=output)
    w['prove'](p, And(w['ip'](b) == 6,
        eq(output[2:42:3], expected),
        *[output[j] == before.m[j] for j in range(42) if j % 3 != 2],
        eq(b.st[0:27:3], A(a)[:9]),
        eq(b.st[28:36:3], A(a)[9:12]),
        *[b.st[j] == a.r[j] for j in w['raw']]),
        f'{label} SECOND originalC9 emits the one-byte-patched local page; '
        'other lanes/ALL splitA12 held, no physical-page assertion')
    return b


def conditional_writer(address, *, entry_factory=None):
    label = f'lowflag_first28_address{address}_B'
    if entry_factory is None:
        a = q['State'](label); p = w['base'](a, 0x28)
    else:
        # Optional earlier ORIGINAL caller packet. The factory returns
        # its actual symbolic output and solver, never a rewritten IP.
        a, p = entry_factory(address, label)
    p.add(inlet_packet(a, address))
    b = walk(a, p, (0x28, 0x7E, 0x7B, 0xB7, 0x45, 0x8B), label+'_first48')
    w['prove'](p, And(w['ip'](b) == 0x48, b.r[32] == 5, b.r[29] == 11,
        b.r[23] == a.r[23], eq(A(b), A(a)), eq(B(b), B(a))),
        f'{label} FIRST48 already type5/operandB; flag0..2 held, no54')
    b = walk(b, p, prefix_sequence(address)[6:], label, only_ring_writer=0xBC)
    p.add(b.m[22] == 15)
    b = walk(b, p, marker_sequence(address), label+'_marker')
    buffer = [*B(a)[1:], q['N4'](15)]
    w['prove'](p, And(w['ip'](b) == 0xC9, w['stack'](b)[0] == 0x67,
        b.r[2] == 5, b.r[23] == 1, b.r[26] == 0, b.r[29] == 0,
        b.r[38] == 8, b.r[32] == address//7, b.r[35] == address % 7, b.s1 == 9,
        b.r[31] == address % 10, b.r[34] == address // 10,
        eq(A(b), buffer), eq(b.st[0:36:3], [*A(a)[:9], *buffer[9:12]]),
        eq(b.st[28:36:3], A(a)[9:12]),
        *[b.st[j] == a.r[j] for j in w['raw']]),
        f'{label} constructedC9/67 keeps ALL oldA12 split in '
        'ST0lower9/ST1upper3, including all3 raw cached codes')
    p.push()
    assert q['possible_values'](w['byte'](b.r[30], b.r[33]), p, 257) == list(range(0xF0, 0x100))
    p.pop()
    return complete_patch(a, b, p, address, label)


def whole_upper_a_reserve():
    # Full-state pair theorem at the firstC9 boundary. The upper3 were
    # replaced in ST0, but NOT erased: their sole primary copy is ST1.
    label = 'lowflag_B_upperA_reserve'; address = 87
    a = q['State'](label); p = w['base'](a, 0x28)
    p.add(inlet_packet(a, address)); other = q['State'](label+'_other')
    alternate = a.copy()
    for j in (27, 30, 33): alternate.r[j] = other.r[j]
    b, c = a, alternate
    sequence = (*prefix_sequence(address), *marker_sequence(address))
    for index, code in enumerate(sequence):
        if code == 1: p.add(b.m[22] == 15, c.m[22] == 15)
        w['prove'](p, And(w['ip'](b) == code, w['ip'](c) == code),
            label+f' paired actual IP{code:02X}', False)
        pins = q['arbitrary_keys'](label+f'_keys{index}')
        serial = q['State'](label+f'_serial{index}').m
        ob, oc = [], []
        b = w['ex'](b, code, *pins, serial_inputs=serial, emitted_outputs=ob)
        c = w['ex'](c, code, *pins, serial_inputs=serial, emitted_outputs=oc)
        w['prove'](p, eq(ob, oc), label+f' outgoing upperA-independent{code:02X}', False)
    reserved = (28, 31, 34)
    w['prove'](p, And(w['ip'](b) == 0xC9, eq(b.r, c.r), eq(b.m, c.m),
        *[b.st[j] == c.st[j] for j in range(42) if j not in reserved],
        eq([b.st[j] for j in reserved], A(a)[9:12]),
        eq([c.st[j] for j in reserved], A(alternate)[9:12]),
        *[getattr(b, n) == getattr(c, n) for n in ('s', 's1', 'l', 't', 'carry')]),
        'WHOLE-state pair: independent upper3 oldA tetras retained ONLY '
        'in ST1[28/31/34]; not erased or exported before firstC9')
    p.push(); p.add(Or(*[a.r[j] != alternate.r[j] for j in (27, 30, 33)]))
    assert p.check() == sat; p.pop()


if __name__ == '__main__':
    r['inlet']['immutable_reference']()
    compatible_with_necessary_source_bounds()
    for address in (*range(84, 91), 99): conditional_writer(address)
    whole_upper_a_reserve()
    r['inlet']['immutable_reference']()
    print('PASS eight NEW CONDITIONAL low-flag first28/BB contracts toF9/'
          'secondC9,16 abstract F-high values each, ALL raw6 cache tetras '
          'retained, ALL oldA12 in split ST0lower9/ST1upper3. Native joint entry/Ms-byte '
          'origin, safe physical M2/M3 visits, BC recovery and final '
          'exit/inverse remain UNPROVED; not partialK2.', flush=True)
