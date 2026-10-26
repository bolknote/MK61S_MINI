"""Freeze the fully profiled private raw-main ln component."""
from pathlib import Path
from collections import Counter
import difflib
import hashlib
import json

W=Path(__file__).resolve().parent
ROOT=W.parents[1]
BASE=ROOT/'.build/m0-log-ratio-small-limb-20261024'
assert not (W/'result.json').exists()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(n):return json.loads((W/n).read_text())
q,iso,body,cert,unit=[read(n) for n in ('qualification.json','isolation.json','public-body-proof.json','certificate.json','pack-unit-proof.json')]
source,elf=sha(W/'native_eabi_m0_log70.inc'),sha(W/'candidate.elf')
assert source=='8294798875f17de019d15a57208f04daf2d74c431873036ecc87111df583e42f'
assert elf=='b82a9f1f09b5edd41c099abc82208b6254e52d0a817080f78625a0c818ac836a'
for d in (q,iso,body,cert,unit):assert d['source_sha256']==source
for d in (q,iso,body,cert):assert d['candidate_ELF_sha256']==elf
assert q['cases']==len(q['rows'])==97536 and q['unique_inputs']==48768
assert q['actual_ARM_calls']==390144 and q['retained_parent_counts_checked']==68876
assert all(r['correct']['candidate'] and r['outputs']['candidate']==r['outputs']['parent']==r['outputs']['resident'] for r in q['rows'])
assert all(g['newly_slower_correct_Qfplib']==0 for g in q['groups'])
assert q['candidate_stack_bytes']==q['parent_stack_bytes']==640
assert unit['actual_ARM_calls']==32338 and unit['configurations']==16169
assert unit['SIO_accesses']==0 and not unit['firmware_or_ROM_mapped']
assert iso['allocated_object_bytes_delta']==1384
assert all(c['allocated_code_and_data_identical'] for c in iso['contexts'])
assert body['entire_ELF_byte_exact_without_exclusions']
old=json.loads((BASE/'remaining-slower.json').read_text())['rows']
old_raw={r['x'] for r in old}
losses=q['remaining_slower_correct_Qfplib'];raw={r['x'] for r in losses}
assert len(raw)==49 and len(losses)==98
assert len(old_raw-raw)==23 and len(old_raw&raw)==45
fixed=[r for r in q['rows'] if r['correct']['Qfplib'] and r['instructions']['parent']>r['instructions']['Qfplib']>=r['instructions']['candidate']]
assert len(fixed)==24 and all(r['SIO']=='DIRTY' for r in fixed)
parent_raw={r['x'] for r in q['rows'] if r['correct']['Qfplib'] and r['instructions']['parent']>r['instructions']['Qfplib']}
assert len(parent_raw)==73 and not raw-parent_raw
regress=q['regressions_vs_parent']
delta=Counter(r['instructions']['candidate']-r['instructions']['parent'] for r in regress)
assert delta=={4:32670,8:12096}
change=Counter('faster' if r['instructions']['candidate']<r['instructions']['parent'] else 'equal' if r['instructions']['candidate']==r['instructions']['parent'] else 'slower' for r in q['rows'])
(W/'remaining-slower.json').write_text(json.dumps(dict(status='FORTY_NINE_EXPANDED_LN_RAW_SPEED_INPUTS_OPEN',raw_inputs=49,state_rows=98,old68_remaining=45,new_control_remaining=4,rows=losses),indent=2)+'\n')
(W/'regressions.json').write_text(json.dumps(dict(status='ALL_PARENT_REGRESSIONS_RETAINED',state_rows=len(regress),instruction_delta_histogram=dict(delta),rows=regress),indent=2)+'\n')
(W/'raw-main-only.patch').write_text(''.join(difflib.unified_diff((BASE/'native_eabi_m0_log70.inc').read_text().splitlines(True),(W/'native_eabi_m0_log70.inc').read_text().splitlines(True),fromfile='parent/native_eabi_m0_log70.inc',tofile='candidate/native_eabi_m0_log70.inc')))
pins=dict(json.loads((BASE/'input-pins.json').read_text())['files'])
for n,h in pins.items():assert sha(ROOT/n)==h,n
for n in ('result.json','qualification.json','certificate.json','candidate.elf','candidate-full.o','native_eabi_m0_log70_center.inc','native_eabi_m0_log70.inc','isolation.json'):
    p=BASE/n;pins[str(p.relative_to(ROOT))]=sha(p)
p=ROOT/'.build/m0-log-ratio-small-limb-independent-20261024/FINAL-REVIEW.json'
assert sha(p)=='cd842f0284cda419305b6f2610e0a80ab91578406b8ec185435e745512483f63'
assert json.loads(p.read_text())['blockers']==[]
pins[str(p.relative_to(ROOT))]=sha(p)
(W/'input-pins.json').write_text(json.dumps(dict(status='READ_ONLY_INPUTS_PINNED',files=pins),indent=2)+'\n')
r=dict(status='AUTHOR_PASS_RAW_MAIN_LN_WITH_49_EXPANDED_SPEED_INPUTS_OPEN',
    unique_inputs=48768,public_state_cases=97536,all_cases_profiled=True,
    qualified_public_ARM_calls=390144,qualified_bare_pack_ARM_calls=32338,total_qualified_ARM_calls=422482,
    candidate_wrong=0,retained_parent_counts_checked=68876,groups=q['groups'],
    old68_raw_deficits_fixed=23,old68_raw_deficits_remaining=45,
    expanded_parent_raw_losses=73,expanded_candidate_raw_losses=49,
    expanded_correct_Qfplib_raw_deficits_fixed=24,new_correct_Qfplib_deficits=0,remaining_state_rows=98,
    newly_exposed_parent_control_losses=5,new_control_losses_remaining=4,
    vs_parent=dict(change),regression_state_rows=len(regress),regression_instruction_histogram=dict(delta),
    public_stack_bytes=640,parent_public_stack_same_corpus=640,bare_packer_stack_bytes=unit['observed_stack_bytes'],
    allocated_object_code_bytes_delta=1384,linked_component_bytes_delta=1384,
    new_tables_global_RAM_or_libgcc=False,M4_generic_M0_allocated_controls_equal=True,whole_public_rebuild_byte_exact=True,
    historical_ln10_total_fixed=6,historical_ln10_remaining=4,source_sha256=source,candidate_ELF_sha256=elf,
    candidate_full_object_sha256=sha(W/'candidate-full.o'),parent_result_sha256=sha(BASE/'result.json'),
    independent_review='not_claimed',production_integration=False,hardware_accessed=False,
    physical_cycles_measured=False,goal_complete=False)
(W/'HANDOFF.md').write_text(f'''# Private raw main ln

Child of accepted exact-small-limb component. Outside the dyadic low-word
family and with SIO DIRTY, skip exact quotient correction and use the
existing product46 seed. A residual-aware integer gate certifies the final
binary64 RNE; uncertain cases use unchanged ln_refine. READY and family
inputs retain the old exact polynomial/pack body. Source-bound B6.900060<7,
generic radius16 and exact captured h residual are proved in PROOF.md.

Fresh48768inputs/97536all-profiled states/390144public ARM:0wrongMPFR4.2.2,
raw NaN policy identical, PCS/SP/boundedwrites/SIO pass, all68876parent
counts reproduce. Bare exact pack32338ARM/16169configs/22364Fraction
endpointchecks/all1024den/bothSIO and binade/sign boundaries pass. Qualified
ARM total422482; earlier probes/trials and inherited calls are not added.

Old68raw deficits become45. New controls expose5preexisting parent losses,
giving expandedparent73raw to child49raw/98states:24fixed,0new. READY49
and DIRTY49remain, each matching on these deficits. Parent regressions
are explicit32670states+4 and12096states+8; DIRTY12096faster20337equal
16335slower. ln2DIRTY617vsparent613/Qfp711; guard-65input659vs712/Qfp713.

Code+1384B, no new tables/RAM/libgcc; public max stack640same, barepack56.
Only RP public main dispatch and new raw normal body change in object.
Other allocated sections/table data/dependencies match; genericM0/M4
allocated controls match, not whole-platform builds. WholeCPP/ASM/ELF
rebuild byte-exact. Linked addresses relocate; no linked identity claim.

Source:{source}
ELF:{elf}
Object:{r['candidate_full_object_sha256']}

Freeze this packet. Independent review, canonical integration and physical
cycles/HW acceptance are not claimed. Historical ln remains6/10fixed4open.
Other operations/general pow totality/the original full goal remain OPEN.
''')
r['files']={str(p.relative_to(W)):sha(p) for p in sorted(W.rglob('*')) if p.is_file()}
(W/'result.json').write_text(json.dumps(r,indent=2)+'\n')
print(json.dumps({k:v for k,v in r.items() if k!='files'},indent=2))
