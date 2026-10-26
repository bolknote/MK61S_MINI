#!/usr/bin/env python3
"""Verify the seventh offline math checkpoint without running its producers."""
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
PREVIOUS = W.parent / 'm0-math-checkpoint-20261025-2'
spec = importlib.util.spec_from_file_location('sixth_math_checkpoint', PREVIOUS / 'verify.py')
previous = importlib.util.module_from_spec(spec)
spec.loader.exec_module(previous)
image_fingerprint = previous.image_fingerprint


def sha(data):
    return hashlib.sha256(data).hexdigest()


def raw(name, directory=W):
    path = directory / name
    return path.read_bytes() if path.exists() else gzip.decompress(path.with_suffix(path.suffix + '.gz').read_bytes())


def report(name, directory=W):
    return json.loads(raw(name, directory))


def lines(name):
    with gzip.open(W / name, 'rt') as stream:
        for line in stream:
            yield json.loads(line)


def equal(a, b):
    a, b = int(a, 16), int(b, 16)
    if (b & 0x7fffffffffffffff) > 0x7ff0000000000000:
        return bool((a & 0x7fffffffffffffff) > 0x7ff0000000000000 and a & (1 << 51))
    return a == b


def key(row):
    return row['x'], row['y'], row['SIO']


def recount():
    sp, bp = 'components/pow-square128/', 'components/pow-boundary128/'
    fresh = {name: report(prefix + 'new-qualification.json') for name, prefix in [('square', sp), ('boundary', bp)]}
    controls = {name: {key(row): row for row in data['rows']} for name, data in fresh.items()}
    assert all(len(rows) == 10254 for rows in controls.values())
    observations = {name: {} for name in controls}
    originals = {name: report(prefix + 'original153.json')['rows'] for name, prefix in [('square', sp), ('boundary', bp)]}
    original_keys = {(r['x'], r['y'], state) for r in originals['square'] for state in ['READY', 'DIRTY']}
    old_square = iter(lines(sp + 'qualification-records.jsonl.gz'))
    seen = set()
    data = {name: dict(old=set(), new=set(), comparisons=Counter(), deltas=Counter(), wrong=0, variants=0) for name in controls}
    witnesses = []
    for i, (square, boundary) in enumerate(zip_longest(lines(sp + 'union-records.jsonl.gz'), lines(bp + 'qualification-records.jsonl.gz'))):
        assert square is not None and boundary is not None
        k = key(square)
        assert k == key(boundary) and k not in seen
        seen.add(k)
        assert square['expected'] == boundary['expected']
        assert square['candidate'] == boundary['candidate']
        assert square['references'] == boundary['references']
        assert square['candidate_instructions'] == boundary['parent_boundary_instructions']
        if i < 232936:
            old = next(old_square)
            assert key(old) == k
            assert old['candidate'] == old['parent_output'] == square['candidate']
            assert old['references'] == square['references']
            assert old['parent_cost'] == square['parent_instructions']
            assert old['candidate_instructions'] == square['candidate_instructions']
            delta = sum(c['new_cost'] - c['old_cost'] for c in old['square_calls'])
            assert old['candidate_instructions'] == old['parent_cost'] + delta and delta <= 0
        for name, row, parent_field in [('square', square, 'parent_instructions'), ('boundary', boundary, 'parent_boundary_instructions')]:
            assert equal(row['candidate'], row['expected'])
            cost, parent = row['candidate_instructions'], row[parent_field]
            assert cost <= parent
            values = data[name]
            values['deltas'][cost - parent] += 1
            for ref in row['references'].values():
                values['variants'] += 1
                assert ref['correct_Qfplib'] == equal(ref['output'], row['expected'])
                if not ref['correct_Qfplib']:
                    values['wrong'] += 1
                    continue
                qcost = ref['instructions']
                values['comparisons']['faster' if cost < qcost else 'equal' if cost == qcost else 'slower'] += 1
                if parent > qcost:
                    values['old'].add(k[:2])
                if cost > qcost:
                    values['new'].add(k[:2])
            if k in original_keys:
                observations[name][k] = dict(parent=parent, candidate=cost, references=row['references'])
            if k in controls[name]:
                control = controls[name].pop(k)
                assert control['expected'] == row['expected']
                assert len({control['outputs'][n] for n in ['parent', 'control', 'candidate']}) == 1
                assert all(control['correct'][n] for n in ['parent', 'control', 'candidate'])
                assert control['outputs']['candidate'] == row['candidate']
                assert control['instructions']['parent'] == control['instructions']['control'] == parent
                assert control['instructions']['candidate'] == cost
                for label, ref in row['references'].items():
                    assert (ref['output'], ref['instructions'], ref['correct_Qfplib']) == (
                        control['outputs'][label], control['instructions'][label], control['correct'][label])
                if name == 'boundary':
                    assert row['boundary_calls'] == control['boundary_calls']
                    assert row['midpoint_operands'] == control['midpoint_operands']
        if boundary['parent_boundary_instructions'] - boundary['candidate_instructions'] == 180:
            witnesses.append(dict(x=k[0], y=k[1], SIO=k[2], parent_boundary_instructions=boundary['parent_boundary_instructions'], candidate_instructions=boundary['candidate_instructions']))
    assert next(old_square, None) is None
    assert len(seen) == 241960 and len({k[:2] for k in seen}) == 120980
    assert all(not rows for rows in controls.values())
    expected_comparisons = dict(slower=21167, faster=178544, equal=2705)
    out = {}
    for name, values in data.items():
        assert values['variants'] == 279522 and values['wrong'] == 77106
        assert dict(values['comparisons']) == expected_comparisons
        assert len(values['new']) == 11434 and not values['new'] - values['old']
        assert len(values['old']) == (11449 if name == 'square' else 11434)
        hist = {side: Counter() for side in ['parent', 'candidate']}
        for row in originals[name]:
            for state in row['states']:
                observation = observations[name][row['x'], row['y'], state['SIO']]
                ref = observation['references'][row['reference']]
                assert ref['correct_Qfplib']
                assert (state['parent'], state['candidate'], state['Qfplib']) == (observation['parent'], observation['candidate'], ref['instructions'])
            for side in hist:
                states = row['states']
                category = 'slower' if any(s[side] > s['Qfplib'] for s in states) else 'equal' if any(s[side] == s['Qfplib'] for s in states) else 'strict'
                hist[side][category] += 1
        assert hist['candidate'] == dict(slower=34, strict=119)
        assert hist['parent'] == (dict(slower=35, strict=118) if name == 'square' else dict(slower=34, strict=119))
        assert fresh[name]['actual_directed_MPFR_inputs'] == 5051
        assert fresh[name]['sNaN_policy_shortcuts'] == 76
        out[name] = dict(losses=[len(values['old']), len(values['new'])], new_losses=0,
                         wrong_Qfplib_variants_retained=values['wrong'], original153={k: dict(v) for k, v in hist.items()})
    correction = report('corrections/boundary-public-range.json')
    deltas = data['boundary']['deltas']
    assert sum(n for d, n in deltas.items() if d < 0) == 454
    assert [-max(d for d in deltas if d < 0), -min(deltas)] == correction['correct_range'] == [4, 180]
    assert witnesses == correction['witnesses']
    assert correction['FROZEN_sha256'] == sha(raw(bp + 'FROZEN.json'))
    assert correction['result_sha256'] == sha(raw(bp + 'result.json'))
    assert correction['qualification_sha256'] == sha(raw(bp + 'qualification.json'))
    assert correction['records_sha256'] == sha(raw(bp + 'qualification-records.jsonl.gz'))
    unit = report(sp + 'unit-proof.json')
    assert unit['tests'] == 18210 and unit['actual_ARM_calls'] == 36420
    assert unit['old_and_new_all24_output_bytes_identical']
    assert unit['min_SP_frames'] == dict(control=68, candidate=60)
    assert report(sp + 'qualification.json')['fresh_candidate_ARM_calls'] + fresh['square']['fresh_ARM_calls'] + unit['actual_ARM_calls'] == 330880
    unit = report(bp + 'unit-proof.json')
    assert unit['cases'] == 3000 and unit['actual_ARM_calls'] == 6000
    assert unit['all24_midpoint_operand_bytes_identical'] and unit['all_returned_sides_identical']
    assert unit['observed_frames'] == dict(control=212, candidate=156)
    assert report(bp + 'qualification.json')['total_fresh_public_ARM_calls'] + fresh['boundary']['fresh_ARM_calls'] + unit['actual_ARM_calls'] == 309938
    out['square']['qualified_fresh_ARM_calls'] = 330880
    out['boundary'].update(qualified_fresh_ARM_calls=309938, accelerated_states=454, public_instruction_reduction_range=[4, 180])
    return dict(pairs=120980, states=241960, reference_variants=279522, components=out)


def verify(check_local=False):
    index = report('checkpoint.json')
    assert sha((PREVIOUS / 'checkpoint.json').read_bytes()) == index['base_checkpoint_sha256']
    previous.verify(False)
    for name, digest in index['files'].items():
        assert sha((W / name).read_bytes()) == digest, name
    sources = {}
    for entry in report('provenance.json')['archived_files']:
        encoded = (W / entry['path']).read_bytes()
        data = gzip.decompress(encoded) if entry['encoding'] == 'gzip' else encoded
        assert sha(encoded) == entry['sha256'] and sha(data) == entry['uncompressed_sha256']
        assert len(data) == entry['uncompressed_bytes']
        assert entry['source'] not in sources
        sources[entry['source']] = entry
        if check_local:
            assert (ROOT / entry['source']).read_bytes() == data, entry['source']

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

    counts = {}
    for name, meta in index['components'].items():
        prefix = 'components/' + name + '/'
        frozen = report(prefix + 'FROZEN.json')
        for rel, value in frozen['files'].items():
            pin(meta['original_directory'] + '/' + rel, value)
        lineage = report(prefix + 'source-lineage-pins.json')['files']
        for path, value in lineage.items():
            pin(path, value)
        counts[name] = dict(local_pins=len(frozen['files']), external_pins=len(lineage))
    review = report('reviews/pow-square128/FINAL-REVIEW.json')
    assert review['status'] == 'TECH_GO_PRIVATE_EXACT_SQUARE128_COMPONENT_ONLY'
    assert review['findings'] == review['blocking_component_findings'] == []
    for name, filename in [('FROZEN', 'FROZEN.json'), ('result', 'result.json'), ('HANDOFF', 'HANDOFF.md')]:
        assert review['accepted_frozen_target'][name]['sha256'] == sha(raw('components/pow-square128/' + filename))
    for rel, value in report('reviews/pow-square128/MANIFEST.json')['files'].items():
        pin(index['square_review_original_directory'] + '/' + rel, value)
    receipt = report('receipts/pow-square128/RECEIPT.json')
    assert receipt['status'] == 'ACCEPTED_PRIVATE_EXACT_SQUARE128_COMPONENT_ONLY'
    assert receipt['independent_review_sha256'] == sha(raw('reviews/pow-square128/FINAL-REVIEW.json'))
    assert receipt['authoritative_FROZEN'] == sha(raw('components/pow-square128/FROZEN.json'))
    assert not receipt['integration_GO'] and not receipt['hardware_main_or_release_GO']
    for value in receipt['pins']:
        pin(value['path'], value)
    seed = report('work-in-progress/ddiv-seed17/seed-proof.json')
    assert seed['actual_ARM_calls'] == 66288 and seed['exhaustive_divisors'] == 65536
    assert seed['extra_all16_NZCV_edge_calls'] == 752 and seed['code_bytes'] == 194
    assert sum(seed['cost_histogram'].values()) == seed['actual_ARM_calls']
    assert (min(map(int, seed['cost_histogram'])), max(map(int, seed['cost_histogram']))) == (82, 97)
    assert seed['R12_preserved_every_call'] and seed['no_stack_or_memory_writes']
    assert not report('work-in-progress/ddiv-seed17/CHECKPOINT-STATUS.json')['connected_to_binary64_division']
    return dict(status='PASS_INTERMEDIATE_RESEARCH_CHECKPOINT', files=len(index['files']),
                source_pins=counts, public_accounting=recount(), seed_bare_ARM_calls=66288,
                fresh_ARM_or_MPFR_campaign=False, canonical_runtime_integrated=False,
                hardware_accessed=False, goal_complete=False)


def build(output, tc):
    output = output.resolve()
    assert ROOT / '.build' in output.parents, 'Use a fresh directory below .build'
    output.mkdir(parents=True, exist_ok=False)
    target = previous.previous.materialize(output)
    suffixes = previous.previous.SOURCE_SUFFIXES
    for directory in [PREVIOUS, W]:
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
    saved = report('rebuild-recipes.json')
    for alias, source in saved['source_aliases'].items():
        for path in (target / source).rglob('*'):
            if path.is_file() and path.suffix in suffixes:
                dest = target / alias / path.relative_to(target / source)
                dest.parent.mkdir(parents=True, exist_ok=True)
                if dest.exists():
                    assert dest.read_bytes() == path.read_bytes(), dest
                dest.write_bytes(path.read_bytes())
    remap = lambda s: s.replace(saved['original_root'] + '/', str(target) + '/')
    for path in target.rglob('*'):
        if path.is_file() and path.suffix in suffixes:
            text = path.read_text()
            if remap(text) != text:
                path.write_text(remap(text))
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
    assert counts == dict(square128=13, boundary128=17, seed17=2)
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
