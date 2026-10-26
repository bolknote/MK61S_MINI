"""Seal author packet; stdout must be redirected outside this directory."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,subprocess
W=Path(__file__).resolve().parent;ROOT=W.parents[1];P=ROOT/'.build/m0-pow-reciprocal-soft-20261025';S=ROOT/'.build/m0-ddiv-seed-lut-20261025';R=ROOT/'.build/m0-pow-reciprocal-soft-independent-20261025'
assert not(W/'FROZEN.json').exists()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
load=lambda p:json.loads(p.read_bytes())
q=load(W/'qualification.json');f=load(W/'new-qualification.json');d=load(W/'direct-proof.json');t=load(W/'summary.json');b=load(W/'build.json');proof=load(W/'source-proof.json');rebuild=load(W/'rebuild-proof.json')
elf=sha(W/'candidate.elf')
for x in [q,f,d,proof,b['images']['candidate']]:assert x.get('candidate_ELF_sha256',x.get('ELF_sha256'))==elf
assert t['strict_fixed_pairs']==9 and t['qualified_fresh_ARM_calls']==476133 and t['public_instruction_reduction_range']==[59,73]
assert len(rebuild['outputs'])==18
for p,h in rebuild['outputs'].items():assert sha(Path(p))==h
assert not subprocess.check_output(['git','diff','--','code/native_eabi_m0*'],cwd=ROOT)
external={}
def put(path,pin=None):
 p=Path(path);p=p if p.is_absolute()else ROOT/p
 data=p.read_bytes();value=dict(bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
 if pin:assert value=={k:pin[k]for k in value},p
 key=str(p.relative_to(ROOT))
 if key in external:assert external[key]==value
 external[key]=value
for p,pin in load(P/'source-lineage-pins.json')['files'].items():put(p,pin)
for base in [P,S]:
 for p,pin in load(base/'FROZEN.json')['files'].items():put(base/p,pin)
 put(base/'FROZEN.json')
review=load(R/'FINAL-REVIEW.json')
assert review['status']=='TECH_GO_PRIVATE_DIRTY_ROOT_RECIPROCAL_COMPONENT_ONLY'and review['component_review_complete']
assert sha(P/'FROZEN.json')in json.dumps(review)
for p,pin in load(R/'MANIFEST.json')['files'].items():put(R/p,pin)
put(R/'FINAL-REVIEW.json');put(R/'MANIFEST.json')
root_receipt=ROOT/'.build/m0-pow-reciprocal-soft-root-acceptance-20261025-001/RECEIPT.json';root_meta=None
if root_receipt.exists():
 rr=load(root_receipt);assert rr['status'].startswith('ACCEPTED_PRIVATE_')and sha(P/'FROZEN.json')in json.dumps(rr)
 for pin in rr['pins']:put(pin['path'],pin)
 put(root_receipt);root_meta=dict(path=str(root_receipt.relative_to(ROOT)),bytes=root_receipt.stat().st_size,sha256=sha(root_receipt))
(W/'source-lineage-pins.json').write_text(json.dumps(dict(status='VERIFIED_PARENT_SEED_REVIEW_AND_SOURCE_LINEAGE',files=external),indent=2)+'\n')
result=dict(status='FROZEN_AUTHOR_EXACT_SMALL_TABLE_SEED_CALLER_PENDING_REVIEW',source_parent=str(P.relative_to(ROOT)),source_parent_FROZEN_sha256=sha(P/'FROZEN.json'),
 parent_independent_review=dict(path=str((R/'FINAL-REVIEW.json').relative_to(ROOT)),sha256=sha(R/'FINAL-REVIEW.json'),status=review['status']),parent_ROOT_receipt=root_meta,
 seed_comparison_FROZEN_sha256=sha(S/'FROZEN.json'),candidate_ELF_sha256=elf,source_proof_sha256=sha(W/'source-proof.json'),numeric_proof_sha256=sha(W/'NUMERIC-PROOF.md'),
 same_corpus_pairs=120980,states=241960,reference_state_variants=279522,loss_pairs=[11386,11377],new_strict_fixes=9,new_raw_losses=0,candidate_wrong=0,
 accelerated_DIRTY_states=377,public_instruction_reduction_range=[59,73],parent_cost_increase_states=0,READY_instructions_unchanged=True,
 all_parent_return_bits_reciprocal_operands_and_common_RNE_code_identical=True,all_actual_public_cost_deltas_match_measured_seed_cost_deltas=True,
 exact_seed_function_bytes=56,exact_seed_table_bytes=256,exact_seed_total_bytes=312,parent_seed_bytes=194,seed_instruction_range=[20,27],parent_seed_instruction_range=[82,97],
 private_ddiv_allocation_bytes=[1050,1168],allocated_code_delta_bytes=118,new_mathematical_table_values=True,new_global_RAM_or_libgcc_dependencies=False,
 complete_divisor_domain_65536_and_all16_NZCV_table_edges_bare_qualified=True,selected_bare_tests=77840,selected_bare_qualified_ARM_calls=155680,other_variant_experimental_calls_excluded=233520,
 total_qualified_fresh_ARM_calls=476133,fresh_full_candidate_calls=241960,fresh_changed_parent_calls=377,fresh_public_MPFR_control_Qfplib_calls=61524,fresh_direct_operator_calls=16592,
 actual_directed_MPFR_inputs=6761,sNaN_policy_shortcuts=184,fresh_exact_dyadic_operator_oracle_inputs=256,failed_direct_preflight24_ARM3_MPFR_excluded=True,
 parent_qualification_pilot_and_old_seed66288_not_fresh=True,new_original153_pilot_not_run=True,
 all_direct_and_public_Qfplib_raw_output_cost_rows_retained=True,wrong_direct_Qfplib_variants_retained=936,wrong_public_Qfplib_variants_retained=77106,
 correct_Qfplib_comparison=q['correct_Qfplib_comparison'],no_nominal_reference_domain_filter=True,
 all10254_fresh_control_rows_match_full_records=True,all377_changed_paths_fresh_parent_replayed=True,
 DIRTY_all7_SIO_words_preserved_no_writes_seed_R1_R12_PCS_SP_PC_and_alignment_preserved=True,
 default_M0_M4_selected_controls_unchanged_and3_new_seed_disabled_objects_empty=True,eighteen_original_path_object_ELF_rebuilds_exact=True,
 full_observed_stack_bytes=2284,fresh_parent_control_candidate_stack_bytes=f['observed_stacks'],changed_parent388_is_subset_not_comparator=True,
 original_pow153_remaining=[34,34],author_separate507_no_slower=437,reviewed_separate507_no_slower=422,
 private_root_caller_only_other_ddiv_callers_unchanged=True,independent_review_pending=True,
 source_merge_actual_integrated_R12_loader_layout_14B_overlay_hazard_general_pow_totality_other_needed_math_physical_cycles_release_pending=True,
 canonical_runtime_M4_Git_device_USB_Flash_or_release_changed=False,goal_complete=False)
(W/'result.json').write_text(json.dumps(result,indent=2)+'\n')
(W/'HANDOFF.md').write_text('''# Exact small-table seed caller: author qualification complete

Same120980 pairs/241960states:11386->11377 loss pairs,9 new strict Qfplib
fixes,0wrong/0newloss/0parentcostincreases.377 DIRTY public states save59-73
instructions; READY costs unchanged. All377 changed paths were also freshly
parent-replayed. All10254 fresh controls match the full records. Every public
cost delta equals the measured bare seed delta, with no timing model for the
caller. All279522 reference-state variants, including77106 wrong Qfplib
outputs and costs, are retained without a nominal-domain filter.

Only the194B seed suffix changes, to56B instructions plus256B own integer
constants. It takes20-27 instructions instead of82-97. Total private code
allocation1050->1168B (+118B). All other allocated bytes/addresses, hardware
and software setup, common282B RNE tail, root BL, scratch4080 and other ddiv
callers are unchanged. The linked312B blob matches the tested bare image.
No new global RAM or libgcc dependencies. There are new mathematical table
values, explicitly256B. R3 is newly clobbered inside the private seed, but
the caller saves/restores it; R1/R12, PCS, SP/PC and SIO7words are preserved.

The own finite integer proof checks every65536<=D<=131071: the approximate
quotient differs from floor((2^32-1)/D) by[-1,3]; its exact signed residual
fits32 bits even across product wrap. At most3 downward or1 upward correction
restores the Euclidean invariant. No binary64 approximation bound changes.
The selected bare campaign has77840tests/155680 old+selected ARM calls with
all16 NZCV around table boundaries.233520 calls to the other three variants
are exploratory, excluded from selected qualification. Final selection uses
complete-domain worst latency, not the current public-corpus fit. A discarded
sample-only selection and the initial model choice remain in the frozen seed
comparison packet with explicit historical scope.

Total476133 fresh qualified ARM calls:155680 selectedbare,241960 full
candidate,377 changed parents,61524 fresh public controls/references and
16592 direct operator calls.6761 directed MPFR inputs plus184 sNaN policy
shortcuts;256 fresh exact dyadic operator inputs, plus the bare65536-divisor
integer model. Failed direct calibration24ARM/3MPFR is separately preserved
and excluded: the inherited test selected the original resident parent
symbol instead of its newer private alias. All raw direct Qfplib rows are
retained, including936 wrong variants. No fresh original153 pilot was run;
its score is recounted from the full records. Parent qualification/pilot and
original66288 seed calls are not added as fresh.18 exact source rebuilds pass.

Full observed stack remains2284B; fresh controls2148B each. The changed-path
parent388B is a subset, not a full comparison. Original153 stays119strict/
34slower; author separate507 remains437 and reviewed422. Parent reciprocal
now has independent TECH_GO211cf956. This new seed caller still needs its
own independent review. A ROOT parent receipt, when already present at seal,
is pinned in result.json; no parent or child acceptance is widened here.

This remains a private pow reciprocal component, not a global ddiv or C ABI
replacement. Production merge/relink and actual integrated R12/loader/layout
guards, the old168B-overlay/14B-table-entry hazard, general pow totality,
other needed math, physical cycles and release remain open. No M4/canonical/
Git/device/USB/Flash change or hardware/main/release GO. Historical producers
must never be executed inside these frozen directories. Goal stays active.
''')
(W/'progress.json').write_text(json.dumps(dict(status='AUTHOR_QUALIFICATION_COMPLETE_PENDING_REVIEW',completed_states=241960,total_states=241960),indent=2)+'\n')
scope=load(W/'WORK-SCOPE.json');scope.update(status='AUTHOR_QUALIFICATION_COMPLETE_PENDING_REVIEW',this_turn_classification='progress: exact20-27 instruction seed with256B table qualified,9 new strict Qfplib fixes,377 states59-73instructions faster; +118B allocation, IEEE/READY preserved',parent_review_pending=False)
(W/'WORK-SCOPE.json').write_text(json.dumps(scope,indent=2)+'\n')
files={str(p.relative_to(W)):dict(bytes=p.stat().st_size,sha256=sha(p))for p in sorted(W.rglob('*'))if p.is_file()and'__pycache__'not in p.parts}
(W/'FROZEN.json').write_text(json.dumps(dict(status='FROZEN_AUTHOR_COMPONENT_PENDING_INDEPENDENT_REVIEW',utc=datetime.now(timezone.utc).isoformat(),files=files,result_sha256=sha(W/'result.json'),HANDOFF_sha256=sha(W/'HANDOFF.md'),goal_complete=False),indent=2)+'\n')
print(json.dumps(dict(status='AUTHOR_COMPONENT_SEALED',local_files=len(files),external_pins=len(external),FROZEN_sha256=sha(W/'FROZEN.json'),result_sha256=sha(W/'result.json'),HANDOFF_sha256=sha(W/'HANDOFF.md'),candidate_ELF_sha256=elf,parent_ROOT_receipt=root_meta),indent=2))
