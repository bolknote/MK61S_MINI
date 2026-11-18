#!/usr/bin/env python3
"""Verify base binades for all y in the smallest active exponent binade."""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
import fcntl
import hashlib
import json
from pathlib import Path
from time import perf_counter

from midpoint_grid import (GAP_BITS, DENOMINATOR, FixedInterval, ceil_div,
                           constants, generate_block, verify_block,
                           verify_interval_policy)

DEFAULT_BINADE = -739
EXPONENTS = (*range(-1074, -738), *range(738, 1024))
LATTICE_SPLIT = 18
DIRECT_BITS = 22
SHARD_BLOCKS = 64
P_MIN, P_MAX = 1 << 52, (1 << 53)-1


@dataclass(frozen=True)
class Binade:
    exponent: int

    def __post_init__(self):
        if self.exponent not in EXPONENTS:
            raise ValueError('binade already excluded by the outer logarithmic bound')

    @property
    def bits(self):
        return min(52, self.exponent+1074)

    @property
    def bases(self):
        return 1 << self.bits

    @property
    def encoding(self):
        return ((self.exponent+1023) << 52) if self.exponent >= -1022 else self.bases

    @property
    def direct(self):
        return self.bits <= DIRECT_BITS

    @property
    def block_width(self):
        return 1 << min(10, self.bits) if self.direct else self.bases >> LATTICE_SPLIT

    def abs_log(self, grid, log2, offset):
        lo, hi = grid.log(self.bases+offset, self.bases)
        if self.exponent < 0:
            return -self.exponent*log2[0]-hi, -self.exponent*log2[1]-lo
        return self.exponent*log2[0]+lo, self.exponent*log2[1]+hi


def analytic_interval(binade):
    """Offsets that remain after bounding p*abs(log(x)) for every p."""
    precision = 1024
    grid = FixedInterval(precision)
    log2, target = constants(precision)
    strip = DENOMINATOR << (precision-GAP_BITS)

    def separated(offset):
        return P_MAX*binade.abs_log(grid, log2, offset)[1]+strip < target[0]

    # The true absolute logarithm decreases in a negative binade and
    # increases in a positive binade. Each certified endpoint therefore
    # excludes a whole prefix or suffix.
    negative = binade.exponent < 0
    lower, upper = 0, binade.bases
    if separated(lower) == negative:
        return (0, 0) if negative else (0, binade.bases)
    if separated(upper) != negative:
        return (0, binade.bases) if negative else (binade.bases, binade.bases)
    while upper-lower > 1:
        middle = (lower+upper)//2
        if separated(middle) == negative:
            upper = middle
        else:
            lower = middle
    assert separated(upper) == negative and separated(upper-1) != negative
    return (0, upper) if negative else (upper, binade.bases)


def block_range(binade, active):
    lo, hi = active
    if lo == hi:
        return 0, 0
    width = binade.block_width
    # Preserve the journal's shard alignment. A first shard may contain
    # a few blocks already covered by the analytic prefix.
    return (lo//width//SHARD_BLOCKS)*SHARD_BLOCKS, ceil_div(hi, width)


def verify_points(binade, start, stop):
    """Independently check a block of the shortest subnormal binades."""
    remaining = list(range(start, stop))
    for precision in (160, 256, 1024):
        grid = FixedInterval(precision)
        log2, target = constants(precision)
        strip = ceil_div(DENOMINATOR*grid.unit, 1 << GAP_BITS)
        target_strip = target[0]-strip, target[1]+strip
        undecided = []
        for offset in remaining:
            lo, hi = grid.divide(target_strip, binade.abs_log(grid, log2, offset))
            # p = 2**116*abs(y) is integral even if the reduced
            # denominator of y is smaller than 2**116.
            p = max(P_MIN, ceil_div(lo, grid.unit))
            if p <= min(P_MAX, hi//grid.unit):
                undecided.append(offset)
        if not undecided:
            return
        remaining = undecided
    raise AssertionError(('could not separate an isolated base', binade.exponent, remaining[0]))


def read_shard(stream, lower, upper, repair=False):
    """Read complete journal entries. A torn final append can be recovered."""
    rows = {}
    while True:
        position = stream.tell()
        line = stream.readline()
        if not line:
            return rows
        if not line.endswith(b'\n'):
            assert repair, 'incomplete checkpoint record'
            stream.seek(position)
            stream.truncate()
            return rows
        record = json.loads(line)
        index = record['index']
        assert type(index) is int and lower <= index < upper
        proof = record['proof']
        if proof is not None:
            assert index not in rows, ('duplicate checkpoint block', index)
            rows[index] = proof if isinstance(proof, list) else [proof]


def verify_parent(binade, index, proof):
    """Every child must cover its own part of the parent with no gaps."""
    if binade.direct:
        assert not proof
        first = index*binade.block_width
        verify_points(binade, first, first+binade.block_width)
        return
    spans = []
    for row in proof:
        if 'direct_offsets' in row:
            start, stop = row['direct_offsets']
            assert 0 <= start < stop <= binade.bases and stop-start <= 1024
            verify_points(binade, start, stop)
            spans.append((binade.encoding+start, binade.encoding+stop))
        else:
            spans.append(verify_block(row))
    stop = binade.encoding+(index+1)*binade.block_width
    first = stop-binade.block_width
    for start, end in sorted(spans):
        assert start == first and end > start, ('coverage discontinuity', index)
        first = end
    assert first == stop, ('wrong block extent', index)


def generate_parent(binade, index):
    if binade.direct:
        verify_parent(binade, index, [])
        return []
    children = []
    split = LATTICE_SPLIT

    def find(child_split, child, strategies):
        for degree, work_bits, delta in strategies:
            row, _ = generate_block(binade.exponent, child_split, child, degree, work_bits,
                                    delta, 'newton')
            if row is not None:
                try:
                    verify_block(row)
                except AssertionError:
                    continue
                return row
        return None

    for block in range(index*4, index*4+4):
        row = find(split+2, block, ((5, 90, 0.65), (6, 90, 0.50), (7, 98, 0.70)))
        if row is None:
            break
        children.append(row)
    if len(children) == 4:
        return children
    row = find(split, index, ((8, 98, 0.55), (9, 110, 0.88), (10, 128, 0.88)))
    if row is not None:
        return [row]

    def subdivide(child_split, child):
        width = binade.bases >> child_split
        if width <= 1024:
            start, stop = child*width, (child+1)*width
            verify_points(binade, start, stop)
            return [dict(direct_offsets=[start, stop])]
        row = find(child_split, child, ((6, 90, 0.55), (7, 98, 0.75)))
        if row is not None:
            return [row]
        return subdivide(child_split+1, child*2)+subdivide(child_split+1, child*2+1)

    # A failed search is not a verdict. Keep the successfully certified
    # children, then try smaller pieces of the rest of the parent.
    for block in range(index*4+len(children), index*4+4):
        children.extend(subdivide(split+2, block))
    return children


def run_shard(task):
    action, binade, directory, lower, upper = task
    path = directory/f'{lower:06d}-{upper:06d}.jsonl'
    digest = None
    if action == 'verify':
        if not path.exists():
            return lower, 0, 0, lower, None
        with path.open('rb') as source:
            fcntl.flock(source, fcntl.LOCK_SH | fcntl.LOCK_NB)
            rows = read_shard(source, lower, upper)
            source.seek(0)
            digest = hashlib.file_digest(source, 'sha256').hexdigest()
        for index, proof in rows.items():
            verify_parent(binade, index, proof)
    else:
        with path.open('a+b', buffering=0) as journal:
            fcntl.flock(journal, fcntl.LOCK_EX | fcntl.LOCK_NB)
            journal.seek(0)
            rows = read_shard(journal, lower, upper, repair=True)
            for index in range(lower, upper):
                if index in rows:
                    continue
                proof = generate_parent(binade, index)
                data = (json.dumps(dict(index=index, proof=proof), separators=(',', ':'))+'\n').encode()
                if journal.write(data) != len(data):
                    raise OSError(f'Short append to checkpoint {path}')
                rows[index] = proof
    missing = next((i for i in range(lower, upper) if i not in rows), None)
    return lower, len(rows), sum(map(len, rows.values())), missing, digest


def process(action, binade, directory, workers, lower, upper):
    tasks = [(action, binade, directory, index, min(index+SHARD_BLOCKS, upper))
             for index in range(lower, upper, SHARD_BLOCKS)]
    start = perf_counter()
    checked, children, hole = 0, 0, None
    digests = {}
    with ProcessPoolExecutor(max_workers=workers) as pool:
        running = [pool.submit(run_shard, task) for task in tasks]
        for n, job in enumerate(as_completed(running), 1):
            index, count, subblocks, missing, digest = job.result()
            checked += count
            children += subblocks
            if digest is not None:
                digests[index] = digest
            if missing is not None:
                hole = missing if hole is None else min(hole, missing)
            if n % 16 == 0 or n == len(tasks):
                print(f'{action}: {n}/{len(tasks)} shards, {checked} certified blocks, '
                      f'{perf_counter()-start:.1f}s', flush=True)
    manifest = hashlib.sha256()
    for index, digest in sorted(digests.items()):
        manifest.update(f'{index} {digest}\n'.encode())
    return checked, children, hole, manifest.hexdigest()


def layer_plan(output):
    plan = []
    for exponent in EXPONENTS:
        binade = Binade(exponent)
        interval = analytic_interval(binade)
        first, stop = block_range(binade, interval)
        plan.append(dict(exponent=exponent, direct=binade.direct, first=first, stop=stop,
                         block_width=binade.block_width,
                         analytically_separated=binade.bases-(interval[1]-interval[0])))
    lattice_blocks = sum(row['stop']-row['first'] for row in plan if not row['direct'])
    direct_bases = sum((row['stop']-row['first'])*row['block_width']
                       for row in plan if row['direct'])
    print(f'{len(plan)} binades require {lattice_blocks} lattice blocks '
          f'and {direct_bases} direct point checks', flush=True)
    if output:
        output.write_text(json.dumps(dict(exponent_denominator='2^116', reduced_denominator=False,
                                          binades=plan,
                                          lattice_blocks=lattice_blocks, direct_bases=direct_bases),
                                     indent=2)+'\n')


def run_direct_chunk(task):
    binade, start, stop = task
    verify_points(binade, start, stop)
    return stop-start


def verify_all_direct(workers, output):
    binades = [binade for binade in map(Binade, EXPONENTS) if binade.direct]
    checked_initial = 0
    tasks = []
    for binade in binades:
        lo, hi = analytic_interval(binade)
        checked_initial += binade.bases-(hi-lo)
        span = 1 << 14
        tasks.extend((binade, first, min(first+span, hi)) for first in range(lo, hi, span))
    checked = checked_initial
    start = perf_counter()
    with ProcessPoolExecutor(max_workers=workers) as pool:
        running = [pool.submit(run_direct_chunk, task) for task in tasks]
        for n, job in enumerate(as_completed(running), 1):
            checked += job.result()
            if n % 32 == 0 or n == len(tasks):
                print(f'verify-direct: {n}/{len(tasks)} chunks, {checked} base encodings, '
                      f'{perf_counter()-start:.1f}s', flush=True)
    assert checked == sum(binade.bases for binade in binades)
    if output:
        report = dict(status='PASS_DIRECT_BINADES', binary64_base_binades=[b.exponent for b in binades],
                      exponent_denominator='2^116', reduced_denominator=False,
                      only_possible_midpoint='1-2^-54',
                      strict_abs_log_gap_lower_bound=f'2^-{GAP_BITS}',
                      total_binary64_bases_covered=checked,
                      tool_sha256={name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                                   for name in ('midpoint_grid.py', 'midpoint_binade.py')})
        output.write_text(json.dumps(report, indent=2)+'\n')


def main():
    if not __debug__:
        raise RuntimeError('Enable Python assertions for certificate checking')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('geometry', 'plan', 'generate', 'verify', 'verify-direct'))
    parser.add_argument('--checkpoint', type=Path)
    parser.add_argument('--workers', type=int, default=1)
    parser.add_argument('--binade', type=int, default=DEFAULT_BINADE)
    parser.add_argument('--first', type=int)
    parser.add_argument('--stop', type=int)
    parser.add_argument('--report', type=Path, help='write the plan or successful verification')
    args = parser.parse_args()
    product_bound = verify_interval_policy()
    if args.mode == 'plan':
        layer_plan(args.report)
        return 0
    if args.mode == 'verify-direct':
        if args.workers < 1:
            parser.error('--workers must be positive')
        verify_all_direct(args.workers, args.report)
        return 0
    try:
        binade = Binade(args.binade)
    except ValueError as error:
        parser.error(str(error))
    active = analytic_interval(binade)
    required_start, required_stop = block_range(binade, active)
    separated = binade.bases-(active[1]-active[0])
    width = binade.block_width
    print(f'binade {binade.exponent}, {separated} of {binade.bases} bases separated analytically, '
          f'blocks [{required_start}, {required_stop}) at width {width}', flush=True)
    if args.mode == 'geometry':
        return 0
    if args.checkpoint is None:
        parser.error('--checkpoint is required')
    if args.report is not None and args.mode != 'verify':
        parser.error('--report is only available with verify')
    first = required_start if args.first is None else args.first
    end = required_stop if args.stop is None else args.stop
    if not (args.workers > 0 and first % SHARD_BLOCKS == 0 and
            required_start <= first < end <= required_stop and
            (end == required_stop or end % SHARD_BLOCKS == 0)):
        parser.error('select a nonempty range at 64-block shard boundaries')
    if args.mode == 'generate':
        args.checkpoint.mkdir(parents=True, exist_ok=True)
    checked, children, hole, manifest = process(args.mode, binade, args.checkpoint,
                                                args.workers, first, end)
    if hole is not None:
        print(f'INCOMPLETE {checked}/{end-first} blocks, first missing block {hole}', flush=True)
        return 1
    complete = args.mode == 'verify' and first == required_start and end == required_stop
    if args.report is not None:
        root = Path(__file__).resolve().parent
        repo = root.parents[1]
        sources = ('midpoint_grid.py', 'midpoint_binade.py')
        prerequisites = ('code/native_eabi_m0_pow_interval.inc',
                         'code/native_eabi_m0_pow_interval_table.inc',
                         'dev/tools/certify_m0_pow_interval.py')
        report = dict(status='PASS_COMPLETE_BINADE' if complete else 'PASS_VERIFIED_RANGE',
                      binary64_base_binade=binade.exponent, exponent_denominator='2^116',
                      reduced_denominator=False,
                      only_possible_midpoint='1-2^-54',
                      strict_abs_log_gap_lower_bound=f'2^-{GAP_BITS}',
                      lattice_start_encoding=f'{binade.encoding+active[0]:016x}',
                      lattice_stop_encoding=f'{binade.encoding+active[1]:016x}',
                      analytically_separated_bases=separated,
                      required_first_block=required_start,
                      required_checkpoint_blocks=required_stop-required_start,
                      verified_first_block=first, verified_stop_block=end,
                      verified_checkpoint_blocks=checked, verified_lattice_subblocks=children,
                      total_binary64_bases_covered=separated+max(
                          0, min(end*width, active[1])-max(first*width, active[0])),
                      maximum_512_and_1024_full_products=product_bound,
                      checkpoint_manifest_sha256=manifest,
                      tool_sha256={name: hashlib.sha256((root/name).read_bytes()).hexdigest()
                                   for name in sources},
                      interval_source_sha256={name: hashlib.sha256((repo/name).read_bytes()).hexdigest()
                                              for name in prerequisites},
                      practical_uniform_bound_for_all_binary64=False)
        if binade.exponent < 0:
            report['first_analytic_suffix_encoding'] = report['lattice_stop_encoding']
        args.report.write_text(json.dumps(report, indent=2)+'\n')
    if complete:
        print(f'PASS complete binade, {binade.bases} bases, log gap > 2^-{GAP_BITS}', flush=True)
    else:
        print(f'PASS blocks [{first}, {end})', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
