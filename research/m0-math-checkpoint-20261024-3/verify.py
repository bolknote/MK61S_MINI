#!/usr/bin/env python3
"""Verify the third offline math checkpoint and optional bare-ARM replay."""
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
BASE = W.parent / 'm0-math-checkpoint-20261024'
SECOND = W.parent / 'm0-math-checkpoint-20261024-2'
NAMES = ('atan-residual', 'atan-geometry', 'atan-directional-ninth')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def raw(name):
    p = W / name
    return p.read_bytes() if p.exists() else gzip.decompress(p.with_suffix(p.suffix + '.gz').read_bytes())


def report(name):
    return json.loads(raw(name))


def verify(check_local):
    index = report('checkpoint.json')
    spec = importlib.util.spec_from_file_location('math_checkpoint_second', SECOND / 'verify.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    preceding = module.verify(False)
    assert sha((SECOND / 'checkpoint.json').read_bytes()) == index['base_checkpoint_sha256']
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
    for name, digest in index['review_pins'].items():
        assert sha(raw('reviews/' + name + '/FINAL-REVIEW.json')) == digest
        assert report('reviews/' + name + '/FINAL-REVIEW.json')['blockers'] == []
    summaries = {}
    for name, count in zip(NAMES, (65416, 79096, 106312)):
        prefix = 'deltas/' + name + '/'
        q, r = report(prefix + 'qualification.json'), report(prefix + 'result.json')
        b = report(prefix + 'candidate-build.json')
        source = sha(raw(prefix + 'native_eabi_m0_atan_fast.inc'))
        assert source == b['source_include_sha256'] == r['source_sha256']
        assert b['ELF_sha256'] == r['candidate_ELF_sha256']
        assert q['cases'] == len(q['rows']) == count
        assert all(row['correct']['candidate'] and row['correct']['parent'] and
                   row['outputs']['candidate'] == row['outputs']['parent'] for row in q['rows'])
        iso = report(prefix + 'isolation.json')
        assert all(c['allocated_code_and_data_identical'] for c in iso['contexts'])
        assert report(prefix + 'public-body-proof.json')['whole_independent_ELF_byte_identical']
        if name != 'atan-residual':
            assert q['profiled'] == count and all(row['profiled'] for row in q['rows'])
        summaries[name] = dict(public_cases=count, total_qualified_ARM_calls=r['total_actual_ARM_calls'],
                               candidate_wrong=0, independent_review=name != NAMES[-1])
        if name != NAMES[-1]:
            continue
        assert q['unique_inputs'] == 53156 and q['ARM_calls'] == 425248
        assert r['total_actual_ARM_calls'] == 500546
        losses = [row for row in q['rows'] if row['correct']['Qfplib'] and
                  row['instructions']['candidate'] > row['instructions']['Qfplib']]
        assert losses == q['remaining_slower_correct_Qfplib'] == report(prefix + 'remaining-slower.json')['rows']
        assert len(losses) == 4 and {row['x'] for row in losses} == {'3FEF1BCDCF0D1830', 'BFEF1BCDCF0D1830'}
        fixed = [row for row in q['rows'] if row['correct']['Qfplib'] and
                 row['instructions']['parent'] > row['instructions']['Qfplib'] >= row['instructions']['candidate']]
        assert fixed == r['fixed_rows'] and len(fixed) == 36 and len({row['x'] for row in fixed}) == 18
        assert all(not (row['correct']['Qfplib'] and
                       row['instructions']['parent'] <= row['instructions']['Qfplib'] < row['instructions']['candidate'])
                   for row in q['rows'])
        regress = report(prefix + 'regressions.json')
        for label, key, count_regress in [('parent', 'parent_regression_rows', 60),
                                          ('resident', 'V164_regression_rows', 8)]:
            rows = [row for row in q['rows'] if row['instructions']['candidate'] > row['instructions'][label]]
            assert rows == regress[key] and len(rows) == count_regress
            changes = dict(Counter('faster' if row['instructions']['candidate'] < row['instructions'][label]
                                   else 'equal' if row['instructions']['candidate'] == row['instructions'][label]
                                   else 'slower' for row in q['rows']))
            assert changes == r['vs_parent' if label == 'parent' else 'vs_V164']
        assert sum(g['Qfplib_wrong'] for g in q['groups']) == r['raw_Qfplib_wrong_state_rows'] == 8272
        assert iso['total_allocated_bytes_delta'] == 400 and not iso['new_tables_or_global_RAM_or_libgcc_dependency']
        assert q['candidate_observed_stack_bytes'] == 912 and q['parent_observed_stack_bytes'] == 888
        for proof in ('helper-proof.json', 'extra-helper-proof.json'):
            h = report(prefix + proof)
            assert h['source_sha256'] == source and h['candidate_ELF_sha256'] == b['ELF_sha256']
        unit = report(prefix + 'ninth-unit-build.json')
        header = raw(prefix + 'native_eabi_m0_atan_fast.inc').decode()
        fragment = header[header.index('struct AtanTailCorrection '):header.index('// Pack the bounded atan domain')]
        assert sha(fragment.encode()) == unit['exact_fragment_sha256']
        assert fragment in raw(prefix + 'ninth-unit.cpp').decode()
        assert unit['public_source_sha256'] == source
    return dict(archive_files=len(index['files']), original_artifacts=len(provenance['archived_files']),
                preceding_archives_verified=2, preceding_second_files=preceding['archive_files'],
                independent_receipts=2, local_originals_checked=check_local, components=summaries,
                canonical_runtime_integrated=False, hardware_accessed=False, goal_complete=False)


def build(output, tc):
    output = output.resolve()
    for protected in (W, BASE, SECOND):
        assert protected != output and protected not in output.parents
    output.mkdir(parents=True, exist_ok=False)
    includes = BASE / 'baseline-v164/source/code'
    commands, hashes = [], {}

    def run(args):
        commands.append([str(a) for a in args])
        subprocess.run(commands[-1], check=True)

    flags = ['-mcpu=cortex-m0plus', '-mthumb', '-mfloat-abi=soft', '-Os', '-std=gnu++17',
             '-fno-exceptions', '-fno-rtti', '-fno-unwind-tables', '-fno-use-cxa-atexit',
             '-ffunction-sections', '-fdata-sections', '-fno-lto',
             '-DMK61_USE_M0_EABI=1', '-DMK61_M0_RP2040_EABI=1']
    for name in NAMES:
        source, target = W / 'deltas' / name, output / name
        target.mkdir()
        for filename in ('native_eabi_m0.cpp', 'native_eabi_m0_atan.inc',
                         'native_eabi_m0_atan_fast.inc', 'candidate.ld', 'candidate-build.json'):
            shutil.copyfile(source / filename, target / filename)
        run([tc / 'arm-none-eabi-g++', *flags, '-I', includes, '-I', SECOND / 'support/includes',
             '-c', target / 'native_eabi_m0.cpp', '-o', target / 'candidate-full.o'])
        run([tc / 'arm-none-eabi-ld', '--gc-sections', '-e', 'mk61_m0_atan', '-T',
             target / 'candidate.ld', target / 'candidate-full.o', '-o', target / 'candidate.elf'])
        saved = report('deltas/' + name + '/result.json')
        actual = sha((target / 'candidate.elf').read_bytes())
        assert actual == saved['candidate_ELF_sha256'], (name, actual)
        assert sha((target / 'candidate-full.o').read_bytes()) == saved['candidate_full_object_sha256']
        hashes[name] = actual
    target = output / NAMES[-1]
    source = W / 'deltas' / NAMES[-1]
    for filename in ('ninth-unit.cpp', 'ninth-unit.ld', 'ninth-unit-build.json'):
        shutil.copyfile(source / filename, target / filename)
    unit_flags = ['-mcpu=cortex-m0plus', '-mthumb', '-mfloat-abi=soft', '-Os', '-std=gnu++17',
                  '-fno-exceptions', '-fno-rtti', '-fno-unwind-tables', '-ffunction-sections', '-fno-lto']
    run([tc / 'arm-none-eabi-g++', *unit_flags, '-c', target / 'ninth-unit.cpp', '-o', target / 'ninth-unit.o'])
    run([tc / 'arm-none-eabi-ld', '-T', target / 'ninth-unit.ld', target / 'ninth-unit.o', '-o', target / 'ninth-unit.elf'])
    actual = sha((target / 'ninth-unit.elf').read_bytes())
    assert actual == report('deltas/' + NAMES[-1] + '/ninth-unit-build.json')['wrapper_ELF_sha256']
    hashes['inline-ninth-unit'] = actual
    (output / 'build-commands.json').write_text(json.dumps(commands, indent=2) + '\n')
    return output, hashes


def replay(output):
    # Adapt only import paths in copies of the original bare-helper producers.
    # They write fresh reports into the new build directory, never the archive.
    prefix = 'deltas/' + NAMES[-1] + '/'
    target = output / NAMES[-1]
    imports = "sys.path.insert(0," + repr(str(BASE / 'support/support')) + ")"
    scripts = [('verify-helper.py', "sys.path.insert(0,str(Q/'support'))", 'helper-proof.json'),
               ('verify-extra-helpers.py', "sys.path.insert(0,str(ROOT/'.build/m0-float-fma-qualification-20261023/support'))",
                'extra-helper-proof.json')]
    reproduced = {}
    for script, old_import, evidence in scripts:
        code = raw(prefix + script).decode()
        assert code.count(old_import) == 1
        path = target / script
        path.write_text(code.replace(old_import, imports))
        subprocess.run([sys.executable, '-B', str(path)], check=True, capture_output=True, text=True)
        fresh = json.loads((target / evidence).read_text())
        saved = report(prefix + evidence)
        assert {k: v for k, v in fresh.items() if k != 'elapsed_seconds'} == {
            k: v for k, v in saved.items() if k != 'elapsed_seconds'}, evidence
        reproduced[evidence] = {k: v for k, v in fresh.items() if 'transcript_sha256' in k or k == 'digest_sha256'}
    sys.path.insert(0, str(BASE / 'support/support'))
    sys.path.insert(0, str(BASE / 'support'))
    from m0_mpfr_oracle import Oracle
    from oracles import equal
    oracle = Oracle()
    q = report(prefix + 'qualification.json')
    expected = {}
    for row in q['rows']:
        raw_input = int(row['x'], 16)
        if raw_input not in expected:
            expected[raw_input] = oracle.reference('atan', raw_input)
        assert equal(int(row['expected'], 16), expected[raw_input], 64)
        assert equal(int(row['outputs']['candidate'], 16), expected[raw_input], 64)
    assert len(expected) == 53156
    return dict(fresh_bare_helper_ARM_calls=75298, reproduced_transcripts=reproduced,
                fresh_MPFR_unique_inputs=len(expected), MPFR_version=oracle.version,
                public_atan_or_Qfplib_ARM_replayed=False, firmware_or_ROM_mapped=False,
                whole_library_replayed=False, hardware_accessed=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-local', action='store_true')
    parser.add_argument('--build-output', type=Path)
    parser.add_argument('--toolchain', type=Path)
    parser.add_argument('--replay', action='store_true')
    args = parser.parse_args()
    if args.replay and args.build_output is None:
        parser.error('--replay requires --build-output')
    result = dict(status='PASS_INTERMEDIATE_RESEARCH_CHECKPOINT', **verify(args.check_local))
    if args.build_output:
        tc = args.toolchain
        if tc is None:
            compiler = shutil.which('arm-none-eabi-gcc')
            if compiler is None:
                parser.error('Specify --toolchain /path/to/arm-none-eabi/bin')
            tc = Path(compiler).parent
        output, result['rebuilt_ELF_hashes'] = build(args.build_output, tc)
        if args.replay:
            result['replay'] = replay(output)
        (output / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
