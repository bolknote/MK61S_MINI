#!/usr/bin/env python3
"""CONDITIONAL high77/odd operandB writer, not a native key sequence.

The direct C/operandC writer is globally excluded by cache-bc-77-parity.py.
The remaining even-typeA/odd operandB component calls the originalBB
beforeBC. It can pass only the16 F0..FF byte values, not an arbitrary Ms
byte. Original callers construct all return heads; ALL12 A survive split
across ST0/ST1. Joint native input/source/phase/exchange is still missing.
"""
from pathlib import Path
import runpy

from z3 import And, sat

root = Path(__file__).resolve().parent
source = runpy.run_path(str(root / 'cache-bc-77-producer.py'))
r, w, q = (source[n] for n in ('r', 'w', 'q'))
A, B, ST0, ST1 = (source[n] for n in ('A', 'B', 'ST0', 'ST1'))
walk, double = source['walk'], source['double']


def limited_B_writer_contracts():
    for address in (*range(84, 91), 99):
        label = f'bc77_limited_address{address}_B'; counter = address//7+1
        a = q['State'](label); p = w['base'](a, 0x77)
        p.add(a.r[32] == 10, a.r[29] == 11, a.r[35] == 7, a.r[38] == 12,
            a.r[26] != 0, a.r[25] == a.r[31],
            a.st[1] == 5, a.st[22] == 1, a.st[25] == 0,
            a.st[30] == address % 10, a.st[33] == address // 10)
        b = walk(a, p, (0x77, 0x6D, 0x60, 0x48, 0xB1, 0xB3, 0xBB,
            0xBC, 0x49, 0xBD, *double, 0xBE, 0x63, *([0x64]*counter), 0x66),
            label, only_ring_writer=0xBC)
        p.add(b.m[22] == 15)  # explicit PRIMARY marker assumption, not native injection
        b = walk(b, p, (1, *([2]*counter), 3, 4, 0xBA, 0xCC, 0xCD), label+'_wait')
        buffer = [*B(a)[1:12], q['N4'](15)]
        w['prove'](p, And(w['ip'](b) == 0xC9, w['stack'](b)[0] == 0x67,
            b.r[2] == 5, b.r[23] == 1, b.r[26] == 0,
            b.r[31] == address % 10, b.r[34] == address // 10,
            w['eq'](A(b), buffer),
            w['eq'](ST0(b)[:9], A(a)[1:10]),
            w['eq'](ST1(b)[9:12], [*A(a)[10:12], A(a)[0]]),
            w['eq']([b.st[j] for j in (34, 0, 6, 9, 15, 18)], [a.r[j] for j in w['raw']])),
            label+' CONDITIONAL even-typeA/odd-numberB writer; ALL12 oldA split reserve')
        p.push(); byte = q['BitVec'](label+'_possible_byte', 8)
        p.add(w['byte'](b.r[30], b.r[33]) == byte)
        assert p.check() == sat and q['possible_values'](byte, p, 257) == list(range(0xF0, 0x100))
        p.pop()
    print('PASS eight CONDITIONAL high77/B/BB/BC writer interfaces, seven positions '
          'plus control99. EXACTLY16 source-byte valuesF0..FF, not all256. '
          'ALL12 oldA held in split ST0/ST1. The allowed parity is necessary, '
          'NOT evidence of a native producer, actual Ms byte, safe phase/exit or exchange.', flush=True)


if __name__ == '__main__':
    r['inlet']['immutable_reference']()
    limited_B_writer_contracts()
    r['inlet']['immutable_reference']()
    print('PASS limited component contract only. No new native key protocol or partialK2.', flush=True)
