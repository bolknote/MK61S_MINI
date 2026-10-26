#!/usr/bin/env python3
"""Verify the sixth offline checkpoint without executing historical producers."""
from pathlib import Path
from collections import Counter
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
PREVIOUS = W.parent / 'm0-math-checkpoint-20261025'
spec = importlib.util.spec_from_file_location('previous_math_checkpoint', PREVIOUS / 'verify.py')
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


def table_recount():
    prefix = 'components/pow-exp-table-product/'
    states = {}

    def add(row, references, output, cost, parent):
        key = row['x'], row['y'], row['SIO']
        values = dict(output=output, cost=cost, parent=parent)
        saved = states.setdefault(key, values | dict(references={}))
        assert all(saved[k] == v for k, v in values.items()), key
        for name, reference in references.items():
            if name in saved['references']:
                assert saved['references'][name] == reference, (key, name)
            saved['references'][name] = reference

    for row in lines(prefix + 'old-records.jsonl.gz'):
        refs = {name: {k: r[k] for k in ('output', 'instructions', 'correct_Qfplib')}
                for name, r in row['references'].items()}
        add(row, refs, row['candidate'], row['candidate_instructions'], row['parent_C77_instructions'])
    q = report(prefix + 'new-qualification.json')
    assert q['candidate_wrong'] == 0
    for row in q['rows']:
        assert all(row['correct'][name] for name in ('parent', 'control', 'candidate'))
        assert len({row['outputs'][name] for name in ('parent', 'control', 'candidate')}) == 1
        assert row['instructions']['parent'] == row['instructions']['control']
        refs = {name: dict(output=row['outputs'][name], instructions=row['instructions'][name],
                           correct_Qfplib=row['correct'][name])
                for name in ('qfp_composed_pow', 'qfp_composed_pow_exact', 'qfp_composed_pow_integer')}
        add(row, refs, row['outputs']['candidate'], row['instructions']['candidate'], row['instructions']['parent'])
    old_loss, new_loss, comparisons, increases = set(), set(), Counter(), Counter()
    wrong = variants = 0
    for key, row in states.items():
        if row['cost'] > row['parent']:
            increases[row['cost'] - row['parent']] += 1
        for reference in row['references'].values():
            variants += 1
            if not reference['correct_Qfplib']:
                wrong += 1
                continue
            qcost = reference['instructions']
            comparisons['faster' if row['cost'] < qcost else 'equal' if row['cost'] == qcost else 'slower'] += 1
            if row['parent'] > qcost:
                old_loss.add(key[:2])
            if row['cost'] > qcost:
                new_loss.add(key[:2])
    assert len(states) == 232936 and variants == 252450 and wrong == 60686
    assert len({key[:2] for key in states}) == 116468
    assert len(old_loss) == 10866 and len(new_loss) == 10853 and not new_loss - old_loss
    assert dict(comparisons) == dict(faster=170087, equal=2693, slower=18984)
    assert dict(increases) == {2: 8024}
    original = report(prefix + 'original153.json')['rows']
    counts = {name: Counter() for name in ('parent', 'candidate')}
    for row in original:
        assert len(row['states']) == 2
        for value in row['states']:
            saved = states[row['x'], row['y'], value['SIO']]
            reference = saved['references'][row['reference']]
            assert reference['correct_Qfplib']
            assert (value['parent'], value['candidate'], value['Qfplib']) == (
                saved['parent'], saved['cost'], reference['instructions'])
        for name in counts:
            values = row['states']
            classification = 'slower' if any(v[name] > v['Qfplib'] for v in values) else (
                'equal' if any(v[name] == v['Qfplib'] for v in values) else 'strict')
            counts[name][classification] += 1
    assert dict(counts['parent']) == dict(slower=48, strict=105)
    assert dict(counts['candidate']) == dict(slower=35, strict=118)
    return states, dict(pairs=116468, states=232936, reference_variants=variants,
                        losses=[len(old_loss), len(new_loss)], new_losses=0,
                        original153={name: dict(value) for name, value in counts.items()},
                        wrong_Qfplib_variants_retained=wrong, parent_cost_increases=dict(increases))


def square_recount(table_states):
    prefix = 'work-in-progress/pow-square128/'
    status = report(prefix + 'CHECKPOINT-STATUS.json')
    assert status['full_qualification_executed'] is False
    assert status['independent_review_complete'] is False
    assert not (W / prefix / 'qualification.json').exists()
    unit = report(prefix + 'unit-proof.json')
    assert unit['tests'] == 18210 and unit['actual_ARM_calls'] == 36420
    assert sum(unit['class_counts'].values()) == unit['tests']
    assert unit['old_and_new_all24_output_bytes_identical']
    assert unit['class_costs'] == {
        '(False, False)': dict(control=129, candidate=94),
        '(True, False)': dict(control=195, candidate=154),
        '(True, True)': dict(control=182, candidate=149),
        '(False, True)': dict(control=116, candidate=89)}
    assert unit['min_SP_frames'] == dict(control=68, candidate=60)
    pilot = report(prefix + 'probe.json')
    assert len(pilot['rows']) == 306 and pilot['fresh_ARM_calls'] == 918
    assert pilot['oracle_evaluations'] == 153 and pilot['candidate_wrong'] == 0
    old_loss, new_loss, deltas, keys = set(), set(), Counter(), set()
    for row in pilot['rows']:
        key = row['x'], row['y'], row['SIO']
        assert key not in keys
        keys.add(key)
        assert row['correct']['parent'] and row['correct']['candidate']
        assert row['outputs']['parent'] == row['outputs']['candidate'] == row['expected']
        assert row['instructions']['parent'] == table_states[key]['cost']
        delta = sum(c['new_cost'] - c['old_cost'] for c in row['square_calls'])
        assert delta <= 0
        assert row['instructions']['candidate'] - row['instructions']['parent'] == delta
        deltas[str(delta)] += 1
        if row['correct']['Qfplib']:
            for name, target in [('parent', old_loss), ('candidate', new_loss)]:
                if row['instructions'][name] > row['instructions']['Qfplib']:
                    target.add(key[:2])
    assert len(old_loss) == 35 and len(new_loss) == 34 and not new_loss - old_loss
    assert dict(deltas) == pilot['cost_delta_histogram']
    assert sorted(old_loss - new_loss) == [tuple(v) for v in pilot['fixed_pairs']]
    binding = report(prefix + 'corpus-binding.json')
    assert sha((W / prefix / 'parent-corpus.jsonl.gz').read_bytes()) == binding['corpus_sha256']
    prepared = set()
    for row in lines(prefix + 'parent-corpus.jsonl.gz'):
        key = row['x'], row['y'], row['SIO']
        assert key not in prepared
        prepared.add(key)
        table = table_states[key]
        assert row['parent_cost'] == table['cost'] and row['parent_output'] == table['output']
        assert row['references'] == table['references']
    assert prepared == set(table_states)
    return dict(unit_tests=unit['tests'], unit_ARM_calls=unit['actual_ARM_calls'],
                pilot_ARM_calls=pilot['fresh_ARM_calls'], pilot_oracle_evaluations=153,
                pilot_original_losses=[35, 34], prepared_states=len(prepared),
                full_qualification_executed=False)


def verify(check_local=False):
    index = report('checkpoint.json')
    assert sha((PREVIOUS / 'checkpoint.json').read_bytes()) == index['base_checkpoint_sha256']
    previous.verify(False)
    for name, digest in index['files'].items():
        assert sha((W / name).read_bytes()) == digest, name
    by_source = {}
    for entry in report('provenance.json')['archived_files']:
        saved = (W / entry['path']).read_bytes()
        assert sha(saved) == entry['sha256'], entry['path']
        data = gzip.decompress(saved) if entry['encoding'] == 'gzip' else saved
        assert sha(data) == entry['uncompressed_sha256'] and len(data) == entry['uncompressed_bytes']
        assert entry['source'] not in by_source
        by_source[entry['source']] = entry
        if check_local:
            assert (ROOT / entry['source']).read_bytes() == data, entry['source']
    table = 'components/pow-exp-table-product/'
    frozen = report(table + 'FROZEN.json')
    checked = 0
    for rel, pin in frozen['files'].items():
        source = index['table_original_directory'] + '/' + rel
        if source in by_source:
            saved = by_source[source]
            assert saved['uncompressed_sha256'] == pin['sha256'] and saved['uncompressed_bytes'] == pin['bytes']
        if check_local:
            data = (ROOT / source).read_bytes()
            assert sha(data) == pin['sha256'] and len(data) == pin['bytes'], source
            checked += 1
    review_prefix = 'reviews/pow-exp-table-product/'
    review = report(review_prefix + 'FINAL-REVIEW.json')
    assert review['status'] == 'TECH_GO_PRIVATE_TABLE_ONLY_POW_PRODUCT_COMPONENT'
    assert review['findings'] == review['blocking_component_findings'] == []
    assert review['accepted_frozen_target']['FROZEN']['sha256'] == sha(raw(table + 'FROZEN.json'))
    assert review['accepted_frozen_target']['result']['sha256'] == sha(raw(table + 'result.json'))
    manifest = report(review_prefix + 'MANIFEST.json')
    for name, pin in manifest['files'].items():
        source = index['review_original_directory'] + '/' + name
        if source in by_source:
            assert by_source[source]['uncompressed_sha256'] == pin['sha256']
            assert by_source[source]['uncompressed_bytes'] == pin['bytes']
        if check_local:
            data = (ROOT / source).read_bytes()
            assert sha(data) == pin['sha256'] and len(data) == pin['bytes']
    lineage = report(table + 'lineage/qualified-R-focused-binding.json')
    data = gzip.decompress((W / table / 'lineage/qualified-R-focused.json.gz').read_bytes())
    assert sha(data) == lineage['uncompressed_sha256'] and len(data) == lineage['bytes']
    states, table_summary = table_recount()
    square_summary = square_recount(states)
    return dict(status='PASS_INTERMEDIATE_RESEARCH_CHECKPOINT', archive_files=len(index['files']),
                original_artifacts=len(by_source), local_originals_checked=check_local,
                local_frozen_files_checked=checked, independent_table_review_saved=True,
                qualified_R_focused_lineage_preserved=True, table_recount=table_summary,
                square_work_in_progress=square_summary, fresh_ARM_or_MPFR_campaign=False,
                canonical_runtime_integrated=False, hardware_accessed=False, goal_complete=False)


def build(output, tc):
    output = output.resolve()
    assert ROOT / '.build' in output.parents, 'Use a fresh directory below .build'
    output.mkdir(parents=True, exist_ok=False)
    target = previous.materialize(output)
    for entry in report('provenance.json')['archived_files']:
        source = Path(entry['source'])
        assert not source.is_absolute() and '..' not in source.parts and '.git' not in source.parts
        if source.suffix not in previous.SOURCE_SUFFIXES:
            continue
        data = (W / entry['path']).read_bytes()
        if entry['encoding'] == 'gzip':
            data = gzip.decompress(data)
        dest = target / source
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
    saved = report('rebuild-recipes.json')
    original = saved['original_root']
    remap = lambda s: s.replace(original + '/', str(target) + '/')
    # Historical linker scripts name input objects inside section selectors.
    # Remap their contents as well as command arguments, so a replay cannot
    # silently load binaries or includes from the original private directory.
    for path in target.rglob('*'):
        if path.is_file() and path.suffix in previous.SOURCE_SUFFIXES:
            data = path.read_text()
            relocated = remap(data)
            if relocated != data:
                path.write_text(relocated)
    commands, counts = [], {}
    for name, recipe in saved['recipes'].items():
        for recorded in recipe['commands']:
            command = [str(tc / Path(recorded[0]).name)] + [remap(s) for s in recorded[1:] if s != '-g']
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
    assert sum(counts.values()) == 31
    (output / 'build-commands.json').write_text(json.dumps(commands, indent=2) + '\n')
    return dict(allocated_bytes_symbols_semantic_relocations_exact=counts,
                relocated_table_ELFs_excluded_due_to_path_dependent_veneer_order=True,
                debug_path_bytes_compared=False, actual_ARM_calls=0, hardware_accessed=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-local', action='store_true')
    parser.add_argument('--build-output', type=Path)
    parser.add_argument('--toolchain', type=Path)
    args = parser.parse_args()
    result = verify(args.check_local)
    if args.build_output:
        assert args.toolchain, 'Specify --toolchain /path/to/arm-none-eabi/bin'
        result['code_rebuild'] = build(args.build_output, args.toolchain)
        (args.build_output / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
