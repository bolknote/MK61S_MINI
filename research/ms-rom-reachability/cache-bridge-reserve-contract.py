#!/usr/bin/env python3
"""The exact double-restore bridge creates no new numeric-ST raw reserve.

Local universal paired contract, not a native keyboard completeness theorem.
ST may contain an independent backup before entry; this proof does not erase
or exclude that possibility, other chips, or other paths. No emulator setters.
"""
from pathlib import Path
import runpy

from z3 import And

root = Path(__file__).resolve().parent
w = runpy.run_path(str(root / 'cache46-writer-contracts.py'))
State, ex, base, keys, ip, eq, prove = (w[name] for name in
    ('State', 'ex', 'base', 'keys', 'ip', 'eq', 'prove'))
raw = (0, 3, 9, 12, 18, 21)
sequence = (0x8C, 0x91, 0x92, 0x93, 0x94, 0x95, 0x98, 0x9A,
            0x93, 0x94, 0x95, 0x98, 0x9A, 0x8D)


def main():
    a = State('bridge_reserve_first')
    other = State('bridge_reserve_other')
    paired = a.copy()
    for j in raw:
        paired.r[j] = other.r[j]
    p = base(a, 0x8C)
    pages = [State(f'bridge_reserve_page{j}').m for j in range(len(sequence)+1)]
    a.m = pages[0]
    paired.m = pages[0]
    b, c = a, paired
    for j, code in enumerate(sequence):
        prove(p, And(ip(b) == code, ip(c) == code),
              f'paired bridge command{j} {code:02X} forced', False)
        pins = keys(f'bridge_reserve_keys{j}')
        out_b, out_c = [], []
        b = ex(b, code, *pins, serial_inputs=pages[j+1], emitted_outputs=out_b)
        c = ex(c, code, *pins, serial_inputs=pages[j+1], emitted_outputs=out_c)
        prove(p, And(eq(out_b, pages[j]), eq(out_c, pages[j])),
              f'paired bridge command{j} no outgoing write', False)
    prove(p, And(*[b.r[j] == a.r[j] for j in raw],
                 *[c.r[j] == paired.r[j] for j in raw]),
          'bridge recovers both independent sets of six raw tetras in A')
    prove(p, eq(b.st, c.st),
          'whole ST after8D is independent of the six raw A input tetras')
    prove(p, eq([b.r[j] for j in range(42) if j not in raw],
                [c.r[j] for j in range(42) if j not in raw]),
          'all R fields outside raw A6 after8D have no raw-input dependence')
    print('LIMIT: no NEW R/ST reserve from this bridge; prior reserves, '
          'scalars, other chips and other routes are not globally excluded.', flush=True)


if __name__ == '__main__':
    main()
