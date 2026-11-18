#!/usr/bin/env python3
"""Generate or replay compressed shards for the exponent grid with step 2^-116."""
import argparse
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from dataclasses import dataclass
import gzip
import hashlib
import json
from pathlib import Path
import shutil
from time import perf_counter

from midpoint_binade import (Binade, DEFAULT_BINADE, EXPONENTS, analytic_interval, block_range,
                             generate_parent, read_shard, verify_parent)
from midpoint_grid import verify_interval_policy

SHARD_WIDTH = 512


@dataclass(frozen=True)
class Shard:
    binade: Binade
    directory: Path
    first: int
    stop: int

    @property
    def path(self):
        return self.directory / f'{self.first:06d}-{self.stop:06d}.jsonl.gz'

    def generate(self):
        if self.path.exists():
            return 0
        partial = self.path.with_suffix('.part')
        try:
            with gzip.open(partial, 'wt', encoding='utf-8', compresslevel=1) as stream:
                for index in range(self.first, self.stop):
                    proof = generate_parent(self.binade, index)
                    stream.write(json.dumps(dict(index=index, proof=proof),
                                            separators=(',', ':'))+'\n')
            partial.replace(self.path)
        finally:
            partial.unlink(missing_ok=True)
        return self.path.stat().st_size

    def verify(self):
        with gzip.open(self.path, 'rb') as stream:
            rows = read_shard(stream, self.first, self.stop)
        if len(rows) != self.stop-self.first:
            raise ValueError('incomplete shard')
        for index, proof in rows.items():
            verify_parent(self.binade, index, proof)
        with self.path.open('rb') as source:
            return hashlib.file_digest(source, 'sha256').hexdigest()


def run_shard(mode, shard):
    try:
        if mode == 'generate':
            return shard.generate(), None
        return shard.verify(), None
    except (AssertionError, EOFError, OSError, ValueError) as error:
        return None, f'{shard.path}: {error}'


def jobs(root, binades, limit):
    for binade in binades:
        first, stop = block_range(binade, analytic_interval(binade))
        directory = root / f'e{binade.exponent}'
        if limit is not None:
            stop = min(stop, first+limit*SHARD_WIDTH)
        for index in range(first, stop, SHARD_WIDTH):
            yield Shard(binade, directory, index, min(index+SHARD_WIDTH, stop))


def run(mode, root, binades, workers, limit, reserve, report):
    all_shards = list(jobs(root, binades, limit))
    if mode == 'generate':
        root.mkdir(parents=True, exist_ok=True)
        for binade in binades:
            (root / f'e{binade.exponent}').mkdir(exist_ok=True)
        if shutil.disk_usage(root).free < reserve:
            raise OSError('checkpoint filesystem below the free-space reserve')
    print(f'{mode}: {len(all_shards)} shards, '
          f'{sum(shard.stop-shard.first for shard in all_shards)} blocks, {workers} workers',
          flush=True)
    remaining = iter(all_shards)
    start = perf_counter()
    total, saved, checked, failed = 0, 0, 0, 0
    digests = {}
    with ProcessPoolExecutor(max_workers=workers) as pool:
        active = {}

        def submit_next():
            shard = next(remaining, None)
            if shard is not None:
                active[pool.submit(run_shard, mode, shard)] = shard

        for _ in range(workers*2):
            submit_next()
        while active:
            ready, _ = wait(active, return_when=FIRST_COMPLETED)
            for result in ready:
                shard = active.pop(result)
                value, error = result.result()
                total += 1
                if error:
                    failed += 1
                    print(f'INCOMPLETE {error}', flush=True)
                else:
                    checked += shard.stop-shard.first
                    if mode == 'generate':
                        saved += value
                    else:
                        digests[shard.path.relative_to(root).as_posix()] = value
                if total % 32 == 0 or total == len(all_shards):
                    elapsed = perf_counter()-start
                    print(f'{mode}: {total}/{len(all_shards)} shards, {checked} blocks, '
                          f'{failed} incomplete, {saved} new bytes, {elapsed:.1f}s', flush=True)
                if mode == 'generate' and total % 256 == 0 and shutil.disk_usage(root).free < reserve:
                    raise OSError('checkpoint filesystem reached the free-space reserve')
                submit_next()
    if report is not None:
        manifest = hashlib.sha256()
        for name, digest in sorted(digests.items()):
            manifest.update(f'{name} {digest}\n'.encode())
        summary = dict(verified_blocks=checked, expected_blocks=sum(
            shard.stop-shard.first for shard in all_shards), incomplete_shards=failed,
            binades=[binade.exponent for binade in binades], pilot=limit is not None,
            exponent_grid_step='2^-116', strict_abs_log_gap_lower_bound='2^-900',
            checkpoint_manifest_sha256=manifest.hexdigest(),
            tool_sha256={})
        for name in ('midpoint_grid.py', 'midpoint_binade.py', 'midpoint_layer.py'):
            with Path(__file__).with_name(name).open('rb') as source:
                summary['tool_sha256'][name] = hashlib.file_digest(source, 'sha256').hexdigest()
        report.write_text(json.dumps(summary, indent=2)+'\n')
    return 1 if failed else 0


def main():
    if not __debug__:
        raise RuntimeError('Enable Python assertions for certificate checking')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('generate', 'verify'))
    parser.add_argument('--checkpoint', type=Path, required=True)
    parser.add_argument('--workers', type=int, default=1)
    parser.add_argument('--binade', type=int, action='append', help='limit the run to these binades')
    parser.add_argument('--pilot', type=int, help='maximum shards per selected binade')
    parser.add_argument('--reserve-gib', type=int, default=32, help='keep this much space free')
    parser.add_argument('--report', type=Path, help='write the verification manifest summary')
    args = parser.parse_args()
    if args.workers < 1 or args.reserve_gib < 0 or (args.pilot is not None and args.pilot < 1):
        parser.error('invalid worker, reserve or pilot size')
    if args.report is not None and args.mode != 'verify':
        parser.error('--report requires verify')
    verify_interval_policy()
    if args.binade:
        binades = [Binade(exponent) for exponent in sorted(set(args.binade))]
        if any(binade.direct for binade in binades):
            parser.error('use midpoint_binade.py verify-direct for the shortest subnormal binades')
    else:
        # Start at the other analytic edge, then leave a complete
        # checkpoint for each successive binade. The default negative
        # edge and the direct subnormal binades have separate proofs.
        order = (738, *EXPONENTS)
        binades = [Binade(exponent) for exponent in dict.fromkeys(order) if exponent != DEFAULT_BINADE]
        binades = [binade for binade in binades if not binade.direct]
    return run(args.mode, args.checkpoint, binades, args.workers, args.pilot,
               args.reserve_gib << 30, args.report)


if __name__ == '__main__':
    raise SystemExit(main())
