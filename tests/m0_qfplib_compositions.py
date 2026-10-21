"""Deterministic comparisons with explicitly composed Qfplib functions."""
import math
import random

from m0_mpfr_oracle import Oracle, bits, real


FORMULAS = {
    'asin': 'atan2(x, sqrt(mul(sub(1,x), add(1,x))))',
    'acos': 'atan2(sqrt(mul(sub(1,x), add(1,x))), x)',
    'log10': 'mul(ln(x), 0x1.bcb7b1526e50ep-2)',
    'pow': 'exp(mul(y, ln(x)))',
}


def corpus():
    rng = random.Random(0x61C04F05)
    oracle = Oracle()
    groups = []

    def add(op, stream, pairs, *, reference=None, formula=None, domain=None):
        vectors = []
        for a, b in pairs:
            x, y = real(a), real(b)
            assert math.isfinite(x) and math.isfinite(y)
            if reference=='qfp_composed_pow_integer':
                assert op=='pow' and x<0 and y.is_integer()
            else:
                assert (-1 <= x <= 1) if op in ('asin', 'acos') else x > 0
            expected = oracle.reference(op, a, b) if op == 'pow' else oracle.reference(op, a)
            vectors.append((a, b, expected))
        groups.append(dict(
            operation=op, stream=stream, own_symbol=f'_ZN12compact_math{len(op)}{op}E' + ('dd' if op == 'pow' else 'd'),
            qfplib_symbol=reference or 'qfp_composed_' + op, kind=0 if op == 'pow' else 1,
            vectors=vectors, reference_kind='qfplib_composition',
            reference_formula=formula or FORMULAS[op],
            reference_domain=domain or ('positive finite base, finite exponent' if op == 'pow' else
                             '[-1,1]' if op in ('asin', 'acos') else 'positive finite input')))

    ordinary = [(bits(rng.uniform(-1, 1)), 0) for _ in range(256)]
    edges = [(bits(x), 0) for x in (-1., -.5, -0., 0., .5, 1.)]
    for center in (bits(.5), bits(1.)):
        for delta in (-1024, -127, -15, -2, -1, 0, 1, 2, 15, 127, 1024):
            a = center + delta
            if a <= bits(1.):
                edges.extend([(a, 0), (a | (1 << 63), 0)])
    tiny = [(bits(math.ldexp(sign * 1.25, exponent)), 0)
            for exponent in (-1022, -900, -100, -54, -53, -52, -27, -10)
            for sign in (-1, 1)]
    for op in ('asin', 'acos'):
        add(op, 'composed_ordinary', ordinary)
        add(op, 'composed_boundaries', edges)
        add(op, 'composed_tiny_normal', tiny)

    logarithms = [(bits(math.ldexp(rng.uniform(1, 2), rng.randrange(-1000, 1000))), 0)
                  for _ in range(256)]
    add('log10', 'composed_normal_exponents', logarithms)
    add('log10', 'composed_near_one', [(bits(1.) + delta, 0)
                                     for delta in range(-128, 129)])
    add('log10', 'composed_powers_of_ten', [(bits(10. ** exponent), 0)
                                          for exponent in range(-300, 301, 5)])

    add('pow', 'composed_ordinary', [(bits(2. ** rng.uniform(-8, 8)), bits(rng.uniform(-8, 8)))
                                   for _ in range(256)])
    add('pow', 'composed_wide_exponents',
        [(bits(math.ldexp(rng.uniform(1, 2), rng.randrange(-900, 900))), bits(rng.uniform(-1, 1)))
         for _ in range(256)])
    near = []
    for delta in (-128, -17, -2, -1, 1, 2, 17, 128):
        for y in (-2. ** 48, -17., -.5, .5, 17., 2. ** 48):
            near.append((bits(1.) + delta, bits(y)))
    add('pow', 'composed_near_one', near)
    signed_formula='y=0:1; y=1:x; y=-1:div(1,x); y=2:mul(x,x); otherwise apply integer parity sign to exp(mul(y,ln(abs(x))))'
    signed_domain='negative finite base, finite integer exponent'
    add('pow','composed_negative_integer',
        [(bits(-2.**rng.uniform(-8,8)),bits(float(rng.randrange(-8,9)))) for _ in range(256)],
        reference='qfp_composed_pow_integer',formula=signed_formula,domain=signed_domain)
    add('pow','composed_negative_wide',
        [(bits(-math.ldexp(rng.uniform(1,2),rng.randrange(-900,900))),bits(float(rng.randrange(-32,33)))) for _ in range(256)],
        reference='qfp_composed_pow_integer',formula=signed_formula,domain=signed_domain)
    signed_near=[]
    for delta in (-128,-17,-2,-1,1,2,17,128):
        for y in (-2.**48,-17.,17.,2.**48,2.**52-1,2.**52+1,2.**53-1,2.**53+2):
            signed_near.append(((bits(1.)+delta)|(1<<63),bits(y)))
    add('pow','composed_negative_near_one',signed_near,
        reference='qfp_composed_pow_integer',formula=signed_formula,domain=signed_domain)
    add('pow','composed_exact_exponents',
        [(bits(math.ldexp(rng.uniform(1,2),rng.randrange(-900,900))),bits(rng.choice((1.,-1.,2.,.5,-.5)))) for _ in range(256)],
        reference='qfp_composed_pow_exact',
        formula='y=1:x; y=-1:div(1,x); y=2:mul(x,x); y=0.5:sqrt(x); y=-0.5:div(1,sqrt(x)); otherwise exp(mul(y,ln(x)))',
        domain='positive finite base; exponent in {1,-1,2,0.5,-0.5}')
    return groups
