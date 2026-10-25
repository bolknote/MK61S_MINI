#!/usr/bin/env python3
"""Verify the eighth offline math checkpoint without running its producers."""
from pathlib import Path
from collections import Counter
from itertools import zip_longest
import argparse
import gzip
import hashlib
import importlib.util
import json
import subprocess
import sys

sys.dont_write_bytecode = True
W = Path(__file__).resolve().parent
ROOT = W.parents[1]
PREVIOUS = W.parent / 'm0-math-checkpoint-20261025-3'
spec = importlib.util.spec_from_file_location('seventh_math_checkpoint', PREVIOUS / 'verify.py')
previous = importlib.util.module_from_spec(spec)
spec.loader.exec_module(previous)
image_fingerprint = previous.image_fingerprint
STAGES = ['soft', 'lut', 'one', 'inline']


def sha(data):
    return hashlib.sha256(data).hexdigest()


def raw(name, directory=W):
    path = directory / name
    return path.read_bytes() if path.exists() else gzip.decompress(path.with_suffix(path.suffix + '.gz').read_bytes())


def report(name, directory=W):
    return json.loads(raw(name, directory))


def lines(name, directory=W):
    with gzip.open(directory / name, 'rt') as stream:
        for line in stream:
            yield json.loads(line)


def equal(a, b):
    a, b = int(a, 16), int(b, 16)
    if (b & 0x7fffffffffffffff) > 0x7ff0000000000000:
        return bool((a & 0x7fffffffffffffff) > 0x7ff0000000000000 and a & (1 << 51))
    return a == b


def key(row):
    return row['x'], row['y'], row['SIO']


def public_recount(stage):
    prefix = 'components/pow-reciprocal-' + stage + '/'
    prior = (lines('components/pow-boundary128/qualification-records.jsonl.gz', PREVIOUS)
             if stage == 'soft' else lines('components/pow-reciprocal-' + STAGES[STAGES.index(stage) - 1] + '/qualification-records.jsonl.gz'))
    fresh = report(prefix + 'new-qualification.json')
    controls = {key(row): row for row in fresh['rows']}
    assert len(controls) == 10254
    seen, old_loss, new_loss = set(), set(), set()
    costs, deltas, accelerated = Counter(), Counter(), Counter()
    wrong = variants = 0
    for row, parent in zip_longest(lines(prefix + 'qualification-records.jsonl.gz'), prior):
        assert row is not None and parent is not None
        k = key(row)
        assert k == key(parent) and k not in seen
        seen.add(k)
        assert row['candidate'] == parent['candidate'] and row['expected'] == parent['expected']
        assert row['references'] == parent['references']
        c, p = row['candidate_instructions'], row['parent_reciprocal_instructions']
        assert p == parent['candidate_instructions'] and c <= p
        assert equal(row['candidate'], row['expected'])
        deltas[c - p] += 1
        if c < p:
            accelerated[row['SIO']] += 1
        for ref in row['references'].values():
            variants += 1
            assert ref['correct_Qfplib'] == equal(ref['output'], row['expected'])
            if not ref['correct_Qfplib']:
                wrong += 1
                continue
            q = ref['instructions']
            costs['faster' if c < q else 'equal' if c == q else 'slower'] += 1
            if p > q:
                old_loss.add(k[:2])
            if c > q:
                new_loss.add(k[:2])
        if k in controls:
            control = controls.pop(k)
            assert control['expected'] == row['expected']
            assert all(control['outputs'][n] == row['candidate'] and control['correct'][n]
                       for n in ['parent', 'control', 'candidate'])
            assert control['instructions']['parent'] == control['instructions']['control'] == p
            assert control['instructions']['candidate'] == c
            for label, ref in row['references'].items():
                assert (ref['output'], ref['instructions'], ref['correct_Qfplib']) == (
                    control['outputs'][label], control['instructions'][label], control['correct'][label])
    assert len(seen) == 241960 and len({k[:2] for k in seen}) == 120980 and not controls
    assert variants == 279522 and wrong == 77106 and not new_loss - old_loss
    result, qualification = report(prefix + 'result.json'), report(prefix + 'qualification.json')
    assert [len(old_loss), len(new_loss)] == result['loss_pairs']
    assert costs == qualification['correct_Qfplib_comparison']
    fixed = {tuple(k) for k in qualification['fixed_pairs']}
    assert old_loss - new_loss == fixed
    assert not result['candidate_wrong'] and not result['new_raw_losses']
    return dict(losses=[len(old_loss), len(new_loss)], strict_fixes=len(fixed),
                accelerated_states=dict(accelerated), instruction_delta_histogram=dict(deltas),
                correct_Qfplib_comparisons=dict(costs), wrong_Qfplib_retained=wrong)


def scalar_recount(stage):
    prefix = 'components/pow-reciprocal-' + stage + '/'
    proof = report(prefix + 'direct-proof.json')
    rows = lines(prefix + 'direct-records.jsonl.gz') if stage in ['one', 'inline'] else iter(proof['rows'])
    counts = {name: Counter() for name in ['parent', 'candidate']}
    increases, deltas = Counter(), Counter()
    wrong = cases = new_losses = 0
    for row in rows:
        cases += 1
        r = row['results']
        assert r['parent'] == r['control']
        assert r['parent']['output'] == r['candidate']['output']
        assert r['candidate']['correct'] and equal(r['candidate']['output'], row['expected'])
        q = r['Qfplib']
        assert q['correct'] == equal(q['output'], row['expected'])
        delta = r['candidate']['instructions'] - r['parent']['instructions']
        deltas[delta] += 1
        if delta > 0:
            increases[delta] += 1
        if not q['correct']:
            wrong += 1
            continue
        for label in counts:
            cost = r[label]['instructions']
            counts[label]['faster' if cost < q['instructions'] else 'equal' if cost == q['instructions'] else 'slower'] += 1
        new_losses += r['candidate']['instructions'] > q['instructions'] >= r['parent']['instructions']
    # Early exhaustive seed calibration retains only selected timing rows.
    # Its per-divisor correctness is not a per-divisor Qfplib speed claim.
    if stage in ['one', 'inline']:
        assert cases == proof['states'] and cases * 4 == proof['actual_ARM_calls']
        assert {k: dict(v) for k, v in counts.items()} == proof['correct_Qfplib_comparisons']
        assert not new_losses
    if stage == 'inline':
        assert cases == 41988 and wrong == 9600
        assert counts['parent']['slower'] == 7422 and counts['candidate']['slower'] == 13
        assert increases == {8: 3168, 2: 352, 11: 6144}
    return dict(saved_timing_rows=cases, correct_Qfplib_comparisons={k: dict(v) for k, v in counts.items()},
                wrong_Qfplib_timing_rows_retained=wrong, parent_increase_histogram=dict(increases),
                exhaustive_Qfplib_per_seed_speed_claim=False)


def verify(check_local=False):
    index = report('checkpoint.json')
    assert sha((PREVIOUS / 'checkpoint.json').read_bytes()) == index['base_checkpoint_sha256']
    previous.verify(False)
    for name, digest in index['files'].items():
        assert sha((W / name).read_bytes()) == digest, name
    sources = {}
    for entry in report('provenance.json')['archived_files']:
        data = (W / entry['path']).read_bytes()
        decoded = gzip.decompress(data) if entry['encoding'] == 'gzip' else data
        assert sha(data) == entry['sha256'] and sha(decoded) == entry['uncompressed_sha256']
        assert len(decoded) == entry['uncompressed_bytes'] and entry['source'] not in sources
        sources[entry['source']] = entry
        if check_local:
            assert (ROOT / entry['source']).read_bytes() == decoded, entry['source']

    def pin(source, value):
        path = Path(source)
        if path.is_absolute():
            path = path.relative_to(index['original_root'])
        source = str(path)
        if source in sources:
            entry = sources[source]
            assert (entry['uncompressed_sha256'], entry['uncompressed_bytes']) == (value['sha256'], value['bytes']), source
        if check_local:
            data = (ROOT / source).read_bytes()
            assert sha(data) == value['sha256'] and len(data) == value['bytes'], source

    for name, meta in index['components'].items():
        prefix = 'components/' + name + '/'
        frozen = report(prefix + 'FROZEN.json')
        assert sha(raw(prefix + 'FROZEN.json')) == meta['FROZEN_sha256']
        for rel, value in frozen['files'].items():
            pin(meta['original_directory'] + '/' + rel, value)
        if name != 'ddiv-seed-lut':
            for path, value in report(prefix + 'source-lineage-pins.json')['files'].items():
                pin(path, value)
    for name, meta in index['reviews'].items():
        prefix = 'reviews/' + name + '/'
        review = report(prefix + 'FINAL-REVIEW.json')
        assert review['status'] == meta['status'] and review['component_review_complete']
        assert sha(raw(prefix + 'FINAL-REVIEW.json')) == meta['sha256']
        for rel, value in report(prefix + 'MANIFEST.json')['files'].items():
            pin(meta['original_directory'] + '/' + rel, value)
        receipt = report('receipts/' + name + '/RECEIPT.json')
        assert receipt['independent_review_sha256'] == meta['sha256']
        assert not receipt['integration_GO']
        for value in receipt['pins']:
            pin(value['path'], value)
    pub = {stage: public_recount(stage) for stage in STAGES}
    assert [pub[s]['losses'] for s in STAGES] == [[11434, 11386], [11386, 11377], [11377, 11372], [11372, 11371]]
    scalar = {stage: scalar_recount(stage) for stage in STAGES}
    latest = report('components/pow-reciprocal-inline/result.json')
    assert latest['total_qualified_fresh_ARM_calls'] == 615606
    assert latest['actual_directed_MPFR_inputs'] == 26011 and latest['sNaN_policy_shortcuts'] == 110
    assert latest['independent_review_pending'] and not latest['goal_complete']
    assert latest['private_code_bytes'] == [1060, 1072]
    unit = report('components/pow-reciprocal-inline/unit-proof.json')
    assert unit['actual_ARM_calls'] == 143392
    correction = report('corrections/numerator-one-normal-lag.json')
    assert correction['FROZEN_sha256'] == sha(raw('components/pow-reciprocal-one/FROZEN.json'))
    draft = report('work-in-progress/remainder-certificate/CHECKPOINT-STATUS.json')
    assert not draft['ARM_execution_performed'] and not draft['connected_to_binary64_division']
    study = report('work-in-progress/remainder-certificate/study.json')
    assert study['structured_cases'] + study['random_cases'] == 338416
    assert study['actual_ARM_or_MPFR_calls'] == 0 and study['all_certified_signs_identical']
    return dict(status='PASS_INTERMEDIATE_RESEARCH_CHECKPOINT', files=len(index['files']),
                public_accounting=pub, scalar_accounting=scalar, local_originals_checked=check_local,
                fresh_ARM_or_MPFR_campaign=False, canonical_runtime_integrated=False,
                hardware_accessed=False, goal_complete=False)


def build(output, tc):
    output = output.resolve()
    assert ROOT / '.build' in output.parents, 'Use a fresh directory below .build'
    output.mkdir(parents=True, exist_ok=False)
    base = previous.previous.previous
    target = base.materialize(output)
    suffixes = base.SOURCE_SUFFIXES
    directories = [previous.previous.W, previous.W, W]
    aliases = {}
    for directory in directories:
        for entry in report('provenance.json', directory)['archived_files']:
            source = Path(entry['source'])
            assert not source.is_absolute() and '..' not in source.parts and '.git' not in source.parts
            if source.suffix not in suffixes:
                continue
            encoded = (directory / entry['path']).read_bytes()
            data = gzip.decompress(encoded) if entry['encoding'] == 'gzip' else encoded
            dest = target / source
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
        aliases.update(report('rebuild-recipes.json', directory).get('source_aliases', {}))
    for alias, source in aliases.items():
        for path in (target / source).rglob('*'):
            if path.is_file() and path.suffix in suffixes:
                dest = target / alias / path.relative_to(target / source)
                dest.parent.mkdir(parents=True, exist_ok=True)
                if dest.exists():
                    assert dest.read_bytes() == path.read_bytes(), dest
                dest.write_bytes(path.read_bytes())
    saved = report('rebuild-recipes.json')
    remap = lambda s: s.replace(saved['original_root'] + '/', str(target) + '/')
    for path in target.rglob('*'):
        if path.is_file() and path.suffix in suffixes:
            data = path.read_text()
            if remap(data) != data:
                path.write_text(remap(data))
    counts, commands = {}, []
    for name, recipe in saved['recipes'].items():
        for recorded in recipe['commands']:
            command = [str(tc / Path(recorded[0]).name)] + [remap(arg) for arg in recorded[1:] if arg != '-g']
            for i, arg in enumerate(command):
                if arg.startswith('-I'):
                    Path(arg[2:]).mkdir(parents=True, exist_ok=True)
                elif arg == '-isystem':
                    Path(command[i + 1]).mkdir(parents=True, exist_ok=True)
            cwd = Path(remap(recipe['cwd']))
            cwd.mkdir(parents=True, exist_ok=True)
            commands.append(command)
            subprocess.run(command, cwd=cwd, check=True)
        for path, expected in recipe['outputs'].items():
            assert image_fingerprint((target / path).read_bytes()) == expected, (name, path)
        counts[name] = len(recipe['outputs'])
    assert sum(counts.values()) == 102
    (output / 'build-commands.json').write_text(json.dumps(commands, indent=2) + '\n')
    return dict(allocated_bytes_symbols_semantic_relocations_exact=counts,
                debug_path_bytes_compared=False, actual_ARM_calls=0, hardware_accessed=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-local', action='store_true')
    parser.add_argument('--build-output', type=Path)
    parser.add_argument('--toolchain', type=Path)
    args = parser.parse_args()
    result = verify(args.check_local)
    if args.build_output:
        assert args.toolchain
        result['code_rebuild'] = build(args.build_output, args.toolchain)
        (args.build_output / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
