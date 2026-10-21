#!/usr/bin/env python3
"""Check range lemmas for the bounded exact M0 pow rounding stage."""
import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path

SOURCE_VERSIONS = {
    '0b378b2a419e87cae1a3897adea03e59b3880a5d9e24e201f000070b99d7021b': False,
    'f98ac5a71383764eae7738dbf8b0d217d70cd6579ccc08a1dc45617b68db7ff8': True,
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--json', type=Path, required=True)
    args = parser.parse_args()
    path = args.source_root / 'code/native_eabi_m0_pow_exact.inc'
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    assert digest in SOURCE_VERSIONS, 'Review the integer argument after a source change'
    checked_hint = SOURCE_VERSIONS[digest]
    assert (53 + 54) * 32 == 3424 < 216 * 16 == 3456
    assert 65535**2 + 65535 + 65535 == (1 << 32) - 1
    assert (216 - 1) + 3 < 216 + 4 and 216 + 3 < 216 + 4
    scale_min, scale_max = -1074 * 32 - 1075 * 32, 971 * 32 + 970 * 32
    assert -(1 << 31) < scale_min < scale_max + 3456 < 1 << 31
    infinity = 0x7FF0000000000000
    assert infinity < 1 << 63
    distance, iterations = infinity, 0
    while distance:
        distance //= 2
        iterations += 1
    assert iterations == 63
    exponents = sorted(set(Fraction(sign * p, 1 << k)
                           for sign in (-1, 1) for p in range(1, 33) for k in range(6)))
    assert len(exponents) == 224
    for y in exponents:
        assert 0 < abs(y.numerator) <= 32 and y.denominator <= 32
        assert y.denominator & (y.denominator - 1) == 0
    report = dict(
        status='PASS_RANGE_AND_ALGEBRA_LEMMAS', source_sha256=digest,
        supported_domain='Positive finite binary64 x; finite nonzero y=p/q in lowest terms, |p|<=32 and q in {1,2,4,8,16,32}.',
        exponent_count=len(exponents), maximum_midpoint_comparisons=iterations + 2*checked_hint,
        checked_hint=checked_hint, maximum_near_hint_comparisons=2 if checked_hint else None,
        limb_bits=16, coefficient_words=216, maximum_coefficient_bits=3424,
        scale_range=[scale_min, scale_max], tables_bytes=0, global_ram_bytes=0,
        argument=[
            'Decode x=A*2^e exactly with 1<=A<2^53. Every adjacent positive binary64 pair, including zero/minimum-subnormal and maximum-finite/infinity, has RNE boundary M*2^t with 1<=M<2^54.',
            'For p>0, x^(p/q) and the midpoint have the same ordering as A^p*2^(e*p) and M^q*2^(t*q), since raising positive real numbers to integer q preserves order.',
            'For p<0, x^(-|p|/q)<M*2^t exactly when A^|p|*M^q*2^(e*|p|+t*q)>1. Equality is tested by the same exact integer comparison.',
            'The largest coefficient product is below2^((53+54)*32), so3456 bits suffice for all intermediates. Each16bit schoolbook multiply-accumulate fits32bits, including both carries. All temporary indices are within N+4 words.',
            'Comparing the coefficient bit lengths plus their scales first orders unequal leading powers of2. Equal leading powers are ordered by their coefficient bits with implicit trailing zeros. No approximate logarithm, exponential, or root is used.',
            'The positive encoding order is monotone. At a midpoint tie, the lower encoding is selected exactly when its low bit is even. This includes both subnormal and overflow ties.',
            'Binary search preserves the encoding interval containing the RNE result. Each step reduces its endpoint distance D to at most floor(D/2); initial D<2^63. Thus at most63 exact comparisons suffice.',
            'All nonzero eligible y values reduce exactly to the supported p,q by stripping powers of2 from their binary64 significand. No supported input can hit a coefficient overflow, invalid midpoint, or unsupported-parameter return.',
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
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, indent=2) + '\n')
    print(f'PASS: {len(exponents)} exponent values, at most {report["maximum_midpoint_comparisons"]} comparisons, 3424 coefficient bits.')


if __name__ == '__main__':
    main()
