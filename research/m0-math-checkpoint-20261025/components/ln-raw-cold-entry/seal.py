"""Freeze the fully profiled private ln IEEE entry component."""
from pathlib import Path
from collections import Counter
import difflib
import hashlib
import json

W=Path(__file__).resolve().parent
ROOT=W.parents[1]
BASE=ROOT/'.build/m0-ln-main-raw-split-family-20261024'
assert not (W/'result.json').exists()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(n):return json.loads((W/n).read_text())
q,iso,body,cert,unit,mask=[read(n) for n in ('qualification.json','isolation.json','public-body-proof.json','certificate.json','entry-unit-proof.json','raw-mask-proof.json')]
source,elf=sha(W/'native_eabi_m0_log70.inc'),sha(W/'candidate.elf')
assert source=='52e3a6f0a32069120fe0ccd3ec6593872cb97bd9579bd1a2e9b8d654bd2efb1a'
assert elf=='cc8ac3115c96e3424ac9f4f4ac848d403c9114c4d1fc81270042c53d8c417ef6'
for d in (q,iso,body,cert,unit,mask):assert d['source_sha256']==source
for d in (q,iso,body,cert,mask):assert d['candidate_ELF_sha256']==elf
assert q['cases']==len(q['rows'])==97998 and q['unique_inputs']==48999
assert q['actual_ARM_calls']==391992 and q['retained_parent_counts_checked']==97536
assert all(r['correct']['candidate'] and r['outputs']['candidate']==r['outputs']['parent']==r['outputs']['resident'] for r in q['rows'])
assert all(g['newly_slower_correct_Qfplib']==0 for g in q['groups'])
assert q['candidate_stack_bytes']==q['parent_stack_bytes']==640
assert unit['actual_ARM_calls']==131072 and unit['raw_inputs']==65536 and unit['SIO_accesses']==0
assert iso['allocated_object_bytes_delta']==16 and all(c['allocated_code_and_data_identical'] for c in iso['contexts'])
assert body['entire_ELF_byte_exact_without_exclusions']
losses=q['remaining_slower_correct_Qfplib'];raw={r['x'] for r in losses}
assert len(raw)==46 and len(losses)==92
parent_raw={r['x'] for r in q['rows'] if r['correct']['Qfplib'] and r['instructions']['parent']>r['instructions']['Qfplib']}
assert len(parent_raw)==49 and not raw-parent_raw
fixed=[r for r in q['rows'] if r['correct']['Qfplib'] and r['instructions']['parent']>r['instructions']['Qfplib']>=r['instructions']['candidate']]
assert {r['x'] for r in fixed}=={'0000000000000000','8000000000000000','7FF0000000000000'} and len(fixed)==6
early={r['x']:dict(candidate=r['instructions']['candidate'],Qfplib=r['instructions']['Qfplib']) for r in fixed if r['SIO']=='READY'}
assert early=={'7FF0000000000000':{'candidate':8,'Qfplib':10},'8000000000000000':{'candidate':6,'Qfplib':6},'0000000000000000':{'candidate':6,'Qfplib':8}}
regress=q['regressions_vs_parent'];delta=Counter(r['instructions']['candidate']-r['instructions']['parent'] for r in regress)
assert delta=={1:19562,5:8344,6:2022,4:1026}
change=Counter('faster' if r['instructions']['candidate']<r['instructions']['parent'] else 'equal' if r['instructions']['candidate']==r['instructions']['parent'] else 'slower' for r in q['rows'])
(W/'remaining-slower.json').write_text(json.dumps(dict(status='FORTY_SIX_EXPANDED_LN_RAW_SPEED_INPUTS_OPEN',raw_inputs=46,state_rows=92,rows=losses),indent=2)+'\n')
(W/'regressions.json').write_text(json.dumps(dict(status='ALL_PARENT_REGRESSIONS_RETAINED',state_rows=len(regress),instruction_delta_histogram=dict(delta),rows=regress),indent=2)+'\n')
(W/'IEEE-entry-only.patch').write_text(''.join(difflib.unified_diff((BASE/'native_eabi_m0_log70.inc').read_text().splitlines(True),(W/'native_eabi_m0_log70.inc').read_text().splitlines(True),fromfile='parent/native_eabi_m0_log70.inc',tofile='candidate/native_eabi_m0_log70.inc')))
pins=dict(json.loads((BASE/'input-pins.json').read_text())['files'])
for n,h in pins.items():assert sha(ROOT/n)==h,n
for n in ('result.json','qualification.json','certificate.json','candidate.elf','candidate-full.o','native_eabi_m0_log70.inc','native_eabi_m0_log70_center.inc','isolation.json','pack-unit-proof.json','public-body-proof.json'):
    p=BASE/n;pins[str(p.relative_to(ROOT))]=sha(p)
p=ROOT/'.build/m0-ln-cold-entry-20261024/prepare.py';pins[str(p.relative_to(ROOT))]=sha(p)
(W/'input-pins.json').write_text(json.dumps(dict(status='READ_ONLY_INPUTS_PINNED',files=pins),indent=2)+'\n')
r=dict(status='AUTHOR_PASS_LN_IEEE_ENTRY_WITH_46_EXPANDED_SPEED_INPUTS_OPEN',
    unique_inputs=48999,public_state_cases=97998,all_cases_profiled=True,
    qualified_public_ARM_calls=391992,qualified_bare_entry_ARM_calls=131072,total_qualified_ARM_calls=523064,
    inherited_parent_bare_pack_calls_not_added=32338,candidate_wrong=0,retained_parent_counts_checked=97536,
    groups=q['groups'],expanded_parent_raw_losses=49,expanded_candidate_raw_losses=46,
    correct_Qfplib_raw_deficits_fixed=3,new_correct_Qfplib_deficits=0,remaining_state_rows=92,IEEE_early_costs=early,
    vs_parent=dict(change),regression_state_rows=len(regress),regression_instruction_histogram=dict(delta),
    public_stack_bytes=640,parent_public_stack_same_corpus=640,tagged_entry_unit_stack_bytes=unit['observed_stack_bytes'],
    allocated_object_code_bytes_delta=16,linked_component_bytes_delta=16,
    new_tables_global_RAM_or_libgcc=False,M4_generic_M0_allocated_controls_equal=True,whole_public_rebuild_byte_exact=True,
    historical_ln10_total_fixed=9,historical_ln10_remaining=1,source_sha256=source,candidate_ELF_sha256=elf,
    candidate_full_object_sha256=sha(W/'candidate-full.o'),parent_result_sha256=sha(BASE/'result.json'),
    independent_review='not_claimed',production_integration=False,hardware_accessed=False,
    physical_cycles_measured=False,goal_complete=False)
(W/'HANDOFF.md').write_text(f'''# Private short IEEE ln entry

Child of frozen raw-main-split-family. Naked RP entry returns ln(+/-0)
as -Inf and ln(+Inf) unchanged, with6/6/8instructions vsQfp8/6/10.
All other inputs tail forward exact original bits: positive normals to
the unchanged normal source, cold inputs to unchanged ln_special.

Fresh48999inputs/97998fullyprofiled states/391992publicARM:0wrongMPFR4.2.2,
raw NaN policy/callerSIO/PCS/SP/boundedwrites pass; all97536parentcounts
reproduce. Exact naked unit131072bareARM/65536raw/all4096sign-exponent
fields/fraction+lowclasses/bothSIO passes with0SIOaccess. Qualified total
523064ARM, inherited32338parentpack calls not added. Numerical enclosure
proofs inherited; new classifier/source and raw object mask are proved.

49expanded raw deficits→46raw/92states, exactly3IEEEfixed,0new. Historical
ln9/10fixed1open. Overall producer candidates301/507(295faster6equal),
independently reviewed298/507 unchanged pending new delta reviews.
Regressions vsparent are explicit30954states:19562+1,8344+5,2022+6,1026+4;
all remain no slower than correct Qfp when parent was no slower. ln2DIRTY
622vsparent617/Qfp711. No whole-parent speed-win claim.

Code+16B, stack640same, no newtables/RAM/libgcc. Source numeric bodies,
other allocated object code/data/deps and genericM0/M4controls match.
Raw object1356→1360 adds one sign-mask instruction+alignmentNOP due lost
IPA positive-input fact; all normalized instructions/literals/relocations
otherwise match. WholeCPP/ASM/ELF rebuildbyteexact; linked addresses shift.

Source:{source}
ELF:{elf}
Object:{r['candidate_full_object_sha256']}

Freeze packet. No canonical/Git/device/lease/shipping action. Independent
review, whole-library integration, physical cycles/HW, remaining ln46,
other operations/general pow totality/original full goal remain OPEN.
''')
r['files']={str(p.relative_to(W)):sha(p) for p in sorted(W.rglob('*')) if p.is_file()}
(W/'result.json').write_text(json.dumps(r,indent=2)+'\n')
print(json.dumps({k:v for k,v in r.items() if k!='files'},indent=2))
