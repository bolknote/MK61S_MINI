#!/usr/bin/env python3
"""Check range lemmas for the bounded exact M0 pow rounding stage."""

import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import re

SOURCE_VERSIONS = {
    '0b378b2a419e87cae1a3897adea03e59b3880a5d9e24e201f000070b99d7021b': False,
    'f98ac5a71383764eae7738dbf8b0d217d70cd6579ccc08a1dc45617b68db7ff8': True,
}
EXPANDED_SOURCE = 'de453513894bb204fd1b80d623f80760a70a7c62139187c76353770ffebb7ef9'
ODD_COEFFICIENT_SOURCE = '6696a03a2b7e59bf278e9b9bb5d287d8388c748e1399eb34c96677c22468ca25'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--json', type=Path, required=True)
    args = parser.parse_args()
    path = args.source_root / 'code/native_eabi_m0_pow_exact.inc'
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    source = path.read_text()
    words = int(re.search(r'enum \{N=(\d+)[,}]', source)[1])
    odd_coefficients = digest == ODD_COEFFICIENT_SOURCE
    if digest in SOURCE_VERSIONS:
        checked_hint = SOURCE_VERSIONS[digest]
        p_max, k_max = 32, 5
    elif odd_coefficients:
        assert words == 432
        checked_hint = True
        p_max, k_max = 16*words, 12
    else:
        assert digest == EXPANDED_SOURCE, 'Review the integer argument after a source change'
        assert words == 432
        checked_hint = True
        p_max, k_max = (16*words-54)//53, 7
    assert 65535**2 + 65535 + 65535 == (1 << 32) - 1
    assert (words - 1) + 3 < words + 4 and words + 3 < words + 4
    q_max = 1 << k_max
    x_scale_max = 1023 if odd_coefficients else 971
    scale_min, scale_max = -1074*p_max-1075*q_max, x_scale_max*p_max+970*q_max
    assert -(1 << 31) < scale_min < scale_max + 16*words < 1 << 31
    infinity = 0x7FF0000000000000
    assert infinity < 1 << 63
    distance, iterations = infinity, 0
    while distance:
        distance //= 2
        iterations += 1
    assert iterations == 63
    exponents = {Fraction(sign*p, 1 << k) for sign in (-1, 1)
                 for p in range(1, min(p_max,16*words//53)+1) for k in range(min(k_max,7)+1)}

    def coefficient_bound(y):
        base = 53*abs(y.numerator)
        midpoint = 54*y.denominator
        return max(base,midpoint) if odd_coefficients and y>0 else base+midpoint

    exponents = sorted(y for y in exponents if coefficient_bound(y) <= 16*words)
    assert len(exponents) == (1041 if odd_coefficients else 912 if words == 432 else 224)
    assert all(Fraction(sign * p, 1 << k) in exponents
               for sign in (-1, 1) for p in range(1, 33) for k in range(6))
    maximum_bits = 0
    for y in exponents:
        assert 0 < abs(y.numerator) <= p_max and y.denominator <= q_max
        assert y.denominator & (y.denominator - 1) == 0
        maximum_bits = max(maximum_bits, coefficient_bound(y))
    assert maximum_bits <= 16*words
    report = dict(
        status='PASS_RANGE_AND_ALGEBRA_LEMMAS', source_sha256=digest,
        supported_domain=('Positive finite binary64 x; finite nonzero y=p/q in lowest terms; '
                          f'|p|<={p_max}, q is a power of 2 <= {q_max}. '
                          + ('For arbitrary base and search hint, max(53*p,54*q) for p>0 '
                             f'or 53*|p|+54*q for p<0 is at most {16*words}.'
                             if odd_coefficients else f'53*|p|+54*q <= {16*words}.')),
        exponent_count=len(exponents), maximum_midpoint_comparisons=iterations + 2*checked_hint,
        checked_hint=checked_hint, maximum_near_hint_comparisons=2 if checked_hint else None,
        limb_bits=16, coefficient_words=words, maximum_coefficient_bits=maximum_bits,
        scale_range=[scale_min, scale_max], tables_bytes=0, global_ram_bytes=0,
        argument=[
            'Decode x=A*2^e exactly with 1<=A<2^53. Every adjacent positive binary64 pair, including zero/minimum-subnormal and maximum-finite/infinity, has RNE boundary M*2^t with 1<=M<2^54.',
            'For p>0, x^(p/q) and the midpoint have the same ordering as A^p*2^(e*p) and M^q*2^(t*q), since raising positive real numbers to integer q preserves order.',
            'For p<0, x^(-|p|/q)<M*2^t exactly when A^|p|*M^q*2^(e*|p|+t*q)>1. Equality is tested by the same exact integer comparison.',
            'Each 16-bit schoolbook multiply-accumulate fits 32 bits, including both carries. All temporary indices are within N+4 words.',
            'Comparing the coefficient bit lengths plus their scales first orders unequal leading powers of2. Equal leading powers are ordered by their coefficient bits with implicit trailing zeros. No approximate logarithm, exponential, or root is used.',
            'The positive encoding order is monotone. At a midpoint tie, the lower encoding is selected exactly when its low bit is even. This includes both subnormal and overflow ties.',
            'Binary search preserves the encoding interval containing the RNE result. Each step reduces its endpoint distance D to at most floor(D/2); initial D<2^63. Thus at most63 exact comparisons suffice.',
            'The exponent is reduced exactly to coprime p and q by stripping powers of two. Every input inside the arbitrary-base, arbitrary-hint bound fits the coefficient arrays.',
        ],
        limitations=[
            'The algebra establishes the exact algorithm on its stated domain; this is not machine-checked verification of all C++ instructions.',
            'Source-pinned ARM qualification, ABI checks and a bounded stack measurement are separate evidence.',
            'This stage does not prove totality for binary64 exponents outside the supported set. The general undecided pow trap is retained.',
        ])
    if checked_hint:
        report['argument'].append(
            'The initial hint is never trusted as an enclosure. Exact midpoint comparisons either isolate the hinted encoding or its successor, or leave an interval that still contains the RNE encoding. The remaining binary search has distance no larger than the original infinity encoding, so it needs at most63 more comparisons. At most two hint comparisons plus63 search comparisons give the bound65, for every initialized unsigned hint word.')
        report['argument'].append(
            'If the RNE encoding is the hint or its immediate successor, the exact hint tests close the encoding interval after at most two comparisons. This is a search optimization and does not require an approximation error assumption.')
    if odd_coefficients:
        assert 54*q_max < 1<<32
        assert (3**4096).bit_length()+54 <= 16*words
        assert (3**4362).bit_length() > 16*words
        report['argument'] += [
            'Moving powers of two from the x coefficient into its scale is exact. Adjacent positive encodings have an odd midpoint coefficient, including across binades and at the underflow and overflow boundaries.',
            'For positive p the two coefficient powers fit independently. For negative p their product must fit. The actual bound uses the odd coefficients present at the examined midpoint, so it can be smaller than the full-width bound.',
            'If factor bit width is w, each repetition grows the integer by at least w-1 bits. Rejecting a lower bound larger than the available width cannot discard any product that fits. Each multiply initializes and checks exactly used+ceil(w/16) temporary limbs, at most N+4.',
            'For negative p, compare the most significant bit of the scaled product to the bit at binary exponent zero. If they match, equality holds only for an odd coefficient of one. Any wider odd coefficient has a nonzero lower bit.',
        ]
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, indent=2) + '\n')
    print(f'PASS: {len(exponents)} exponent values, at most {report["maximum_midpoint_comparisons"]} comparisons, {maximum_bits} coefficient bits.')


if __name__ == '__main__':
    main()
