"""Seal completed independent artifacts; no further numerical execution."""
import hashlib,json
from pathlib import Path
R=Path('/Users/bolk/Projects/MK61S_MINI');O=Path(__file__).resolve().parent;W=R/'.build/m0-pow-boundary128-20261025'
def ref(p):
 p=Path(p);b=p.read_bytes();return dict(path=str(p),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def save(n,d):
 with (O/n).open('x')as f:json.dump(d,f,indent=2);f.write('\n')
 return ref(O/n)
binding=json.loads((O/'binding.json').read_text());proof=json.loads((O/'proof.json').read_text());raw=json.loads((O/'accounting.json').read_text())
bare=json.loads((O/'bare-arm.json').read_text());public=json.loads((O/'public-arm-mpfr.json').read_text());fail=json.loads((O/'PREFLIGHT-RECONCILIATION.json').read_text())
assert binding['counts']==dict(local=68,external=1695)and len(binding['five_own_rebuilt_outputs'])==5
assert bare['actual_ARM_calls']==320 and public['actual_ARM_calls']==324 and public['directed_MPFR_inputs']==25 and public['sNaN_policy_shortcuts']==2
assert fail['prior_failed_ARM_calls']==290 and fail['own_actual_ARM_including_failed_attempt']==934
assert raw['loss_pairs_parent_candidate']==[11434,11434]and raw['corrected_public_instruction_reduction_range']==[4,180]
requirements=save('INTEGRATION-REQUIREMENTS.json',dict(status='MANDATORY_BEFORE_ANY_MERGED_FIRMWARE_OR_RELEASE_QUALIFICATION',
 source_parent='Actual Square128 r2 /31de and prior table-product chain; near-one is a separate sibling.',
 exact_supplier=binding['refs']['FROZEN'],
 source_merge_relink='Merge source deliberately with accepted Square128/table product and separate near-one; rebuild the actual complete firmware. This private overlay is not a combined firmware.',
 new_CPP_and_alias='Build the RP2040-guarded boundary TU and bind mk61_m0_boundary128_compare to the actual retained root128 compare in the merged image. Do not carry frozen diagnostic absolute addresses as a production binding.',
 boundary_ABI='Fresh linked tail/body/caller check: R0-R2 pointer/denominator/bool, incoming aligned uint64 cell at SP, ordinary int32 R0 return, R3 volatile; all24 midpoint bytes and retained endpoint policies.',
 target_R12='Run required shared-product R12 producer/consumer and veneer checks against fresh actual linked consumers after all merges. Boundary ordinary PCS checks are not that guard. The separate near-one88-instruction/16-byte-veneer guard remains required if that sibling is merged.',
 loader_layout='Fresh final ELF and loader ordering/layout checks, table/veneer targets, scratch4080 and Flash/RAM/stack bounds. Old168-byte exp overlay must not be loaded over the new bank: it corrupts14 bytes of the new table entry.',
 selected_contexts='Retain defaultM0 and M4soft/hard selected assembly and compile-time exclusion of the extra TU; validate in actual complete build contexts.',
 report_correction='Carry additive corrigendum729a5e18 with frozen result/HANDOFF: full public range4-180, old4-169 pilot upper bound is inaccurate for the full corpus.',
 performance='Instruction counts only, no physical cycle or universal speed proof. Invalid cells still return0 but additional own guard cases cost+4/+7; general invalid-argument speed is outside the public claim.',
 remaining_work='General pow totality, remaining loss cases, whole math, integrated correctness/performance and physical qualification remain separate work.',
 reviewed_whole507=422,author437_separate_union_not_promoted=True,main_GO=False,hardware_GO=False,release_GO=False))
evidence={p.relative_to(O).as_posix():ref(p)for p in sorted(O.rglob('*'))if p.is_file()and p.name not in ['MANIFEST.json','FINAL-REVIEW.json','VALIDATION.json']}
manifest=save('MANIFEST.json',dict(status='IMMUTABLE_COMPLETED_INDEPENDENT_COMPONENT_EVIDENCE',files=evidence,file_count=len(evidence),
 no_running_logs_in_manifest=True,all_generated_outputs_own_directory=True,device_IO=0,Git=0,network=0,canonical=0))
final=save('FINAL-REVIEW.json',dict(status='TECH_GO_PRIVATE_EXACT_BOUNDARY128_CALLER_COMPONENT_ONLY',component_review_complete=True,
 exact_frozen_supplier=binding['refs'],accepted_parent='Square128 r2/31de with independent eaa55a85; near-one separate sibling, not present in this ELF',
 new_caller_independently_reviewed_not_inherited_parent_GO=True,
 integrity=dict(local_pins=68,external_pins=1695,source_patch_exact=True,unchanged_other_RP_allocated_bytes_semantic_relocations_BSS_addresses_veneers=True,
  unchanged_defaultM0_M4_selected_ASM_and_guarded_CPP_empty=True,own_five_full_object_ELF_rebuilds_byte_exact=True,
  changed_source_CPP=binding['refs']['CPP'],candidate_ELF=binding['refs']['ELF']),
 arithmetic=dict(midpoint_initialization_all24bytes_same=True,loop_and_accepted_square_transform_induction=True,
  radius16_normalization_carry32wrap_policies_preserved=True,same_actual_original490byte_multiply372byte_compare94byte_helper=True,
  original_cell_range_and_inverse_endpoint_thresholds_preserved_including_radius0=True,noninverse_compare_and_public_RNE_enclosures_packing_unchanged=True,
  returned_zero_still_undecided=True,preservation_not_general_pow_totality=True),
 source_and_ABI=dict(old_resident_slot_bytes=532,new_tail_instructions=2,new_tail_plus_literal_bytes=8,unused_slot_padding_bytes=524,
  new_diagnostic_section_code_plus_literals_bytes=228,new_body_code_bytes=212,
  incoming_stack_cell_uint64_after_R0_R2=True,R3_unused_ABI_argument_slot=True,ordinary_int32_R0_no_extra_R12_return=True,
  four_real_retained_callers_and_three_new_BL_destinations_fresh_disassembled=True,
  no_new_tables_global_RAM_libgcc_or_ROM_math=True,current_private_free_Flash_below2MiB_no_overlap=True,
  no_fresh_actual_integrated_shared_R12_guard_claim=True),
 independent_qualified_checks=dict(actual_ARM=644,bare_cases=160,bare_ARM=320,public_pairs=27,public_states=54,public_ARM=324,
  directed_MPFR_inputs=25,sNaN_policy_shortcuts=2,MPFR_version=public['MPFR_version'],all3_actual_Qfplib_compositions_and_wrong_outputs_costs_retained=True,
  both_SIO_PCS_R4_R11_SP_PC_and28byteSIO_checked=True,bare_all16NZCV_noisy_R3_R12_input_cell_and_write_bounds=True,
  all24bytes_entry_args_midpoint_operands_and_sides_identical=True,exact_dyadic_endpoint_proofs_for_all58_nonzero_bare_decisions=True,
  actual_PC_excludes_mul_two_GAS_padding_bytes_and_literal_pools=True,actual180instruction_witness_bothSIO=True,
  no_second_complete_ARM_campaign=True),
 independent_saved_raw_recount=dict(pairs=120980,states=241960,reference_variants=279522,wrong_Qfplib_variants_retained=77106,
  parent_and_candidate_loss_pairs=[11434,11434],original153=dict(strict119=True,slower34=True,parent_candidate_unchanged=True),
  faster_public_states=454,public_instruction_reduction_range=[4,180],parent_cost_increases=0,candidate_wrong=0,new_raw_loss_pairs=0,new_Qfplib_win_claim=False,
  all10254_fresh_control_rows_overlap_and_match_full_raw=True,strict_quietNaN_and_no_nominal_reference_filter=True,
  current_parent_cost_field='parent_boundary_instructions',inherited_parent_instructions_preSquare_not_used_as_comparator=True),
 corrected_reporting=dict(corrigendum=binding['refs']['corrigendum'],frozen_result_and_HANDOFF_original4to169_inaccurate_for_full_corpus=True,
  independently_recounted_witnesses=raw['witnesses'],correct_full_range4to180=True,no_frozen_mutation=True,no_new_author_ARM_or_MPFR_from_corrigendum=True),
 author_evidence_separate=dict(qualified_fresh_ARM=309938,partition=[241960,454,61524,6000],MPFR5051_plus76sNaN=True,
  author17rebuilds_not_counted_as_own5=True,parent_inherited_MPFR_Qfplib_not_fresh=True,
  pilot1836_syntax_preflight0_rejected_bound80_bare19221_and_pilot1836_MPFR153_excluded=True,
  rejected80bit_filter_not_candidate_no_new_precision_filter=True),
 resources=dict(own_bare_boundary_peak=[212,156],own_selected_public_peak=[968,968,968],
  author_same_complete_corpus_peak=[2284,2284],author_fresh_controls_peak=[2148,2148,2148],
  parent_changed716_is_subset_not_complete_corpus_comparator=True,no_universal_stack_reduction=True,
  scratch_reservation4080_unchanged=True,retained_slot_not_reclaimed_new228allocated=True),
 honest_preflights=dict(reconciliation=ref(O/'PREFLIGHT-RECONCILIATION.json'),three_failed_static_reviewer_preflights_retained=True,
  one_failed_reviewer_overbroad_speed_assertion_retained=True,prior_failed_ARM290_not_in_qualified644=True,own_total_executed_ARM_including_failure934=True,
  invalid_cells_same_return0_no_midpoint_calls=True,additional_invalid_guard_cost_histogram=bare['invalid_guard_cost_delta_histogram'],
  valid_bare_and_saved_public_no_cost_increase=True,no_arithmetic_or_side_failure=True,auto_review_rejections=0),
 limits=dict(component_only=True,reviewed507_stays422=True,author437_not_promoted=True,near_one_sibling_not_combined=True,
  old168overlay_corrupts14byte_table_entry_HOST_negative=True,source_merge_relink_and_actual_R12_loader_layout_guards_required=True,
  general_pow_totality=False,physical_cycles=False,hardware_GO=False,integration_GO=False,main_GO=False,release_GO=False,overall_goal_complete=False),
 requirements=requirements,evidence_manifest=manifest,
 evidence={n:ref(O/n)for n in ['binding.json','proof.json','accounting.json','bare-arm.json','public-arm-mpfr.json','PREFLIGHT-RECONCILIATION.json','NOTES.md']},
 reviewer_scope=dict(device_IO=0,USB=0,Flash=0,network=0,install=0,Git=0,canonical=0,product_source_edits=0)))
# Validate only completed receipt/manifest bindings, then make this own bundle
# read-only. No live producer log, process query or external-state claim.
for n,d in evidence.items():assert ref(O/n)==d,n
assert json.loads((O/'FINAL-REVIEW.json').read_text())['evidence_manifest']==ref(O/'MANIFEST.json')
validation=save('VALIDATION.json',dict(status='PASS_FINAL_RECEIPT_MANIFEST_AND_ALL_OWN_ARTIFACT_BINDINGS',final_review=final,manifest=manifest,
 verified_manifest_file_count=len(evidence),own_qualified_ARM644=True,own_failed_ARM290_separate=True,
 no_required_review_work_remaining=True,integration_hardware_main_release_all_false=True,device_IO=0))
for p in O.rglob('*'):
 if p.is_file():p.chmod(0o444)
print(json.dumps(dict(final_review=final,manifest=manifest,requirements=requirements,validation=validation),indent=2),flush=True)
