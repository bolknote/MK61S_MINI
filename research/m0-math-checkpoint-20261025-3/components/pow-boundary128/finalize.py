"""Seal completed exact-boundary evidence; invoke with stdout outside this folder."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,subprocess,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1];BASE=ROOT/'.build/m0-pow-square128-r2-20261025'
assert not (W/'FROZEN.json').exists()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
s=json.loads((W/'summary.json').read_bytes());p=json.loads((W/'source-proof.json').read_bytes())
q=json.loads((W/'qualification.json').read_bytes());fresh=json.loads((W/'new-qualification.json').read_bytes())
assert s['candidate_wrong']==s['new_raw_losses']==s['parent_cost_increase_states']==0
assert s['accelerated_states']==454 and s['total_qualified_fresh_ARM_calls']==309938
assert sha(W/'candidate.elf')==q['candidate_ELF_sha256']==fresh['candidate_ELF_sha256']
assert q['record_sha256']==sha(W/'qualification-records.jsonl.gz')
assert json.loads((W/'rebuild-proof.json').read_bytes())['status'].startswith('PASS_SEVENTEEN')
external={}
def pin(path,expected=None):
 path=Path(path);name=str(path.relative_to(ROOT));v=dict(bytes=path.stat().st_size,sha256=sha(path))
 if expected:assert v=={k:expected[k]for k in ['bytes','sha256']},name
 if name in external:assert external[name]==v
 external[name]=v
for name,value in json.loads((BASE/'FROZEN.json').read_bytes())['files'].items():pin(BASE/name,value)
for name,value in json.loads((BASE/'source-lineage-pins.json').read_bytes())['files'].items():pin(ROOT/name,value)
pin(BASE/'FROZEN.json')
review_dir=ROOT/'.build/m0-pow-square128-independent-20261025'
review=json.loads((review_dir/'FINAL-REVIEW.json').read_bytes())
assert review['status']=='TECH_GO_PRIVATE_EXACT_SQUARE128_COMPONENT_ONLY'
assert review['findings']==review['blocking_component_findings']==[]
for value in review['accepted_frozen_target'].values():pin(value['path'],value)
for name,value in json.loads((review_dir/'MANIFEST.json').read_bytes())['files'].items():pin(value.get('path',review_dir/name),value)
pin(review_dir/'MANIFEST.json')
pin(ROOT/'.build/m0-pow-square128-r2-postseal-20261025.json')
rejected=ROOT/'.build/m0-pow-bound80-20261025'
pilot=json.loads((rejected/'probe.json').read_bytes());precision=json.loads((rejected/'required-precision.json').read_bytes())
assert pilot['boundary_calls']==pilot['fallback_calls']==56 and not pilot['fixed_pairs']
rejection=dict(status='REJECTED_AS_INSUFFICIENT_PRECISION_AND_SLOWER_PUBLIC_PATH',
 candidate_ELF_sha256=sha(rejected/'candidate.elf'),bare_ARM_calls=19221,pilot_ARM_calls=1836,pilot_MPFR_inputs=153,
 candidate_wrong_in_pilot=0,all56_public_boundary_calls_fell_back=True,
 public_instruction_increase_range=[min(int(k)for k in pilot['cost_delta_histogram']if int(k)>0),max(map(int,pilot['cost_delta_histogram']))],
 exact_relative_gap_bits_histogram=precision['relative_gap_bits_histogram'],
 ideal96_model_decisions=precision['ideal_exact_truncation_filter_decisions']['96'],
 full_corpus_not_run=True,all_calls_excluded_from_qualified_boundary128_totals=True,
 no_canonical_or_device_changes=True)
with (rejected/'REJECTED.json').open('x')as f:json.dump(rejection,f,indent=2);f.write('\n')
for name in ['REJECTED.json','filter.cpp','kernels.S','probe.json','unit-proof.json','required-precision.json','candidate.elf']:pin(rejected/name)
(W/'source-lineage-pins.json').write_text(json.dumps(dict(status='VERIFIED_EXECUTION_ACCEPTED_SQUARE_PARENT_AND_REJECTED_TRIAL_LINEAGE',files=external),indent=2)+'\n')
scope=dict(status='QUALIFIED_EXACT_BOUNDARY128_COMPONENT_PENDING_INDEPENDENT_REVIEW',
 previous_goal_turn_classification='progress: qualified square128 full corpus and frozen author component; it now has independent TECH_GOeaa55a85',
 this_turn_classification='progress: rejected80bitfilter from real evidence, measured97..108bit gaps, implemented exact128boundary reuse, qualified454faster states and reduced bare frame212->156',
 HEAD=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
 canonical_runtime_changed=False,M4_changed=False,device_or_Flash_accessed=False,
 integration_hardware_or_release_GO=False,goal_complete=False)
assert not subprocess.check_output(['git','diff','--','code/native_eabi_m0*'],cwd=ROOT)
(W/'WORK-SCOPE.json').write_text(json.dumps(scope,indent=2)+'\n')
result=dict(status='FROZEN_AUTHOR_EXACT_BOUNDARY128_REUSE_COMPONENT_PENDING_REVIEW',
 source_parent=str(BASE.relative_to(ROOT)),source_parent_FROZEN_sha256=sha(BASE/'FROZEN.json'),
 parent_independent_review=dict(status=review['status'],path=str((review_dir/'FINAL-REVIEW.json').relative_to(ROOT)),sha256=sha(review_dir/'FINAL-REVIEW.json')),
 candidate_ELF_sha256=sha(W/'candidate.elf'),source_CPP_sha256=sha(W/'boundary.cpp'),source_proof_sha256=sha(W/'source-proof.json'),numeric_proof_sha256=sha(W/'NUMERIC-PROOF.md'),
 unique_pairs=120980,profiled_states=241960,reference_state_variants=279522,
 same_corpus_loss_pairs=[11434,11434],new_raw_losses=0,candidate_wrong=0,
 accelerated_public_states=454,public_instruction_reduction_range=[4,169],parent_cost_increase_states=0,
 all_parent_raw_bits_and_all24_midpoint_operand_bytes_identical=True,
 fresh_parent_replayed_on_every_changed_path=True,
 new_diagnostic_allocated_code_and_literals_bytes=p['added_diagnostic_body_bytes'],retained_resident_slot_bytes=532,
 new_tables_global_RAM_libgcc_or_ROM_math_dependencies=False,
 observed_bare_boundary_call_stack_bytes=[212,156],old_full_corpus_candidate_stack_bytes=2284,
 fresh_controls_parent_control_candidate_stack_bytes=fresh['observed_stacks'],
 unchanged_other_RP_code_tables_addresses_veneers_and_scratch_reservation=True,
 default_M0_M4_selected_source_controls_equal_and_extra_CPP_empty=True,
 seventeen_complete_source_object_ELF_rebuilds_byte_exact=True,
 total_qualified_fresh_ARM_calls=309938,fresh_full_candidate_calls=241960,fresh_full_changed_path_parent_calls=454,
 fresh_directed_MPFR_control_public_calls=61524,fresh_bare_calls=6000,
 actual_directed_MPFR_inputs=5051,sNaN_policy_shortcuts=76,oracle_evaluations=5127,
 all_fresh_control_rows_match_full_corpus_records=True,
 pilot1836_preflight0_and_all_rejected80bit_calls_excluded=True,
 inherited_old_parent_Qfplib_MPFR_not_fresh=True,
 correct_Qfplib_comparison=s['correct_Qfplib_comparison'],wrong_Qfplib_reference_variants_retained=77106,
 strict_quiet_NaN_reference_policy_and_no_nominal_domain_filter=True,
 original_pow153_remaining=[34,34],original_candidate_strict=119,
 author_original507_separate_union=dict(no_slower=437,strict=431,equal=6,remaining=70,remaining_by_operation=dict(pow=34,sin=22,cos=14),not_one_integrated_binary=True),
 reviewed_original507_stays422_per_ROOT=True,
 independent_review_pending=True,general_pow_totality_remaining_math_source_merge_R12_loader_layout_cycles_release_pending=True,
 no_canonical_Git_device_USB_Flash_or_release_changes=True,goal_complete=False)
(W/'result.json').write_text(json.dumps(result,indent=2)+'\n')
handoff=f'''# Exact midpoint boundary: author qualification complete, independent review pending

Parent `{BASE.relative_to(ROOT)}`, FROZEN31de9242, now has independent square
TECH_GO `{sha(review_dir/'FINAL-REVIEW.json')}`. That verdict is limited to the
square kernel and is not acceptance of this new caller. Candidate ELF
`{result['candidate_ELF_sha256']}`, source CPP `{result['source_CPP_sha256']}`.

The old inline128-bit midpoint square is replaced by a loop using the accepted
scheduled square kernel. All24 midpoint bytes and radius16/comparison rules
are identical. No precision reduction. The complete120980-pair/241960-state/
279522-reference-variant corpus freshly executes the candidate. Every one of454
changed states also freshly executes the parent, matching all24 midpoint bytes
and saved parent costs.454states save4–169instructions,0increases/0wrong/0new.
Loss pairs remain11434; original153 deficits remain34,119strict. This reduces
the gap but adds no new Qfplib victories. Author separate507 remains437=431strict
+6equal with70remaining(pow34/sin22/cos14); reviewed507 remains422 per ROOT.

Fresh5127-pair controls execute parent/control/candidate/all3Qfplib compositions:
61524ARM calls,5051 directedMPFR inputs plus76sNaN shortcuts. All10254state rows
match the full saved corpus. Wrong77106reference variants/costs retained with
strictquietNaN policy, no nominal filtering. Qualified309938freshARM=
241960candidate+454changed-path parent+61524freshcontrols+6000bare. Pilot1836,
failed preflight0, all rejected80trial calls and inherited oracle/reference
calls are not pooled into those totals.

Bare3000cases/6000actualARM use only actual code, no firmware/ROM/math models.
All16NZCV/noisyR3R12, ordinary PCS/SP/PC, bounded writes and exact dyadic interval
endpoints pass. Every side and midpoint byte matches old. Observed bare peak
212→156B. Overall candidate corpus peak2284unchanged; changed-path parent716
is a subset and is not a comparator for that full peak. Fresh control peaks
parent/control/candidate2148equal. Seventeen full objects/ELFs rebuilt byteexact.

Only the532B front slot changes; its two-instruction8B tail entry preserves
R0-R2/LR/SP/stack cell. New diagnostic body+literal228B, no new table/globalRAM/
libgcc/ROM-math dependency. Others' resident code, addresses, veneers, scratch
and tables unchanged. GenericM0/M4soft/M4hard selected assembly is equal;
guarded extraCPP is empty outsideRP2040. This is not a whole M4 firmware build.

The80bit filter remains explicitly rejected: all56public checks declined,
adding262–904instructions. Exact gaps require97–108 relative bits; an ideal96bit
filter also declined. Its19221bare+1836pilot ARM and153pilotMPFR are excluded.

No canonical source, Git, USB/device/Flash, hardware lease or release changes.
Near-one exp remains a separate accepted sibling. Generalpowtotality, remaining
math, source merge/relink, actual integrated R12/loader/layout guards, physical
cycles and release are open. Overall goal incomplete. Next investigation:
measure the actual1/hint double-division and32bitseed costs in READY/DIRTY before
designing a certified specialized reciprocal path; preserve correctly rounded
hint bits or all original boundary-selection invariants.
'''
(W/'HANDOFF.md').write_text(handoff)
(W/'progress.json').write_text(json.dumps(dict(status='FROZEN_AUTHOR_COMPONENT_PENDING_REVIEW',completed_states=241960,accelerated_states=454,goal_complete=False),indent=2)+'\n')
files={str(path.relative_to(W)):dict(bytes=path.stat().st_size,sha256=sha(path))for path in sorted(W.rglob('*'))if path.is_file()and'__pycache__'not in path.parts}
frozen=dict(status='FROZEN_QUALIFIED_PRIVATE_EXACT_BOUNDARY128_COMPONENT',utc=datetime.now(timezone.utc).isoformat(),files=files,
 result_sha256=sha(W/'result.json'),HANDOFF_sha256=sha(W/'HANDOFF.md'),HEAD_at_seal=scope['HEAD'],goal_complete=False)
(W/'FROZEN.json').write_text(json.dumps(frozen,indent=2)+'\n')
print(json.dumps(dict(directory=str(W.relative_to(ROOT)),FROZEN_sha256=sha(W/'FROZEN.json'),result_sha256=sha(W/'result.json'),HANDOFF_sha256=sha(W/'HANDOFF.md'),local_pins=len(files),external_pins=len(external)),indent=2))
