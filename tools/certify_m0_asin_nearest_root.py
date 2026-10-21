#!/usr/bin/env python3
"""Bound the RP2040 nearest-root asin/acos geometry with exact rationals."""
import argparse
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path

from certify_m0_asin_fast import certificate, verify_atan_table


def function(text, name):
    start = text.index('static ', text.index(name) - 100)
    opening = text.index('{', text.index(name, start))
    depth = 1
    end = opening + 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[start:end]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--baseline-root', type=Path,
                        help='Optional additional comparison with the previous source tree')
    parser.add_argument('--json', type=Path, required=True)
    args = parser.parse_args()
    name = 'code/native_eabi_m0_asin.inc'
    source = (args.source_root / name).read_text()
    baseline_source = (args.baseline_root / name).read_text() if args.baseline_root else None
    assert 'mk61_m0_math_udiv32(numerator+(denominator>>1),denominator)' in source
    assert 'const U Y=asin_root_shift(root,scale);' in source
    assert 'error=63+2*bias;' in source
    assert 'const U q=(U(hi>>scale)<<32)|((lo>>scale)|(hi<<(32-scale)));' in source
    assert 'return q+((lo>>(scale-1))&1U);' in source
    unchanged = {}
    expected = {
        'asin_root_normalized(': '6d6f3e22392df72e7882398a5081de24171cfe1c8bca83973151c4de590a24e1',
        'asin_geometry(': '160eabaac99cdae6717f43ae9fa4429e03ffef76d9a17c98ff325102b988efc4',
        'asin_geometry_refined(': '22d84c8a5460b24bdc60aca71f46cf71c3a8587a580e52e5cf9482f66c8c81af',
        'asin_refine(': '6b83d9063c389eb6cfe6b62512ad6d2301e9dcc1d70b1f990b6e7cfc2c07f04f',
    }
    for symbol, digest in expected.items():
        body = function(source, symbol)
        unchanged[symbol] = hashlib.sha256(body.encode()).hexdigest()
        assert unchanged[symbol] == digest, symbol
        if baseline_source is not None:
            assert body == function(baseline_source, symbol), symbol
    old = certificate()
    r = 1 << 63
    seed_error = old['root_seed_absolute_bound']
    assert seed_error == 4096
    newton = F(seed_error**2, 1 << 63)
    ratio_error = F(seed_error + 1, 32768) + newton
    assert ratio_error == F(old['root_quotient_error'])
    # floor((n+floor(d/2))/d) is a nearest integer for all n>=0,d>0.
    normalized = F(1, 2) + ratio_error
    assert normalized < F(627, 1000) < 1
    # The source shifts positive words by s=1..26, then uses bit s-1
    # to round half up. This is nearest rounding with error <=1/2.
    shifted = max(normalized, F(1, 2) + normalized / 2)
    assert shifted < F(814, 1000) < 1
    x_min, x_max = 1 << 57, r - 1024
    n_min, n_max = r*r - x_max*x_max, r*r - x_min*x_min
    assert n_min.bit_length() == 74 and n_max.bit_length() == 126
    assert ((126 - n_min.bit_length()) & ~1) // 2 == 26
    # g>=2^62, hence floor(g/2^47)>=32768. The added half divisor
    # cannot overflow the 32bit numerator on the certified seed domain.
    numerator_max = F(seed_error * (2*r + seed_error), 1 << 48)
    assert numerator_max + (1 << 15) + 1 < 1 << 32
    nonroot = F(old['geometry_q70_error']) - 257
    assert nonroot < 62
    rows = []
    for j in range(64):
        xmax = ((j+1) << 57) - 1
        root_angle_error = F(xmax * (1 << 70), r*r - r)
        interval = 63 + 2*(j+1)
        assert nonroot + root_angle_error < interval
        rows.append(dict(x_bin=j, interval=interval, error_bound=str(nonroot + root_angle_error)))
    table = verify_atan_table(args.source_root / 'code/native_eabi_m0_refine_table.inc')
    report = dict(status='PASS', source_sha256=hashlib.sha256(source.encode()).hexdigest(),
                  unchanged_functions_sha256=unchanged, root_seed_absolute_bound=seed_error,
                  root_quotient_error=str(ratio_error), normalized_root_error=str(normalized),
                  shifted_root_error_q63=str(shifted), shifted_root_error_q63_float=float(shifted),
                  maximum_shift=26, geometry_interval_rule='63+2*(floor(X/2^57)+1)',
                  geometry_interval_maximum=191, per_x_bin=rows, atan_table=table,
                  assumptions=old['assumptions'],
                  scope='Exact rational seed/quotient/shift and angle-error bounds, tied to source expressions. ARM implementation and final rounding require separate qualification.')
    args.json.write_text(json.dumps(report, indent=2) + '\n')
    print('PASS: shifted root error <1 Q63; geometry interval <=191 Q70 units.')


if __name__ == '__main__':
    main()
