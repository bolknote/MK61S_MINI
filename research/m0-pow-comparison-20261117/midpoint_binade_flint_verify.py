#!/usr/bin/env python3
"""Replay the same binade verifier with FLINT's exact polynomial product."""
import sys

import midpoint_binade
from midpoint_grid import use_flint_products


# Spawned verifier workers also load this module before loading their jobs.
# All interval formulas and modular checks still run in midpoint_grid.
use_flint_products()

if __name__ == '__main__':
    if sys.argv[1:2] != ['verify']:
        raise SystemExit('Use midpoint_binade_flint_verify.py verify ...')
    raise SystemExit(midpoint_binade.main())
