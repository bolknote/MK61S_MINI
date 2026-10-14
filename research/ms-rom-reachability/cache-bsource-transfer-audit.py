#!/usr/bin/env python3
"""Source-driven A-to-B transfers and DC entrances in all primary ROM words.

Exact one-word universal contracts, not a native keyboard entry. Arbitrary
keys and serial inputs overapproximate the full device. Missing universal
copies do not rule out conditional, encoded or multiword transfers.
"""
from pathlib import Path
import runpy

from z3 import And, Or, ZeroExt, sat, unsat

root = Path(__file__).resolve().parent
q = runpy.run_path(str(root / 'ik1302_symbolic.py'))
State, ex, base, keys = (q[n] for n in
    ('State', 'execute_command', 'base_solver', 'arbitrary_keys'))
byte = lambda lo, hi: ZeroExt(4, lo) | (ZeroExt(4, hi) << 4)
address = lambda a: byte(a.r[36], a.r[39])
top = lambda a: byte(a.st[36], a.st[39])
A = lambda a: a.r[0:36:3]
B = lambda a: a.r[1:36:3]
raw = (0, 3, 9, 12, 18, 21)


def necessary(p, claim):
    p.push()
    p.add(~claim)
    answer = p.check()
    assert answer in (sat, unsat), p.reason_unknown()
    p.pop()
    return answer == unsat


def audit():
    transfers, dc_inputs = [], []
    for code in range(256):
        a = State(f'bsource_transfer_{code:02X}')
        out = []
        b = ex(a, code, *keys(f'bsource_transfer_keys_{code:02X}'),
               emitted_outputs=out)
        p = base(a, code)
        assert p.check() == sat
        no_write = necessary(p, And(*[v == t for v, t in zip(out, a.m)]))
        preserves_b = necessary(p, And(*[v == t for v, t in zip(B(b), B(a))]))
        copies_raw = necessary(p, And(*[b.r[j+1] == a.r[j] for j in raw]))
        copies_word = necessary(p, And(*[v == t for v, t in zip(B(b), A(a))]))
        if copies_raw:
            destinations = q['possible_values'](address(b), base(a, code), 257)
            transfers.append((code, copies_word, no_write, destinations))
            print(f'A→B {code:02X}: raw6={copies_raw}; word12={copies_word}; '
                  f'no_write={no_write}; next=' +
                  ' '.join(f'{v:02X}' for v in destinations), flush=True)
        p.push()
        p.add(address(b) == 0xDC)
        answer = p.check()
        assert answer in (sat, unsat), p.reason_unknown()
        if answer == sat:
            kind = ('return' if necessary(p, address(b) == top(a)) else
                    'vector' if necessary(p, address(b) == byte(a.r[37], a.r[40])) else
                    'other')
            unconditional_b = preserves_b
            joint_b = necessary(p, And(*[v == t for v, t in zip(B(b), B(a))]))
            dc_inputs.append((code, kind, no_write, unconditional_b, joint_b))
            print(f'DC predecessor {code:02X}: kind={kind}; no_write={no_write}; '
                  f'holdsB12={unconditional_b}; holdsB12_on_DC_edge={joint_b}', flush=True)
        p.pop()
    assert [item[0] for item in transfers] == [
        0x16, 0x3F, 0x49, 0x91, 0x98, 0xE1, 0xE4, 0xEC]
    assert all(item[1] and item[2] for item in transfers)
    print('PASS: exact all256 primary words; eight full no-write A→B transfers; '
          'inventory is local only.', flush=True)
    return transfers, dc_inputs


if __name__ == '__main__':
    audit()
