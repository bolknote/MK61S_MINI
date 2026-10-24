"""Freeze the exact busy quotient without dropping any remaining ln loss."""
from pathlib import Path
from collections import Counter
import hashlib
import json

W = Path(__file__).resolve().parent
ROOT = W.parents[1]
P = ROOT/'.build/m0-asin-scaled-bound-v164-20261023'
assert not (W/'result.json').exists()


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def read(name):
    return json.loads((W/name).read_text())


q, h, i, b, c, seed = [read(n) for n in ('qualification.json','helper-proof.json',
    'isolation.json','public-body-proof.json','certificate.json','seed-source-proof.json')]
source, elf = sha(W/'native_eabi_m0_log70_center.inc'), sha(W/'candidate.elf')
assert source == '9480f6ffa1abc80b502f35499b4d8b2fd1fdd42b3de0408af2feaadcd7be6d74'
assert elf == '4e1a6b9151b96b5f9355e75c891c508809cad22d6c67fb9ef33354485acd5dff'
for d in (q,h,i,b):
    assert d['source_sha256'] == source and d['candidate_ELF_sha256'] == elf
assert c['source_sha256'] == source and c['busy_zero_shortcut_exact']
assert c['both_dyadic_endpoint_shortcuts_exact_all_denominators']
assert q['cases'] == len(q['rows']) == 29814 and q['unique_inputs'] == 14907
assert q['actual_ARM_calls'] == 119256 and h['actual_ARM_calls'] == 155608
assert all(r['correct']['candidate'] and r['correct']['parent'] for r in q['rows'])
assert not q['regressions_vs_parent']
assert q['candidate_stack_bytes'] == q['parent_stack_bytes'] == 488
assert all(g['newly_slower_correct_Qfplib'] == 0 for g in q['groups'])
assert [g['candidate_slower_correct_Qfplib'] for g in q['groups']] == [27,27]
assert [g['parent_slower_correct_Qfplib'] for g in q['groups']] == [27,8310]
losses = q['remaining_slower_correct_Qfplib']
assert len(losses) == 54 and len({r['x'] for r in losses}) == 27
fixed = [r for r in q['rows'] if r['correct']['Qfplib'] and
    r['instructions']['parent'] > r['instructions']['Qfplib'] >= r['instructions']['candidate']]
assert len(fixed) == 8283
assert all(t['allocated_code_and_data_identical'] for t in i['contexts'])
assert i['allocated_object_bytes_delta'] == 156 and i['ratio_ASM_allocated_bytes_delta'] == 8
assert i['linked_component_allocated_bytes_delta'] == 160
assert b['entire_ELF_byte_exact_without_exclusions'] and h['SIO_accesses'] == 0
assert seed['code_sha256'] == h['additional_loaded_seed_code_sha256']
(W/'remaining-slower.json').write_text(json.dumps(dict(status='TWENTY_SEVEN_RAW_LN_SPEED_INPUTS_OPEN',
    raw_inputs=27,state_rows=54,rows=losses),indent=2)+'\n')
pins = {}
paths = list((P/'source/code').rglob('*')) + [P/'firmware/mk61s-picocalc-pico-h.elf',
    ROOT/'.build/m0-v138-execution-20261023/reference/reference.elf',
    ROOT/'research/rp2040-memset-2026-10-21/capture/bootrom.bin', ROOT/'tests/check_stm32_vectors.py']
support = ROOT/'.build/m0-float-fma-qualification-20261023'
paths += [support/'oracles.py',support/'support/native_eabi_m0_arm_self_test.py',support/'support/m0_mpfr_oracle.py']
for p in paths:
    if p.is_file():
        pins[str(p.relative_to(ROOT))] = sha(p)
cc = Path('/Users/bolk/Library/Arduino15/packages/STMicroelectronics/tools/xpack-arm-none-eabi-gcc/14.2.1-1.1/bin')
for name in ('arm-none-eabi-gcc','arm-none-eabi-g++','arm-none-eabi-ld'):
    pins[str(cc/name)] = sha(cc/name)
(W/'input-pins.json').write_text(json.dumps(dict(status='READ_ONLY_INPUTS_PINNED',files=pins),indent=2)+'\n')
r = dict(status='AUTHOR_PASS_EXACT_BUSY_LOG_QUOTIENT_WITH_27_SPEED_INPUTS_OPEN',
    unique_inputs=q['unique_inputs'], public_state_cases=q['cases'], all_cases_profiled=True,
    public_ARM_calls=q['actual_ARM_calls'], bare_helper_ARM_calls=h['actual_ARM_calls'],
    total_actual_ARM_calls=q['actual_ARM_calls']+h['actual_ARM_calls'], candidate_wrong=0,
    groups=q['groups'], correct_Qfplib_state_deficits_fixed=8283, remaining_observed_speed_inputs=27,
    remaining_speed_state_rows=54, new_correct_Qfplib_deficits=0,
    all_READY_counts_identical=True, vs_parent=dict(faster=12893,equal=16921,slower=0),
    public_stack_bytes_observed=488, direct_helper_stack_bytes_observed=h['observed_stack_bytes'],
    allocated_object_bytes_delta=164, linked_component_bytes_delta=160,
    new_tables_or_global_RAM_or_libgcc=False, M4_generic_M0_allocated_controls_equal=True,
    whole_independent_public_relink_ELF_identical=True,
    source_sha256=source, ratio_ASM_source_sha256=sha(W/'native_eabi_m0_log70_ratio.inc'),
    candidate_ELF_sha256=elf, candidate_full_object_sha256=sha(W/'candidate-full.o'),
    independent_review='not_claimed', production_integration=False, hardware_accessed=False,
    canonical_runtime_or_device_changed=False, physical_cycles_measured=False, goal_complete=False,
    files={p.name:sha(p) for p in sorted(W.iterdir()) if p.is_file()})
(W/'result.json').write_text(json.dumps(r,indent=2)+'\n')
print(json.dumps({k:v for k,v in r.items() if k!='files'},indent=2))
