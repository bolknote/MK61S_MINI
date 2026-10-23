"""Read-only integrity and evidence-binding checks for the V138 pow checkpoint."""
import argparse
import ast
import hashlib
import json
from pathlib import Path


archive = Path(__file__).resolve().parent
root = archive.parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--check-local', action='store_true')
args = parser.parse_args()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path):
    return json.loads(path.read_text())


manifest = load(archive / 'checkpoint.json')
actual = {
    str(p.relative_to(archive)): sha(p)
    for p in sorted(archive.rglob('*'))
    if p.is_file() and p.name != 'checkpoint.json' and '__pycache__' not in p.parts
}
assert actual == manifest['files'], 'Archive file hashes differ'
for name in actual:
    path = archive / name
    assert not path.is_symlink(), path
    if path.suffix == '.json':
        load(path)
    elif path.suffix == '.py':
        ast.parse(path.read_text(), filename=str(path))

provenance = load(archive / 'provenance.json')
recorded_root = Path(provenance['original_workspace'])
originals = provenance['archived_originals']
assert len(originals) == 163
for name, ref in originals.items():
    assert sha(archive / name) == ref['sha256'], name
freeze = load(archive / 'offline-checkpoint.json')
assert len(freeze['files']) == 13
for original, digest in freeze['files'].items():
    matches = [name for name, ref in originals.items() if ref['path'] == original]
    assert len(matches) == 1 and sha(archive / matches[0]) == digest, original

elf_sha = 'f4010ce9153d8b9776b236751fcfe67da5e528c2bff5725f87478fec74a42895'
for report, producer in [
    ('totality/exact-boundary.json', 'totality/exact-boundary.py'),
    ('totality/boundary-gap.json', 'totality/boundary-gap.py'),
    ('totality/witness-arm.json', 'totality/witness-arm.py'),
    ('exact-space/active-bounds.json', 'exact-space/active-bounds.py'),
    ('exact-space/digit-circuit.json', 'exact-space/digit-circuit.py'),
    ('exact-space/tiny-profile.json', 'exact-space/tiny-profile.py'),
]:
    data = load(archive / report)
    assert data['producer_sha256'] == sha(archive / producer), report
    assert data['candidate_changed'] is False and data['hardware_accessed'] is False
    if 'elf_sha256' in data:
        assert data['elf_sha256'] == elf_sha, report

boundary = load(archive / 'totality/exact-boundary.json')
assert boundary['cases'] == 10049 and boundary['ARM_calls'] == 20098
assert sum(boundary['outcomes'].values()) == boundary['cases']
assert boundary['general_pow_totality_proved'] is False
gaps = load(archive / 'totality/boundary-gap.json')
assert len(gaps['cases']) == 19
assert gaps['witnesses'] == 18 and gaps['RNE_midpoint_witnesses'] == 13
witness = load(archive / 'totality/witness-arm.json')
assert witness['input_report_sha256'] == sha(archive / 'totality/boundary-gap.json')
assert witness['cases'] == 19 and witness['wrong_rounding'] == 0
assert witness['final_rescue_entries'] == 0
digits = load(archive / 'exact-space/digit-circuit.json')
assert digits['small_integer_oracle']['cases'] == 4109
assert digits['small_integer_oracle']['power_comparisons'] == 160
assert len(digits['experiments']) == 46
assert digits['retained_limb_baseline']['total_limb_products'] == 8128

tiny = load(archive / 'exact-space/tiny-profile.json')
rows = tiny['cases_data']
normal = [row for row in rows if row['positive_normal_base']]
assert len(rows) == tiny['cases'] == 196
assert len(normal) == tiny['normal_base_cases'] == 168
assert all(row['own'] == row['expected'] == '3FF0000000000000' for row in rows)
assert all(row['own_instructions'] > row['qfplib_instructions'] for row in normal)
assert tiny['own_slower_normal_cases'] == 168
assert sum(row['qfplib_wrong'] for row in rows) == tiny['qfplib_wrong'] == 28
assert all(not row['qfplib_wrong'] for row in normal)
for key, field in [('own_mean_instructions', 'own_instructions'),
                   ('qfplib_mean_instructions', 'qfplib_instructions')]:
    assert tiny[key] == sum(row[field] for row in normal) / len(normal)

package = archive / 'math-execution'
execution_path = package / 'execution-manifest.json'
assert sha(execution_path) == provenance['math_execution_manifest_sha256']
assert sha(execution_path) == 'fd584f3e2b9a1387ff236eabdac66b888c452b16cb73c21449c6cb0b8262b18c'
execution = load(execution_path)
assert execution['target']['elf_sha256'] == elf_sha
assert execution['target']['build'] == '83CF4AC4'
assert len(execution['artifacts']) == 189
assert execution['expected']['matrix_groups'] == 117
assert execution['expected']['matrix_chunks'] == 119
assert execution['expected']['matrix_cases'] == 23352
assert execution['expected']['supplementary_cases'] == 30
assert execution['expected']['total_APP_launches'] == 120
assert len(execution['steps']) == 2
assert execution['goal_complete'] is False
assert execution['general_pow_trap_still_open'] is True
assert len(list((package / 'inputs').glob('*.bin'))) == 120
by_original = {ref['path']: name for name, ref in originals.items()}
archived_bindings = 0
for ref in execution['artifacts']:
    path = Path(ref['path'])
    relative = str(path.relative_to(recorded_root))
    if relative in by_original:
        assert sha(archive / by_original[relative]) == ref['sha256'], relative
        archived_bindings += 1
benchmark = load(package / 'benchmark.json')
assert benchmark['elf_sha256'] == elf_sha
assert benchmark['streams'] == 117 and benchmark['cases'] == 23352
assert len(benchmark['chunks']) == 119
for chunk in benchmark['chunks']:
    assert sha(package / 'inputs' / Path(chunk['input']).name) == chunk['input_sha256']
app = load(package / 'app-self-test/result.json')
assert app['status'] == 'PASS' and app['exact_V138_elf_sha256'] == elf_sha
assert app['packed_APP_abi_kinds'] == list(range(13))
assert len(app['negative_guard_rejections']) == 5
runner = load(package / 'runner-self-test/result.json')
assert runner['status'] == 'PASS_OFFLINE_ORCHESTRATION'
assert runner['runner_sha256'] == sha(package / 'run-math.py')
assert runner['helper_sha256'] == sha(package / 'frozen_helpers.py')
assert runner['mock_APP_launches'] == 240 and runner['physical_device_accessed'] is False

local_checks = 0
if args.check_local:
    for ref in originals.values():
        path = root / ref['path']
        assert path.is_file() and sha(path) == ref['sha256'], path
        local_checks += 1
    for ref in execution['artifacts']:
        path = Path(ref['path'])
        assert path.is_file() and sha(path) == ref['sha256'], path
        local_checks += 1

print('PASS: archive, 13 frozen research files, tiny-pow deficit,',
      archived_bindings, 'execution bindings,', local_checks, 'local reference checks.')
