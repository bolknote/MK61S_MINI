"""Seal the measured four-input improvement without hiding remaining gaps."""
from pathlib import Path
from collections import Counter
import hashlib,json
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
BASE=ROOT/'.build/m0-atan-original-goal-20261024'
P=ROOT/'.build/m0-asin-scaled-bound-v164-20261023'
assert not (W/'result.json').exists()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def report(name):return json.loads((W/name).read_text())
q=report('qualification.json');c=report('cold-profile.json');h=report('helper-proof.json')
i=report('isolation.json');b=report('public-body-proof.json');cert=report('certificate.json')
assert all(g['candidate_wrong']==0 and g['parent_wrong']==0 for g in q['groups'])
assert q['cases']==65416 and q['profiled']==32084 and q['ARM_calls']==228332
assert c['cases']==44 and c['ARM_calls']==176 and c['remaining_correct_Qfplib_slower_inputs']==11
assert h['ARM_calls']==30408 and h['all_bounded_quotients_0_to_33_covered']
source=sha(W/'native_eabi_m0_atan_fast.inc');elf=sha(W/'candidate.elf')
for record in (q,c,h,i):assert record['source_sha256']==source and record['candidate_ELF_sha256']==elf
assert b['source_include_sha256']==source and b['candidate_ELF_sha256']==elf and b['whole_independent_ELF_byte_identical']
assert i['total_allocated_bytes_delta']==444 and all(t['allocated_code_and_data_identical'] for t in i['contexts'])
assert cert['strict_radius_Q70']==6 and cert['residual_modular_width']==71
measured={(r['x'],r['SIO']):r for r in q['rows'] if r['profiled']}
for r in c['rows']:
 key=(r['x'],r['SIO'])
 if key in measured:
  assert r['outputs']==measured[key]['outputs'] and r['instructions']==measured[key]['instructions']
 measured[key]=r
assert len(measured)==32124
losses=[r for r in measured.values() if r['correct']['Qfplib'] and r['instructions']['candidate']>r['instructions']['Qfplib']]
assert len(losses)==22 and len({r['x'] for r in losses})==11
assert all(r['instructions']['parent']>r['instructions']['Qfplib'] for r in losses)
def comparison(label):
 return dict(Counter('faster' if r['instructions']['candidate']<r['instructions'][label] else 'equal' if r['instructions']['candidate']==r['instructions'][label] else 'slower' for r in measured.values()))
delta_counts=dict(sorted(Counter(r['instructions']['candidate']-r['instructions']['parent'] for r in measured.values()).items()))
speed=dict(status='ALL_OBSERVED_CORE_ROUTES_PROFILED_WITH_ELEVEN_SPEED_INPUTS_OPEN',
           original_profiled_state_cases=32084,additional_distinct_profiled_state_cases=40,
           distinct_profiled_state_cases=len(measured),vs_parent=comparison('parent'),vs_V164=comparison('resident'),
           parent_instruction_deltas=delta_counts,remaining_correct_Qfplib_slower_state_rows=len(losses),
           remaining_correct_Qfplib_slower_unique_inputs=11,remaining_rows=losses,new_correct_Qfplib_deficits_vs_parent=0,
           functional_report_sha256=sha(W/'qualification.json'),cold_report_sha256=sha(W/'cold-profile.json'),
           all_measured_owned_results_correct=True,instructions_are_not_cycles=True,goal_complete=False)
(W/'speed-proof.json').write_text(json.dumps(speed,indent=2)+'\n')
parent_pins=json.loads((BASE/'input-pins.json').read_text())['files']
for name,digest in parent_pins.items():assert sha(ROOT/name)==digest,name
manifest=ROOT/'research/m0-math-checkpoint-20261024/baseline-v164/evidence/math-component-manifest.json'
components=json.loads(manifest.read_text())['files']
for name,digest in components.items():assert sha(P/'source'/name)==digest,name
inputs={**parent_pins,**{str((P/'source'/name).relative_to(ROOT)):digest for name,digest in components.items()}}
for name in ('result.json','qualification.json','candidate-full.o','candidate.elf','native_eabi_m0_atan_fast.inc','certify.py','table-proof.json'):
 inputs[str((BASE/name).relative_to(ROOT))]=sha(BASE/name)
receipt=ROOT/'.build/m0-atan-original-goal-independent-20261024/FINAL-REVIEW.json'
assert sha(receipt)=='320ba7d86efaae128e9e98f0e8dd1c35297ad393b4dfdc2d7513e505d3006f29'
inputs[str(receipt.relative_to(ROOT))]=sha(receipt)
for name in ('native_eabi.hpp','compact_math_tables.hpp'):
 p=P/'source/code'/name
 assert p.read_bytes()==(ROOT/'research/m0-math-checkpoint-20261024-2/support/includes'/name).read_bytes()
 inputs[str(p.relative_to(ROOT))]=sha(p)
(W/'input-pins.json').write_text(json.dumps(dict(status='READ_ONLY_PARENT_AND_BASELINE_INPUTS_PINNED',files=inputs,math_components=len(components)),indent=2)+'\n')
result=dict(status='AUTHOR_PASS_BOUNDED_ATAN_RESIDUAL_WITH_ELEVEN_NEWLY_MEASURED_PREEXISTING_SPEED_INPUTS_OPEN',
            public_cases=q['cases'],unique_inputs=q['unique_inputs'],public_ARM_calls=q['ARM_calls'],
            additional_cold_route_ARM_calls=c['ARM_calls'],helper_ARM_calls=h['ARM_calls'],
            total_actual_ARM_calls=q['ARM_calls']+c['ARM_calls']+h['ARM_calls'],
            distinct_profiled_state_cases=len(measured),candidate_wrong=0,
            old4_faster_correct_Qfplib_both_states=True,hard4=q['hard4'],
            remaining_correct_Qfplib_slower_inputs=11,new_correct_Qfplib_deficits_vs_parent=0,
            vs_parent=speed['vs_parent'],vs_V164=speed['vs_V164'],parent_instruction_deltas=delta_counts,
            full_functional_Qfplib_wrong_state_rows=sum(g['Qfplib_wrong'] for g in q['groups']),
            all_observed_CORE_routes_measured=True,MPFR_version=q['MPFR_version'],
            candidate_stack_max_observed=q['candidate_observed_stack_bytes'],parent_stack_max_observed=q['parent_observed_stack_bytes'],
            total_allocated_code_bytes_delta=444,new_tables_or_global_RAM_or_libgcc_dependency=False,
            generic_M0_M4_allocated_controls_equal=True,whole_independent_relink_ELF_identical=True,
            source_sha256=source,candidate_full_object_sha256=sha(W/'candidate-full.o'),candidate_ELF_sha256=elf,
            immutable_parent_ELF_sha256=sha(W/'control.elf'),independent_review='not_claimed',
            canonical_or_frozen_changed=False,Git_USB_Flash_accessed=False,production_integration=False,
            physical_cycles_measured=False,whole_library_goal_complete=False,
            files={p.name:sha(p) for p in sorted(W.iterdir()) if p.is_file() and not p.name.startswith('trial-')})
(W/'result.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k not in ('hard4','files')},indent=2))
