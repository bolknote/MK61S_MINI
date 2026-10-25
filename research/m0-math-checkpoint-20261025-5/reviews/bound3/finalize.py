"""Seal finite Bound3 correctness evidence, excluding all performance adoption."""
import hashlib,json,stat
from pathlib import Path
O=Path(__file__).resolve().parent
def ref(p):
 p=Path(p);b=p.read_bytes();return dict(path=str(p),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def put(n,j):
 with(O/n).open('x')as f:json.dump(j,f,indent=2);f.write('\n')
 return ref(O/n)
b,p,a,c,ua=[json.loads((O/n).read_text())for n in ['binding.json','proof.json','accounting.json','closure.json','unit-accounting.json']]
cpu=[json.loads((O/n).read_text())for n in ['unit-arm.json','scalar-arm-mpfr.json','public-arm-mpfr.json']]
assert len(b['own12_byteexact_rebuilds'])==12 and sum(j['actual_ARM_calls']for j in cpu)==2908
assert sum(j.get('directed_MPFR_inputs',0)for j in cpu)==62 and sum(j.get('sNaN_shortcuts',0)for j in cpu)==6
assert len(list(O.glob('HOST-PREFLIGHT-*')))==2 and not list(O.glob('RUNTIME-FAILURE-*'))
req=put('INTEGRATION-REQUIREMENTS.json',dict(status='MANDATORY_PRIVATE_SEED_AND_PHYSICAL_TIMING_LIMITS',exact_supplier=b['refs']['FROZEN'],parent=b['refs']['parent_FROZEN'],
 private_entry='Positive numerator1 only: R0=0,R1=3ff00000; any binary64 divisor R2:R3. Sole actual root caller. NEW inline seed requires rawR0=0; not generic ddiv or C seed ABI.',
 integer_seed='Exact existing128-entry table, D65536..131071 and initial error[-1,3]. First BPL exits error1; immediate second ADD carry distinguishes error2/3; SBC q,R0 must see zero and fresh carry.',
 R7='Only error3 yields old_residue-D modulo2^32. No exact remainder guarantee. R7 must remain dead before second-product overwrite under actual Zero scratch/R3 certificate; all full downstream registers/NZCV/frame28 must rejoin.',
 PCS_SIO='Original20B saved frame/raw operands/guarded R6/R12 sign+exponent; inline ownentrySP-20; READY9ALU gap and all7 DIRTY words/no writes unchanged.',
 timing='Error1 changes branch direction. Zero instruction increases does NOT imply cycle nonregression; keep exact old-loop control and measure actual physical timing before any performance-adoption conclusion.',
 ancestry='All32 Certificate regressions vsInline remain (26×+6,6×+5), including2 already-losing correctQfp states. Existing corrigendum and adoptionfalse stay binding.',
 integration='Near-one is separate. Source merge/relink and fresh actual integrated sharedR12/consumer/veneer/loader/layout guards; old168B overlay overwrites14B of new table entry. Do not combine binary overlays mechanically.',
 limits='Finite two-pattern scalar scans are not universal speed/totality or physical cycles. General pow totality, other math, hardware, main/release and further micro-optimizations outside.',
 reviewed507=422,author438_not_promoted=True,integration_GO=False,physical_cycles_GO=False,performance_adoption_GO=False,hardware_GO=False,main_GO=False,release_GO=False))
files={str(f.relative_to(O)):ref(f)for f in sorted(O.rglob('*'))if f.is_file()and f.name not in ['FINAL-REVIEW.json','MANIFEST.json','VALIDATION.json']}
manifest=put('MANIFEST.json',dict(status='IMMUTABLE_COMPLETED_PRIVATE_BOUND3_CORRECTNESS_REVIEW',file_count=len(files),files=files,no_running_processes_or_open_logs=True,own_outputs_only=True,devices=0,network=0,Git=0,canonical=0))
final=put('FINAL-REVIEW.json',dict(status='TECH_GO_PRIVATE_BOUND3_EXACT_SEED_CORRECTNESS_COMPONENT_ONLY_CYCLES_UNMEASURED',component_review_complete=True,
 exact_supplier={k:b['refs'][k]for k in ['FROZEN','result','HANDOFF','ELF','unit_FROZEN']},
 actual_parent=dict(FROZEN=b['refs']['parent_FROZEN'],independent=b['refs']['parent_independent'],later_ROOT_additive=c['later_parentROOT_additive'],child_missing_ROOT_at_seal_not_rewritten=True,correctness_only_performance_adoption_false=True,near_one_is_sibling=True),
 new_child_correctness_NOT_inherited_parent_GO=True,
 integrity=dict(local_pins84=True,external_pins2742=True,unit_files=b['unit_files'],own_byteexact_whole_rebuilds=12,only_software_macro_changed=True,
  entire_hardware_source_and_resident_calls_unchanged=True,all_other_allocated_sections_addresses_semanticrelocs_unchanged=True,
  unit_production_shared_macro_except_decoded_ADR=True,all128table_constants_256B_unchanged=True,defaultM0_M4_and6disabled_unchanged=True),
 independent_whole_domain_integer_proof=dict(actual_D=65536,range=[65536,131071],exact_uint32_ASR_table_model=True,initial_error_histogram=p['error_histogram'],
  exact_floor_quotient_everyD=True,k1_BPL_afterfirst_ADD=True,k2_secondADDcarry1_SBCsubtract0=True,k3_secondADDcarry0_SBCsubtract1=True,
  true_negative_residual_signed_safe_no_overflow=True,new_R0zero_precondition_freshly_bound_not_generic_contract=True,
  error3_only_R7_old_residue_minusD_modulo32_no_exact_remainder_claim=True,post_ADD1_LSR_flags_and_u0_identical=True,
  R7_no_use_until_first_second_product_overwrite=True,all_full_after_product_residual_R3certificate_pack_live_states_equal=True,
  decoded_mapping=p['mapping']),
 independent_CPU_checks=dict(qualified_actual_Thumb_calls=2908,unit240cases480calls15D_all16flags=True,scalar272flagjobs47D2176calls=True,nestedpublic21pairs252calls_all3realQfp=True,
  directed_MPFR_invocations=62,sNaN_shortcuts=6,MPFR_version='4.2.2',all5errorclasses_allflags_and_actual_ADDC_SBC_R0zero_checked=True,
  full_context_counts=c['counts'],allowed_R7differences58_then_full_live_state_rejoin=True,
  actual_positive_one_caller_return_originalframe20_PCS_R6guard_R12_inline_ownSP_READY9ALU_DIRTY7words=True,
  both_old_expanded149_147vs146_now146_144vs146_actually_reproduced=True,
  old_new_control_roles_explicit=True,own_numerical_failed_partial_discarded_calls=0,own2HOSTpreflights0ARM0MPFR_retained=True,
  no_2M_3M_241960_262144_ARM_replay=True),
 independent_saved_unit_recount=dict(all65536rows_all16flags1048576tests=True,author_paired_ARM2097152=True,
  exact_all_quotient_residue_and_cost_vectors_match_independent_integer_proof=True,saved_signed_residual_normalized_modulo32_explicit=True,
  delta_histogram=ua['delta_histogram'],error1_branch_direction_changes_in564032_saved_flag_tests_NOT_cycles=True),
 independent_saved_public_recount=dict(pairs=120980,states=241960,reference_variants=279522,wrongQfp77106_retained=True,no_nominal_filter=True,
  loss_pairs=[11369,11369],no_new_pair_fix=True,delta=a['public_delta'],correctQfp=a['correctQfp'],faster10states_save3_only_error3=True,
  no_newloss_wrong_or_parent_instruction_increase=True,all10254fresh_overlap=True,parent778replays_include768unchanged10changed=True,original153=a['original153']),
 independent_saved_scalar_recount=dict(same20994cases41988states=True,correctQfp=a['scalar_comparison'],wrong9600_retained=True,same_delta=a['scalar_delta'],
  expanded131072inputs262144states_all65536actualD_two_patterns=True,expanded_correctQfp=a['expanded_comparison'],expanded_delta=a['expanded_delta'],
  old_expanded2losses_to0_finite_NOT_allbinary64_or_cycles=True,newloss_or_instruction_increase=0),
 cumulative_tradeoff=dict(ancestral32_Certificate_regressions_vsInline_remain_hist=a['ancestral32_regressions_still_worse_than_Inline_hist'],two_already_losing_Qfp_states=a['ancestral2_already_losing'],corrigendum_and_prior_adoption_false_still_binding=True),
 honest_evidence_accounting=dict(author3355798_ARM_additive_partition=a['additive_fresh_author3355798_partition'],author157083MPFR_plus110sNaN=True,overlapping_campaigns_NOT_unique_union=True,
  rejected_author_trace14184completed_ARM1106MPFR76sNaN_0partial_excluded=True,corrected_only_parent_control_False_and_defaultTrue_oldnew_semantics_unchanged=True,
  only_terminal_publiccontrol_repeat_counted_not_double_full_expanded=True,parent_campaigns_not_fresh=True,own_HOST_representation_and_syntax_failures_retained=True),
 physical_timing_and_adoption=dict(instruction_nonincrease_NOT_cycle_nonregression=True,error1_taken_branch_direction_changed=True,old_loop_control_retained=True,physical_cycles_unmeasured=True,performance_adoption_GO=False),
 resources=dict(allocation=[1100,1108],delta=8,same256B_table=True,new_RAM_libgcc_external_calls=False,
  author_full2284_public2148_same_scalar176_unchanged=True,expanded_normal28_different_corpus_not_stackdrop=True,own_scalar176_public968_equal_across_versions=True,no_universal_stack_bound=True,
  freeFlash_below2MiB_nooverlap_checked=True),
 limits=dict(component_correctness_only=True,reviewed507_stays422=True,author438_not_promoted=True,near_one_separate_sibling=True,
  source_merge_relink_actual_R12_loader_layout_old168overlay14B_guard_required=True,general_pow_totality=False,other_math=False,
  physical_cycles=False,integration_GO=False,performance_adoption_GO=False,hardware_GO=False,main_GO=False,release_GO=False,overall_goal_complete=False,no_new_microoptimization_scope=True),
 requirements=req,evidence_manifest=manifest,evidence={n:ref(O/n)for n in ['binding.json','proof.json','integer-domain.json','unit-accounting.json','accounting.json','unit-arm.json','scalar-arm-mpfr.json','public-arm-mpfr.json','closure.json','runtime-base-binding.json','NOTES.md']},
 scope=dict(CPU_HOST_only=True,devices=0,USB=0,ports=0,Flash=0,network=0,install=0,Git=0,canonical=0,product_source_edits=0,own_outputs_only=True)))
for x in files.values():assert ref(x['path'])==x
assert json.loads((O/'FINAL-REVIEW.json').read_text())['evidence_manifest']==ref(O/'MANIFEST.json')
validation=put('VALIDATION.json',dict(status='PASS_FINAL_RECEIPT_MANIFEST_ALL_QUOTIENT_LIVENESS_AND_HONEST_CYCLE_LIMITS',final_review=final,manifest=manifest,verified_manifest_files=len(files),
 own_ARM2908_MPFR62_plus6sNaN=True,own2HOSTpreflights_numerical_failures0=True,rejected_author_calls_excluded=True,
 all_ancestral_tradeoffs_and_error1_branch_cycle_uncertainty_preserved=True,no_required_finite_review_work_remaining=True,integration_adoption_hardware_main_release_all_false=True,devices=0))
for f in O.rglob('*'):
 if f.is_file():f.chmod(stat.S_IRUSR|stat.S_IRGRP|stat.S_IROTH)
print(json.dumps(dict(final=final,manifest=manifest,requirements=req,validation=validation)),flush=True)
