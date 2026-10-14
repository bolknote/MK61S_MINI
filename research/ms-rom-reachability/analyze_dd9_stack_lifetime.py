#!/usr/bin/env python3
"""Selector9 DD return lifetimes with reset-projected, exact return stacks.

The goal is input ROM60 with R26=1, R2>=5, and R25=R31 before any
following R38 assignment. Initial chip data and per-tick keys/ring are
arbitrary. No positive result is a physical calculator protocol.
"""
import argparse
import runpy
import sys
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--mode', choices=('low', 'high', 'all'), default='low')
parser.add_argument('--limit', type=int, default=20000)
parser.add_argument('--complete', action='store_true')
parser.add_argument('--proved-no77', action='store_true',
                    help='also use the separately proved absence of 77/selector9')
parser.add_argument('--verify-candidate', action='store_true')
parser.add_argument('--check-certificate', action='store_true')
parser.add_argument('--expect-excluded', action='store_true')
args = parser.parse_args()
root = Path(__file__).resolve().parent
sys.argv = ['analyze_dd_contexts.py', '--selector', '9']
inventory = runpy.run_path(str(root / 'analyze_dd_contexts.py'))
engine = runpy.run_path(str(root / 'analyze_dd_stack_lifetime.py'))
contexts = [(ip, sp, tuple(record['vectors']))
            for (ip, sp), record in sorted(inventory['contexts'].items())]
print(f'Using all {len(contexts)} projected D4/D6 seeds; exact stacks and '
      'their vector classes are retained, marker/type domains are relaxed.', flush=True)
report = engine['run'](mode=args.mode, limit=args.limit, complete=args.complete,
                       selector_value=9, bootstrap=True, seed_contexts=contexts,
                       selector9_gate=args.proved_no77)
if args.verify_candidate and report['path']:
    first = report['path'][0]
    vectors = next(v for ip, sp, v in contexts if (ip, sp) == first)
    engine['verify'](report['path'], args.mode, selector_value=9,
                     bootstrap=True, vectors=vectors,
                     selector9_gate=args.proved_no77)
if args.check_certificate:
    engine['check_certificate'](report, args.mode)
if args.expect_excluded:
    assert report['excluded'], 'selector9/bootstrap has not been excluded for these seeds'
