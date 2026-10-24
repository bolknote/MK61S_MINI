"""Seal the current author result, keeping every known speed deficit."""
from pathlib import Path
from collections import Counter
import hashlib
import json

W = Path(__file__).resolve().parent
ROOT = W.parents[1]
BASE = ROOT / '.build/m0-atan-residual-geometry-20261024'
assert not (W / 'result.json').exists()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def report(name):
    return json.loads((W / name).read_text())


q, h, e, i, b = [report(n) for n in ['qualification.json', 'helper-proof.json',
                                    'extra-helper-proof.json', 'isolation.json',
                                    'public-body-proof.json']]
source, elf = sha(W / 'native_eabi_m0_atan_fast.inc'), sha(W / 'candidate.elf')
assert source == '996dcd240df881b6592b61aeca95fd446c7522b6fff71bc1c6de8eeed9001d23'
assert elf == '35247afa5324a99d061028c606b495a5cd2ccf4bb778a62949d285cf32d99b0a'
for d in (q, h, e, i):
    assert d['source_sha256'] == source and d['candidate_ELF_sha256'] == elf
assert b['source_include_sha256'] == source and b['candidate_ELF_sha256'] == elf
assert b['whole_independent_ELF_byte_identical']
assert q['cases'] == q['profiled'] == len(q['rows']) == 106312
assert q['unique_inputs'] == 53156 and q['ARM_calls'] == 425248
assert all(r['profiled'] and r['correct']['candidate'] and r['correct']['parent'] for r in q['rows'])
assert h['ARM_calls'] == 30412 and h['all_bounded_quotients_0_to_33_covered']
extra = sum(e[k] for k in ('ninth_ARM_calls', 'inverse_ARM_calls', 'exact_third_ARM_calls'))
assert extra == 44886 and extra + h['ARM_calls'] == 75298
assert i['total_allocated_bytes_delta'] == 400
assert i['other_allocated_sections_and_all_tables_identical']
assert not i['new_tables_or_global_RAM_or_libgcc_dependency']
assert all(c['allocated_code_and_data_identical'] for c in i['contexts'])
losses = q['remaining_slower_correct_Qfplib']
assert len(losses) == 4 and {r['x'] for r in losses} == {'3FEF1BCDCF0D1830', 'BFEF1BCDCF0D1830'}
fixed = [r for r in q['rows'] if r['correct']['Qfplib'] and
         r['instructions']['parent'] > r['instructions']['Qfplib'] >= r['instructions']['candidate']]
assert len(fixed) == 36 and len({r['x'] for r in fixed}) == 18
old = json.loads((BASE / 'remaining-slower.json').read_text())['rows']
index = {(r['x'], r['SIO']): r for r in q['rows']}
assert all(index[r['x'], r['SIO']]['instructions']['candidate'] < r['instructions']['Qfplib'] for r in old)
assert all(g['new_slower_correct_Qfplib'] == 0 for g in q['groups'])


def comparison(label):
    return dict(Counter('faster' if r['instructions']['candidate'] < r['instructions'][label]
                        else 'equal' if r['instructions']['candidate'] == r['instructions'][label]
                        else 'slower' for r in q['rows']))


parent_regress = [r for r in q['rows'] if r['instructions']['candidate'] > r['instructions']['parent']]
v164_regress = [r for r in q['rows'] if r['instructions']['candidate'] > r['instructions']['resident']]
assert len(parent_regress) == 60 and len(v164_regress) == 8
(W / 'remaining-slower.json').write_text(json.dumps(dict(
    status='TWO_RAW_ATAN_SPEED_DEFICITS_OPEN', raw_inputs=2, state_rows=4, rows=losses), indent=2) + '\n')
(W / 'regressions.json').write_text(json.dumps(dict(
    status='ALL_OBSERVED_REGRESSIONS_RETAINED', vs_parent=comparison('parent'), vs_V164=comparison('resident'),
    parent_regression_rows=parent_regress, V164_regression_rows=v164_regress,
    parent_instruction_deltas=dict(sorted(Counter(r['instructions']['candidate'] - r['instructions']['parent']
                                                for r in q['rows']).items()))), indent=2) + '\n')
pins = json.loads((BASE / 'input-pins.json').read_text())['files']
for name, digest in pins.items():
    assert sha(ROOT / name) == digest, name
for name in ('result.json', 'qualification.json', 'candidate-full.o', 'candidate.elf', 'native_eabi_m0_atan_fast.inc'):
    pins[str((BASE / name).relative_to(ROOT))] = sha(BASE / name)
receipt = ROOT / '.build/m0-atan-geometry-independent-20261024/FINAL-REVIEW.json'
assert sha(receipt) == '20f3a52335bf160c89b02bcf25262b4a5306e29cbbe0b61da94e284e8b6ba1fc'
assert json.loads(receipt.read_text())['blockers'] == []
pins[str(receipt.relative_to(ROOT))] = sha(receipt)
(W / 'input-pins.json').write_text(json.dumps(dict(status='READ_ONLY_INPUTS_PINNED', files=pins), indent=2) + '\n')
result = dict(
    status='AUTHOR_PASS_DIRECTIONAL_NINTH_ATAN_WITH_TWO_OBSERVED_SPEED_INPUTS_OPEN',
    unique_inputs=q['unique_inputs'], public_state_cases=q['cases'], all_cases_profiled=True,
    public_ARM_calls=q['ARM_calls'], bare_helper_ARM_calls=h['ARM_calls'] + extra,
    total_actual_ARM_calls=q['ARM_calls'] + h['ARM_calls'] + extra, candidate_wrong=0,
    correct_Qfplib_raw_deficits_parent=20, correct_Qfplib_raw_deficits_candidate=2,
    correct_Qfplib_state_deficits_candidate=4, newly_faster_correct_Qfplib_raw_inputs=18,
    old17_faster_correct_Qfplib_both_states=True, new_Qfplib_deficits_vs_parent=0,
    fixed_rows=fixed, vs_parent=comparison('parent'), vs_V164=comparison('resident'),
    raw_Qfplib_wrong_state_rows=sum(g['Qfplib_wrong'] for g in q['groups']),
    allocated_code_bytes_delta=400, stack_bytes_observed=q['candidate_observed_stack_bytes'],
    parent_stack_bytes_observed=q['parent_observed_stack_bytes'],
    new_tables_or_global_RAM_or_libgcc=False, M4_generic_M0_allocated_controls_equal=True,
    whole_independent_public_relink_ELF_identical=True, independent_review='not_claimed',
    source_sha256=source, candidate_ELF_sha256=elf, candidate_full_object_sha256=sha(W / 'candidate-full.o'),
    parent_result_sha256=sha(BASE / 'result.json'), production_integration=False,
    canonical_runtime_or_device_changed=False, physical_cycles_measured=False, goal_complete=False,
    files={p.name: sha(p) for p in sorted(W.iterdir()) if p.is_file()})
(W / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps({k: v for k, v in result.items() if k not in ('fixed_rows', 'files')}, indent=2))
