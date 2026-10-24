"""Pin this all-input-profiled child without suppressing remaining losses."""
from pathlib import Path
from collections import Counter
import hashlib,json
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
BASE=ROOT/'.build/m0-atan-residual-original-goal-20261024'
assert not (W/'result.json').exists()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def report(name):return json.loads((W/name).read_text())
q=report('qualification.json');h=report('helper-proof.json');i=report('isolation.json');b=report('public-body-proof.json')
assert q['cases']==q['profiled']==len(q['rows'])==79096 and q['unique_inputs']==39548
assert q['ARM_calls']==316384 and all(g['candidate_wrong']==g['parent_wrong']==0 for g in q['groups'])
assert all(r['profiled'] and r['correct']['candidate'] and r['correct']['parent'] for r in q['rows'])
assert h['ARM_calls']==30412 and h['all_bounded_quotients_0_to_33_covered']
source=sha(W/'native_eabi_m0_atan_fast.inc');elf=sha(W/'candidate.elf')
for d in (q,h,i):assert d['source_sha256']==source and d['candidate_ELF_sha256']==elf
assert b['source_include_sha256']==source and b['candidate_ELF_sha256']==elf and b['whole_independent_ELF_byte_identical']
assert i['added_sections']=={} and i['total_allocated_bytes_delta']==32
assert i['changed_sections']=={'.text.atan_fast':[1748,1780]}
assert all(t['allocated_code_and_data_identical'] for t in i['contexts'])
losses=q['remaining_slower_correct_Qfplib'];assert len(losses)==34 and len({r['x'] for r in losses})==17
fixed=[r for r in q['rows'] if r['correct']['Qfplib'] and r['instructions']['parent']>r['instructions']['Qfplib']>=r['instructions']['candidate']]
assert len(fixed)==12 and len({r['x'] for r in fixed})==6
vs=lambda label:dict(Counter('faster' if r['instructions']['candidate']<r['instructions'][label] else 'equal' if r['instructions']['candidate']==r['instructions'][label] else 'slower' for r in q['rows']))
regress=[r for r in q['rows'] if r['instructions']['candidate']>r['instructions']['resident']]
assert len(regress)==8 and len({r['x'] for r in regress})==4
(W/'remaining-slower.json').write_text(json.dumps(dict(status='SEVENTEEN_RAW_ATAN_SPEED_DEFICITS_OPEN',raw_inputs=17,state_rows=34,rows=losses),indent=2)+'\n')
(W/'regressions.json').write_text(json.dumps(dict(status='ALL_OBSERVED_REGRESSIONS_RETAINED',vs_parent=vs('parent'),vs_V164=vs('resident'),V164_regression_rows=regress,
 parent_instruction_deltas=dict(sorted(Counter(r['instructions']['candidate']-r['instructions']['parent'] for r in q['rows']).items()))),indent=2)+'\n')
pins=json.loads((BASE/'input-pins.json').read_text())['files']
for name,digest in pins.items():assert sha(ROOT/name)==digest,name
for name in ('result.json','qualification.json','cold-profile.json','candidate-full.o','candidate.elf','native_eabi_m0_atan_fast.inc'):
 pins[str((BASE/name).relative_to(ROOT))]=sha(BASE/name)
receipt=ROOT/'.build/m0-atan-residual-independent-20261024/FINAL-REVIEW.json'
assert sha(receipt)=='b6a2234936391b97077999065e3055fd28e1935e519fd603a6a008c9d44bbaed'
assert json.loads(receipt.read_text())['blockers']==[]
pins[str(receipt.relative_to(ROOT))]=sha(receipt)
(W/'input-pins.json').write_text(json.dumps(dict(status='READ_ONLY_INPUTS_PINNED',files=pins),indent=2)+'\n')
result=dict(status='AUTHOR_PASS_ALL_GEOMETRY_ATAN_REPAIR_WITH_SEVENTEEN_OBSERVED_SPEED_INPUTS_OPEN',
 unique_inputs=q['unique_inputs'],public_state_cases=q['cases'],all_cases_profiled=True,public_ARM_calls=q['ARM_calls'],
 helper_ARM_calls=h['ARM_calls'],total_actual_ARM_calls=q['ARM_calls']+h['ARM_calls'],candidate_wrong=0,
 correct_Qfplib_raw_deficits_parent=23,correct_Qfplib_raw_deficits_candidate=17,correct_Qfplib_state_deficits_candidate=34,
 newly_faster_correct_Qfplib_raw_inputs=6,new_Qfplib_deficits_vs_parent=0,fixed_rows=fixed,
 vs_parent=vs('parent'),vs_V164=vs('resident'),raw_Qfplib_wrong_state_rows=sum(g['Qfplib_wrong'] for g in q['groups']),
 allocated_code_bytes_delta=32,stack_bytes_observed=q['candidate_observed_stack_bytes'],parent_stack_bytes_observed=q['parent_observed_stack_bytes'],
 helper_allocated_bytes_unchanged=True,other_allocated_sections_tables_dependencies_identical=True,
 M4_generic_M0_allocated_controls_equal=True,whole_independent_public_relink_ELF_identical=True,
 source_sha256=source,candidate_ELF_sha256=elf,candidate_full_object_sha256=sha(W/'candidate-full.o'),
 parent_result_sha256=sha(BASE/'result.json'),independent_review='not_claimed',
 canonical_or_frozen_changed=False,Git_USB_Flash_accessed=False,new_tables_or_global_RAM_or_libgcc=False,
 production_integration=False,physical_cycles_measured=False,goal_complete=False,
 files={p.name:sha(p) for p in sorted(W.iterdir()) if p.is_file()})
(W/'result.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k not in ('fixed_rows','files')},indent=2))
