#!/usr/bin/env python3
"""Search for and independently check an all-binary64 RP2040 no-stream proof."""

import argparse
from collections import Counter, deque
from concurrent.futures import ProcessPoolExecutor
from contextlib import nullcontext
from dataclasses import dataclass, replace
from fractions import Fraction
from functools import lru_cache
import gzip
from hashlib import sha256
import json
from pathlib import Path
import re
import sys
from time import monotonic

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'research/m0-pow-comparison-20261117'))
from midpoint_grid import FixedInterval

SCHEMA = 'mk61-rp2040-pow-no-stream-v1'
GAP = 16300
RESIDUE_BITS = 49152
ONE = 0x3ff0000000000000
INF = 0x7ff0000000000000
Y_MIN = 0x3bf0000000000000           # 2**-64
Y_NEXT = 0x3c00000000000000          # 2**-63
Y_MAX = 0x43e0000000000000           # 2**63, excluded
SIGNIFICAND = 1 << 52
FRACTION_MASK = SIGNIFICAND-1
AXES = ('x', 'y', 'm')
# 512 in PowerBounds<512> counts 16-bit words, not bits.
EXACT_BITS = 8192
SOURCES = (
    'code/native_eabi_m0.S', 'code/native_eabi_m0.hpp', 'code/native_eabi_m0_cr.cpp',
    'code/native_eabi_m0_cr_shim.inc', 'code/native_eabi_m0_cr_types.hpp',
    'code/native_eabi_m0_uint128.hpp',
    *(f'code/{path.name}' for path in sorted((ROOT/'code').glob('native_eabi_m0_pow_*.inc'))),
    *(f'third_party/core_math/pow/{name}' for name in ('pow.c', 'pow.h', 'dint.h', 'qint.h')),
)
SOURCE_FINGERPRINT = '1e1f5bedd7b8a481f75854c7255505f7c1d44e2994ce44ed5dce1ee5f040430e'
LAYER_SOURCES = tuple(f'research/m0-pow-comparison-20261117/{name}.py' for name in (
    'midpoint_grid', 'midpoint_binade', 'midpoint_layer'))
LAYER_FINGERPRINT = '485c5a67e31e11f11e6b851e58a04b3ac84b046bb832bc9e3367735af9e17cae'
INTERVAL_SHA256 = '09371512c50964956257eb2a9bee71089da81ac2fd130bb768a273288218841d'


class InvalidProof(ValueError):
    pass


@dataclass(frozen=True)
class Box:
    # Half-open ranges of unsigned binary64 encodings. For m the encoding
    # is that of the lower endpoint, not the midpoint rounded to binary64.
    x: tuple
    y: tuple
    m: tuple
    negative_y: bool

    def split(self, axis, cut):
        lo, hi = getattr(self, axis)
        if not lo < cut < hi:
            raise InvalidProof(f'{axis} cut is not strictly inside its box')
        return replace(self, **{axis: (lo, cut)}), replace(self, **{axis: (cut, hi)})

    def describe(self):
        return dict(**{axis: [f'{edge:016x}' for edge in getattr(self, axis)] for axis in AXES},
                    negative_y=self.negative_y)


def roots():
    # After the special-value checks, a valid negative base uses the
    # same magnitude computation and only changes the sign of its result.
    # |x|=1 and the two y cutoffs do not enter the exact comparison.
    return tuple(Box(x, (Y_MIN, Y_MAX), (0, INF), negative)
                 for negative in (False, True) for x in ((1, ONE), (ONE+1, INF)))


def fingerprint(paths):
    manifest = sha256()
    for name in paths:
        manifest.update(f'{sha256((ROOT/name).read_bytes()).hexdigest()}  {name}\n'.encode('ascii'))
    return manifest.hexdigest()


def check_model():
    from certify_m0_pow_log_side import arithmetic
    from certify_m0_pow_residue import BITS

    if not __debug__:
        raise InvalidProof('Python assertions must be enabled')
    if fingerprint(SOURCES) != SOURCE_FINGERPRINT:
        raise InvalidProof('the RP2040 source model has changed; re-audit its proof obligations')
    if sha256((ROOT/LAYER_SOURCES[0]).read_bytes()).hexdigest() != INTERVAL_SHA256:
        raise InvalidProof('the directed interval arithmetic has changed')
    if RESIDUE_BITS != BITS or arithmetic()['unresolved_gap'] != f'2^-{GAP}':
        raise InvalidProof('the cutoff or residue capacity does not match the proof model')
    grid, (_, ln2_hi) = log_grid(128)
    ln2_hi = Fraction(ln2_hi, grid.unit)
    tiny, large = dyadic_scale(1, dyadic(Y_MIN)), dyadic_scale(1, dyadic(Y_MAX))
    # All |ln x| < 745. The indices either side of one give the
    # closest midpoint and nearest nontrivial base on each side.
    # The bounds use t/(1+t) < ln(1+t) and t < -ln(1-t).
    if not (tiny == Fraction(1, 1 << 64) and large == 1 << 63
            and 1074*ln2_hi < 745 and 745*tiny < Fraction(1, 1 << 54)
            < Fraction(1, (1 << 53)+1)
            and Fraction(1, (1 << 52)+1) > Fraction(1, 1 << 53)
            and 1075*ln2_hi < large/(1 << 53)):
        raise InvalidProof('the arithmetic reduction of the two exponent cutoffs failed')


def dyadic(bits, midpoint=False):
    field, fraction = bits >> 52, bits & FRACTION_MASK
    significand = fraction+(SIGNIFICAND if field else 0)
    scale = max(1, field)-1075
    # The upward spacing is that of the lower endpoint, including zero,
    # a binade transition and the virtual value 2**1024 after max finite.
    return (2*significand+1, scale-1) if midpoint else (significand, scale)


def odd_dyadic(bits):
    significand, scale = dyadic(bits)
    zeros = (significand & -significand).bit_length()-1
    return significand >> zeros, scale+zeros


@lru_cache(maxsize=24)
def log_grid(precision):
    grid = FixedInterval(precision)
    return grid, grid.log(2, 1)


@lru_cache(maxsize=16384)
def log_point(bits, precision, midpoint):
    grid, ln2 = log_grid(precision)
    significand, scale = dyadic(bits, midpoint)
    leading = significand.bit_length()-1
    a, b = grid.log(significand, 1 << leading)
    c, d = grid.scale(ln2, scale+leading)
    return a+c, b+d


def log_range(span, precision, midpoint=False):
    lo, hi = span
    return log_point(lo, precision, midpoint)[0], log_point(hi-1, precision, midpoint)[1]


def ceil_div(numerator, denominator):
    return -(-numerator//denominator)


def dyadic_scale(number, value):
    significand, scale = value
    return Fraction(number*significand << max(scale, 0), 1 << max(-scale, 0))


def ceil_binary64(value):
    """First nonnegative binary64 encoding >= an exact rational."""
    if value <= 0:
        return 0
    n, d = value.as_integer_ratio()
    exponent = n.bit_length()-d.bit_length()
    if n << max(-exponent, 0) < d << max(exponent, 0):
        exponent -= 1
    if exponent > 1023:
        return INF
    scale = max(-1074, exponent-52)
    significand = ceil_div(n << max(-scale, 0), d << max(scale, 0))
    if exponent < -1022:
        return significand
    return ((exponent+1023) << 52)+significand-SIGNIFICAND


def enclosures(box, precision):
    return log_range(box.x, precision), log_range(box.m, precision, midpoint=True)


def excludes_gap(box, precision, logs):
    xlog, mlog = logs
    y = (dyadic(box.y[0]), dyadic(box.y[1]-1))
    values = tuple(dyadic_scale(a, b) for a in xlog for b in y)
    lo, hi = min(values), max(values)
    if box.negative_y:
        lo, hi = -hi, -lo
    strip = Fraction(1 << max(precision-GAP, 0), 1 << max(GAP-precision, 0))
    return lo-mlog[1] >= strip or mlog[0]-hi >= strip


def project_y(box, precision, logs):
    """Overapproximate the closed midpoint strip projected onto |y|."""
    xlog, mlog = logs
    decreasing_x = box.x[1] <= ONE
    if decreasing_x:
        xlog = -xlog[1], -xlog[0]
    if xlog[0] <= 0:
        return None
    if decreasing_x != box.negative_y:
        mlog = -mlog[1], -mlog[0]
    # Widen the strip outward to whole units before taking exact rational
    # ratios; the two logarithms use the same fixed-point scale.
    strip = 1 << max(precision-GAP, 0)
    ratios = [Fraction(a, b)
              for a in (mlog[0]-strip, mlog[1]+strip) for b in xlog]
    return min(ratios), max(ratios)


def candidate_y(box, precision, logs):
    projected = project_y(box, precision, logs)
    if projected is None:
        return box.y
    lower, upper = projected
    lo, hi = box.y
    first = max(lo, ceil_binary64(lower))
    if first >= hi or dyadic_scale(1, dyadic(first)) > upper:
        return first, first
    last = hi
    if upper < dyadic_scale(1, dyadic(hi-1)):
        last = ceil_binary64(upper)
        last += dyadic_scale(1, dyadic(last)) == upper
    return first, last


def excludes_y_grid(box, precision, logs):
    lo, hi = candidate_y(box, precision, logs)
    return lo >= hi


def interval_product(a, b):
    products = tuple(x*y for x in a for y in b)
    return min(products), max(products)


def affine_geometry(box, precision):
    """Enclose the centre and both derivatives of the projected numerator."""
    if any(lo >> 52 != (hi-1) >> 52 for lo, hi in (box.x, box.y, box.m)):
        return None
    x_center = (box.x[0]+box.x[1]-1)//2
    m_center = (box.m[0]+box.m[1]-1)//2
    x_log, m_log = enclosures(box, precision)
    if x_log[0] <= 0 <= x_log[1]:
        return None
    unit = 1 << precision
    dyadic_y_scale = dyadic(box.y[0])[1]
    projection = dyadic_scale(-1 if box.negative_y else 1, (1, -dyadic_y_scale))
    x_mid_log = log_point(x_center, precision, False)
    m_mid_log = log_point(m_center, precision, True)
    if x_mid_log[0] <= 0 <= x_mid_log[1]:
        return None
    value = interval_product(tuple(projection*l for l in sorted(m_mid_log, reverse=box.negative_y)),
                             (Fraction(1, x_mid_log[1]), Fraction(1, x_mid_log[0])))
    inverse = Fraction(unit, x_log[1]), Fraction(unit, x_log[0])
    x_first, x_last = (dyadic(i)[0] for i in (box.x[0], box.x[1]-1))
    m_first, m_last = (dyadic(i, True)[0] for i in (box.m[0], box.m[1]-1))
    signed_log_m = tuple(projection*Fraction(m, unit) for m in
                         sorted(m_log, reverse=box.negative_y))
    # d(log x)/d xbits = 1/coefficient; for m the coefficient changes
    # by two per lower-endpoint encoding. The two scales are constant.
    xd = interval_product(interval_product(inverse, inverse), signed_log_m)
    dx = interval_product((-xd[1], -xd[0]), (Fraction(1, x_last), Fraction(1, x_first)))
    dm_magnitude = Fraction(2, m_last), Fraction(2, m_first)
    dm = interval_product(inverse, tuple(projection*d for d in
                                         sorted(dm_magnitude, reverse=box.negative_y)))
    x_offset = box.x[0]-x_center, box.x[1]-1-x_center
    m_offset = box.m[0]-m_center, box.m[1]-1-m_center
    vertical_error = abs(projection)*max(map(abs, inverse))/(1 << min(precision, GAP))
    return value, dx, dm, x_offset, m_offset, vertical_error


def affine_excludes(geometry, denominator, x_slope, m_slope):
    if geometry is None:
        return False
    value, dx, dm, x_offset, m_offset, error = geometry
    # If p is integral, D*p-A*I-B*J is integral. Enclose this whole
    # expression by integrating the derivative deviations from the centre.
    x_delta = interval_product(tuple(denominator*v-x_slope for v in dx), x_offset)
    m_delta = interval_product(tuple(denominator*v-m_slope for v in dm), m_offset)
    lower = denominator*(value[0]-error)+x_delta[0]+m_delta[0]
    upper = denominator*(value[1]+error)+x_delta[1]+m_delta[1]
    return ceil_div(lower.numerator, lower.denominator) > upper.numerator//upper.denominator


def convergent_denominators(value):
    n, d = abs(value.numerator), value.denominator
    previous, current = 1, 0
    while d:
        a, remainder = divmod(n, d)
        previous, current = current, previous+a*current
        if current > 1 << 22:
            return
        yield current
        n, d = d, remainder


def try_affine(box):
    widths = (box.x[1]-box.x[0], box.m[1]-box.m[0])
    if not 1 < max(widths) <= (1 << 18):
        return None
    precision = 192
    geometry = affine_geometry(box, precision)
    if geometry is None:
        return None
    _, dx, dm, *_ = geometry
    x_slope, m_slope = sum(dx)/2, sum(dm)/2
    for denominator in sorted(set(range(1, 33)) | set(convergent_denominators(x_slope))
                              | set(convergent_denominators(m_slope))):
        a, b = round(denominator*x_slope), round(denominator*m_slope)
        if affine_excludes(geometry, denominator, a, b):
            return ['affine', precision, denominator, a, b]
    return None


def origin_covered(box):
    for radius, first_e, last_e in ((23, -64, 4), (22, -27, -1),
                                    (20, -18, -1), (18, -5, -1)):
        lo, hi = ONE-(1 << (53-radius)), ONE+(1 << (52-radius))+1
        if (lo <= box.x[0] and box.x[1] <= hi and (1023+first_e) << 52 <= box.y[0]
                and box.y[1] <= (((1023+last_e) << 52)+1)):
            return True
    return False


@lru_cache(maxsize=1)
def check_origin_theorem():
    from certify_m0_pow_determinant import certify
    result = certify()
    upper = result['origin_all_exponents_up_to']
    if ((upper['relative_radius_bits'], upper['abs_y_upper_shift']) != (23, 4)
            or {(r['relative_radius_bits'], r['abs_y_lower_shift'], r['abs_y_upper_shift'])
                for r in result['origin_additional_ranges']} != {
                    (22, -27, -1), (20, -18, -1), (18, -5, -1)}
            or result['comparator_gap_bits'] != GAP):
        raise InvalidProof('origin determinant obligations do not match the model')


def powers_width(box):
    y0, y1 = box.y
    if y1-y0 == 1:
        odd, scale = odd_dyadic(y0)
        p = odd << max(scale, 0)
        k = max(-scale, 0)
    else:
        top, scale = dyadic(y1-1)
        top_value = (top << scale) if scale >= 0 else (top >> -scale)
        k = max(0, 1075-(y0 >> 52))
        # The numerator of a reduced fractional y is at most 53 bits;
        # ties-to-even exactness can also use the reduced singleton case.
        p = max(top_value, 2*SIGNIFICAND-1) if k else top_value

    x0, x1 = box.x
    if x1-x0 == 1:
        a, _ = odd_dyadic(x0)
        x_bits = a.bit_length() if a > 1 else 0
    else:
        x_bits = dyadic(x1-1)[0].bit_length()
    m, _ = dyadic(box.m[1]-1, midpoint=True)
    m_bits = m.bit_length() if m > 1 else 0
    left, right = x_bits*p, m_bits << k
    return (left+right if box.negative_y else max(left, right)), k


def check_leaf(box, row):
    if row == ['open']:
        return 'open'
    if row == ['q116']:
        if box.y[1] > Y_NEXT:
            raise InvalidProof('q116 cannot certify a box outside 2**-64 <= |y| < 2**-63')
        return 'q116'
    if row == ['origin'] and origin_covered(box):
        check_origin_theorem()
        return 'origin'
    if row in (['powers'], ['residue']):
        width, k = powers_width(box)
        if row == ['powers'] and width <= EXACT_BITS:
            return 'powers'
        # Positive y: one aligned power has no left shift. Negative y:
        # after log-side fails the product is within a factor two of
        # 2**(-scale), hence the inverse width is at most the sum above.
        if row == ['residue'] and width+2+k <= GAP+RESIDUE_BITS:
            return 'residue'
    if len(row) == 2 and row[0] in ('gap', 'y-grid'):
        precision = row[1]
        if type(precision) is not int or not 96 <= precision <= 65536:
            raise InvalidProof('invalid directed logarithm precision')
        logs = enclosures(box, precision)
        excludes = excludes_gap if row[0] == 'gap' else excludes_y_grid
        if excludes(box, precision, logs):
            return row[0]
    if len(row) == 5 and row[0] == 'affine':
        precision, denominator, a, b = row[1:]
        if (not all(type(v) is int for v in row[1:]) or not 96 <= precision <= 65536
                or not 1 <= denominator <= 1 << 32 or max(abs(a), abs(b)).bit_length() > 512):
            raise InvalidProof('invalid integer affine coefficients')
        if affine_excludes(affine_geometry(box, precision), denominator, a, b):
            return 'affine'
    raise InvalidProof(f'leaf {row!r} does not prove its box: {box.describe()}')


def read_record(stream):
    line = stream.readline(4097)
    if not line or len(line) > 4096 or not line.endswith('\n'):
        raise InvalidProof('missing, truncated or oversized proof record')
    row = json.loads(line)
    if not isinstance(row, list) or not row or type(row[0]) is not str:
        raise InvalidProof('expected a proof record array')
    return row


def split_record(box, row):
    if (len(row) != 3 or row[1] not in AXES or type(row[2]) is not str
            or not re.fullmatch('[0-9a-f]{16}', row[2])):
        raise InvalidProof('invalid split record')
    return box.split(row[1], int(row[2], 16))


def verify_partition(stream, domain):
    if read_record(stream) != [SCHEMA]:
        raise InvalidProof('wrong proof schema; a partial-run receipt is not a proof')
    stack = list(reversed(domain))
    counts, first_open = Counter(), None
    while stack:
        box = stack.pop()
        row = read_record(stream)
        if row[0] == 'split':
            stack.extend(reversed(split_record(box, row)))
        else:
            rule = check_leaf(box, row)
            counts[rule] += 1
            if rule == 'open' and first_open is None:
                first_open = box.describe()
    if stream.read(1):
        raise InvalidProof('unexpected records after all proof roots')
    return counts, first_open


def verify_q116(layer, edge, workers, flint):
    if layer is None or edge is None or not layer.is_dir() or not edge.is_dir():
        raise InvalidProof('q116 requires both original checkpoint directories, not JSON receipts')
    if fingerprint(LAYER_SOURCES) != LAYER_FINGERPRINT:
        raise InvalidProof('the q116 certificate checkers have changed')
    from midpoint_binade import (Binade, DEFAULT_BINADE, EXPONENTS, analytic_interval,
                                 block_range, process, verify_all_direct)
    from midpoint_grid import verify_interval_policy
    from midpoint_layer import run

    verify_interval_policy()
    grid, (_, ln2_hi) = log_grid(128)
    # EXPONENTS omits the middle range. Its bases lie in [2**-738,2**738)
    # and hence cannot meet the closest midpoint, even with a 2**-900 strip.
    max_y = Fraction(2*SIGNIFICAND-1, 1 << 116)
    if max_y*Fraction(738*ln2_hi, grid.unit)+Fraction(1, 1 << 900) >= Fraction(1, 1 << 54):
        raise InvalidProof('q116 central exclusion did not hold')
    boundary = Binade(DEFAULT_BINADE)
    first, last = block_range(boundary, analytic_interval(boundary))
    checked, _, missing, _ = process('verify', boundary, edge, workers, first, last)
    if missing is not None or checked != last-first:
        raise InvalidProof('q116 negative boundary proof has holes')
    verify_all_direct(workers, None)
    binades = [Binade(e) for e in EXPONENTS if e != DEFAULT_BINADE]
    binades = [b for b in binades if not b.direct]
    if run('verify', layer, binades, workers, limit=None, reserve=0, report=None,
           flint_products=flint):
        raise InvalidProof('q116 layer did not replay completely')


def try_leaf(box, precision, reuse_layer):
    if reuse_layer and box.y[1] <= Y_NEXT:
        return ['q116']
    width, k = powers_width(box)
    if width <= EXACT_BITS:
        return ['powers']
    if width+2+k <= GAP+RESIDUE_BITS:
        return ['residue']
    if origin_covered(box):
        return ['origin']
    logs = enclosures(box, precision)
    if excludes_gap(box, precision, logs):
        return ['gap', precision]
    if excludes_y_grid(box, precision, logs):
        return ['y-grid', precision]
    return None


def choose_split(box):
    if box.y[0] < Y_NEXT < box.y[1]:
        return 'y', Y_NEXT
    xlog, mlog = enclosures(box, 128)
    possible_lo, possible_hi = candidate_y(box, 128, (xlog, mlog))
    if box.y[0] < possible_lo < box.y[1]:
        return 'y', possible_lo
    if box.y[0] < possible_hi < box.y[1]:
        return 'y', possible_hi
    ylo, yhi = dyadic(box.y[0]), dyadic(box.y[1]-1)
    y_max = dyadic_scale(1, yhi)
    y_width = y_max-dyadic_scale(1, ylo)
    scores = (y_max*(xlog[1]-xlog[0]), y_width*max(map(abs, xlog)), mlog[1]-mlog[0])
    axes = [axis for axis in AXES if getattr(box, axis)[1]-getattr(box, axis)[0] > 1]
    if not axes:
        return None
    axis = max(axes, key=lambda a: scores[AXES.index(a)])
    lo, hi = getattr(box, axis)
    cut = (lo+hi)//2
    # Prefer binade boundaries for wide cuts, useful for finer arithmetic
    # rules as well as for reducing the spread of the enclosures.
    boundary = cut & ~FRACTION_MASK
    return axis, boundary if lo < boundary < hi else cut


def analyze(request):
    box, reuse_layer = request
    row = try_leaf(box, 128, reuse_layer)
    if row is not None:
        return row
    row = try_affine(box)
    if row is not None:
        return row
    split = choose_split(box)
    if split is not None:
        axis, cut = split
        return ['split', axis, f'{cut:016x}']
    for precision in (256, 1024, 4096, 16448, 32832, 65536):
        row = try_leaf(box, precision, reuse_layer)
        if row is not None:
            return row
    return ['open']


def search_frontier(previous, domain):
    forest = [[] for _ in domain]
    initial = [(0, box, node) for box, node in zip(domain, forest)]
    if previous is None:
        return forest, deque(initial)
    if read_record(previous) != [SCHEMA]:
        raise InvalidProof('cannot resume from a different proof schema')
    pending, stack = [], list(reversed(initial))
    while stack:
        depth, box, node = stack.pop()
        row = read_record(previous)
        if row == ['open']:
            pending.append((depth, box, node))
            continue
        node.append(row)  # The independent verifier rechecks these leaves.
        if row[0] == 'split':
            children = [[], []]
            node.extend(children)
            children = [(depth+1, subbox, subnode)
                        for subbox, subnode in zip(split_record(box, row), children)]
            stack.extend(reversed(children))
    if previous.read(1):
        raise InvalidProof('unexpected records after the prior proof roots')
    return forest, deque(sorted(pending, key=lambda item: item[0]))


def search(stream, budget, seconds, reuse_layer, workers=1, previous=None):
    forest, queue = search_frontier(previous, roots())
    checked, stuck, new_closed = 0, 0, Counter()
    start = monotonic()
    context = ProcessPoolExecutor(max_workers=workers) if workers > 1 else nullcontext()
    with context as pool:
        while queue and checked < budget and monotonic()-start < seconds:
            size = min(len(queue), budget-checked, 128*workers if pool else 1)
            chunk = [queue.popleft() for _ in range(size)]
            requests = [(box, reuse_layer) for _, box, _ in chunk]
            rows = pool.map(analyze, requests, chunksize=16) if pool else map(analyze, requests)
            for (depth, box, node), row in zip(chunk, rows):
                checked += 1
                node.append(row)
                if row[0] == 'split':
                    children = [[], []]
                    node.extend(children)
                    queue.extend((depth+1, subbox, child)
                                 for subbox, child in zip(split_record(box, row), children))
                elif row[0] == 'open':
                    stuck += 1
                else:
                    new_closed[row[0]] += 1
    print(json.dumps([SCHEMA]), file=stream)
    stack = list(reversed(forest))
    while stack:
        node = stack.pop()
        print(json.dumps(node[0] if node else ['open'], separators=(',', ':')), file=stream)
        stack.extend(reversed(node[1:]))
    return dict(visited=checked, open_boxes=len(queue)+stuck, newly_closed=new_closed,
                singleton_boxes_not_proved=stuck, elapsed_s=round(monotonic()-start, 2))


def open_proof(path, mode):
    if path.suffix == '.gz':
        return gzip.open(path, mode+'t', encoding='ascii')
    return path.open(mode, encoding='ascii')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest='mode', required=True)
    verify = modes.add_parser('verify', help='require an independently proved complete partition')
    verify.add_argument('proof', type=Path)
    verify.add_argument('--q116-layer', type=Path)
    verify.add_argument('--q116-edge', type=Path)
    verify.add_argument('--workers', type=int, default=8)
    verify.add_argument('--flint-products', action='store_true')
    solve = modes.add_parser('search', help='start a bounded proof search from all binary64 roots')
    solve.add_argument('proof', type=Path)
    solve.add_argument('--nodes', type=int, default=100_000)
    solve.add_argument('--seconds', type=float, default=60.0)
    solve.add_argument('--workers', type=int, default=1)
    solve.add_argument('--continue-from', type=Path)
    solve.add_argument('--reuse-q116', action='store_true', help='defer that layer to its checkpoints')
    args = parser.parse_args()
    try:
        if not __debug__:
            raise InvalidProof('Python assertions must be enabled')
        if args.workers < 1:
            parser.error('expected positive workers')
        if args.mode == 'search':
            if args.nodes < 1 or not 0 < args.seconds < float('inf'):
                parser.error('expected positive finite search limits')
            # The solver is untrusted and needs no firmware source files.
            # Only the verifier can issue a source-bound PASS_NO_STREAM.
            prior = open_proof(args.continue_from, 'r') if args.continue_from else nullcontext()
            with prior as previous, open_proof(args.proof, 'x') as stream:
                result = search(stream, args.nodes, args.seconds, args.reuse_q116, args.workers, previous)
            print(json.dumps(dict(status='SEARCH_OUTPUT', **result), sort_keys=True))
            return 2 if result['open_boxes'] else 0
        check_model()
        with open_proof(args.proof, 'r') as stream:
            counts, first_open = verify_partition(stream, roots())
        if first_open is None and counts.get('q116'):
            verify_q116(args.q116_layer, args.q116_edge, args.workers, args.flint_products)
        status = 'INCOMPLETE' if first_open is not None else 'PASS_NO_STREAM'
        print(json.dumps(dict(status=status, leaf_counts=counts, first_open=first_open,
                              source_fingerprint=SOURCE_FINGERPRINT), sort_keys=True))
        return 2 if first_open is not None else 0
    except (ValueError, OSError, EOFError, AssertionError) as error:
        print(f'INVALID: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
