"""Freeze the source-bound, fully profiled Q77 near-ln component."""
from pathlib import Path
from collections import Counter
import difflib
import hashlib
import json

W=Path(__file__).resolve().parent
ROOT=W.parents[1]
BASE=ROOT/'.build/m0-ln-raw-cold-entry-20261024'
assert not (W/'result.json').exists()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(n):return json.loads((W/n).read_text())
q,iso,body,cert,core,pack,units=[read(n) for n in ('qualification.json','isolation.json','public-body-proof.json','certificate.json','core-unit-proof.json','pack-unit-proof.json','unit-body-proof.json')]
source,elf=sha(W/'native_eabi_m0_log70.inc'),sha(W/'candidate.elf')
assert source=='84213d8eb6c7841b48a834cd2304eb8c0ccd6bedc150ee84fd01cf39a8a7e06b'
assert elf=='1164948d280c23bc66601af789dbd2a4af44c0982fb8c813b35fa2b7a396052e'
for d in (q,iso,body,cert,core,pack,units):assert d['source_sha256']==source
for d in (q,iso,body,cert,core,units):assert d['candidate_ELF_sha256']==elf
assert q['cases']==len(q['rows'])==118044 and q['unique_inputs']==59022
assert q['actual_ARM_calls']==472176 and q['retained_parent_counts_checked']==97998
assert q['retained_control_counts_from_previous_full_trial']==114766
assert q['previous_trial_candidate_not_used_as_parent']
assert all(r['correct']['candidate'] and r['outputs']['candidate']==r['outputs']['parent']==r['outputs']['resident'] for r in q['rows'])
assert all(g['newly_slower_correct_Qfplib']==0 for g in q['groups'])
assert q['candidate_stack_bytes']==q['parent_stack_bytes']==640
assert core['actual_ARM_calls']==80120 and core['SIO_accesses']==0 and not core['full_firmware_or_ROM_loaded']
assert pack['actual_ARM_calls']==21504 and pack['SIO_accesses']==0 and not pack['firmware_or_ROM_mapped']
assert core['executed_PC_restricted_to_exact_units_and184Bcapsule']
assert iso['allocated_object_bytes_delta']==452 and iso['new_readonly_table_bytes']==256
assert all(c['allocated_code_and_data_identical'] for c in iso['contexts'])
assert body['entire_ELF_byte_exact_without_exclusions'] and all(u['object_and_whole_ELF_byte_exact'] for u in units['units'])
losses=q['remaining_slower_correct_Qfplib'];raw={r['x'] for r in losses}
assert raw=={'3FF06FFEFFFFFFC1','3FF1146855697319','5FFA5B2647E9E2C7','3FEC7001FFFFFFC1'} and len(losses)==8
parent_raw={r['x'] for r in q['rows'] if r['correct']['Qfplib'] and r['instructions']['parent']>r['instructions']['Qfplib']}
assert len(parent_raw)==58 and not raw-parent_raw
old={r['x'] for r in json.loads((BASE/'remaining-slower.json').read_text())['rows']}
assert len(old)==46 and len(old-raw)==42
fixed=[r for r in q['rows'] if r['correct']['Qfplib'] and r['instructions']['parent']>r['instructions']['Qfplib']>=r['instructions']['candidate']]
assert len(fixed)==108 and len({r['x'] for r in fixed})==54
regress=q['regressions_vs_parent'];delta=Counter(r['instructions']['candidate']-r['instructions']['parent'] for r in regress)
assert len(regress)==47110 and min(delta)==5 and max(delta)==132
change=Counter('faster' if r['instructions']['candidate']<r['instructions']['parent'] else 'equal' if r['instructions']['candidate']==r['instructions']['parent'] else 'slower' for r in q['rows'])
assert change=={'faster':11428,'equal':59506,'slower':47110}
historical=json.loads((ROOT/'.build/m0-asin-scaled-bound-v164-20261023/slower-inputs.json').read_text())['rows']
historical_ln={r['x'] for r in historical if r['operation']=='ln'}
assert len(historical_ln)==10 and not raw&historical_ln
by_key={(r['x'],r['SIO']):r for r in q['rows']}
for x in historical_ln:
    for state in ('READY','DIRTY'):
        r=by_key[x,state];assert r['correct']['Qfplib'] and r['instructions']['candidate']<=r['instructions']['Qfplib']
(W/'remaining-slower.json').write_text(json.dumps(dict(status='FOUR_GENERAL_LN_RAW_SPEED_INPUTS_OPEN',raw_inputs=4,state_rows=8,historical_ln10_all_fixed=True,rows=losses),indent=2)+'\n')
(W/'regressions.json').write_text(json.dumps(dict(status='ALL_PARENT_REGRESSIONS_RETAINED',state_rows=len(regress),instruction_delta_histogram=dict(delta),rows=regress),indent=2)+'\n')
(W/'Q77-near-only.patch').write_text(''.join(difflib.unified_diff((BASE/'native_eabi_m0_log70.inc').read_text().splitlines(True),(W/'native_eabi_m0_log70.inc').read_text().splitlines(True),fromfile='parent/native_eabi_m0_log70.inc',tofile='candidate/native_eabi_m0_log70.inc')))
pins=dict(json.loads((BASE/'input-pins.json').read_text())['files'])
for n,h in pins.items():assert sha(ROOT/n)==h,n
for n in ('result.json','qualification.json','certificate.json','candidate.elf','candidate-full.o','native_eabi_m0_log70.inc','isolation.json','entry-unit-proof.json','public-body-proof.json'):
    p=BASE/n;pins[str(p.relative_to(ROOT))]=sha(p)
for n in ('.build/m0-ln-near-q77-products-20261024/qualification.json','.build/m0-ln-near-q77-products-20261024/qualify.py','.build/m0-ln-near-q77-products-20261024/trial-result.json','.build/m0-ln-near-q77-seed-20261024/probe.json'):
    pins[n]=sha(ROOT/n)
(W/'input-pins.json').write_text(json.dumps(dict(status='READ_ONLY_INPUTS_PINNED',files=pins),indent=2)+'\n')
r=dict(status='AUTHOR_PASS_Q77_NEAR_LN_WITH_FOUR_GENERAL_SPEED_INPUTS_OPEN',
    unique_inputs=59022,public_state_cases=118044,all_cases_profiled=True,
    qualified_public_ARM_calls=472176,qualified_bare_core_ARM_calls=80120,qualified_bare_pack_ARM_calls=21504,total_qualified_ARM_calls=573800,
    nested_capsule_entries_not_added=16384,discarded_trial_and_inherited_calls_not_added=True,
    candidate_wrong=0,retained_frozen_parent_counts_checked=97998,retained_cold_parent_counts_from_previous_full_trial=114766,
    groups=q['groups'],old46_raw_deficits_fixed=42,expanded_parent_raw_losses=58,expanded_candidate_raw_losses=4,
    expanded_correct_Qfplib_raw_deficits_fixed=54,new_correct_Qfplib_deficits=0,remaining_state_rows=8,new_control_parent_losses_fixed=12,
    vs_parent=dict(change),regression_state_rows=len(regress),regression_instruction_histogram=dict(delta),
    public_stack_bytes=640,parent_public_stack_same_corpus=640,bare_core_stack_bytes=core['observed_stack_bytes'],bare_pack_stack_bytes=pack['observed_stack_bytes'],
    allocated_object_code_bytes_delta=196,new_readonly_center_correction_bytes=256,allocated_object_total_delta=452,linked_component_bytes_delta=448,
    no_new_global_RAM_or_libgcc=True,existing_shared_tables_byte_identical=True,M4_generic_M0_allocated_controls_equal=True,whole_public_and_bare_unit_rebuilds_byte_exact=True,
    historical_ln10_total_fixed=10,historical_ln10_remaining=0,source_sha256=source,candidate_ELF_sha256=elf,
    candidate_full_object_sha256=sha(W/'candidate-full.o'),parent_result_sha256=sha(BASE/'result.json'),
    independent_review='not_claimed',production_integration=False,hardware_accessed=False,physical_cycles_measured=False,goal_complete=False)
(W/'HANDOFF.md').write_text(f'''# Private Q77 near ln

Child of frozen IEEE-entry packet. Keep original shared tables; add256B
signed centre corrections. New Q77 near kernel uses an inexpensive
argument correction with captured exact residue, six-product cube,
one-product fifth, exact coefficient biases and3/2cold/4fast RNE gates.
h<=2^38 uses a certified linear path. Full source bounds/table/domain/
overflow/binade/capsule proof is in PROOF.md and certificate.json.

Fresh59022inputs/118044fullyprofiledstates/472176publicARM,0wrongMPFR4.2.2,
raw NaN policy/SIO/PCS/SP/boundedwrites pass. All97998frozenparentcounts
and114766cold-parentcounts from rejectedfulltrial reproduce. Rejected
candidate is not the parent. Barecore80120ARM +exactpack21504ARM yield
qualified573800ARM total;16384nestedcapsuleentries, rejectedtrials and
inherited calls are not added again. Only unit code/184Bcapsule, no full
firmware/ROM,0SIOaccess,PCextent and capsuleentrySP8 checks pass.

Old46rawlosses→4generalraw/8states. Newcontrols add12preexistingparent
losses: expanded58→4,54rawfixed0new. All10originalhistorical ln cases
now no slower than correct Qfp. Last hard3FF01E2A43FC46C8 READY/DIRTY
662vsparent2083/Qfp805; former newloss3FEFF7FFFFFFFFFC398vs601/Qfp673.
The four remaining general inputs are fully retained in remaining-slower.

vsparent11428faster59506equal47110slower. Ordinarynear regressions often
88..102instructions, full range5..132, all retained; no whole-parent
speed-win claim. Qfpwrong18446stateoutcomes are retained. Publicstack640
same, barecore60 andpack48 scoped separately. Oldnear1160→1356code,
+256readonlybytes: object+452/linked+448 after alignmentreuse. No new
globalRAM/libgcc. All other object code/data and original shared tables
match; genericM0/M4allocated controls match, not whole-platform firmware.
WholeCPP/ASM/ELF and both bareunit rebuilds byteexact; linked addresses move.

Source:{source}
ELF:{elf}
Object:{r['candidate_full_object_sha256']}

Freeze packet. Independentreview/canonicalintegration/physicalcycles/HW
are not claimed. Producer historical candidates302/507(296faster6equal),
reviewed298/507 unchanged pending newdelta reviews; immutable507matrix
untouched. Four new general ln controls, otheroperations/generalpow
totality/originalfullgoal remain OPEN. No canonical/Git/device action.
''')
r['files']={str(p.relative_to(W)):sha(p) for p in sorted(W.rglob('*')) if p.is_file()}
(W/'result.json').write_text(json.dumps(r,indent=2)+'\n')
print(json.dumps({k:v for k,v in r.items() if k!='files'},indent=2))
