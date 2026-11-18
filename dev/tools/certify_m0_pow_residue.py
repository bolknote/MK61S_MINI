#!/usr/bin/env python3
"""Check the signed-residue pow bounds and its maximum limb-product count."""
import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path

from certify_m0_pow_log_side import GAP, ROOT, arithmetic

WORDS = 3072
BITS = 16*WORDS
MAX_DENOMINATOR_SHIFT = 116


def work(width, max_squares):
    # Immediately before a square with j squares still to do, the
    # current power is bounded by the 2^j-th root of a bound on the
    # final power. Its residue cannot be larger than the exact integer.
    limbs = [min(WORDS, (width+(16 << j)-1)//(16 << j))
             for j in range(max_squares+1)]
    squares = sum(n*(n+1)//2 for n in limbs[1:])
    short_products = 4*sum(limbs[:-1])
    return squares, short_products, limbs[0]


def certify():
    assert arithmetic()['unresolved_gap'] == f'2^-{GAP}'
    assert GAP > MAX_DENOMINATOR_SHIFT+2
    # For |t| <= 1/4, |exp(t)-1| <= |t|/(1-|t|) < 2*|t|.
    assert 1/(1-Fraction(1,4)) < 2
    # The common binary scale is removed exactly. A modulus of 2^w
    # suffices when |D|<2^(w-1), including D=0 and either sign.
    # After the width guard, either integer power is below 2^(N+1).
    # For the inverse case their product is also below 2^(N+1).
    n = BITS+GAP-2
    individual_width, inverse_sum = n+1, n+2
    maximum_squares = n.bit_length()-1
    assert maximum_squares == 15
    work_by_width = [work(b,maximum_squares) for b in range(individual_width+1)]

    squares, short, _ = work_by_width[individual_width]
    positive_products = 2*squares+short
    inverse_products = 0
    for x_width in range(1,individual_width+1):
        m_width = inverse_sum-x_width
        x_square, x_short, x_limbs = work_by_width[x_width]
        m_square, _, m_limbs = work_by_width[m_width]
        inverse_products = max(inverse_products,x_square+x_short+m_square+x_limbs*m_limbs)

    # Each diagonal has at most WORDS unsigned 16x16 products. The
    # incoming carry is bounded by WORDS*(radix-1).
    radix = 1 << 16
    assert WORDS*(radix-1)*radix < 1 << 64
    assert (radix-1)**2+2*(radix-1) == (1 << 32)-1
    # With the rescue cutoffs, even the estimates with scale alignment
    # fit in a signed 128-bit value. The first scale corresponds to p,
    # and the second to q, so bounding their maxima independently is safe.
    assert (1075+54)*((1 << 63)+(1 << MAX_DENOMINATOR_SHIFT))+2+MAX_DENOMINATOR_SHIFT < 1 << 127

    source = ROOT/'code/native_eabi_m0_pow_residue.inc'
    assert f'constexpr unsigned MaximumWords = {WORDS};' in source.read_text()
    paths = (Path(__file__),source,ROOT/'code/native_eabi_m0_cr.cpp',
             ROOT/'code/native_eabi_m0_pow_log_side.inc',ROOT/'code/native_eabi_m0_pow_stream.inc')
    # For positive y at least one aligned power has zero shift. For
    # negative y, closeness gives 2^s < 2*A*B <= 2^(53*p+54*q+1),
    # so the integer bound s is at most 53*p+54*q.
    numerator_limits = {}
    for k in range(11):
        q = 1 << k
        assert 54*q+k <= n
        numerator_limits[str(q)] = dict(positive=(n-k)//53, inverse=(n-k-54*q)//53)
    return dict(status='PASS_RESIDUE_BOUND', practical_uniform_latency_established=False,
                log_gap_bits=GAP, maximum_residue_bits=BITS, maximum_product_width_bound=n,
                residue_array_bytes=3*WORDS*2, maximum_squarings_per_power=maximum_squares,
                maximum_limb_products_positive=positive_products,
                maximum_limb_products_inverse=inverse_products,
                sufficient_numerator_limits_by_denominator=numerator_limits,
                source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
                               for p in paths})


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--json', type=Path)
    args = parser.parse_args()
    if not __debug__:
        raise RuntimeError('Enable Python assertions to verify the certificate')
    result = certify()
    if args.json:
        args.json.write_text(json.dumps(result,indent=2)+'\n')
    print(result)
