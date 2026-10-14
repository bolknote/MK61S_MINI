#!/usr/bin/env python3
"""Cross-check the unary/pair reset covers against keyboard-only traces.

This is a regression check, not a completeness proof. All observations
must fit ONE core context and all of its tracked field/pair projections.
"""
import json
import runpy
import subprocess
from collections import defaultdict
from pathlib import Path

root = Path(__file__).resolve().parent
if 'restore_pairs' not in globals():
    restore_pairs = runpy.run_path(str(root / 'analyze_restore_field_pairs.py'),
                                  init_globals={'all_pairs':True})
rp = restore_pairs
rf = rp['f']
by_key = defaultdict(list)
for state in rp['domains']:
    by_key[state[0], state[1]].append(state)


def fits_core(state, row):
    _, _, vector, selectors, delta, r38, dr38, r26, types = state[:9]
    if vector == 'diagonal':
        if row['vector'] % 16 != row['vector'] // 16:
            return False
    elif vector is not None and row['vector'] != vector:
        return False
    if row['s1'] not in selectors:
        return False
    if delta is not None and (row['s1']-row['r35']) % 16 != delta:
        return False
    if r38 is not None and row['r38'] not in r38:
        return False
    if dr38 is not None and (row['r38']-row['r35']) % 16 != dr38:
        return False
    if r26 is not None and row['r26'] not in r26:
        return False
    assert types is None, 'extend native capture before adding type fields'
    return True


def fits_fields(state, row):
    values = row['values']
    if not all(mask & (1 << v) for mask, v in zip(rf['domains'][state], values)):
        return False
    return all(mask & (1 << (16*values[i]+values[j]))
               for mask, (i, j) in zip(rp['domains'][state], rp['PAIRS']))


cases = json.loads(subprocess.check_output(
    ['node', str(root / 'probe_restore_domains_keyboard.cjs'), '--json'], text=True))
count = 0
for case in cases:
    for row in case['records']:
        candidates = by_key[row['ip'], tuple(row['sp'])]
        fitting = [state for state in candidates if fits_core(state, row)]
        assert any(fits_fields(state, row) for state in fitting), (
            case['name'], row, 'core candidates', fitting)
        count += 1
    print(f"PASS {case['name']}: {len(case['records'])} boundary states fit "
          'one common core/unary/pair context', flush=True)
print(f"PASS: {count} keyboard-only observations, {len(rf['NAMES'])} nibbles "
      f"and {len(rp['PAIRS'])} pairs each. "
      'No native state assignment.', flush=True)
