#!/usr/bin/env python3
"""Generate and independently verify the e=-739, q=2^116 pow certificate."""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import fcntl
import hashlib
import json
from pathlib import Path
from time import perf_counter

from midpoint_grid import (GAP_BITS, DENOMINATOR, FixedInterval, ceil_div,
                           constants, generate_block, verify_block,
                           verify_interval_policy)

BINADE = -739
ENCODING = (BINADE+1023) << 52
BASES = 1 << 52
SPLIT = 18
BLOCK_WIDTH = BASES >> SPLIT
SHARD_BLOCKS = 64


def analytic_suffix():
    """Find an encoding from which p*abs(log(x)) is too small for all p."""
    precision = 1024
    grid = FixedInterval(precision)
    log2, target = constants(precision)
    p_max = (1 << 53)-1
    strip = DENOMINATOR << (precision-GAP_BITS)

    def separated(offset):
        # Use the lower mantissa logarithm when bounding -log(x) above.
        mantissa_log_lower, _ = grid.log(BASES+offset, BASES)
        logarithm_upper = -BINADE*log2[1]-mantissa_log_lower
        return p_max*logarithm_upper+strip < target[0]

    lower, upper = 0, BASES
    assert not separated(lower) and separated(upper)
    while upper-lower > 1:
        middle = (lower+upper)//2
        if separated(middle):
            upper = middle
        else:
            lower = middle
    assert separated(upper) and not separated(upper-1)
    # The true abs(log(x)) decreases monotonically throughout the binade.
    return upper


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


def verify_parent(index, proof):
    """Every child must cover its own part of the parent with no gaps."""
    spans = sorted(verify_block(row) for row in proof)
    first = ENCODING+index*BLOCK_WIDTH
    for start, end in spans:
        assert start == first and end > start, ('coverage discontinuity', index)
        first = end
    assert first == ENCODING+(index+1)*BLOCK_WIDTH, ('wrong block extent', index)


def generate_parent(index):
    children = []
    for block in range(index*4, index*4+4):
        for degree, work_bits, delta in ((6, 90, 0.50), (7, 98, 0.70)):
            row, _ = generate_block(BINADE, SPLIT+2, block, degree, work_bits, delta, 'newton')
            if row is not None:
                try:
                    verify_block(row)
                except AssertionError:
                    continue
                children.append(row)
                break
        else:
            break
    if len(children) == 4:
        return children
    for degree, work_bits, delta in ((8, 98, 0.55), (9, 110, 0.88), (10, 128, 0.88)):
        row, _ = generate_block(BINADE, SPLIT, index, degree, work_bits, delta, 'newton')
        if row is not None:
            try:
                verify_block(row)
            except AssertionError:
                continue
            return [row]
    return None


def run_shard(task):
    action, directory, lower, upper = task
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
            verify_parent(index, proof)
    else:
        with path.open('a+b', buffering=0) as journal:
            fcntl.flock(journal, fcntl.LOCK_EX | fcntl.LOCK_NB)
            journal.seek(0)
            rows = read_shard(journal, lower, upper, repair=True)
            for index in range(lower, upper):
                if index in rows:
                    continue
                proof = generate_parent(index)
                if proof is not None:
                    data = (json.dumps(dict(index=index, proof=proof), separators=(',', ':'))+'\n').encode()
                    if journal.write(data) != len(data):
                        raise OSError(f'Short append to checkpoint {path}')
                    rows[index] = proof
    missing = next((i for i in range(lower, upper) if i not in rows), None)
    return lower, len(rows), sum(map(len, rows.values())), missing, digest


def process(action, directory, workers, lower, upper):
    tasks = [(action, directory, index, min(index+SHARD_BLOCKS, upper))
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


def main():
    if not __debug__:
        raise RuntimeError('Enable Python assertions for certificate checking')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('geometry', 'generate', 'verify'))
    parser.add_argument('--checkpoint', type=Path)
    parser.add_argument('--workers', type=int, default=1)
    parser.add_argument('--first', type=int, default=0)
    parser.add_argument('--stop', type=int)
    parser.add_argument('--report', type=Path, help='write a report after successful verification')
    args = parser.parse_args()
    product_bound = verify_interval_policy()
    cutoff = analytic_suffix()
    blocks = ceil_div(cutoff, BLOCK_WIDTH)
    print(f'binade {BINADE}, analytic suffix starts at {ENCODING+cutoff:016x}, '
          f'{blocks} lattice blocks required', flush=True)
    if args.mode == 'geometry':
        print(f'{BASES-cutoff} analytically separated base encodings of {BASES}', flush=True)
        return 0
    if args.checkpoint is None:
        parser.error('--checkpoint is required')
    if args.report is not None and args.mode != 'verify':
        parser.error('--report is only available with verify')
    end = blocks if args.stop is None else args.stop
    if not (args.workers > 0 and args.first % SHARD_BLOCKS == 0 and
            0 <= args.first < end <= blocks and (end == blocks or end % SHARD_BLOCKS == 0)):
        parser.error('select a nonempty range at 64-block shard boundaries')
    if args.mode == 'generate':
        args.checkpoint.mkdir(parents=True, exist_ok=True)
    checked, children, hole, manifest = process(args.mode, args.checkpoint, args.workers, args.first, end)
    if hole is not None:
        print(f'INCOMPLETE {checked}/{end-args.first} blocks, first missing block {hole}', flush=True)
        return 1
    complete = args.mode == 'verify' and args.first == 0 and end == blocks
    if args.report is not None:
        root = Path(__file__).resolve().parent
        repo = root.parents[1]
        sources = ('midpoint_grid.py', 'midpoint_binade.py')
        prerequisites = ('code/native_eabi_m0_pow_interval.inc',
                         'code/native_eabi_m0_pow_interval_table.inc',
                         'dev/tools/certify_m0_pow_interval.py')
        report = dict(status='PASS_COMPLETE_BINADE' if complete else 'PASS_VERIFIED_RANGE',
                      binary64_base_binade=BINADE, exponent_denominator='2^116',
                      only_possible_midpoint='1-2^-54',
                      strict_abs_log_gap_lower_bound=f'2^-{GAP_BITS}',
                      first_analytic_suffix_encoding=f'{ENCODING+cutoff:016x}',
                      analytically_separated_bases=BASES-cutoff,
                      required_checkpoint_blocks=blocks,
                      verified_first_block=args.first, verified_stop_block=end,
                      verified_checkpoint_blocks=checked, verified_lattice_subblocks=children,
                      total_binary64_bases_covered=BASES-cutoff+
                      min(end*BLOCK_WIDTH, cutoff)-args.first*BLOCK_WIDTH,
                      maximum_512_and_1024_full_products=product_bound,
                      checkpoint_manifest_sha256=manifest,
                      tool_sha256={name: hashlib.sha256((root/name).read_bytes()).hexdigest()
                                   for name in sources},
                      interval_source_sha256={name: hashlib.sha256((repo/name).read_bytes()).hexdigest()
                                              for name in prerequisites},
                      practical_uniform_bound_for_all_binary64=False)
        args.report.write_text(json.dumps(report, indent=2)+'\n')
    if complete:
        print(f'PASS complete binade, {BASES} bases, log gap > 2^-{GAP_BITS}', flush=True)
    else:
        print(f'PASS blocks [{args.first}, {end})', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
