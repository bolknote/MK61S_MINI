"""Read-only portable checkpoint verifier; never executes archived producers."""
import argparse
import collections
import contextlib
import gzip
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import statistics
import sys

sys.dont_write_bytecode = True
W = Path(__file__).resolve().parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--records', action='store_true')
parser.add_argument('--extract-candidate', type=Path)
args = parser.parse_args()


def digest_stream(stream):
    h, size = hashlib.sha256(), 0
    for block in iter(lambda: stream.read(1 << 20), b''):
        h.update(block)
        size += len(block)
    return h.hexdigest(), size


def checked(name):
    p = PurePosixPath(name)
    assert p.parts and not p.is_absolute() and all(v not in ('.', '..') for v in p.parts)
    for part in p.parts:
        assert not re.match(r'^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)', part, re.I)
        assert part[-1] not in '. ' and not any(c in part for c in '<>:"\\|?*')
    result = W.joinpath(*p.parts)
    assert not result.is_symlink()
    return result


index = json.loads((W / 'checkpoint.json').read_text())
names = set(index['files']) | {'checkpoint.json'}
assert len(names) == len({v.casefold() for v in names})
assert names == {str(p.relative_to(W)) for p in W.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
for name, expected in index['files'].items():
    with checked(name).open('rb') as f:
        assert digest_stream(f)[0] == expected, name
provenance = json.loads((W / 'provenance.json').read_text())
entries = {v['source']: v for v in provenance['archived_files']}
omitted = {v['source']: v for v in provenance['omitted_binary_files']}
assert len(entries) == len(provenance['archived_files']) and not entries.keys() & omitted.keys()


@contextlib.contextmanager
def source_stream(source):
    row = entries[source]
    if row['encoding'] == 'identity':
        with checked(row['path']).open('rb') as f:
            yield f
    else:
        assert row['encoding'] == 'gzip'
        with gzip.open(checked(row['path']), 'rb') as f:
            yield f


def source_json(source):
    with source_stream(source) as f:
        return json.load(f)


def same_numeric_result(a, b):
    # Match the frozen qualification: finite values are bit-exact; qNaN sign
    # and payload are retained in the records but are not rounding errors.
    x, y = int(a, 16), int(b, 16)
    quiet_nan = 0x7ff8000000000000
    return x == y or (x & quiet_nan) == quiet_nan and (y & quiet_nan) == quiet_nan


@contextlib.contextmanager
def source_lines(source):
    with source_stream(source) as stream:
        decoded = gzip.GzipFile(fileobj=stream) if source.endswith('.gz') else stream
        with io.TextIOWrapper(decoded, encoding='utf-8') as f:
            yield f


verified = set()
for row in entries.values():
    if row['path'] in verified:
        continue
    with checked(row['path']).open('rb') as f:
        assert digest_stream(f) == (row['sha256'], row['stored_bytes'])
    with source_stream(row['source']) as f:
        assert digest_stream(f) == (row['uncompressed_sha256'], row['uncompressed_bytes'])
    verified.add(row['path'])
manifest_pins = 0
for source, info in json.loads((W / 'manifests.json').read_text()).items():
    manifest = source_json(source)
    assert entries[source]['uncompressed_sha256'] == info['sha256']
    assert len(manifest['files']) == info['pins']
    parent = str(PurePosixPath(source).parent)
    for name, pin in manifest['files'].items():
        target = parent + '/' + name
        if target in entries:
            row = entries[target]
            actual = (row['uncompressed_bytes'], row['uncompressed_sha256'])
        else:
            row = omitted[target]
            actual = (row['bytes'], row['sha256'])
        assert actual == (pin['bytes'], pin['sha256']), target
        manifest_pins += 1
S = '.build/m0-math-r64-final-host-20261028-001/'
R = '.build/m0-math-r64-ram-hil-host-20261028-001/'
O = '.build/m0-math-r64-d6-wake-operators-20261028-001/'
A = '.build/m0-math-r64-all84-physical-report-20261028-001/'
P = 'external/primary/.build/development-next-root-20261028-001/'
author = source_json(S + 'AUTHOR-RESULT.json')
report = source_json(A + 'REPORT.json')
root = source_json(P + 'ROOT-R64-ALL84-FINAL-HIL-AND-RETURN.json')
assert root['status'] == 'ROOT_R64_R63_ALL84_HIL_AND_D6_DATA_RETURN_ACCEPTED_HARDWARE_CLOSED'
assert root['typed_settings_UI_exact_from_first_to_final'] and root['full2MiB_Flash_reads'] == 12
assert root['final_epoch'] == ['18', '00010001'] and root['final_keys'] == 0
assert entries[P + 'ROOT-R64-ALL84-FINAL-HIL-AND-RETURN.json']['uncompressed_sha256'] == '2394e8c039d40090ff4a5ff618ad9b05f6851b1c30c765b414062676692f3f50'
assert omitted[S + 'candidate.elf']['sha256'] == author['candidate_ELF']['sha256']
assert author['complete_same_old_corpus']['R64_losing_pairs'] == 1398
assert not index['goal_complete'] and not index['canonical_runtime_integrated'] and not index['M4_changed']
result = dict(status='PASS_PORTABLE_R64_CHECKPOINT', archived_files=len(entries), unique_payloads=len(verified),
              omitted_binaries=len(omitted), verified_manifest_pins=manifest_pins, records_recounted=False,
              new_device_ARM_MPFR_SDK_calls=0, goal_complete=False)
if args.records:
    pairs, old_losses, new_losses = set(), set(), set()
    rows = increased = introduced = wrong_refs = positives = 0
    max_increase = 0
    with source_lines(S + 'joined-pow-records.jsonl.gz') as f:
        for line in f:
            r = json.loads(line)
            key = (r['x'], r['y'])
            pairs.add(key)
            rows += 1
            assert same_numeric_result(r['candidate']['bits'], r['expected'])
            assert same_numeric_result(r['parent_R63']['bits'], r['expected'])
            delta = r['candidate']['instructions'] - r['parent_R63']['instructions']
            assert delta == r['candidate_minus_R63_instructions']
            increased += delta > 0
            max_increase = max(max_increase, delta)
            assert all(v['correct'] == same_numeric_result(v['bits'], r['expected']) for v in r['references'].values())
            wrong_refs += sum(not v['correct'] for v in r['references'].values())
            correct = [v['instructions'] for v in r['references'].values() if v['correct']]
            before = bool(correct and r['parent_R63']['instructions'] > min(correct))
            after = bool(correct and r['candidate']['instructions'] > min(correct))
            assert before == r['previously_losing'] and after == r['currently_losing']
            if before:
                old_losses.add(key)
            if after:
                new_losses.add(key)
            introduced += after and not before
            if not (int(r['x'], 16) >> 63):
                positives += 1
                assert delta == 0
    assert (len(pairs), rows, len(old_losses), len(new_losses), introduced) == (152937, 324446, 1400, 1398, 0)
    assert (increased, max_increase, wrong_refs, positives) == (7658, 14, 391799, 242400)
    expected = {(r['x'], r['y'], r['SIO']): r['expected'] for r in source_json(R + 'HIL-MATRIX-CORRECTED.json')}
    versions = {'R64': {}, 'R63': {}}
    calls, wrong = collections.Counter(), collections.Counter()
    queries = calibrations = 0
    for batch, role in [('r64-smoke', 'R64'), ('r63-smoke', 'R63'), ('r64-tail', 'R64'), ('r63-tail', 'R63')]:
        nonce = None
        with source_lines(O + 'stage-outputs/' + batch + '-math-cdc-001/records.jsonl') as f:
            for line in f:
                r = json.loads(line)
                if r['kind'] == 'identity':
                    assert nonce is None
                    nonce = r['value']['nonce']
                    assert r['value']['math_ok'] == 1 and r['value']['core_hz'] == 125000000
                    continue
                if r['kind'] == 'explicit_exit_to_ROM_USB':
                    assert r['value'] == {'type': 'X', 'nonce': nonce}
                    continue
                queries += 1
                assert r['done']['samples'] == len(r['samples'])
                assert all(s['nonce'] == nonce and s['id'] == r['request_id'] for s in r['samples'])
                if r['kind'] == 'calibration':
                    calibrations += len(r['samples'])
                    continue
                assert r['kind'] == 'math_case' and len(r['samples']) == 40
                case = r['source_case']
                key = (case['x'], case['y'], case['SIO'])
                assert key not in versions[role] and case['expected'] == expected[key]
                libs = {}
                for lib in range(4):
                    ss = [s for s in r['samples'] if s['library'] == lib]
                    assert sorted(s['round'] for s in ss) == [0, 1, 2, 3, 4, 5, 6, 7, 128, 129]
                    label = role if lib == 0 else 'Qfp' + str(lib)
                    calls[label] += len(ss)
                    bad = sum(s['bits'] != int(case['expected'], 16) or s['flags'] != 0 for s in ss)
                    wrong[label] += bad
                    if lib == 0:
                        assert bad == 0
                    libs[lib] = dict(correct=bad == 0,
                                     cycles=statistics.median(s['cycles'] for s in ss if s['round'] < 8),
                                     bits=[s['bits'] for s in ss])
                refs = [v['cycles'] for k, v in libs.items() if k and v['correct']]
                cls = 'no_correct_Qfplib' if not refs else 'slower' if libs[0]['cycles'] > min(refs) else 'equal' if libs[0]['cycles'] == min(refs) else 'faster'
                versions[role][key] = dict(libs=libs, cls=cls)
    assert versions['R64'].keys() == versions['R63'].keys() == expected.keys() and len(expected) == 84
    counts = collections.Counter()
    classes = {role: collections.Counter(r['cls'] for r in data.values()) for role, data in versions.items()}
    deltas = []
    for key, new in versions['R64'].items():
        old = versions['R63'][key]
        delta = new['libs'][0]['cycles'] - old['libs'][0]['cycles']
        deltas.append(delta)
        counts['faster' if delta < 0 else 'slower' if delta > 0 else 'equal'] += 1
        assert not (old['cls'] in ('faster', 'equal') and new['cls'] == 'slower')
        for lib in (1, 2, 3):
            assert new['libs'][lib] == old['libs'][lib]
    assert dict(counts) == report['R64_vs_R63'] == dict(faster=39, equal=18, slower=27)
    assert [min(deltas), max(deltas)] == report['R64_vs_R63_cycle_delta_range'] == [-4135, 40]
    assert {k: dict(v) for k, v in classes.items()} == report['against_fastest_correct_Qfplib']
    assert (queries, calibrations, sum(calls.values()), sum(wrong.values())) == (192, 240, 6720, 3060)
    assert calls['R64'] == calls['R63'] == 840 and wrong['R64'] == wrong['R63'] == 0
    assert len(source_json(A + 'WORSE-THAN-R63.json')) == 27
    assert len(source_json(A + 'REMAINING-SLOWER-THAN-QFPLIB.json')) == 45
    result.update(records_recounted=True, HOST_pairs=len(pairs), HOST_states=rows, HOST_remaining_pow_pairs=len(new_losses),
                  HOST_adverse_states=increased, HOST_max_adverse_instructions=max_increase,
                  physical_states_per_runtime=84, physical_total_calls=6960, our_wrong=0,
                  retained_wrong_Qfplib_calls=3060, R64_vs_R63=dict(counts),
                  physical_R64_vs_correct_Qfplib=dict(classes['R64']),
                  physical_delta_range=[min(deltas), max(deltas)], universal_claim=False)
if args.extract_candidate:
    dest = args.extract_candidate.resolve()
    assert not dest.exists(), 'Use a new directory'
    dest.mkdir(parents=True)
    prefix = S + 'source/'
    for source in entries:
        if not source.startswith(prefix):
            continue
        name = PurePosixPath(source[len(prefix):])
        assert not name.is_absolute() and '..' not in name.parts
        target = dest.joinpath(*name.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        with source_stream(source) as src, target.open('xb') as out:
            for block in iter(lambda: src.read(1 << 20), b''):
                out.write(block)
print(json.dumps(result, ensure_ascii=False, indent=2))
