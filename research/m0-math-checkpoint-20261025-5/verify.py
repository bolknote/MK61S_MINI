#!/usr/bin/env python3
"""Verify the ninth offline math checkpoint without running its producers."""
from pathlib import Path
from collections import Counter
from itertools import zip_longest
import argparse
import gzip
import hashlib
import importlib.util
import io
import json
import subprocess
import sys

sys.dont_write_bytecode = True
W = Path(__file__).resolve().parent
ROOT = W.parents[1]
PREVIOUS = W.parent / 'm0-math-checkpoint-20261025-4'
spec = importlib.util.spec_from_file_location('eighth_math_checkpoint', PREVIOUS / 'verify.py')
previous = importlib.util.module_from_spec(spec)
spec.loader.exec_module(previous)
image_fingerprint = previous.image_fingerprint
STAGES = ['certificate', 'zero', 'bound3']
SOURCE_SUFFIXES = {'.py', '.cpp', '.hpp', '.h', '.c', '.inc', '.S', '.ld', '.txt', '.TXT'}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def raw(name, directory=W):
    p = directory / name
    return p.read_bytes() if p.exists() else gzip.decompress(p.with_suffix(p.suffix + '.gz').read_bytes())


def report(name, directory=W):
    return json.loads(raw(name, directory))


def lines(name, directory=W):
    with gzip.GzipFile(fileobj=io.BytesIO(raw(name, directory))) as stream:
        for line in stream:
            yield json.loads(line)


def equal(a, b):
    return previous.equal(a, b)


def public_recount(stage):
    prefix = 'components/pow-reciprocal-' + stage + '/'
    parent = (lines('components/pow-reciprocal-inline/qualification-records.jsonl.gz', PREVIOUS)
              if stage == 'certificate' else
              lines('components/pow-reciprocal-' + STAGES[STAGES.index(stage) - 1] + '/qualification-records.jsonl.gz'))
    q = report(prefix + 'qualification.json')
    costs, deltas = Counter(), Counter()
    old_losses, losses, seen = set(), set(), set()
    variants = wrong = increases = 0
    for row, prior in zip_longest(lines(prefix + 'qualification-records.jsonl.gz'), parent):
        assert row is not None and prior is not None
        key = row['x'], row['y'], row['SIO']
        assert key == (prior['x'], prior['y'], prior['SIO']) and key not in seen
        seen.add(key)
        assert row['candidate'] == prior['candidate'] and row['expected'] == prior['expected']
        assert row['references'] == prior['references'] and equal(row['candidate'], row['expected'])
        c, p = row['candidate_instructions'], row['parent_reciprocal_instructions']
        assert p == prior['candidate_instructions']
        deltas[c - p] += 1
        increases += c > p
        for ref in row['references'].values():
            variants += 1
            assert ref['correct_Qfplib'] == equal(ref['output'], row['expected'])
            if not ref['correct_Qfplib']:
                wrong += 1
                continue
            r = ref['instructions']
            costs['faster' if c < r else 'equal' if c == r else 'slower'] += 1
            if p > r:
                old_losses.add(key[:2])
            if c > r:
                losses.add(key[:2])
    assert len(seen) == 241960 and len({k[:2] for k in seen}) == 120980
    assert variants == 279522 and wrong == 77106 and not losses - old_losses
    assert len(old_losses) == q['parent_raw_loss_pairs'] and len(losses) == q['candidate_raw_loss_pairs'] == 11369
    assert dict(costs) == q['correct_Qfplib_comparison']
    assert dict(deltas) == {int(k): v for k, v in q['instruction_delta_histogram'].items()}
    assert increases == q['parent_cost_increase_states'] == (32 if stage == 'certificate' else 0)
    return dict(loss_pairs=[len(old_losses), len(losses)], comparison=dict(costs),
                parent_increase_states=increases, instruction_deltas=dict(deltas), wrong_Qfplib_retained=wrong)


def scalar_recount(stage, expanded=False):
    prefix = 'components/pow-reciprocal-' + stage + '/'
    proof = report(prefix + ('expanded-seed-proof.json' if expanded else 'direct-proof.json'))
    counts = {name: Counter() for name in ['parent', 'candidate']}
    seen, divisors = set(), set()
    deltas = Counter()
    wrong = new_losses = rows = 0
    for row in lines(prefix + ('expanded-seed-records.jsonl.gz' if expanded else 'direct-records.jsonl.gz')):
        rows += 1
        if expanded:
            key = row['D'], row['pattern'], row['SIO']
            assert key not in seen
            seen.add(key)
            divisors.add(row['D'])
        r = row['results']
        if 'control' in r:
            assert r['control'] == r['parent']
        assert r['candidate']['correct'] and equal(r['candidate']['output'], row['expected'])
        assert r['candidate']['output'] == r['parent']['output']
        q = r['Qfplib']
        assert q['correct'] == equal(q['output'], row['expected'])
        c, p = r['candidate']['instructions'], r['parent']['instructions']
        deltas[c - p] += 1
        if not q['correct']:
            wrong += 1
            continue
        for name in counts:
            n = r[name]['instructions']
            counts[name]['faster' if n < q['instructions'] else 'equal' if n == q['instructions'] else 'slower'] += 1
        new_losses += c > q['instructions'] >= p
    # The direct campaign intentionally repeats inputs between case groups.
    # Preserve and recount all executions; do not silently deduplicate them.
    assert rows == proof['states'] == (262144 if expanded else 41988)
    assert {k: dict(v) for k, v in counts.items()} == proof['correct_Qfplib_comparisons']
    assert not new_losses and wrong == (0 if expanded else 9600)
    if expanded:
        assert divisors == set(range(65536, 131072))
        assert counts['candidate']['slower'] == (2 if stage == 'zero' else 0)
    else:
        assert counts['candidate']['slower'] == (1 if stage == 'certificate' else 0)
    if stage != 'certificate':
        assert not any(k > 0 for k in deltas)
    return dict(states=rows, comparison={k: dict(v) for k, v in counts.items()},
                instruction_deltas=dict(deltas), wrong_Qfplib_retained=wrong)


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
        assert len(data) == entry['uncompressed_bytes'] and entry['source'] not in sources
        sources[entry['source']] = entry
        if check_local:
            assert (ROOT / entry['source']).read_bytes() == data, entry['source']

    def pin(origin, value):
        p = Path(origin)
        if p.is_absolute():
            p = p.relative_to(index['original_root'])
        origin = str(p)
        if origin in sources:
            e = sources[origin]
            assert (e['uncompressed_sha256'], e['uncompressed_bytes']) == (value['sha256'], value['bytes']), origin
        if check_local:
            data = (ROOT / origin).read_bytes()
            assert (sha(data), len(data)) == (value['sha256'], value['bytes']), origin

    for name, meta in index['components'].items():
        prefix = 'components/' + name + '/'
        assert sha(raw(prefix + 'FROZEN.json')) == meta['FROZEN_sha256']
        for rel, value in report(prefix + 'FROZEN.json')['files'].items():
            pin(meta['original_directory'] + '/' + rel, value)
        if name.startswith('pow-'):
            for origin, value in report(prefix + 'source-lineage-pins.json')['files'].items():
                pin(origin, value)
    for name, meta in index['reviews'].items():
        prefix = 'reviews/' + name + '/'
        review = report(prefix + 'FINAL-REVIEW.json')
        assert sha(raw(prefix + 'FINAL-REVIEW.json')) == meta['sha256']
        assert review['status'] == meta['status'] and review['component_review_complete']
        for rel, value in report(prefix + 'MANIFEST.json')['files'].items():
            pin(meta['original_directory'] + '/' + rel, value)
        if meta['root_receipt_saved']:
            receipt = report('receipts/' + name + '/RECEIPT.json')
            assert receipt['independent_review_sha256'] == meta['sha256'] and not receipt['integration_GO']
            for value in receipt['pins']:
                pin(value['path'], value)
    public = {s: public_recount(s) for s in STAGES}
    scalar = {s: scalar_recount(s) for s in STAGES}
    expanded = {s: scalar_recount(s, True) for s in ['zero', 'bound3']}
    correction = report('corrections/certificate-performance-tradeoff.json')
    assert correction
    link = report('unified/link-result.json')
    guard = report('unified/private-return-proof.json')
    controls = report('unified/private-guard-controls.json')
    loader = report('unified/loader-layout-proof.json')
    candidate = link['images']['candidate']['ELF_sha256']
    assert guard['status'].startswith('PASS') and controls['status'].startswith('PASS')
    assert guard['candidate_ELF_sha256'] == controls['candidate_ELF_sha256'] == candidate
    assert guard['actual_wrapper_and_leaf_from_this_ELF_not_old_firmware']
    assert len(controls['postcall_negative_controls']) + len(controls['marker_to_consumer_negative_controls']) == 17
    assert loader['status'] == 'PASS_ACTUAL_SOURCE_LOADER_AND_LINKED_MATH_LAYOUT'
    assert loader['actual_loader_ARM_calls'] == 2 and loader['actual_MPFR_calls'] == 0
    for name, image in link['images'].items():
        p = loader['images'][name]
        assert image['all_undefined_symbols_resolved'] and not image['old_firmware_address_bindings']
        assert p['ELF_sha256'] == image['ELF_sha256'] and p['scratch_y_bytes'] == 4080
        assert p['loader']['reserved_tail_untouched'] and p['real_BootROM_without_models']
        assert p['old_overlay_intersects_new_entry_bytes'] == 14 and p['host_negative_old_overlay_detected']
    assert link['no_libgcc_or_Qfplib_object_linked'] and link['zero_control_is_previous_exact_seed_loop']
    status = report('CHECKPOINT-STATUS.json')
    assert not status['unified_math_numeric_qualification_performed'] and not status['goal_complete']
    assert status['automatic_ROM_lookup_initializations_excluded'] == 2
    return dict(status='PASS_INTERMEDIATE_RESEARCH_CHECKPOINT', files=len(index['files']) + 1,
                public_accounting=public, scalar_accounting=scalar, expanded_scalar_accounting=expanded,
                unified_static_R12_and_loader_proof_bindings=True, unified_numerical_qualification_pending=True,
                local_originals_checked=check_local, fresh_ARM_or_MPFR_campaign=False,
                canonical_runtime_integrated=False, hardware_accessed=False, goal_complete=False)


def build(output, tc):
    output = output.resolve()
    assert ROOT / '.build' in output.parents, 'Use a fresh directory below .build'
    output.mkdir(parents=True, exist_ok=False)
    target = output / 'materialized'
    directories, directory = [], W
    while True:
        directories.append(directory)
        index = report('checkpoint.json', directory)
        if not index.get('base_checkpoint'):
            break
        directory = (ROOT / index['base_checkpoint']).parent
    aliases = {}
    for directory in reversed(directories):
        for entry in report('provenance.json', directory)['archived_files']:
            p = Path(entry['source'])
            assert not p.is_absolute() and '..' not in p.parts and '.git' not in p.parts
            if p.suffix not in SOURCE_SUFFIXES:
                continue
            data = (directory / entry['path']).read_bytes()
            if entry['encoding'] == 'gzip':
                data = gzip.decompress(data)
            dest = target / p
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
        if (directory / 'rebuild-recipes.json').exists():
            aliases.update(report('rebuild-recipes.json', directory).get('source_aliases', {}))
    for alias, source in aliases.items():
        for p in (target / source).rglob('*'):
            if p.is_file() and p.suffix in SOURCE_SUFFIXES:
                dest = target / alias / p.relative_to(target / source)
                dest.parent.mkdir(parents=True, exist_ok=True)
                if dest.exists():
                    assert dest.read_bytes() == p.read_bytes(), dest
                dest.write_bytes(p.read_bytes())
    saved = report('rebuild-recipes.json')
    remap = lambda s: s.replace(saved['original_root'] + '/', str(target) + '/')
    for p in target.rglob('*'):
        if p.is_file() and p.suffix in SOURCE_SUFFIXES:
            data = p.read_text()
            if remap(data) != data:
                p.write_text(remap(data))
    counts, commands = {}, []
    for name, recipe in saved['recipes'].items():
        cwd = Path(remap(recipe['cwd']))
        cwd.mkdir(parents=True, exist_ok=True)
        for recorded in recipe['commands']:
            c = [str(tc / Path(recorded[0]).name)] + [remap(arg) for arg in recorded[1:]
                 if arg != '-g' or recipe.get('preserve_debug_for_linker_veneer_order', False)]
            for i, arg in enumerate(c):
                if arg.startswith('-I'):
                    Path(arg[2:]).mkdir(parents=True, exist_ok=True)
                elif arg == '-isystem':
                    Path(c[i + 1]).mkdir(parents=True, exist_ok=True)
                elif arg in ['-o', '-MF']:
                    p = Path(c[i + 1])
                    (p if p.is_absolute() else cwd / p).parent.mkdir(parents=True, exist_ok=True)
            commands.append(c)
            subprocess.run(c, cwd=cwd, check=True)
        for path, expected in recipe['outputs'].items():
            assert image_fingerprint((target / path).read_bytes()) == expected, (name, path)
        counts[name] = len(recipe['outputs'])
    (output / 'build-commands.json').write_text(json.dumps(commands, indent=2) + '\n')
    return dict(allocated_bytes_symbols_semantic_relocations_exact=counts,
                debug_path_bytes_compared=False, unified_debug_metadata_retained_for_exact_linker_veneers=True,
                actual_ARM_calls=0, hardware_accessed=False)


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
