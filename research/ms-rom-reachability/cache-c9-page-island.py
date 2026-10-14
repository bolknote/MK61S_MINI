#!/usr/bin/env python3
"""Original C9/67 byte reader/writer island, NOT a page-exchange witness.

Three mode/flag families and seven byte offsets use ORIGINAL ROM edges.
Return67 is a conditional entry with a proved original66 constructor;
the following05 itself pushes06. No free BB return or repaired S1 is used.
All14 programme tetras, the source byte and future pins/pages are arbitrary.
The C8-inclusive reset cover excludes flag0 ONLY at the actual C8 entry.
"""
from collections import Counter
from pathlib import Path
import runpy

from z3 import And, If, UGE, ULE, ULT, sat

root = Path(__file__).resolve().parent
prior = runpy.run_path(str(root / 'cache-call-return-transport.py'))
r, w, q, states, edges = (prior[n] for n in ('r', 'w', 'q', 'states', 'edges'))
N8 = lambda n: q['BitVecVal'](n, 8)
B = lambda a: a.r[1:42:3]
walk = prior['walk']


def original_call_and_wait_gates():
    for caller, head in ((0x66, 0x67), (0x05, 0x06)):
        a = q['State'](f'page_island_call_{caller:02X}'); p = w['base'](a, caller); out = []
        b = w['ex'](a, caller, *q['arbitrary_keys'](f'page_island_call_keys_{caller:02X}'),
                    emitted_outputs=out)
        w['prove'](p, And(w['ip'](b) == 1, b.s1 == 9, w['stack'](b)[0] == head,
            w['eq'](B(b), B(a)), b.r[26] == a.r[26], w['eq'](out, a.m)),
            f'original{caller:02X} pushes{head:02X}/setsS1nine; B14 and flag held')
    for code in (0x01, 0x02, 0x03, 0x04, 0xBA, 0xCC, 0xCD):
        a = q['State'](f'page_island_wait_{code:02X}'); p = w['base'](a, code); out = []
        b = w['ex'](a, code, *q['arbitrary_keys'](f'page_island_wait_keys_{code:02X}'),
                    emitted_outputs=out)
        w['prove'](p, And(w['eq'](B(b), B(a)), b.s1 == a.s1,
            w['eq'](w['stack'](b), w['stack'](a)),
            b.r[26] == a.r[26], b.r[2] == a.r[2], w['eq'](out, a.m)),
            f'{code:02X} universal B14/S1/return/flag/mode holder; no ring write', False)
        if code == 1:
            claim = And(b.r[29] == 0, b.r[32] == a.r[32],
                w['ip'](b) == If(a.m[22] == 15, N8(2), N8(1)))
        elif code == 2:
            claim = And(b.r[29] == a.r[29]+1, b.r[32] == a.r[32],
                w['ip'](b) == If(a.r[29] == a.r[32], N8(3), N8(2)))
        elif code in (3, 4): claim = w['ip'](b) == (4 if code == 3 else 0xBA)
        elif code == 0xBA: claim = w['ip'](b) == If(UGE(a.s1, 7), N8(0xCC), N8(0xCB))
        elif code == 0xCC: claim = w['ip'](b) == If(UGE(a.s1, 10), N8(0xBB), N8(0xCD))
        else: claim = And(w['ip'](b) == (N8(0xC0) | q['ZeroExt'](4, a.s1)),
                          b.r[29] == 0, b.r[38] == 8)
        w['prove'](p, claim, f'exact original wait/dispatch gate{code:02X}')
    # 01 waits preserve the data at any finite length and reset the counter
    # to0. 02 increments modulo16; with constant R32=k it exits on iteration
    # k+1, at most16, never by a key/data dispatch toBB. This is induction,
    # NOT a bounded enumeration of keyboard waits.
    a = q['State']('page_island_last02'); p = w['base'](a, 2)
    p.add(a.r[29] == a.r[32], a.s1 == 9)
    b = walk(a, p, (2, 3, 4, 0xBA, 0xCC, 0xCD), 'page_island_last02')
    w['prove'](p, And(w['ip'](b) == 0xC9, w['eq'](B(b), B(a)),
        w['eq'](w['stack'](b), w['stack'](a)), b.s1 == 9),
        'last02/S1nine universally forces originalC9, NOT BB/BC; B14 held')
    print('PASS any finite01 marker wait + modulo16 02 induction; '
          '05/66 forceS1=9, whereas CC→BB needsS1>=A. '
          'An infinite01 wait is not a successful exit.', flush=True)


def rotation_and_byte_gates():
    for code in (0x6A, 0x6B):
        a = q['State'](f'page_island_rotate_{code:02X}'); p = w['base'](a, code); out = []
        b = w['ex'](a, code, *q['arbitrary_keys'](f'page_island_rotate_keys_{code:02X}'),
                    emitted_outputs=out)
        values = B(a)
        w['prove'](p, And(w['eq'](B(b), [*values[1:], values[0]]),
            w['ip'](b) == code+1, b.r[26] == a.r[26], w['eq'](out, a.m)),
            f'{code:02X} rotates ALL14 B tetras by one, not only numeric12')
    specs = {
        0x67: lambda a, b: And(w['ip'](b) == 0x6A,
            b.r[32] == a.r[35], b.r[35] == a.r[32]),
        0x6C: lambda a, b: And(w['ip'](b) == (N8(0x60) | q['ZeroExt'](4, a.s1)),
                               b.r[38] == 8),
        0x69: lambda a, b: And(b.r[29] == a.r[29]+1,
            w['ip'](b) == If(a.r[29] == a.r[32], N8(0xFB), N8(0x6A))),
        0xFB: lambda a, b: And(b.s1 == a.r[35],
            w['ip'](b) == If(UGE(a.r[2], 5), N8(0xFD), N8(0xFC))),
        0xFD: lambda a, b: And(b.s1 == a.r[35],
            w['ip'](b) == If(a.r[26] == 0, N8(0xF9), N8(0xFE))),
        0xFE: lambda a, b: w['ip'](b) == 0xFC,
        0xFC: lambda a, b: And(w['ip'](b) == 0x68, b.s1 == 8,
            b.r[35] == a.s1, b.r[30] == a.r[31], b.r[33] == a.r[34]),
    }
    for code, claim in specs.items():
        a = q['State'](f'page_island_gate_{code:02X}'); p = w['base'](a, code); out = []
        b = w['ex'](a, code, *q['arbitrary_keys'](f'page_island_gate_keys_{code:02X}'),
                    emitted_outputs=out)
        w['prove'](p, And(claim(a, b), w['eq'](B(b), B(a)),
                         b.r[26] == a.r[26], w['eq'](out, a.m)),
                   f'{code:02X} exact gate, ALL14 B/flag held; no ring write')
    a = q['State']('page_island_F9'); p = w['base'](a, 0xF9); out = []
    b = w['ex'](a, 0xF9, *q['arbitrary_keys']('page_island_F9_keys'), emitted_outputs=out)
    w['prove'](p, And(w['ip'](b) == 0xFC, b.r[31] == a.r[30], b.r[34] == a.r[33],
        *[b.r[j] == a.r[j] for j in range(1,42,3) if j not in (31,34)],
        b.r[26] == a.r[26], w['eq'](out, a.m)),
        'F9 patches selected B byte from A10/A11, holds the other12 tetras; no ring write')
    a = q['State']('page_island_68'); p = w['base'](a, 0x68)
    p.add(a.r[38] == 8, ULE(a.r[29], 7))
    b = w['ex'](a, 0x68, *q['arbitrary_keys']('page_island_68_keys'))
    w['prove'](p, And(w['ip'](b) == If(a.r[29] == 7, N8(5), N8(0x69)),
                     w['eq'](B(b), B(a))), '68 normal byte counter0..7 closes at05, not a free dispatch')


def opaque_page_families():
    for family in ('low_mode', 'read_byte', 'write_byte'):
        for offset in range(7):
            label = f'page_island_{family}_{offset}'
            a = q['State'](label); p = w['base'](a, 0xC9)
            p.add(w['stack'](a)[0] == 0x67, a.s1 == 9,
                  a.r[29] == 0, a.r[38] == 8, a.r[35] == offset)
            if family == 'low_mode': p.add(ULT(a.r[2], 5))
            else: p.add(UGE(a.r[2], 5), a.r[26] == 0 if family == 'write_byte' else a.r[26] != 0)
            page = list(a.m[2:42:3]); assert len(page) == 14
            byte_index = (2*offset+12) % 14
            patch = [a.r[30], a.r[33]]
            expected = list(page)
            if family == 'write_byte': expected[byte_index:byte_index+2] = patch
            out = []; b = w['ex'](a, 0xC9, *q['arbitrary_keys'](label+'_swap_keys'),
                                    emitted_outputs=out)
            w['prove'](p, And(w['ip'](b) == 0x67, w['eq'](B(b), page),
                w['eq'](out[2:42:3], B(a))), label+' genuine first C9 swap', False)
            first = (0x6A, 0x6B, 0x6C, 0x69)*(offset+1)
            special = ((0xFB, 0xFC, 0x68) if family == 'low_mode' else
                       (0xFB, 0xFD, 0xF9 if family == 'write_byte' else 0xFE, 0xFC, 0x68))
            rest = (0x69, 0x6A, 0x6B, 0x6C, 0x68)*(6-offset)
            sequence = (0x67, *first, *special, *rest, 5)
            b = walk(b, p, sequence, label)
            claim = And(w['ip'](b) == 1, b.s1 == 9, w['stack'](b)[0] == 6,
                w['eq'](B(b), expected), b.r[32] == a.r[32], b.r[35] == offset,
                b.r[26] == a.r[26])
            if family != 'low_mode':
                claim = And(claim, b.r[30] == expected[byte_index],
                            b.r[33] == expected[byte_index+1])
            w['prove'](p, claim, family+f'/offset{offset}: ALL14 opaque page; '
                + ('one-byte patch' if family == 'write_byte' else 'entire page restored in B')
                + f'; original05/head06/S1nine after{len(sequence)} words')
            p.push(); p.add(*[page[j] != B(a)[j] for j in range(14)])
            if family == 'write_byte':
                p.add(patch[0] != page[byte_index], patch[1] != page[byte_index+1])
            assert p.check() == sat; p.pop()
    print('PASS 21 universal opcode-data families: all7 offsets, 14 independent '
          'programme tetras and independent patch byte. Next01/02/03/04/BA/CC/CD '
          'forcesC9/head06 by the wait induction; no BB/BC before that C9. '
          'Correct physical page/safe final exit still need native evidence.', flush=True)


def reader_flag_boundary():
    entries = [s for s in states if s[0] == 0xC8]
    assert len(entries) == 19 and all(s[7] and 0 not in s[7] for s in entries)
    assert Counter(s[1][0] for s in entries) == {0x6E: 19}
    for code in (0xC8, 0x6E, 0x61, 0x63, 0x64, 0x66, 0x01, 0x02, 0x03, 0x04,
                 0xBA, 0xCC, 0xCD, 0xC9, 0x67, 0x6A, 0x6B, 0x6C, 0x69, 0xFB, 0xFD):
        a = q['State'](f'page_flag_hold_{code:02X}'); p = w['base'](a, code)
        b = w['ex'](a, code, *q['arbitrary_keys'](f'page_flag_hold_keys_{code:02X}'))
        w['prove'](p, b.r[26] == a.r[26], f'{code:02X} holds reader/write flag', False)
    print('PASS complete C8-inclusive reset cover: ALL19 actualC8 contexts exclude '
          'R26zero. Direct C8/6E/61→63/64/66/.../C9/67→FD preserves the flag, '
          'therefore choosesFE, NOT writerF9, irrespective of payload/keys/waits. '
          'Different intervening routes/earlier reserves/flag repair remain open.', flush=True)


if __name__ == '__main__':
    r['inlet']['immutable_reference']()
    original_call_and_wait_gates()
    rotation_and_byte_gates()
    opaque_page_families()
    reader_flag_boundary()
    r['inlet']['immutable_reference']()
