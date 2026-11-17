#!/usr/bin/env python3
"""Replay the same binade verifier with FLINT's exact polynomial product."""
import sys

from flint import fmpz_poly

import midpoint_binade
import midpoint_grid


def convolve(first, second, count):
    exact = fmpz_poly(first)*fmpz_poly(second)
    coefficients = [int(value) for value in exact.coeffs()[:count]]
    return coefficients+[0]*(count-len(coefficients))


# Spawned verifier workers also load this module before loading their jobs.
# All interval formulas and modular checks still run in midpoint_grid.
midpoint_grid.convolve = convolve

if __name__ == '__main__':
    if sys.argv[1:2] != ['verify']:
        raise SystemExit('Use midpoint_binade_flint_verify.py verify ...')
    raise SystemExit(midpoint_binade.main())
