#!/usr/bin/env python3
"""Generate and replay one full control row in each surviving y binade."""

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from functools import partial
import gzip
from itertools import product
import json
import os
from pathlib import Path
from time import monotonic, process_time

from midpoint_exponential_row import flatter_reducer, prove_row, verify_cover
from midpoint_grid import use_flint_products
from midpoint_scale_projection import CONTROL_M, CONTROL_X
from midpoint_surface_rotated import reduce_lattice, require


WIDTH = 43
SHAPES = tuple(product((32,34,36,38),(6,8)))
reducer = reduce_lattice


def witness_rows(path, binade):
    projection = json.loads(path.read_text())
    rows = {}
    for key,witness in projection['full_row_witnesses'].items():
        b = int(key)
        if binade is None or binade == b:
            rows[b] = [witness['x_scale'],witness['midpoint_scale'],b,
                       CONTROL_X[0],CONTROL_M[0],CONTROL_M[1]-1]
    return rows


def init_prover(flatter):
    global reducer
    use_flint_products()
    if flatter:
        reducer = partial(flatter_reducer,flatter)


def tile(fields, width, offset):
    first = fields[4]+2*offset
    return fields[:4]+[first,first+(2 << width)-2]


def calibrate_tile(fields, width, degree, offset):
    start = monotonic()
    report = prove_row(tile(fields,width,offset),degree,112,True,reducer)
    return fields[2],width,degree,offset,report['status'],round(monotonic()-start,6),report['best_log2']


def solve_tile(fields, width, degree):
    start = monotonic()
    result = prove_row(fields,degree,112,True,reducer)
    if result['proof']:
        return result,[],monotonic()-start
    require(width >= 18, f'smallest tile remains open {fields}')
    half = 1 << (width-1)
    split = [(tile(fields,width-1,offset),width-1,degree) for offset in (0,half)]
    return result,split,monotonic()-start


def certificate_path(directory, binade):
    return directory/f'band-{binade:+03}.jsonl.gz'


def replay(fields, path):
    start = monotonic()
    cpu = process_time()
    with gzip.open(path,'rt') as stream:
        segments = verify_cover(fields,map(json.loads,stream))
    return dict(row=fields,verified_tiles=segments,verified_m=1<<WIDTH,
                verify_wall_s=round(monotonic()-start,3),verify_cpu_s=round(process_time()-cpu,3))


def calibrate(pool, rows, path):
    jobs = [pool.submit(calibrate_tile,fields,width,degree,offset)
            for fields in rows.values() for width,degree in SHAPES
            for offset in (0,(1<<WIDTH)-(1<<width))]
    with path.open('a') as stream:
        for future in as_completed(jobs):
            print(json.dumps(future.result()),file=stream,flush=True)


def select(rows, calibration):
    result = {}
    for binade in rows:
        costs = []
        for width,degree in SHAPES:
            trials = [s for s in calibration if s[:3] == [binade,width,degree]]
            if len(trials) >= 2 and all(s[4] == 'EXCLUDED' for s in trials):
                costs.append((sum(s[5] for s in trials)/(len(trials)*(1<<width)),width,degree))
        result[binade] = min(costs)[1:] if costs else (32,8)
    return result


def prove(pool, rows, directory, calibration_path):
    start = monotonic()
    calibration = list(map(json.loads,calibration_path.read_text().splitlines()))
    config = select(rows,calibration)
    print('config',json.dumps(config,sort_keys=True),flush=True)
    live = []
    for binade,(width,degree) in config.items():
        for offset in range(0,1<<WIDTH,1<<width):
            live.append(pool.submit(solve_tile,tile(rows[binade],width,offset),width,degree))
    opened = dict.fromkeys(rows,0)
    completed = {b:[] for b in rows}
    elapsed = dict.fromkeys(rows,0.0)
    while live:
        pending = []
        for future in as_completed(live):
            report,split,duration = future.result()
            binade = report['row'][2]
            elapsed[binade] += duration
            if split:
                opened[binade] += 1
                pending.extend(split)
            else:
                completed[binade].append(dict(row=report['row'],proof=report['proof']))
        live = [pool.submit(solve_tile,*job) for job in pending]
        print('wave',sum(map(len,completed.values())),len(live),round(monotonic()-start,3),flush=True)
    for binade,reports in completed.items():
        with gzip.open(certificate_path(directory,binade),'wt',compresslevel=3) as stream:
            for report in sorted(reports,key=lambda r:r['row'][4]):
                print(json.dumps(report,separators=(',',':')),file=stream)
        print(json.dumps(dict(exponent=binade,segments=len(reports),split=opened[binade],
                              accumulated_worker_wall_s=round(elapsed[binade],3))),flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('calibrate','prove','verify'))
    parser.add_argument('--directory',type=Path,required=True)
    parser.add_argument('--projection',type=Path,required=True)
    parser.add_argument('--flatter',type=Path)
    parser.add_argument('--workers',type=int,default=8)
    parser.add_argument('--band',type=int)
    args = parser.parse_args()
    require(__debug__, 'enable interval assertions')
    for name in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):
        os.environ[name] = '1'
    rows = witness_rows(args.projection,args.band)
    require(rows, 'no row in the requested binade')
    path = args.directory/'calibration.jsonl'
    args.directory.mkdir(parents=True,exist_ok=True)
    start = monotonic()
    init = None if args.mode == 'verify' else init_prover
    initargs = () if init is None else (args.flatter,)
    with ProcessPoolExecutor(max_workers=args.workers,initializer=init,initargs=initargs) as pool:
        if args.mode == 'calibrate':
            calibrate(pool,rows,path)
        elif args.mode == 'prove':
            prove(pool,rows,args.directory,path)
        else:
            jobs = [pool.submit(replay,fields,certificate_path(args.directory,b)) for b,fields in rows.items()]
            for future in as_completed(jobs):
                print(json.dumps(future.result()),flush=True)
    print('DONE',args.mode,round(monotonic()-start,3),flush=True)


if __name__ == '__main__':
    main()
