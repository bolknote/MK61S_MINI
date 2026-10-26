"""Seal the qualified private main-ln coefficient child, retaining all losses."""
from pathlib import Path
from collections import Counter
import difflib
import hashlib
import json

W=Path(__file__).resolve().parent
ROOT=W.parents[1]
BASE=ROOT/'.build/m0-ln-main-ln2-sign-20261024'
assert not (W/'result.json').exists()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
read=lambda n:json.loads((W/n).read_text())
q,iso,cert,pack,body,unit=[read(n) for n in ('qualification.json','isolation.json','certificate.json','pack-unit-proof.json','public-body-proof.json','unit-body-proof.json')]
source,elf=sha(W/'native_eabi_m0_log70.inc'),sha(W/'candidate.elf')
assert source=='4db4753b23ebaa7a17aed662d2f59d6b351f6c0d8739559ad4235e6c615f1fd2'
assert elf=='2c0d376fe0b12c99f694279c2382977b00001875b4777aed504c0e1e309df728'
for item in (q,iso,cert,pack,body,unit):
    assert item['source_sha256']==source
    assert item['candidate_ELF_sha256']==elf
assert q['cases']==len(q['rows'])==177178 and q['unique_inputs']==88589
assert len({(r['x'],r['SIO']) for r in q['rows']})==177178
assert q['actual_ARM_calls']==708712 and q['retained_parent_counts_checked']==120988
assert q['candidate_stack_bytes']==648 and q['parent_stack_bytes']==640
assert all(r['correct']['candidate'] and r['outputs']['candidate']==r['outputs']['parent']==r['outputs']['resident'] for r in q['rows'])
assert all(g['newly_slower_correct_Qfplib']==0 for g in q['groups'])
assert pack['actual_ARM_calls']==120256 and pack['SIO_accesses']==0 and not pack['full_firmware_or_ROM_loaded']
assert pack['rational_RNE_endpoint_checks']==13940 and pack['new_coefficient_forced_pack_configurations']==2880
assert iso['allocated_object_bytes_delta']==888 and iso['no_new_tables_global_RAM_or_libgcc']
assert all(c['allocated_code_and_data_identical'] for c in iso['contexts'])
assert body['entire_ELF_byte_exact_without_exclusions'] and unit['whole_ELF_byte_exact'] and unit['object_byte_exact']

def loses(row,name):return row['correct']['Qfplib'] and row['instructions'][name]>row['instructions']['Qfplib']
parent_raw={r['x'] for r in q['rows'] if loses(r,'parent')}
losses=q['remaining_slower_correct_Qfplib'];remaining={r['x'] for r in losses}
assert len(parent_raw)==14 and len(remaining)==5 and len(losses)==10
assert remaining=={'3FF04001FFFFFFFF','3FF0C9049694DE26','3FF0E29E2E0FBA0B','3FF0E23E696625E7','3FF051D3CC2E965E'}
assert remaining<=parent_raw
endpoint=json.loads((ROOT/'.build/m0-ln-main-endpoint-lower-20261024/probe.json').read_text())
old_seven={r['x'] for r in endpoint['rows'] if loses(r,'parent')}
assert len(old_seven)==7 and not remaining&old_seven
regress=q['regressions_vs_parent']
histogram=Counter(r['instructions']['candidate']-r['instructions']['parent'] for r in regress)
change=Counter('faster' if r['instructions']['candidate']<r['instructions']['parent'] else 'equal' if r['instructions']['candidate']==r['instructions']['parent'] else 'slower' for r in q['rows'])
assert change==dict(faster=7398,equal=84176,slower=85604)
assert len(regress)==85604 and min(histogram)==1 and max(histogram)==108
(W/'remaining-slower.json').write_text(json.dumps(dict(status='FIVE_EXPANDED_MAIN_LN_RAW_SPEED_INPUTS_OPEN',raw_inputs=5,state_rows=10,rows=losses),indent=2)+'\n')
(W/'regressions.json').write_text(json.dumps(dict(status='ALL_PARENT_INSTRUCTION_REGRESSIONS_RETAINED',state_rows=len(regress),instruction_delta_histogram=dict(histogram),rows=regress),indent=2)+'\n')
(W/'coefficient-only.patch').write_text(''.join(difflib.unified_diff((BASE/'native_eabi_m0_log70.inc').read_text().splitlines(True),(W/'native_eabi_m0_log70.inc').read_text().splitlines(True),fromfile='parent/native_eabi_m0_log70.inc',tofile='candidate/native_eabi_m0_log70.inc')))

pins=dict(json.loads((BASE/'input-pins.json').read_text())['files'])
for name,h in pins.items():assert sha(ROOT/name)==h,name
parent=json.loads((BASE/'result.json').read_text())
for name,h in parent['files'].items():
    path=BASE/name;assert sha(path)==h,path
    pins[str(path.relative_to(ROOT))]=h
pins[str((BASE/'result.json').relative_to(ROOT))]=sha(BASE/'result.json')
for name in ('.build/m0-ln-main-endpoint-lower-20261024/probe.json',
             '.build/m0-ln-main-raw-split-family-independent-20261024/FINAL-REVIEW.json',
             '.build/m0-ln-raw-cold-entry-independent-20261024/FINAL-REVIEW.json',
             '.build/m0-ln-raw-cold-entry-independent-20261024/Q77-parent-premise-closure.json',
             '.build/m0-ln-main-rounding-bias-20261024/trial-result.json'):
    pins[name]=sha(ROOT/name)
(W/'input-pins.json').write_text(json.dumps(dict(status='READ_ONLY_PARENT_AND_CORPUS_INPUTS_PINNED',files=pins),indent=2)+'\n')
r=dict(status='AUTHOR_PASS_MAIN_LN_QUARTER_FIFTH_WITH_FIVE_EXPANDED_SPEED_INPUTS_OPEN',
    unique_inputs=88589,public_state_cases=177178,all_cases_profiled=True,qualified_public_ARM_calls=708712,
    qualified_bare_pack_ARM_calls=120256,total_qualified_ARM_calls=828968,probes_studies_and_inherited_calls_not_added=True,
    candidate_wrong=0,retained_parent_counts_checked=120988,groups=q['groups'],
    expanded_parent_raw_losses=14,expanded_candidate_raw_losses=5,correct_Qfplib_raw_deficits_fixed=9,
    new_correct_Qfplib_deficits=0,remaining_state_rows=10,all_seven_exploratory_endpoint_parent_losses_fixed=True,
    vs_parent=dict(change),regression_state_rows=len(regress),regression_instruction_histogram=dict(histogram),
    public_stack_bytes=648,parent_public_stack_same_corpus=640,bare_pack_stack_bytes=72,
    allocated_object_code_bytes_delta=888,linked_component_bytes_delta=888,
    no_new_tables_global_RAM_or_libgcc=True,inherited_near_Q77_and_shared_tables_byte_identical=True,
    M4_generic_M0_allocated_controls_equal=True,whole_public_and_bare_unit_rebuilds_byte_exact=True,
    historical_ln10_total_fixed=10,historical_ln10_remaining=0,source_sha256=source,candidate_ELF_sha256=elf,
    candidate_full_object_sha256=sha(W/'candidate-full.o'),parent_result_sha256=sha(BASE/'result.json'),
    independent_review='not_claimed',production_integration=False,hardware_accessed=False,
    physical_cycles_measured=False,goal_complete=False)
(W/'HANDOFF.md').write_text(f'''# Private main-ln fourth/fifth coefficient gate

The RP2040 main packer now uses exact fourth/fifth coefficient remainders,
one-sided denominator bands and the exact n/2 ln2 error. Cheaper k=0 gates
use one-sided polynomial bounds first. Existing argument helpers, polynomial,
tables, near-Q77, fallback and generic-M0/M4 controls remain unchanged.
See PROOF.md, exact rational certificate and literal bare-unit source.

Fresh88589inputs/177178fullyprofiledstates/708712publicARM:0wrong MPFR4.2.2,
rawNaN/PCS/SP/boundedwrites/SIO pass; all120988parentcounts reproduce.
Bare120256ARM, including13940pack calls and13940rational endpoint checks;
2880new-predicate forced pack configurations, all normal n magnitudes,
coefficient signs/remainders/band/equality/midpoint/parity/carry controls.
No firmware/ROM in bare tests;0SIO accesses. Qualified828968ARM total;
probe, model and inherited calls are excluded.

Expanded14raw→5raw/10states,9fixed0new. All7earlier endpoint-probe losses
fixed; the larger corpus exposes seven more preexisting parent deficits,
two also fixed. Remaining5raw are retained without a whole-ln speed claim.
Of177178states,7398faster/84176equal/85604slower than parent. All parent
regressions retained, mostly+1..7instructions, maximum+108 on a preexisting
fallback path. Stack648vs640 (+8), bare72. Only2function bodies grow:
raw+376B, exact+512B; object/linked+888B, no newtable/RAM/libgcc.
Q77near and all other object/table bytes exact; genericM0/M4 allocated
controls equal. FullCPP/ASM/ELF and bareunit rebuild byteexact.

3FEC7001FFFFFFC1 READY694/DIRTY775 vsQfp783, parent2263/2344.
Three positive upper-point losses now READY602/DIRTY659 vsQfp785..824.
These are instruction counts, not physical cycles.

Source:{source}
ELF:{elf}
Object:{r['candidate_full_object_sha256']}

Freeze this inspection packet. Independent review, integration, physical
acceptance and whole-library/whole-goal GO remain open. Historicalauthor
302/507 and reviewed298/507 stay unchanged. Pow totality and other needed
operations remain in the original goal. No canonical/Git/device actions.
''')
r['files']={str(p.relative_to(W)):sha(p) for p in sorted(W.rglob('*')) if p.is_file()}
(W/'result.json').write_text(json.dumps(r,indent=2)+'\n')
print(json.dumps({k:v for k,v in r.items() if k!='files'},indent=2))
