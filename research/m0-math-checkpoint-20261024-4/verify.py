#!/usr/bin/env python3
"""Verify the fourth offline M0+ math checkpoint; optionally rebuild it."""
from pathlib import Path
from collections import Counter
import argparse
import gzip
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
W = Path(__file__).resolve().parent
ROOT = W.parents[1]
FIRST = W.parent / 'm0-math-checkpoint-20261024'
SECOND = W.parent / 'm0-math-checkpoint-20261024-2'
THIRD = W.parent / 'm0-math-checkpoint-20261024-3'
COMPONENTS = {'atan-small-h': (58188, 116376),
              'log-ratio-dirty': (14907, 29814),
              'ln-enclosure': (19659, 39318)}
PROTOTYPE = 'work-in-progress/ln-near-rounding'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def raw(name, directory=W):
    p = directory / name
    return p.read_bytes() if p.exists() else gzip.decompress(p.with_suffix(p.suffix + '.gz').read_bytes())


def report(name, directory=W):
    return json.loads(raw(name, directory))


def direction(row, reference):
    a, b = row['instructions']['candidate'], row['instructions'][reference]
    return 'faster' if a < b else 'equal' if a == b else 'slower'


def verify(check_local):
    index = report('checkpoint.json')
    spec = importlib.util.spec_from_file_location('math_checkpoint_third', THIRD / 'verify.py')
    previous = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(previous)
    preceding = previous.verify(False)
    assert sha((THIRD / 'checkpoint.json').read_bytes()) == index['base_checkpoint_sha256']
    for name, digest in index['files'].items():
        assert sha((W / name).read_bytes()) == digest, name
    provenance = report('provenance.json')
    for entry in provenance['archived_files']:
        data = (W / entry['path']).read_bytes()
        assert sha(data) == entry['sha256']
        data = gzip.decompress(data) if entry['encoding'] == 'gzip' else data
        assert len(data) == entry['uncompressed_bytes']
        assert sha(data) == entry['uncompressed_sha256'], entry['path']
        if check_local:
            assert (ROOT / entry['source']).read_bytes() == data, entry['source']
    for name, pin in index['review_pins'].items():
        path = 'reviews/' + name + '/FINAL-REVIEW.json'
        assert sha(raw(path)) == pin['sha256']
        r = report(path)
        assert r['status'] == pin['status'] and r[pin['findings_key']] == []
    summaries, qualifications = {}, {}
    source_files = {'atan-small-h': 'native_eabi_m0_atan_fast.inc',
                    'log-ratio-dirty': 'native_eabi_m0_log70_center.inc',
                    'ln-enclosure': 'native_eabi_m0_log70.inc'}
    for name, (unique, cases) in COMPONENTS.items():
        prefix = 'deltas/' + name + '/'
        q, r = report(prefix + 'qualification.json'), report(prefix + 'result.json')
        b, iso = report(prefix + 'candidate-build.json'), report(prefix + 'isolation.json')
        qualifications[name] = q
        assert q['cases'] == len(q['rows']) == cases
        assert q['unique_inputs'] == len({row['x'] for row in q['rows']}) == unique
        assert len({(row['x'], row['SIO']) for row in q['rows']}) == cases
        assert all(row['correct']['candidate'] and row['correct']['parent'] and
                   row['outputs']['candidate'] == row['outputs']['parent'] for row in q['rows'])
        assert q.get('all_cases_profiled', q.get('all_public_inputs_profiled')) is True
        assert all(row.get('profiled', True) for row in q['rows'])
        source = sha(raw(prefix + source_files[name]))
        assert source == b['source_include_sha256'] == r['source_sha256'] == q['source_sha256']
        assert b['ELF_sha256'] == r['candidate_ELF_sha256'] == q['candidate_ELF_sha256']
        assert b.get('full_object_sha256', r['files']['candidate-full.o']) == r['candidate_full_object_sha256']
        assert all(c['allocated_code_and_data_identical'] for c in iso['contexts'])
        body = report(prefix + 'public-body-proof.json')
        assert body.get('whole_independent_ELF_byte_identical',
                        body.get('entire_ELF_byte_exact_without_exclusions')) is True
        losses = [row for row in q['rows'] if row['correct']['Qfplib'] and direction(row, 'Qfplib') == 'slower']
        assert losses == q['remaining_slower_correct_Qfplib'] == report(prefix + 'remaining-slower.json')['rows']
        assert dict(Counter(direction(row, 'parent') for row in q['rows'])) == {
            k: v for k, v in r['vs_parent'].items() if v}
        if name == 'atan-small-h':
            assert q['ARM_calls'] == 465504 and r['total_actual_ARM_calls'] == 540802
            assert not losses and q['candidate_observed_stack_bytes'] == 912
            correct = [row for row in q['rows'] if row['correct']['Qfplib']]
            assert len(correct) == 107542
            assert dict(Counter(direction(row, 'Qfplib') for row in correct)) == {'faster': 107539, 'equal': 3}
            assert sum(not row['correct']['Qfplib'] for row in q['rows']) == 8834
            assert iso['total_allocated_bytes_delta'] == 60
            assert not iso['new_tables_or_global_RAM_or_libgcc_dependency']
            regress = report(prefix + 'regressions.json')
            for label, key, count in [('parent', 'parent_rows', 132),
                                      ('resident', 'V164_rows', 4)]:
                rows = [row for row in q['rows'] if direction(row, label) == 'slower']
                assert rows == regress[key] and len(rows) == count
            parent = report('deltas/atan-directional-ninth/qualification.json', THIRD)
            retained = {(row['x'], row['SIO']): row for row in parent['rows']}
            assert sum((row['x'], row['SIO']) in retained for row in q['rows']) == 106312
            for row in q['rows']:
                old = retained.get((row['x'], row['SIO']))
                if old:
                    assert row['instructions']['parent'] == old['instructions']['candidate']
            assert not iso.get('new_tables_or_global_RAM_or_libgcc_dependency')
        elif name == 'log-ratio-dirty':
            assert q['actual_ARM_calls'] == 119256 and r['total_actual_ARM_calls'] == 274864
            assert len(losses) == 54 and len({row['x'] for row in losses}) == 27
            assert all(direction(row, 'parent') == 'equal' for row in q['rows'] if row['SIO'] == 'READY')
            assert iso['linked_component_allocated_bytes_delta'] == 160
            assert not iso['new_tables_or_global_RAM_or_libgcc']
            h = report(prefix + 'helper-proof.json')
            assert h['actual_ARM_calls'] == 155608 and h['pairs'] == 38902 and h['SIO_accesses'] == 0
            assert h['all_results_exact_integer_floor'] and not h['firmware_or_ROM_mapped']
        else:
            assert q['actual_ARM_calls'] == 157272 and q['retained_parent_counts_checked'] == 29814
            assert len(losses) == 65 and len({row['x'] for row in losses}) == 34
            assert r['historical_ln10_fixed'] == 5 and r['historical_ln10_remaining'] == 5
            assert r['expanded_correct_Qfplib_raw_deficits_fixed'] == 105
            assert iso['allocated_object_bytes_delta'] == 0 and iso['no_new_tables_global_RAM_or_libgcc']
            assert q['candidate_stack_bytes'] == q['parent_stack_bytes'] == 568
            assert all(row['instructions']['candidate'] - row['instructions']['parent'] == 1
                       for row in q['rows'] if direction(row, 'parent') == 'slower')
        summaries[name] = dict(unique_inputs=unique, public_state_cases=cases, candidate_wrong=0,
                               remaining_correct_Qfplib_raw_inputs=len({row['x'] for row in losses}))
    old = {(row['x'], row['SIO']): row for row in qualifications['log-ratio-dirty']['rows']}
    for row in qualifications['ln-enclosure']['rows']:
        retained = old.get((row['x'], row['SIO']))
        if retained:
            assert row['instructions']['parent'] == retained['instructions']['candidate']
    assert not (W / PROTOTYPE / 'qualification.json').exists()
    p = report(PROTOTYPE + '/candidate-build.json')
    assert sha(raw(PROTOTYPE + '/native_eabi_m0_log70.inc')) == p['source_include_sha256']
    model = report('study/ln-near-directional/model.json')
    assert model['near_loss_inputs'] == 28 and model['residual_accepts'] == 15 and model['plain_accepts'] == 13
    assert sum(not row['model_correct'] for row in model['records']) == 2
    return dict(archive_files=len(index['files']), original_artifacts=len(provenance['archived_files']),
                preceding_archives_verified=3, preceding_third_files=preceding['archive_files'],
                independent_receipts=4, local_originals_checked=check_local, components=summaries,
                near_rounding_prototype='BUILT_ONLY_UNQUALIFIED',
                canonical_runtime_integrated=False, hardware_accessed=False, goal_complete=False)


def build(output, tc):
    output = output.resolve()
    for protected in (W, FIRST, SECOND, THIRD):
        assert protected != output and protected not in output.parents
    output.mkdir(parents=True, exist_ok=False)
    includes = FIRST / 'baseline-v164/source/code'
    flags = ['-mcpu=cortex-m0plus', '-mthumb', '-mfloat-abi=soft', '-Os', '-std=gnu++17',
             '-fno-exceptions', '-fno-rtti', '-fno-unwind-tables', '-fno-use-cxa-atexit',
             '-ffunction-sections', '-fdata-sections', '-fno-lto',
             '-DMK61_USE_M0_EABI=1', '-DMK61_M0_RP2040_EABI=1']
    commands, hashes = [], {}

    def run(args):
        commands.append([str(a) for a in args])
        subprocess.run(commands[-1], check=True)

    for name in [*COMPONENTS, 'ln-near-rounding']:
        prefix = PROTOTYPE if name == 'ln-near-rounding' else 'deltas/' + name
        source, target = W / prefix, output / name
        target.mkdir()
        for src in source.iterdir():
            if src.suffix in {'.cpp', '.inc', '.S', '.ld'}:
                shutil.copyfile(src, target / src.name)
        run([tc / 'arm-none-eabi-g++', *flags, '-I', includes, '-I', SECOND / 'support/includes',
             '-c', target / 'native_eabi_m0.cpp', '-o', target / 'candidate-full.o'])
        objects = [target / 'candidate-full.o']
        entry = 'mk61_m0_atan' if name == 'atan-small-h' else 'mk61_m0_ln'
        if entry == 'mk61_m0_ln':
            run([tc / 'arm-none-eabi-gcc', '-mcpu=cortex-m0plus', '-mthumb', '-mfloat-abi=soft',
                 '-DMK61_USE_M0_EABI=1', '-DMK61_M0_RP2040_EABI=1', '-I', includes,
                 '-c', target / 'ratio.S', '-o', target / 'candidate-ratio.o'])
            objects.append(target / 'candidate-ratio.o')
        run([tc / 'arm-none-eabi-ld', '--gc-sections', '-e', entry, '-T', target / 'candidate.ld',
             *objects, '-o', target / 'candidate.elf'])
        saved = report(prefix + '/candidate-build.json')
        assert sha((target / 'candidate.elf').read_bytes()) == saved['ELF_sha256'], name
        expected_object = (report(prefix + '/result.json')['candidate_full_object_sha256']
                           if name == 'atan-small-h' else saved['full_object_sha256'])
        assert sha((target / 'candidate-full.o').read_bytes()) == expected_object, name
        hashes[name] = saved['ELF_sha256']
    target = output / 'atan-small-h'
    run([tc / 'arm-none-eabi-g++', '-mcpu=cortex-m0plus', '-mthumb', '-mfloat-abi=soft', '-Os',
         '-std=gnu++17', '-fno-exceptions', '-fno-rtti', '-fno-unwind-tables',
         '-ffunction-sections', '-fno-lto', '-c', target / 'ninth-unit.cpp', '-o', target / 'ninth-unit.o'])
    run([tc / 'arm-none-eabi-ld', '-T', target / 'ninth-unit.ld', target / 'ninth-unit.o', '-o', target / 'ninth-unit.elf'])
    digest = sha((target / 'ninth-unit.elf').read_bytes())
    assert digest == report('deltas/atan-small-h/ninth-unit-build.json')['wrapper_ELF_sha256']
    hashes['inline-ninth-unit'] = digest
    target = output / 'log-ratio-dirty'
    run([tc / 'arm-none-eabi-gcc', '-mcpu=cortex-m0plus', '-mthumb', '-mfloat-abi=soft',
         '-c', target / 'seed-kernel.S', '-o', target / 'seed-kernel.o'])
    run([tc / 'arm-none-eabi-objcopy', '-O', 'binary', '-j', '.text.seed',
         target / 'seed-kernel.o', target / 'seed.bin'])
    digest = sha((target / 'seed.bin').read_bytes())
    assert digest == report('deltas/log-ratio-dirty/seed-source-proof.json')['code_sha256']
    hashes['product-seed-code'] = digest
    (output / 'build-commands.json').write_text(json.dumps(commands, indent=2) + '\n')
    return hashes


def replay_oracles():
    sys.path.insert(0, str(FIRST / 'support/support'))
    sys.path.insert(0, str(FIRST / 'support'))
    from m0_mpfr_oracle import Oracle
    from oracles import equal
    oracle, references, counts = Oracle(), {}, Counter()
    for name in COMPONENTS:
        q = report('deltas/' + name + '/qualification.json')
        operation = 'atan' if name == 'atan-small-h' else 'ln'
        for row in q['rows']:
            key = (operation, row['x'])
            if key not in references:
                references[key] = oracle.reference(operation, int(row['x'], 16))
                counts[operation] += 1
            expected = references[key]
            assert equal(int(row['expected'], 16), expected, 64)
            for label, bits in row['outputs'].items():
                assert equal(int(bits, 16), expected, 64) == row['correct'][label], (name, row['x'], label)
    return dict(fresh_MPFR_unique_inputs=dict(counts), MPFR_version=oracle.version,
                public_ARM_or_Qfplib_reexecuted=False, prototype_qualified=False, hardware_accessed=False)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--check-local', action='store_true')
    p.add_argument('--build-output', type=Path)
    p.add_argument('--toolchain', type=Path)
    p.add_argument('--replay-oracles', action='store_true')
    args = p.parse_args()
    result = dict(status='PASS_INTERMEDIATE_RESEARCH_CHECKPOINT', **verify(args.check_local))
    if args.build_output:
        tc = args.toolchain
        if tc is None:
            compiler = shutil.which('arm-none-eabi-gcc')
            if compiler is None:
                p.error('Specify --toolchain /path/to/arm-none-eabi/bin')
            tc = Path(compiler).parent
        result['rebuilt_hashes'] = build(args.build_output, tc)
    if args.replay_oracles:
        result['oracle_replay'] = replay_oracles()
    if args.build_output:
        (args.build_output / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
