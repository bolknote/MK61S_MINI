#!/usr/bin/env python3
"""Export one measured candidate at the production function's public symbol."""
import argparse
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--m0', choices=(4, 16, 64), type=int, default=64)
parser.add_argument('--m4', choices=(4, 16, 64), type=int, default=64)
parser.add_argument('--m4-low', action='store_true', help='Use r4 and narrow word loads on M4')
parser.add_argument('--m4-flash', choices=(4, 16, 64), type=int, default=64)
args = parser.parse_args()
source = (HERE / 'candidates.S').read_text()
parts = {
    'm0': source.split('#if defined(__ARM_ARCH_6M__)\n', 1)[1].split('#else\n.cpu cortex-m4', 1)[0],
    'm4': source.split('#else\n.cpu cortex-m4', 1)[1].split('#endif\ncompare own4', 1)[0],
}
for cpu, architecture, words, low in (
    ('m0', 'm0', args.m0, False),
    ('m4', 'm4', args.m4, args.m4_low),
    ('m4_flash', 'm4', args.m4_flash, False),
):
    part = parts[architecture]
    part = part.replace('function \\name\n', '').replace('end \\name\n', '').replace('.L', '.Lmk61_compare_')
    macros = ('compare', 'word_pair', 'byte_pair', 'merged_pair', 'merge') if architecture == 'm0' else ('compare', 'word_pair', 'byte_pair')
    part = '.syntax unified\n' + part + '\ncompare body,' + str(words // 4) + \
        (',1' if low else '') + '\n'
    part += ''.join('.purgem ' + name + '\n' for name in macros)
    for name in (*macros, 'offset', 'cmp_word'):
        part = re.sub(r'\b' + name + r'\b', 'mk61_compare_' + name, part)
    comment = '''/* Bounded, read-only unsigned lexicographic comparison.
 * Returns the ISO C sign; unequal word results may be -1 or +1.
 * Generated from research/memcmp-2026-10-21/candidates.S by export.py. */
'''
    (ROOT / f'code/memcmp_{cpu}.inc').write_text(comment + ''.join(json.dumps(line + '\n') + '\n' for line in part.splitlines()))
