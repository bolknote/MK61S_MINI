#!/usr/bin/env python3
"""Complete original-ROM writers of the early constructor's physical fields.

All768 control words are inspected at the actual tick/sync addresses. For
each candidate, an arbitrary-state/all-keys symbolic execution proves the
exact initial-register source. SAT output values are source contracts only,
NOT native key constructors. Physical cells24/22/34 are respectively the
ordinary M1 sign, M2 marker and M2 type; M2 sign25 is audited as a possible
intermediate. Reference calculator and ROM are never modified.
"""
from pathlib import Path
import runpy

from z3 import sat, unsat

root = Path(__file__).resolve().parent
e = runpy.run_path(str(root / 'cache-stack-lift-ring.py'))
expected = {
    'ik1302': {
        22: {0x32:'R21', 0xA8:'R21', 0xBC:'R19', 0xC7:'R21', 0xE7:'R21', 0xE9:'R21'},
        24: {0xD4:'R21'},
        25: {0x32:'R24', 0xA8:'R24', 0xBC:'R22', 0xC7:'R24', 0xE7:'R24', 0xE9:'R24'},
        34: {0x34:'R33', 0xA3:'R33', 0xA8:'R33', 0xBC:'R31', 0xC7:'R33', 0xE7:'R33', 0xE9:'R33'},
    },
    'ik1303': {
        22: {0x2A:'R21', 0x3A:'ST21', 0x4E:'R21', 0xD8:'R21', 0xDE:'R21'},
        24: {},
        25: {0x2A:'R24', 0x3A:'ST24', 0x4E:'R24', 0xD8:'R24', 0xDE:'R24'},
        34: {0x2A:'R33', 0x3A:'ST33', 0x4E:'R33', 0xD8:'R33', 0xDE:'R33'},
    },
    'ik1306': {22:{0xFF:'R21'}, 24:{}, 25:{0xFF:'R24'}, 34:{0xFF:'R33'}},
}


def audit():
    sources = {}
    for chip, q in e['models'].items():
        tables = q['execute_command'].__globals__
        candidates = {field: [] for field in (22, 24, 25, 34)}
        for code, word in enumerate(tables['COMMANDS']):
            for field in candidates:
                sync = word & 127 if field < 27 else (word >> 7) & 127
                cell = tables['SYNCS'][sync*9+field % 9] & 63
                choices = ([cell] if cell < 60 else
                           [2*(cell-60)+60, 2*(cell-60)+61])
                if any(tables['MICROS'][v] & (1 << 20) for v in choices):
                    candidates[field].append(code)
        assert all(set(candidates[f]) == set(expected[chip][f]) for f in candidates)
        sources[chip] = {field: {} for field in candidates}
        print(chip, 'complete physical writers',
              {field: [f'{v:02X}' for v in codes] for field, codes in candidates.items()},
              flush=True)
        for code in sorted({v for codes in candidates.values() for v in codes}):
            a, out = q['State'](f'early_meta_{chip}_{code}'), []
            q['execute_command'](a, code, *q['arbitrary_keys'](f'early_meta_keys_{chip}_{code}'),
                                 emitted_outputs=out)
            p = q['base_solver'](a, code)
            assert p.check() == sat
            for field in candidates:
                if code not in candidates[field]:
                    continue
                source = expected[chip][field][code]
                group, index = ('st', int(source[2:])) if source.startswith('ST') else ('r', int(source[1:]))
                p.push()
                p.add(out[field] != getattr(a, group)[index])
                assert p.check() == unsat, (chip, code, field, source)
                p.pop()
                target = 7 if field == 34 else 15
                p.push()
                p.add(out[field] == target, a.m[field] != target)
                assert p.check() == sat
                p.pop()
                sources[chip][field][code] = source
                print(f'  {code:02X}: field{field}←{source}; arbitrary input can create{target:X}', flush=True)
    print('PASS ALL768 ROM words: ordinary M1-sign24 has ONLY primaryD4←R21. '
          'BC differs: M2-sign25←B7/R22, marker22←B6/R19, type34←B10/R31. '
          'These are exact local feeds, not reached native constructors.', flush=True)
    return sources


if __name__ == '__main__':
    audit()
