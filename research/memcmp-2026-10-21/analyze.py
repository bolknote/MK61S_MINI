#!/usr/bin/env python3
"""Collapse paired hardware samples; keep early exits separate from equal spans."""
import argparse
import gzip
import json
import statistics
from pathlib import Path

KEYS = ('source', 'mode', 'size', 'left_offset', 'right_offset')
MODES = {0: 'equal', 1: 'first', 2: 'byte4', 3: 'middle', 4: 'last', 5: 'identity'}


def analyze(data, candidate):
    assert data['status'] == 'PASS'
    groups = {}
    for group in data['groups']:
        for row in group['rows']:
            key = tuple(row[k] for k in KEYS)
            groups.setdefault(key, []).append(row)
    rows = []
    for key, samples in sorted(groups.items()):
        assert len(samples) == data['runs'], (key, len(samples), data['runs'])
        times = {name: statistics.median(r['timings'][name]['median_cycles'] for r in samples)
                 for name in samples[0]['timings']}
        rows.append(dict(zip(KEYS, key), cycles=times))

    summary = dict(cpu=data['cpu'], cases=len(rows), runs=data['runs'], candidate=candidate,
                   correctness_checks=sum(g['checks'] for g in data['groups']), rows=rows,
                   comparisons={})
    for baseline in ('baseline', 'resident', 'runtime', 'own4', 'own16', 'own64', 'own_low64',
                     'selected_body', 'selected_runtime', 'byte', 'sram'):
        if baseline == candidate or baseline not in rows[0]['cycles']:
            continue
        comparisons = {}
        for label, predicate in [('nonempty_distinct', lambda r: r['size'] and r['mode'] != 5),
                                 ('zero', lambda r: not r['size'])] + [
                (label, lambda r, mode=mode: r['size'] and r['mode'] == mode)
                for mode, label in MODES.items()]:
            selected = [r for r in rows if predicate(r)]
            if not selected:
                continue
            speeds = [r['cycles'][baseline] / r['cycles'][candidate] for r in selected
                      if r['cycles'][baseline] > 0 and r['cycles'][candidate] > 0]
            losses = [dict((k, r[k]) for k in KEYS) |
                      dict(old=r['cycles'][baseline], new=r['cycles'][candidate])
                      for r in selected if r['cycles'][candidate] > r['cycles'][baseline] + 1]
            comparisons[label] = dict(cases=len(selected), positive_samples=len(speeds),
                                      median_speedup=statistics.median(speeds) if speeds else None,
                                      minimum_speedup=min(speeds) if speeds else None,
                                      maximum_speedup=max(speeds) if speeds else None,
                                      slower_by_over_one_cycle=losses)
        summary['comparisons'][baseline] = comparisons
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--candidate', default='sdk')
    args = parser.parse_args()
    raw = args.input.read_bytes()
    data = json.loads(gzip.decompress(raw) if args.input.suffix == '.gz' else raw)
    summary = analyze(data, args.candidate)
    args.output.write_text(json.dumps(summary, indent=2) + '\n')
    print(summary['cpu'], summary['cases'], 'cases;', summary['runs'], 'runs;',
          summary['correctness_checks'], 'correctness checks')
    for baseline, comparisons in summary['comparisons'].items():
        for mode in ('nonempty_distinct', 'equal', 'first', 'last'):
            if mode not in comparisons:
                continue
            result = comparisons[mode]
            print(baseline, mode, 'speedup', result['median_speedup'],
                  'worst', result['minimum_speedup'],
                  'losses >1cy', len(result['slower_by_over_one_cycle']))
    for row in summary['rows']:
        if row['source'] == 0 and row['size'] in (0, 1, 4, 16, 64, 4096) and \
                row['mode'] in (0, 1, 4) and row['left_offset'] == 0 and row['right_offset'] in (0, 1):
            print(MODES[row['mode']], row['size'], row['left_offset'], row['right_offset'],
                  {k: round(v, 2) for k, v in row['cycles'].items()})


if __name__ == '__main__':
    main()
