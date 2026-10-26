"""Freeze the main-ln directional ln2 guard component."""
from pathlib import Path
from collections import Counter
import difflib
import hashlib
import json

W=Path(__file__).resolve().parent
ROOT=W.parents[1]
BASE=ROOT/'.build/m0-ln-near-q77-linear-20261024'
assert not (W/'result.json').exists()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(n):return json.loads((W/n).read_text())
q,iso,body,cert,pack,unit,assertion=[read(n) for n in ('qualification.json','isolation.json','public-body-proof.json','certificate.json','pack-unit-proof.json','unit-body-proof.json','static-assert-proof.json')]
source,elf=sha(W/'native_eabi_m0_log70.inc'),sha(W/'candidate.elf')
assert source=='661ae2b62f0f2e3b9da08b689de0a7876f83fa2f80f57380113b78cbbd74e79b'
assert elf=='9f872b40e65543d712459854dd261677ce6b504bc3b829112f09126c940395aa'
for d in (q,iso,body,cert,pack,unit,assertion):assert d['source_sha256']==source
for d in (q,iso,body,cert,unit):assert d['candidate_ELF_sha256']==elf
assert q['cases']==len(q['rows'])==120988 and q['unique_inputs']==60494
assert q['actual_ARM_calls']==483952 and q['retained_parent_counts_checked']==118044
assert all(r['correct']['candidate'] and r['outputs']['candidate']==r['outputs']['parent']==r['outputs']['resident'] for r in q['rows'])
assert all(g['newly_slower_correct_Qfplib']==0 for g in q['groups'])
assert q['candidate_stack_bytes']==q['parent_stack_bytes']==640
assert pack['actual_ARM_calls']==12264 and pack['SIO_accesses']==0 and not pack['full_firmware_or_ROM_loaded']
assert iso['allocated_object_bytes_delta']==16 and iso['no_new_tables_global_RAM_or_libgcc']
assert all(c['allocated_code_and_data_identical'] for c in iso['contexts'])
assert body['entire_ELF_byte_exact_without_exclusions'] and unit['whole_ELF_byte_exact'] and unit['object_byte_exact']
assert assertion['whole_ELF_byte_exact'] and assertion['full_object_byte_exact']
losses=q['remaining_slower_correct_Qfplib'];raw={r['x'] for r in losses}
assert raw=={'3FF06FFEFFFFFFC1','3FF1146855697319','3FEC7001FFFFFFC1'} and len(losses)==6
parent_raw={r['x'] for r in q['rows'] if r['correct']['Qfplib'] and r['instructions']['parent']>r['instructions']['Qfplib']}
assert len(parent_raw)==4 and not raw-parent_raw
fixed=[r for r in q['rows'] if r['correct']['Qfplib'] and r['instructions']['parent']>r['instructions']['Qfplib']>=r['instructions']['candidate']]
assert len(fixed)==2 and {r['x'] for r in fixed}=={'5FFA5B2647E9E2C7'}
regress=q['regressions_vs_parent'];delta=Counter(r['instructions']['candidate']-r['instructions']['parent'] for r in regress)
assert len(regress)==7 and delta=={3:5,4:2}
change=Counter('faster' if r['instructions']['candidate']<r['instructions']['parent'] else 'equal' if r['instructions']['candidate']==r['instructions']['parent'] else 'slower' for r in q['rows'])
assert change=={'faster':2,'equal':120979,'slower':7}
(W/'remaining-slower.json').write_text(json.dumps(dict(status='THREE_GENERAL_LN_RAW_SPEED_INPUTS_OPEN',raw_inputs=3,state_rows=6,rows=losses),indent=2)+'\n')
(W/'regressions.json').write_text(json.dumps(dict(status='ALL_PARENT_REGRESSIONS_RETAINED',state_rows=7,instruction_delta_histogram=dict(delta),rows=regress),indent=2)+'\n')
(W/'ln2-sign-only.patch').write_text(''.join(difflib.unified_diff((BASE/'native_eabi_m0_log70.inc').read_text().splitlines(True),(W/'native_eabi_m0_log70.inc').read_text().splitlines(True),fromfile='parent/native_eabi_m0_log70.inc',tofile='candidate/native_eabi_m0_log70.inc')))
pins=dict(json.loads((BASE/'input-pins.json').read_text())['files'])
for n,h in pins.items():assert sha(ROOT/n)==h,n
for n in ('result.json','qualification.json','qualify.py','certificate.json','candidate.elf','candidate-full.o','native_eabi_m0_log70.inc','isolation.json','core-unit-proof.json','pack-unit-proof.json','public-body-proof.json'):
    p=BASE/n;pins[str(p.relative_to(ROOT))]=sha(p)
for n in ('.build/m0-ln-enclosure-20261024/certificate.json','.build/m0-ln-main-raw-split-family-20261024/certificate.json'):
    pins[n]=sha(ROOT/n)
(W/'input-pins.json').write_text(json.dumps(dict(status='READ_ONLY_INPUTS_PINNED',files=pins),indent=2)+'\n')
r=dict(status='AUTHOR_PASS_MAIN_LN_LN2_SIGN_WITH_THREE_SPEED_INPUTS_OPEN',unique_inputs=60494,public_state_cases=120988,all_cases_profiled=True,
    qualified_public_ARM_calls=483952,qualified_bare_pack_ARM_calls=12264,total_qualified_ARM_calls=496216,inherited_and_pre_assert_probe_calls_not_added=True,
    candidate_wrong=0,retained_parent_counts_checked=118044,groups=q['groups'],expanded_parent_raw_losses=4,expanded_candidate_raw_losses=3,
    correct_Qfplib_raw_deficits_fixed=1,new_correct_Qfplib_deficits=0,remaining_state_rows=6,vs_parent=dict(change),regression_state_rows=7,regression_instruction_histogram=dict(delta),
    public_stack_bytes=640,parent_public_stack_same_corpus=640,bare_pack_stack_bytes=44,allocated_object_code_bytes_delta=16,linked_component_bytes_delta=16,
    no_new_tables_global_RAM_or_libgcc=True,inherited_near_Q77_and_shared_tables_byte_identical=True,M4_generic_M0_allocated_controls_equal=True,whole_public_and_bare_unit_rebuilds_byte_exact=True,
    historical_ln10_total_fixed=10,historical_ln10_remaining=0,source_sha256=source,candidate_ELF_sha256=elf,candidate_full_object_sha256=sha(W/'candidate-full.o'),parent_result_sha256=sha(BASE/'result.json'),
    independent_review='not_claimed',production_integration=False,hardware_accessed=False,physical_cycles_measured=False,goal_complete=False)
(W/'HANDOFF.md').write_text(f'''# Private main-ln ln2 sign gate

Child of frozen Q77 near packet. The Q70 ln2 constant rounds down;
for either exponent sign its magnitude error is negative. Only inside
the old uncertainty guard, n>0 and above-distance>=8exact/14raw can
therefore accept the existing upward RNE. Staticassert/table/source/
interval proof in PROOF.md and certificate.json. Other paths unchanged.

Fresh60494inputs/120988fullyprofiledstates/483952publicARM:0wrongMPFR4.2.2,
rawNaN/SIO/PCS/SP/boundedwrites pass, all118044parentcounts reproduce.
Exactsource bare12264ARM/6132configs/12264rationalRNEendpointchecks cover
all1023exponents, bothpackers/widths/signs/parities/carries; noFW/ROM/0SIO.
Qualified496216ARM total; inherited/preassertprobe calls not added.

Expanded4raw→3raw/6states,1fixed0new.5FFA5B2647E9E2C7 READY595/DIRTY655
vsparent2238/2333/Qfp776. Seven parentregressions retained:5+3,2+4;
vsparent2faster120979equal7slower. Stack640same, barepack44. Onlytwo
functionbodies+8each,object/linked+16B,no newtable/RAM/libgcc. Inherited
Q77near and allotherobject/table bytes exact; genericM0/M4allocated
controls same. WholeCPP/ASM/ELF andbareunit rebuildbyteexact. Preassert
8880stateprobe used identicalwholeELF/object; source/logs preserved,
freshfullqualification uses finalsource. Linkedaddresses relocate.

Source:{source}
ELF:{elf}
Object:{r['candidate_full_object_sha256']}

Freeze packet. Independentreview/integration/physicalcycles/HW/wholegoal
GO not claimed. Historicalauthor302/507 andreviewed298/507 unchanged;
threegeneral ln, otheroperations/generalpowtotality/fullgoal OPEN.
No canonical/Git/device actions.
''')
r['files']={str(p.relative_to(W)):sha(p) for p in sorted(W.rglob('*')) if p.is_file()}
(W/'result.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({k:v for k,v in r.items() if k!='files'},indent=2))
