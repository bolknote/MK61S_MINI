"""Pin the small-h child with every raw outcome and regression retained."""
from pathlib import Path
from collections import Counter
import hashlib
import json

W = Path(__file__).resolve().parent
ROOT = W.parents[1]
BASE = ROOT / '.build/m0-atan-directional-ninth-20261024'
assert not (W / 'result.json').exists()


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def read(name):
    return json.loads((W / name).read_text())


q, i, b, h, e, c = [read(n) for n in ('qualification.json', 'isolation.json',
    'public-body-proof.json', 'helper-proof.json', 'extra-helper-proof.json', 'low-certificate.json')]
source, elf = sha(W / 'native_eabi_m0_atan_fast.inc'), sha(W / 'candidate.elf')
assert source == 'a85bbc49f2366ae64d025b36dfd27e86abf63c118e447cd43cedd060cdf87e2e'
assert elf == 'fce98d75c6a88d57282b74798371c9c990029193741c4a986483a273321a50c9'
for d in (q, i, h, e):
    assert d['source_sha256'] == source and d['candidate_ELF_sha256'] == elf
assert c['source_sha256'] == source and b['source_include_sha256'] == source
assert b['candidate_ELF_sha256'] == elf and b['whole_independent_ELF_byte_identical']
assert q['cases'] == q['profiled'] == len(q['rows']) == 116376 and q['unique_inputs'] == 58188
assert q['ARM_calls'] == 465504 and q['retained_parent_instruction_counts_checked'] == 106312
assert all(r['profiled'] and r['correct']['candidate'] and r['correct']['parent'] for r in q['rows'])
assert not q['remaining_slower_correct_Qfplib']
assert i['changed_sections'] == {'.text.atan_fast': [2040, 2100]} and not i['added_sections']
assert i['total_allocated_bytes_delta'] == 60 and all(t['allocated_code_and_data_identical'] for t in i['contexts'])
bare_calls = h['ARM_calls'] + sum(e[k] for k in ('ninth_ARM_calls', 'inverse_ARM_calls', 'exact_third_ARM_calls'))
assert bare_calls == 75298
correct = [r for r in q['rows'] if r['correct']['Qfplib']]
speed = dict(Counter('faster' if r['instructions']['candidate'] < r['instructions']['Qfplib']
    else 'equal' if r['instructions']['candidate'] == r['instructions']['Qfplib'] else 'slower' for r in correct))
assert speed == {'faster': 107539, 'equal': 3}
regs = {}
comparisons = {}
for label in ('parent', 'resident'):
    regs[label] = [r for r in q['rows'] if r['instructions']['candidate'] > r['instructions'][label]]
    comparisons[label] = dict(Counter('faster' if r['instructions']['candidate'] < r['instructions'][label]
        else 'equal' if r['instructions']['candidate'] == r['instructions'][label] else 'slower' for r in q['rows']))
assert len(regs['parent']) == 132 and len(regs['resident']) == 4
(W / 'remaining-slower.json').write_text(json.dumps(dict(status='ZERO_OBSERVED_CORRECT_QFPLIB_SPEED_DEFICITS',
    scope='All116376 measured state cases, not every binary64 input', raw_inputs=0, state_rows=0, rows=[]), indent=2) + '\n')
(W / 'regressions.json').write_text(json.dumps(dict(status='ALL_OBSERVED_REGRESSIONS_RETAINED',
    comparisons=comparisons, parent_rows=regs['parent'], V164_rows=regs['resident']), indent=2) + '\n')
pins = json.loads((BASE / 'input-pins.json').read_text())['files']
for name, digest in pins.items():
    assert sha(ROOT / name) == digest, name
for name in ('result.json', 'qualification.json', 'candidate-full.o', 'candidate.elf',
             'native_eabi_m0_atan_fast.inc', 'certificate.json'):
    pins[str((BASE / name).relative_to(ROOT))] = sha(BASE / name)
(W / 'input-pins.json').write_text(json.dumps(dict(status='READ_ONLY_INPUTS_PINNED', files=pins), indent=2) + '\n')
r = dict(status='AUTHOR_PASS_SMALL_H_ATAN_ZERO_OBSERVED_CORRECT_QFPLIB_DEFICITS',
    unique_inputs=q['unique_inputs'], public_state_cases=q['cases'], all_cases_profiled=True,
    public_ARM_calls=q['ARM_calls'], bare_helper_ARM_calls=bare_calls,
    total_actual_ARM_calls=q['ARM_calls']+bare_calls, candidate_wrong=0,
    vs_correct_Qfplib=speed, correct_Qfplib_state_cases=len(correct),
    raw_Qfplib_wrong_state_rows=len(q['rows'])-len(correct), remaining_observed_speed_inputs=0,
    vs_parent=comparisons['parent'], vs_V164=comparisons['resident'],
    allocated_code_bytes_delta=60, stack_bytes_observed=q['candidate_observed_stack_bytes'],
    parent_stack_bytes_observed=q['parent_observed_stack_bytes'], new_tables_or_global_RAM_or_libgcc=False,
    M4_generic_M0_allocated_controls_equal=True, whole_independent_public_relink_ELF_identical=True,
    source_sha256=source, candidate_ELF_sha256=elf, candidate_full_object_sha256=sha(W / 'candidate-full.o'),
    parent_result_sha256=sha(BASE / 'result.json'), independent_review='not_claimed',
    production_integration=False, canonical_runtime_or_device_changed=False,
    physical_cycles_measured=False, exhaustive_binary64_performance_proven=False, goal_complete=False,
    files={p.name: sha(p) for p in sorted(W.iterdir()) if p.is_file()})
(W / 'result.json').write_text(json.dumps(r, indent=2) + '\n')
print(json.dumps({k: v for k, v in r.items() if k != 'files'}, indent=2))
