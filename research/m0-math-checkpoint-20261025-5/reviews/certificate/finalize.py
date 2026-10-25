"""Seal only completed own finite review evidence after every check passed."""
import hashlib,json,stat
from pathlib import Path
O=Path(__file__).resolve().parent;R=O.parents[1];W=R/'.build/m0-pow-reciprocal-certificate-20261025'
def ref(p):
 p=Path(p);b=p.read_bytes();return dict(path=str(p),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def put(n,d):
 with(O/n).open('x')as f:json.dump(d,f,indent=2);f.write('\n')
 return ref(O/n)
b,a,p,c,u,s,v=[json.loads((O/n).read_text())for n in ['binding.json','accounting.json','proof.json','closure.json','unit-arm.json','scalar-arm-mpfr.json','public-arm-mpfr.json']]
assert b['local80_external2402']and len(b['own12_rebuilds_byte_exact'])==12
assert u['actual_ARM_calls']+s['actual_ARM_calls']+v['actual_ARM_calls']==5592
assert s['directed_MPFR_inputs']+v['directed_MPFR_inputs']==61 and s['sNaN_shortcuts']+v['sNaN_shortcuts']==6
assert len(a['strict_fixes'])==len(a['equality_fixes_not_strict'])==1 and len(a['two_already_losing_correctQfp_states_further_slowed'])==2
assert c['own_numerical_failed_partial_discarded_calls']==0 and len(list(O.glob('HOST-PREFLIGHT-*.json')))==4
assert not list(O.glob('RUNTIME-FAILURE-*.json'))
requirements=put('INTEGRATION-REQUIREMENTS.json',dict(status='MANDATORY_BEFORE_ANY_SOURCE_MERGED_OR_PERFORMANCE_ADOPTION_DECISION',
 exact_supplier=b['refs']['FROZEN'],parent=b['refs']['parent_FROZEN'],
 private_entry='HIDDEN mk61_m0_reciprocal1: R0=0,R1=0x3ff00000, denominator R2:R3 any binary64. Sole reviewed root caller only; not generic ddiv or one-argument C ABI.',
 private_continuation='20B original callee frame/raw operands/guarded R6/R12 sign+exponent. Inline seed ownentrySP-20 and preserved R0/R2/R3/R5/R12. Preserve current PCS, SP/PC and DIRTY7 words.',
 certificate='Exact E in[0,131071]. Accept only (A&0x7fffffff)>=131072. Both inclusive discontinuity bands use complete original product/borrow/CMP; no zero/INTMIN shortcut. R0/R1/R12/SP live; no missing limb or flag may leak into RNE.',
 zero_shift='Only proven positive-one dataflow: R0=0 through both products, R4=R0<<5=0 and both normalization branches preserve it; flags reset before any consumer.',
 READY='Retain nine independent ALU instructions between divider issue and quotient read; instruction count is not a physical cycle measurement.',
 performance='Explicit tradeoff:32 public +7/+8 states, including two already-losing correct-Qfp states that worsen, and1132 scalar parent increases. 1 strict plus1 equality pair fix. No universal speed or automatic adoption GO.',
 source_merge='Near-one exp is a separate sibling. Merge source and relink, then inspect/test the actual combined ELF; no binary overlay substitution or inherited integration verdict.',
 shared_R12='Fresh actual integrated linked consumer/veneer/entry R12 guards and loader/layout verification are mandatory. Unit/private ELF evidence cannot satisfy this.',
 loader_layout='The old168B exp overlay overwrites14 bytes of the newer table-product entry. Preserve current whole-bank loader ordering; validate actual integrated bytes/addresses/relocations and free Flash.',
 limits='General pow totality, other functions, physical device cycles, hardware qualification, main/release and next known-zero optimization are outside this review.',
 reviewed507=422,author438_not_promoted=True,integration_GO=False,performance_adoption_GO=False,hardware_GO=False,main_GO=False,release_GO=False))
files={str(f.relative_to(O)):ref(f)for f in sorted(O.rglob('*'))if f.is_file()and f.name not in ['FINAL-REVIEW.json','MANIFEST.json','VALIDATION.json']}
manifest=put('MANIFEST.json',dict(status='IMMUTABLE_COMPLETED_PRIVATE_EXACT_REMAINDER_CERTIFICATE_REVIEW_EVIDENCE',file_count=len(files),files=files,
 no_running_processes_or_open_logs=True,all_outputs_own_directory=True,device_IO=0,Git=0,canonical=0,network=0))
final=put('FINAL-REVIEW.json',dict(status='TECH_GO_PRIVATE_EXACT_REMAINDER_SIGN_CERTIFICATE_COMPONENT_ONLY_WITH_RETAINED_TRADEOFF',component_review_complete=True,
 exact_supplier={k:b['refs'][k]for k in ['FROZEN','result','HANDOFF','ELF','unit_FROZEN','corrigendum']},
 actual_parent=dict(FROZEN=b['refs']['parent_FROZEN'],independent=b['refs']['parent_independent'],later_ROOT_additive=c['parentROOT_later_additive'],child_seal_pending_review_ROOT_metadata_not_rewritten=True,near_one_separate_sibling=True),
 new_child_acceptance_not_inherited_parent_GO=True,
 integrity=dict(frozen_local_files=80,external_lineage_pins=2402,unit_files=b['unit_file_count'],own_qualified_byteexact_rebuilds=12,
  exact_patch_and_marker_only_control=True,only_ddiv_allocated_bytes_changed=True,all_other_resident_addresses_calls_and_semantic_relocations_unchanged=True,
  shared_macro_source_in_unit_HW_SW=True,actual_unit_r2_sources_binaries_unchanged_only_R1_assertion_added=True),
 universal_integer_proof=dict(whole_uint32_B_u_v=True,error_E=[0,131071],accept='(A&0x7fffffff)>=131072',
  full_uncertain_bands=[[0,131071],[2147483648,2147614719]],zero_and_INTMIN_use_original_complete_product=True,
  exact_NEGS_low_borrow_SBCS_high_and_modular_restore=True,all32768_classifier_buckets_and_interval_endpoints_checked=True,
  source_emitted12B_nonbranch_prefix_identical_all3=True,eight_instruction16B_macro_decoded_targets=True,
  full42B_product_core_and30B_round_pack_byteequal=True,known_zero_shift_only_private_positive_one_proven=True),
 fresh_private_call_liveness=dict(actual_sole_root_BL=c['actual_linked_sole_root_BL'],
  no_intermediate_entry_label_or_non_one_numerator=True,guarded_R6_raw_operands_R12_frame20_and_PCS_checked=True,
  missing_product_limbs_and_old_flags_dead_before_RNE=True,actual_downstream_quotient_sign_exponent_SP_joins_match=True,
  shared_inline_table_and_ownentrySPminus20_preserved=True,READY9ALU_DIRTY7word_semantics_preserved=True,
  hidden_private_no_general_or_C_ABI_claim=True),
 independent_CPU_checks=dict(actual_Thumb_calls_in_Unicorn=5592,bare_tests1952_calls3904=True,scalar184flagjobs49D_calls1472=True,public18pairs_calls216=True,
  directed_MPFR_invocations=61,sNaN_policy_shortcuts=6,MPFR_version='4.2.2',
  all16_flags_inclusive_sign_bands_zero_INTMIN_wrap_borrow_and_full_path=True,all8_private_decision_classes_actually_executed=True,
  production_certificates=324,original_fallback_restorations=134,pre_certificate_and_zero_yL_complete_contexts=324,after_second_complete_contexts=332,
  actual_inline_ownentrySPminus20_contexts=164,nested_pow_contexts=8,READY9ALU_issue_read_checks=164,original_frame_entry_POP_checks=384,actual_public_root_returns=16,
  scalar_plus7_64_plus8_64_retained=True,remaining_DIRTY149vs146_actually_reproduced=True,
  strict_pair_equality_pair_and_two_already_losing_public_regressions_reproduced=True,
  no_full673814_or241960_corpus_execution_repeat=True,own_failed_partial_discarded_numerical_calls=0),
 independent_saved_public_recount=dict(pairs=120980,states=241960,reference_state_variants=279522,loss_pairs=[11371,11369],strict_fixes=a['strict_fixes'],equality_fixes_not_strict=a['equality_fixes_not_strict'],
  wrong_Qfplib_variants_retained=77106,no_nominal_filter=True,new_loss_pairs=0,candidate_wrong=0,faster_states=354,faster_READY177_DIRTY177=True,faster_instruction_range=[12,15],
  parent_cost_increases=32,increase_histogram={7:6,8:26},two_increases_worsen_existing_correct_Qfp_losses=a['two_already_losing_correctQfp_states_further_slowed'],
  other30_increases_have_no_correct_Qfp=True,original_overbroad_HANDOFF_claim_corrected_by_bound_additive_corrigendum=True,
  all10254_fresh_overlaps_equal=True,all_saved_certificate_arithmetic_branches_costs_recounted=True,
  actual_parent_replays778_include392_unchanged_and386_changed=True,original153=a['original153'],zero_new_loss_does_not_mean_no_performance_regression=True),
 independent_saved_scalar_recount=dict(cases=20994,states=41988,correct_Qfp=a['scalar_correct_Qfp'],wrong_Qfp_variants_retained=9600,
  parent_increases=1132,increase_histogram={7:286,8:846},all_correct_wrong_outputs_costs_and_increases_kept=True,remaining_DIRTY_denominator='3FF27D0DF6735E90',candidate149_Qfp146=True,
  five_equal_states_not_strict_wins=True,no_new_correct_Qfp_deficit_in_saved_corpus=True,no_universal_parent_or_Qfp_speed_claim=True),
 honest_evidence_counts=dict(author_qualified_ARM=673814,author_partition=[241960,778,61524,167952,201600],author_directed_MPFR=26011,author_sNaN_shortcuts=110,
  author_two_HOST_preflights0excluded=True,parent_campaigns_not_fresh=True,shared_unit100800paired_tests201600calls_not_new_from_copy=True,
  own_HOST_preflights4_zero_ARM_MPFR_retained=True,ten_successful_rebuild_outputs_reused_without_rerun_after_basename_fix=True,extra_failed_unit_whole_file_link_retained_not_qualified=True),
 resources=dict(private_allocation=[1072,1108],delta_bytes=36,same256B_table=True,new_table_values_RAM_libgcc=False,default_M0_M4_selected_and6_disabled_unchanged=True,
  author_observed_full_stack2284_controls2148_scalar176_unchanged=True,own_observed_scalar176_public968_parent_control_candidate_equal=True,no_universal_stack_bound=True,
  own_free_Flash_below2MiB_and_no_overlaps_checked=True),
 limits=dict(component_only=True,performance_adoption_GO=False,near_one_separate_sibling=True,reviewed507_stays422=True,author438_not_promoted=True,
  actual_source_merge_relink_shared_R12_loader_layout_and_old168overlay14B_guard_required=True,general_pow_totality=False,physical_cycles=False,
  integration_GO=False,hardware_GO=False,main_GO=False,release_GO=False,overall_goal_complete=False,next_known_zero_study_excluded=True),
 requirements=requirements,evidence_manifest=manifest,evidence={n:ref(O/n)for n in ['binding.json','proof.json','accounting.json','unit-arm.json','scalar-arm-mpfr.json','public-arm-mpfr.json','closure.json','NOTES.md']},
 scope=dict(CPU_HOST_only=True,devices=0,USB=0,ports=0,Flash=0,network=0,install=0,Git=0,canonical=0,product_source_edits=0,own_outputs_only=True)))
for x in files.values():
 actual=ref(x['path']);assert actual==x,x['path']
assert json.loads((O/'FINAL-REVIEW.json').read_text())['evidence_manifest']==ref(O/'MANIFEST.json')
validation=put('VALIDATION.json',dict(status='PASS_FINAL_RECEIPT_MANIFEST_ALL_LIVE_CONTEXTS_AND_RETAINED_PUBLIC_SCALAR_REGRESSIONS',
 final_review=final,manifest=manifest,verified_manifest_files=len(files),qualified_ARM5592_MPFR61_plus6sNaN=True,own_HOST_preflights4_numerical_failures0=True,
 all32_public_and1132_scalar_increases_kept_with_two_existing_Qfp_deficits_worsened=True,no_required_finite_review_work_remaining=True,integration_hardware_main_release_adoption_all_false=True,device_IO=0))
for f in O.rglob('*'):
 if f.is_file():f.chmod(stat.S_IRUSR|stat.S_IRGRP|stat.S_IROTH)
print(json.dumps(dict(final=final,manifest=manifest,requirements=requirements,validation=validation)),flush=True)
