#!/usr/bin/env python3
"""Check the range, enclosure and work bounds for the pow power products."""
import argparse
from fractions import Fraction as F
import hashlib
import json
from math import ceil
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[2]
ONE = 0x3FF0000000000000
INFINITY = 0x7FF0000000000000
ABS_MASK = (1 << 63)-1
POWER_OF_TWO_TAIL_MINIMUM_SHIFT = 100


def odd_dyadic(encoding):
    """Decode a finite positive binary64 as an odd coefficient times 2^e."""
    field = encoding >> 52
    coefficient = encoding & ((1 << 52)-1)
    exponent = -1074
    if field:
        coefficient += 1 << 52
        exponent = field-1075
    trailing = (coefficient & -coefficient).bit_length()-1
    return coefficient >> trailing, exponent+trailing


def midpoint_coefficient(lower):
    """Return the odd coefficient of the exact positive RNE midpoint."""
    if lower == INFINITY-1:
        return (1 << 54)-1
    # Adjacent values in one binade share their scale. Crossing a binade
    # increases the upper scale by one. Zero uses the subnormal scale.
    field = lower >> 52
    a = lower & ((1 << 52)-1)
    ae = field-1075 if field else -1074
    if field:
        a += 1 << 52
    upper = lower+1
    field = upper >> 52
    b = upper & ((1 << 52)-1)
    be = field-1075 if field else -1074
    if field:
        b += 1 << 52
    coefficient = a+(b << (be-ae))
    return coefficient >> ((coefficient & -coefficient).bit_length()-1)


def near_one_midpoint_counts(exponent, precision):
    """Bound midpoint counts for an undecided call in one small-y binade."""
    assert -64 <= exponent <= -12 and precision >= 128
    maximum_y = F((1 << 53)-1)*F(2)**(exponent-52)
    epsilon = 4*(maximum_y+1)*F(2)**(1-precision)
    logarithm = 745*maximum_y+epsilon
    assert logarithm < F(1, 2)

    # An overlap gives |ln(m)| < 745*maximum_y+epsilon. For m<1 use
    # 1-exp(-t)<=t. For m>1 use exp(t)-1<=t/(1-t). Both bounds keep
    # m inside (1/2,2), where all midpoints have one of these forms:
    # m=1-(2j+1)*2^-54, or m=1+(2j+1)*2^-53.
    # The count of positive odd integers strictly below d is ceil(d)//2.
    below_bound = logarithm*(1 << 54)
    above_bound = logarithm/(1-logarithm)*(1 << 53)
    below = ceil(below_bound)//2
    above = ceil(above_bound)//2
    return below, above


def unresolved_candidate(x, y, lower, precision):
    """Necessary conditions for PowerBounds::side to return undecided.

    True is an overapproximation and does not assert that the firmware
    reaches this stage. The predicate also applies to narrow test builds.
    """
    if not (0 < x < INFINITY and (y & ABS_MASK) < INFINITY and 0 <= lower < INFINITY):
        raise ValueError('Expected finite positive base, finite exponent and a valid midpoint')
    assert precision >= 128
    magnitude = y & ABS_MASK
    if x == ONE or magnitude < 0x3BF0000000000000 or magnitude >= 0x43E0000000000000:
        return False

    decreasing = (x < ONE) != bool(y >> 63)
    # Every midpoint has |ln(m)|>2^-54. At P>=128 the overlap gap is
    # <2^-62, so the true logarithm and midpoint have the same sign.
    if (lower < ONE) != decreasing:
        return False

    numerator, scale = odd_dyadic(magnitude)
    if scale >= 0:
        numerator <<= scale
        denominator = 1
    else:
        denominator = 1 << -scale
    if denominator == 1 << 116 and ((1023-738) << 52) <= x <= ((1023+738) << 52):
        return False
    base, _ = odd_dyadic(x)
    if base == 1 and denominator >= 1 << POWER_OF_TWO_TAIL_MINIMUM_SHIFT:
        # power_of_two_tail_certificate checks every possible midpoint
        # against the exponent grid and proves separation already at P=128.
        return False
    midpoint = midpoint_coefficient(lower)
    base_bits = (base.bit_length()*numerator) if base != 1 else 0
    midpoint_bits = (midpoint.bit_length()*denominator) if midpoint != 1 else 0
    if y >> 63:
        exact = base_bits+midpoint_bits <= precision
    else:
        exact = max(base_bits, midpoint_bits) <= precision
    if exact:
        return False

    exponent = (magnitude >> 52)-1023
    if exponent <= -12:
        below, above = near_one_midpoint_counts(exponent, precision)
        if decreasing:
            return ONE-below <= lower < ONE
        return ONE <= lower < ONE+above
    return True


def power_of_two_tail_certificate():
    """Exclude every power-of-two base with q>=2^100 by a finite proof."""
    precision = 128
    grid_bits = 256
    grid_scale = 1 << grid_bits
    ln2_lower = sum((F(2, (2*i+1)*3**(2*i+1)) for i in range(90)), F(0))
    ln2_upper = ln2_lower+F(9, 4*181*3**181)
    ranges = [(k, *near_one_midpoint_counts(52-k, precision))
              for k in range(POWER_OF_TWO_TAIL_MINIMUM_SHIFT, 117)]
    maximum_below, maximum_above = ranges[0][1:]
    assert all(below <= maximum_below and above <= maximum_above for _, below, above in ranges)
    minimum_distance = grid_scale
    closest = None
    checked = 0

    # For x=2^e and y=sign*p/2^k, log2(x^y)=sign*e*p/2^k.
    # Thus only multiples of 2^(grid_bits-k) can equal its scaled log.
    # The near-one ranges contain every midpoint of an undecided P=128
    # comparison. They also contain those of every finer comparison.
    for lower in range(ONE-maximum_below, ONE+maximum_above):
        if lower < ONE:
            displacement = F(2*(ONE-lower)-1, 1 << 54)
            t = displacement/(2-displacement)
        else:
            displacement = F(2*(lower-ONE)+1, 1 << 53)
            t = displacement/(2+displacement)
        square = t*t
        # |ln(m)|=2*atanh(t). Three positive terms and the geometric
        # bound on the remaining denominators give rational endpoints.
        log_lower = 2*t*(1+square/3+square*square/5)
        log_upper = log_lower+2*t*square**3/(7*(1-square))
        lower_bound = log_lower*grid_scale/ln2_upper
        upper_bound = log_upper*grid_scale/ln2_lower
        low = lower_bound.numerator//lower_bound.denominator
        high = ceil(upper_bound)
        for shift, below, above in ranges:
            if not ONE-below <= lower < ONE+above:
                continue
            grid = 1 << (grid_bits-shift)
            remainder = low % grid
            distance = min(remainder, grid-remainder-(high-low))
            assert distance > 0, (hex(lower), shift)
            checked += 1
            if distance < minimum_distance:
                minimum_distance = distance
                closest = dict(lower=f'{lower:016x}', denominator_shift=shift)

    gap_lower = F(minimum_distance, grid_scale)*ln2_lower
    maximum_y = F((1 << 53)-1, 1 << POWER_OF_TWO_TAIL_MINIMUM_SHIFT)
    overlap_gap_upper = 4*(maximum_y+1)*F(2)**(1-precision)
    assert overlap_gap_upper < gap_lower
    assert maximum_below+maximum_above == 71520 and checked == 143039
    assert gap_lower > F(1, 1 << 121)
    # An omitted midpoint has |ln(m)| at least the logarithm bound
    # used by its range. The slack in 745 versus the actual maximum
    # 1074*ln(2) makes its distance larger than the grid minimum too.
    outside_gap = (745-1074*ln2_upper)*F((1 << 53)-1, 1 << 116)
    assert outside_gap > F(1, 1 << 65) > gap_lower

    # The existing 512-bit interval certificate gives a relative width
    # below this looser bound. At these y, both the true value and every
    # potentially ambiguous midpoint lie in (1/2,2). Such an interval
    # cannot cross a boundary with the log separation just established.
    unit = F(1, 1 << 512)
    logarithm_units = 12*(512+16)+4+1074
    q_width = (logarithm_units*(1 << 64)+2)*unit
    endpoint_width = (4*(512+16)+2)*unit
    relative_width = 4*(q_width+1155*unit)+4*endpoint_width
    assert relative_width < F(1, 1 << 400) < gap_lower
    # A power-of-two base has zero normalized log mantissa, so its
    # atanh loop stops after one iteration. The reduction index is zero.
    # Each exponential upper term contracts by at least 37 bits, even
    # when its integer division by n is omitted from this upper bound.
    assert 745*maximum_y+q_width < F(1, 1 << 37) < F(1, 1 << 20)
    # In units of 2^-512, the upward product/division gives
    # T_n=ceil(T_(n-1)*r/n). Dropping n and replacing r by 2^-37
    # preserves an upper bound, including both rounding operations.
    term_units = 1 << 512
    endpoint_terms = 0
    while term_units > 1:
        term_units = ceil(F(term_units, 1 << 37))
        endpoint_terms += 1
    full_products = 4+4*endpoint_terms
    words = 512//16+4
    assert endpoint_terms == 14 and full_products*words*words == 77760
    return dict(
        status='PASS_POWER_OF_TWO_TAIL',
        base_domain='x=2^e, integer -1074<=e<=1023',
        exponent_domain='abs(y)=p/2^k, p odd, 100<=k<=116, 2^-64<=abs(y)',
        unique_midpoints=maximum_below+maximum_above,
        checked_midpoint_denominator_pairs=checked,
        rational_log2_grid_bits=grid_bits,
        minimum_grid_distance_units=minimum_distance,
        closest=closest,
        strict_abs_log_gap_lower_bound='2^-121',
        omitted_midpoints_abs_log_gap_strict_lower_bound='2^-65',
        sufficient_power_product_precision_bits=precision,
        first_512_bit_interval_decides_under_interval_certificate=True,
        first_512_bit_work=dict(
            log_series_iterations=1,
            reduction_index=0,
            maximum_terms_per_exp_endpoint=endpoint_terms,
            maximum_full_fixed_point_products=full_products,
            maximum_full_product_limb_multiply_accumulates=full_products*words*words,
            maximum_limb_divisions=(2+4*endpoint_terms)*words,
            scope='Bounds on these arithmetic loops; scalar scaling, packing and call overhead are additional.'),
        scope='Complete finite enumeration of the necessary midpoint ranges with rational '
              'atanh bounds, covering every numerator and every power-of-two base in '
              'the stated domain. Other bases and denominator ranges remain separate.')


def last_stage_domain(ln2_upper, precision):
    """Certify necessary restrictions on a remaining last-stage input."""
    assert precision >= 8192
    # The closest midpoint above one is 1+2^-53, the closest below is
    # 1-2^-54. Elementary integral bounds on ln give this minimum.
    assert F(1, 1 << 53)/(1+F(1, 1 << 53)) > F(1, 1 << 54)
    assert 4*((1 << 63)-(1 << 10)+1)*F(2)**(1-precision) < F(1, 1 << 54)
    rows = []
    for exponent in range(-64, -11):
        below, above = near_one_midpoint_counts(exponent, precision)
        rows.append(dict(y_binade_exponent=exponent,
                         maximum_denominator_shift=52-exponent,
                         midpoints_below_one=below, midpoints_above_one=above))
    assert (rows[0]['midpoints_below_one'], rows[0]['midpoints_above_one']) == (1, 0)
    assert (rows[10]['midpoints_below_one'], rows[10]['midpoints_above_one']) == (745, 373)

    q = 1 << 116
    maximum_y = F((1 << 53)-1, q)
    epsilon = 4*(maximum_y+1)*F(2)**(1-precision)
    minimum_midpoint_log = F(1, 1 << 54)
    assert (minimum_midpoint_log-epsilon)/maximum_y > 512
    test_epsilon = 4*(maximum_y+1)*F(2)**(1-128)
    assert (minimum_midpoint_log-test_epsilon)/maximum_y > 512
    assert 738*ln2_upper < 512
    minimum_numerators = {}
    for name, log_limit in (('base_below_one', 1074*ln2_upper),
                            ('base_above_one', 1024*ln2_upper)):
        threshold = q*(minimum_midpoint_log-epsilon)/log_limit
        minimum = threshold.numerator//threshold.denominator+1
        if minimum % 2 == 0:
            minimum += 1
        minimum_numerators[name] = minimum

    # All coefficients fit whenever these inequalities hold. Squaring
    # and multiplying visit only powers with no more factors, so every
    # intermediate is exact as well, including exact midpoint ties.
    exact_rows = []
    for shift in range(8):
        denominator = 1 << shift
        positive = precision//53
        inverse = max(0, (precision-54*denominator)//53)
        assert 53*positive <= precision and 54*denominator <= precision
        if inverse:
            assert 53*inverse+54*denominator <= precision
        exact_rows.append(dict(denominator=denominator,
                               positive_numerator_maximum=positive,
                               negative_numerator_maximum=inverse))
    sources = ('code/native_eabi_m0_cr.cpp', 'code/native_eabi_m0_pow_interval.inc',
               'code/native_eabi_m0_pow_exact.inc', 'code/native_eabi_m0_pow_power_bounds.inc')
    source_text = {name: (ROOT/name).read_text() for name in sources}
    assert 'if(upper==lower+1) result=lower;' in source_text[sources[1]]
    assert source_text[sources[2]].count('*result=') == 1
    assert '*result=lower;\n  return 1;' in source_text[sources[2]]
    assert 'if(!side) return false;\n  lower+=unsigned(side>0);' in source_text[sources[3]]
    assert 'if(hint<infinity) return hint+unsigned(pow_final_side(x,y,hint)>0);' in source_text[sources[0]]
    return dict(
        precision_bits=precision,
        source_sha256={name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in sources},
        log_gap_strict_upper_bound='4*(abs(y)+1)*2^(1-P)',
        public_rescue_hint_contract=dict(
            prerequisite='The 1024-bit interval certificate proves that every undecided valid input publishes one adjacent pair.',
            exact_small_preserves_hint_on_failure=True,
            power_bounds_preserves_hint_on_failure=True,
            maximum_exact_small_boundary_comparisons=2,
            maximum_4096_boundary_comparisons=1,
            maximum_8192_boundary_comparisons=1,
            maximum_stream_boundary_comparisons=1,
            unhinted_binary_search_reachable_under_interval_invariant=False),
        midpoint_log_has_same_sign_as_y_log_x=True,
        exact_coefficient_exclusions=exact_rows,
        small_exponent_midpoint_limits=rows,
        denominator_2_to_116=dict(
            only_lower_encoding=f'{ONE-1:016x}',
            midpoint='1-2^-54',
            y_log_x_negative=True,
            abs_log_x_strict_lower_bound=512,
            excluded_base_interval=['2^-738', '2^738'],
            minimum_odd_numerator=minimum_numerators),
        practical_uniform_latency_established=False,
        scope='Necessary input restrictions from exact rational inequalities and source-bound '
              'enclosure arguments. They do not prove that an undecided production call exists '
              'or exclude every remaining input. These are not machine-checked compiler proofs.')

def uniform_precision_bound(ln2_lower, ln2_upper, max_k):
    """Specialize Laurent's real two-logarithm bound using exact rationals.

    This is a sufficient precision for the enclosure argument. It does not
    assert that any binary64 pair needs that precision, or that the firmware
    supports the corresponding allocation.
    """
    # A reduced binary64 base has numerator and denominator at most 2^1074.
    # A rounding midpoint can also be 2^-1075. Inverting a rational leaves
    # its logarithmic height unchanged. Thus log(A_i)=746 is admissible
    # in Laurent's Corollary 2, with D=1, for either inverted base.
    log_height = 746
    assert 1075*ln2_upper < log_height

    # After the exponent cutoffs, p+q <= 2^116+2^53-1. For q=1 the
    # separate p<2^63 bound is smaller. Laurent's b' is (p+q)/746.
    terms = (1 << max_k)+(1 << 53)-1
    assert (1 << 63)+1 < terms
    log_terms_upper = max_k*ln2_upper+F((1 << 53)-1, 1 << max_k)
    # 746=2^9*(373/256); ln(373/256)>2*(117/629).
    log_height_lower = 9*ln2_lower+F(234, 629)
    assert 512*373 == 746*256
    normalized_coefficient_log_upper = log_terms_upper-log_height_lower+F(19, 50)
    h = 75
    assert max(F(30), F(1), normalized_coefficient_log_upper) < h

    # Laurent, Corollary 2, Table 1, m=30 and C2=17.9, gives
    # ln|Lambda| >= -17.9*h^2*746^2 for independent bases. Dividing
    # Lambda by q<=2^116 gives the log gap used by PowerBounds::side.
    loss_nats = F(179, 10)*h*h*log_height*log_height
    gap_bits = int(loss_nats/ln2_lower)+max_k+1
    assert gap_bits*ln2_lower > loss_nats+max_k*ln2_upper

    # An undecided comparison at precision P has gap <2^(66-P).
    # At P>=gap_bits+66 that contradicts the nonzero gap above. Round
    # upward to whole 16-bit limbs. This also covers the dependent
    # gap and exact-tie precision established by the main certificate.
    assert 4*((1 << 63)-(1 << 10)+1) < 1 << 65
    precision = ((gap_bits+66+15)//16)*16
    assert precision-66 >= gap_bits > 170
    significand_bytes = (precision+7)//8
    assert significand_bytes > 264*1024
    return dict(
        source='https://www.impan.pl/shop/en/publication/transaction/download/product/82485',
        theorem='Corollary 2, D=1, m=30, C2=17.9',
        rational_height_log_upper=log_height,
        normalized_coefficient_log_plus_038_upper=str(normalized_coefficient_log_upper),
        rounded_coefficient_log_upper=h,
        logarithmic_form_loss_nats=str(loss_nats),
        nonzero_abs_log_gap_strict_lower_bound=f'2^-{gap_bits}',
        enclosure_error_overhead_bits=66,
        sufficient_enclosure_precision_bits=precision,
        one_significand_bytes_at_sufficient_precision=significand_bytes,
        supported_firmware_precision_bits=8192,
        practical_uniform_latency_established=False,
        scope='A sufficient mathematical precision derived from a cited theorem; '
              'the firmware does not allocate it and no input is proved to need it. '
              'A practical uniform bound still requires a stronger whole-domain '
              'separation proof or another bounded exact comparison algorithm.')


def certify():
    # For finite nonzero x, abs(log(x)) < 745. The rational series verifies
    # both log(2) cutoffs used by the existing fixed-point pow interval.
    lo = sum((F(2, (2*i+1)*3**(2*i+1)) for i in range(40)), F(0))
    hi = lo+F(9, 4*81*3**81)
    assert 1074*hi < 745 and 1075*hi < 1024
    assert F(745, 1 << 64) < F(1, 1 << 54)
    tiny = F(745, 1 << 64)
    assert tiny/(1-tiny) < F(1, 1 << 53)
    assert F(1, (1 << 52)+1) > F(1,1 << 53)
    assert struct.unpack('<Q',struct.pack('<d',2.**-64))[0] == 0x3BF0000000000000
    assert struct.unpack('<Q',struct.pack('<d',2.**63))[0] == 0x43E0000000000000

    # The exponent field for a binary64 value at or above 2^-64
    # provides at least -116 after removing its 52 fraction bits.
    max_k = 64+52
    max_fraction_p = (1 << 53)-1
    max_integer_p = (1 << 63)-1
    terms = (1 << max_k)+max_fraction_p
    assert terms > max_integer_p+1
    assert 1075*terms+3 < 1 << 127
    radix = 1 << 16
    assert (radix-1)**2+2*(radix-1) < 1 << 32
    # Doubling each off-diagonal digit, adding a diagonal digit and
    # propagating the carry needs at most two carry units per word.
    assert (3*(radix-1)+2)//radix == 2
    # The biased half-square sum minus the difference square is at most
    # two carry units. The reconstructed cross term needs at most one
    # digit beyond the two half-squares, hence the final carry is 0 or 1.
    assert 2*(radix-1)+radix-1+2 < 3*radix
    assert 2 < radix

    # Truncating one normalized multiplication loses strictly less than
    # delta=2^(1-P) relative. The exact expression, with each square
    # expanded as two subexpressions, has terms leaves and terms-1
    # products. Bernoulli bounds the total loss by z=(terms-1)*delta.
    # Since z<1/2, 1/(1-z) <= 1+2z. For S < 2^P, 2*z*S < 4*(terms-1).
    # The renormalizing ceil can add at most one unit of the old scale.
    addition = 4*(terms-1)
    assert addition+1 < 1 << 119
    for precision in (128,256,4096,8192):
        delta = F(1,1 << (precision-1))
        loss = (terms-1)*delta
        assert 0 < loss < F(1,2)
        assert F(1,1-loss) <= 1+2*loss
        assert addition < 1 << (precision-2)

    words = 4096//16
    leaf_words = 16
    largest_work = {}
    for length in (words,2*words):
        # The dense case splits down to 16-word squares. Each leaf uses
        # one multiply for each diagonal or unordered off-diagonal pair.
        leaf_count = 3**((length//leaf_words).bit_length()-1)
        square_work = leaf_count*leaf_words*(leaf_words+1)//2
        largest_work[16*length] = max(
            62*square_work+length**2+62*4*length,
            (52+max_k)*square_work+length**2+52*4*length)
    assert largest_work == {4096:1969472,8192:5920704}
    delta = F(1,1 << (16*words-1))
    assert (addition+1)*delta < F(1,1 << 3976)

    # If the lower endpoints agree, or the smaller upper endpoint reaches
    # the larger lower endpoint, the two closed enclosures overlap. For
    # true values A and B this gives both ratios <= (1+eps_a)*(1+eps_b),
    # with eps_i <= (4*(n_i-1)+1)*delta including the renormalizing ceil.
    # ln(1+eps) <= eps, so the absolute log gap divided by q is strictly
    # below 4*(p/q+1)*delta. The inverse case uses one product with p+q
    # leaves and an exact one, giving the same bound.
    last_y_bits = 0x43DFFFFFFFFFFFFF
    last_y = int(struct.unpack('<d', struct.pack('<Q',last_y_bits))[0])
    assert last_y == (1 << 63)-(1 << 10)
    failure_log_gap = F(1,1 << 4030)
    assert 4*(last_y+1)*delta < failure_log_gap
    final_failure_log_gap = F(1,1 << 8126)
    assert 4*(last_y+1)*F(1,1 << 8191) < final_failure_log_gap

    # For dependent dyadic bases, the primitive integer valuation vector
    # represents a dyadic g with odd coefficient below 2^54, up to inversion.
    # If 1/2 <= g <= 2 and g != 1, the numerator and denominator are at most
    # 2^54, so |ln(g)| >= |g-1|/max(1,g) >= 2^-54. Outside that range use ln(2).
    # For x=g^i, m=g^j, a nonzero |(sign(y)*p*i-q*j)/q| is at least 1/q.
    min_primitive_log = F(1,1 << 54)
    assert lo > min_primitive_log
    dependent_log_gap = min_primitive_log/(1 << max_k)
    assert failure_log_gap < dependent_log_gap == F(1,1 << 170)

    # At a positive exact midpoint tie with a nontrivial odd coefficient,
    # the reduced p and q require x's odd coefficient to be C^q and the
    # midpoint's to be C^p, for odd C >= 3. Thus q <= 32 and both exact
    # power products have fewer than 54*q significant bits. An inverse
    # tie requires both coefficients to be one, as does any other tie
    # with a trivial odd coefficient. Normalization preserves powers of two.
    assert 3**64 > (1 << 53) and 3**35 > (1 << 54)
    assert 54*32 < 16*words
    source = ROOT/'code/native_eabi_m0_pow_power_bounds.inc'
    contents = source.read_text()
    assert 'PowerBounds<256>::side' in contents and f'SquareLeafWords={leaf_words}' in contents
    return dict(status='PASS_POWER_PRODUCT_ENCLOSURE',
        source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        active_domain='positive finite binary64 x, 2^-64 <= |y| < 2^63, one adjacent rounding boundary',
        maximum_denominator_shift=max_k,maximum_product_leaves=terms,
        significand_bits=16*words,minimum_signed_scale_bits=128,
        maximum_full_products=52+max_k+1,
        maximum_limb_multiply_accumulates=largest_work[4096],
        maximum_8192_limb_multiply_accumulates=largest_work[8192],
        relative_width_bound='2^-3976',
        undecided_abs_log_gap_strict_upper_bound='2^-4030',
        undecided_8192_abs_log_gap_strict_upper_bound='2^-8126',
        dependent_nonzero_abs_log_gap_lower_bound='2^-170',
        exact_midpoint_products_significand_bits_upper_bound=54*32,
        last_stage_domain=last_stage_domain(hi, 8192),
        power_of_two_tail=power_of_two_tail_certificate(),
        uniform_precision_bound=uniform_precision_bound(lo, hi, max_k),
        scope='For a valid adjacent midpoint, only multiplicatively independent bases with a nonzero cancelling log gap can remain undecided.')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--json',type=Path,required=True)
    args = parser.parse_args()
    report = certify()
    args.json.write_text(json.dumps(report,indent=2)+'\n')
    print(report['status'], report['relative_width_bound'])

if __name__=='__main__':
    main()
