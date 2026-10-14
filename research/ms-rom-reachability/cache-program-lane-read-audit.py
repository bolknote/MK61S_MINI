#!/usr/bin/env python3
"""C9 is the sole observer of the whole M3 program lane in all three ROMs.

Exact paired one-command induction contract, arbitrary R/ST/scalars, keys and
serial streams. Corresponding non-M3 serial inputs are shared; every M3 input
tetra may differ independently both in the current and next page. A prior
backup in R/ST or a primary-chip M3-to-M2 export is not excluded. No reference
calculator state or original ROM is edited.
"""
import json
from pathlib import Path
import runpy
import subprocess

from z3 import And, sat, unsat

root = Path(__file__).resolve().parent
program = tuple(range(2, 42, 3))
non_program = tuple(j for j in range(42) if j not in program)


def check(chip, expected_observers=()):
    q = runpy.run_path(str(root / 'ik1302_symbolic.py'))
    rom = json.loads(subprocess.check_output([
        'node', '-e', 'console.log(JSON.stringify(require(process.argv[1])[process.argv[2]]))',
        str(q['ROM_PATH']), chip], text=True))
    q['execute_command'].__globals__.update(
        COMMANDS=rom['команды'], SYNCS=rom['синхропрограммы'], MICROS=rom['микрокоманды'])
    State, ex, base, keys = (q[name] for name in
                           ('State', 'execute_command', 'base_solver', 'arbitrary_keys'))
    observers = []
    for code in range(256):
        a = State(f'secondary_no_program_{chip}_{code:02X}')
        other = State(f'secondary_other_program_{chip}_{code:02X}')
        paired = a.copy()
        for j in program:
            paired.m[j] = other.m[j]
        next_a = State(f'secondary_next_page_{chip}_{code:02X}')
        next_other = State(f'secondary_other_next_page_{chip}_{code:02X}')
        next_b = list(next_a.m)
        for j in program:
            next_b[j] = next_other.m[j]
        pins = keys(f'secondary_no_program_keys_{chip}_{code:02X}')
        oa, ob = [], []
        b = ex(a, code, *pins, serial_inputs=next_a.m, emitted_outputs=oa)
        c = ex(paired, code, *pins, serial_inputs=next_b, emitted_outputs=ob)
        p = base(a, code)
        assert p.check() == sat
        claims = [v == t for name in ('r', 'st')
                  for v, t in zip(getattr(b, name), getattr(c, name))]
        claims += [getattr(b, name) == getattr(c, name)
                   for name in ('s', 's1', 'l', 't', 'carry')]
        claims += [b.m[j] == c.m[j] for j in non_program]
        claims += [oa[j] == ob[j] for j in non_program]
        claims += [oa[j] == a.m[j] for j in program]
        claims += [ob[j] == paired.m[j] for j in program]
        p.add(~And(*claims))
        answer = p.check()
        assert answer in (sat, unsat), p.reason_unknown()
        if answer == sat:
            observers.append(code)
            if chip == 'ИК1302' and code == 0xC9:
                # Positive sensitivity/control: the paired test must detect
                # the genuine reader, not accidentally hide every M3 input.
                p = base(a, code)
                assert p.check() == sat
                swap = And(*[b.r[1+3*j] == a.m[2+3*j] for j in range(14)],
                           *[oa[2+3*j] == a.r[1+3*j] for j in range(14)],
                           *[c.r[1+3*j] == paired.m[2+3*j] for j in range(14)],
                           *[ob[2+3*j] == paired.r[1+3*j] for j in range(14)])
                p.add(~swap)
                assert p.check() == unsat
                print('PASS: primary C9 really swaps all14 M3 tetras with B;',
                      'paired observer check detects it.', flush=True)
        if code % 64 == 63:
            print('PASS:', chip, code+1, '/256 words;',
                  'potential M3 observers', [f'{v:02X}' for v in observers], flush=True)
    assert observers == list(expected_observers), (chip, observers, expected_observers)
    if not observers:
        print('PASS:', chip, 'all256 words ignore all14 M3 tetras, including38/41;',
              'R/ST/scalars/non-M3 outputs independent; M3 passes unchanged;',
              'inductive for arbitrary incoming M3-only differences.', flush=True)
    else:
        print('PASS:', chip, 'all255 words exceptC9 ignore all14 M3 tetras;',
              'onlyC9 observes/writes the program lane.', flush=True)


if __name__ == '__main__':
    check('ИК1302', expected_observers=(0xC9,))
    for chip in ('ИК1303', 'ИК1306'):
        check(chip)
    print('PASS: all768 ROM words; C9 is the sole direct program-lane reader; '
          'no direct program-lane reader or numeric exporter in either '
          'secondary chip.', flush=True)
    print('LIMIT: prior R/ST backups and primary M3-to-M1/M2 transfers remain '
          'open; this is not a full-system partial-K2 impossibility theorem.', flush=True)
