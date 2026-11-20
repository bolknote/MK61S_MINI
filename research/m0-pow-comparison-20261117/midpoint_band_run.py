#!/usr/bin/env python3
"""Generate a small-exponent layer in resumable, independently replayed archives."""

import argparse
from collections import Counter
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from functools import partial
import fcntl
import gzip
from hashlib import file_digest, sha256
import json
import os
from pathlib import Path
from shutil import copyfile
from time import monotonic, time

from midpoint_band_layer import (GAP, INTERVAL_GAPS, SCHEMA, SHIFT, archive_range, generate_block,
                                 indexed_spans, merged_ranges, record_batches, require, spans, tasks,
                                 verify_early_interval, verify_rows)
from midpoint_grid import use_flint_products


def missing_ranges(covered, first, last, shard_size):
    start = first
    for a,b in [*merged_ranges(covered),(last,last)]:
        require(start <= a <= b <= last,'archive lies outside the requested range')
        for left in range(start,a,shard_size):
            yield left,min(a,left+shard_size)
        start = b


def plan_data(width, shift, gap=GAP):
    plan = tuple(spans(width,shift,gap))
    total = max(stop for _,stop,*_ in indexed_spans(plan))
    digest = sha256(json.dumps(plan,separators=(',',':')).encode()).hexdigest()
    schema = SCHEMA if shift == SHIFT else f'pow-q{shift}-rotated-layer-v1'
    # The header keeps the original, weaker claim. Replays widen the strip
    # from scratch, including the analytic midpoint and mantissa exclusions.
    return plan, [schema,GAP,width,digest], total


def read_archives(directory, prefix, total):
    paths = sorted(directory.glob('*.jsonl.gz'))
    archives = {archive_range(path,prefix,total):path for path in paths}
    require(len(archives) == len(paths),'duplicate archive ranges')
    return archives


def write_json(path, result):
    scratch = path.with_suffix('.tmp')
    scratch.write_text(json.dumps(result,sort_keys=True)+'\n')
    os.replace(scratch,path)


def archive_name(first, stop):
    return f'{first:08}-{stop:08}.jsonl.gz'


def import_archives(paths, directory, prefix, total):
    for path in paths:
        first,stop = archive_range(path,prefix,total)
        destination = directory/archive_name(first,stop)
        if destination.exists():
            with path.open('rb') as a, destination.open('rb') as b:
                require(file_digest(a,'sha256').digest() == file_digest(b,'sha256').digest(),
                        f'import conflicts with {destination.name}')
        else:
            scratch = destination.with_suffix('.tmp')
            copyfile(path,scratch)
            os.replace(scratch,destination)


def init_checker(plan, shift, gap, exact_flint):
    global replay_plan, replay_shift, replay_gap
    replay_plan = plan
    replay_shift = shift
    replay_gap = gap
    if exact_flint:
        use_flint_products()


def replay(path, prefix, first, stop, total):
    stats = Counter()
    with gzip.open(path,'rt') as file:
        require(json.loads(file.readline()) == prefix+[first,stop,total],'archive header changed')
        for job in record_batches(file,tasks(replay_plan,first,stop,replay_shift)):
            stats.update(verify_rows(job,replay_gap))
    with path.open('rb') as f:
        checksum = file_digest(f,'sha256').hexdigest()
    return dict(first=first,stop=stop,sha256=checksum,leaves=dict(stats))


def save_archive(path, header, rows):
    scratch = path.with_suffix('.tmp')
    with gzip.open(scratch,'wt',compresslevel=3) as file:
        print(json.dumps(header,separators=(',',':')),file=file)
        for index in range(len(rows)):
            print(json.dumps(rows[index],separators=(',',':')),file=file)
    require(not path.exists(),f'archive already exists {path.name}')
    os.replace(scratch,path)


def verify_complete(directory, width, shift, workers, flint_products, gap=GAP):
    """Check original certificates without depending on progress or manifest files."""
    require(__debug__ and workers > 0,'invalid verifier settings')
    plan, prefix, total = plan_data(width,shift,gap)
    archives = read_archives(directory,prefix,total)
    require(merged_ranges(archives) == [(0,total)],'archives do not cover the entire layer')
    leaves = Counter()
    with ProcessPoolExecutor(max_workers=workers,initializer=init_checker,
                             initargs=(plan,shift,gap,flint_products)) as pool:
        checks = [pool.submit(replay,path,prefix,a,b,total) for (a,b),path in archives.items()]
        for future in checks:
            leaves.update(future.result()['leaves'])
    require(not leaves['open'],'the layer contains unresolved blocks')
    return total, leaves


def run(args):
    plan, prefix, total = plan_data(args.width,args.shift,args.gap)
    first,stop = args.first,total if args.stop is None else args.stop
    require(0 <= first < stop <= total,'invalid plan range')
    digest = prefix[-1]
    archive_dir = args.directory/'archives'
    archive_dir.mkdir(exist_ok=True)
    import_archives(args.import_archive,archive_dir,prefix,total)
    existing = read_archives(archive_dir,prefix,total)
    needed = list(missing_ranges(list(existing),first,stop,args.shard_size))
    if args.verify_only:
        require(not needed,'the supplied archives leave gaps in the requested range')
    generated = sum(b-a for a,b in existing)
    checked = 0
    leaves = Counter()
    reports = []
    started = monotonic()
    request = ((a,b,index,block) for a,b in needed
               for index,block in enumerate(tasks(plan,a,b,args.shift)))
    interval_work = verify_early_interval(args.shift,args.gap) if args.gap in INTERVAL_GAPS else None

    def report(status, **extra):
        result = dict(status=status,shift=args.shift,gap_bits=args.gap,plan_sha256=digest,
                      first=first,stop=stop,total_plan_roots=total,
                      generated_roots=generated,verified_roots=checked,verified_archives=len(reports),
                      elapsed_s=round(monotonic()-started,3),updated_unix=round(time()),
                      leaves=dict(leaves),**extra)
        write_json(args.directory/'status.json',result)
        return result

    generate = partial(generate_block,flatter=args.flatter,gap=args.gap)
    status = 'RUNNING'
    try:
        with ProcessPoolExecutor(max_workers=args.workers,initializer=use_flint_products) as gen_pool, \
                ProcessPoolExecutor(max_workers=args.check_workers,initializer=init_checker,
                                    initargs=(plan,args.shift,args.gap,args.flint_products)) as check_pool:
            checks = {check_pool.submit(replay,path,prefix,a,b,total): (a,b)
                      for (a,b),path in existing.items()}
            gen_jobs, buffers = {}, {}
            exhausted = False
            last_report = started-60
            while gen_jobs or checks or not exhausted:
                while not exhausted and len(gen_jobs) < 3*args.workers:
                    job = next(request,None)
                    if job is None:
                        exhausted = True
                        break
                    a,b,index,block = job
                    gen_jobs[gen_pool.submit(generate,block)] = a,b,index
                if not gen_jobs and not checks:
                    break
                if monotonic()-last_report >= 10:
                    report(status,queued_generation=len(gen_jobs),queued_replay=len(checks))
                    last_report = monotonic()
                done,_ = wait([*gen_jobs,*checks],timeout=10,return_when=FIRST_COMPLETED)
                for future in done:
                    result = future.result()
                    if future in gen_jobs:
                        a,b,index = gen_jobs.pop(future)
                        rows = buffers.setdefault((a,b),{})
                        rows[index] = result
                        if len(rows) == b-a:
                            path = archive_dir/archive_name(a,b)
                            save_archive(path,prefix+[a,b,total],rows)
                            del buffers[a,b]
                            generated += b-a
                            checks[check_pool.submit(replay,path,prefix,a,b,total)] = a,b
                    else:
                        a,b = checks.pop(future)
                        reports.append(result)
                        leaves.update(result['leaves'])
                        checked += b-a
            require(not buffers,'unfinished generated archive')
        require(checked == generated == stop-first and
                merged_ranges((row['first'],row['stop']) for row in reports) == [(first,stop)],
                'verified archives do not cover the requested range')
        status = 'INCOMPLETE' if leaves['open'] else (
            f'VERIFIED_Q{args.shift}' if (first,stop) == (0,total) else 'VERIFIED_RANGE')
        write_json(args.directory/'manifest.json',dict(plan_sha256=digest,gap_bits=args.gap,
                   archives=sorted(reports,key=lambda row:row['first'])))
    except BaseException as error:
        report('FAILED',error=str(error))
        raise
    extra = {'maximum_wide_products_per_interval':interval_work} if interval_work and status != 'INCOMPLETE' else {}
    print(json.dumps(report(status,**extra),sort_keys=True),flush=True)
    return 2 if status == 'INCOMPLETE' else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path)
    parser.add_argument('--width',type=int,default=42)
    parser.add_argument('--shift',type=int,default=SHIFT,help='binary exponent grid denominator shift')
    parser.add_argument('--gap',type=int,choices=(*INTERVAL_GAPS,GAP),default=GAP,
                        help='exponent of the strict logarithmic gap to exclude')
    parser.add_argument('--first',type=int,default=0)
    parser.add_argument('--stop',type=int)
    parser.add_argument('--shard-size',type=int,default=256)
    parser.add_argument('--workers',type=int,default=8)
    parser.add_argument('--check-workers',type=int,default=2)
    parser.add_argument('--flatter',type=Path)
    parser.add_argument('--flint-products',action='store_true',help='use exact FLINT products in replay')
    parser.add_argument('--import-archive',type=Path,action='append',default=[])
    parser.add_argument('--verify-only',action='store_true')
    args = parser.parse_args()
    require(__debug__ and min(args.shard_size,args.workers,args.check_workers)>0,'invalid run settings')
    for name in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):
        os.environ[name] = '1'
    args.directory.mkdir(parents=True,exist_ok=True)
    with (args.directory/'lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        return run(args)


if __name__ == '__main__':
    raise SystemExit(main())
