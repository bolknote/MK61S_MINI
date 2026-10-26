"""Seal only the independently accepted private RP f2d component receipt."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json
O=Path(__file__).resolve().parent;R=O.parents[1];P=R/'.build/m0-f2d-leaf-20261024'
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def ref(p):return dict(path=str(p),bytes=Path(p).stat().st_size,sha256=sha(p))
assert sha(P/'FROZEN.json')=='931cce0b812981236a8fcadaf6cabf074ee473463092c90a8555764e4e288164'
assert sha(P/'result.json')=='1dc77e5fe5152b60df8ff5de59ad1bf4aeca5d0b5ad5ac6c85b9ffe47a41650e'
postread=[]
for name,base,count in [('FROZEN.json',P,61),('source-lineage-pins.json',R,424)]:
 files=read(P/name)['files'];assert len(files)==count
 for n,d in files.items():
  p=base/n;assert sha(p)==d['sha256'] and p.stat().st_size==d['bytes'];postread.append(ref(p))
b=read(O/'binding.json');p=read(O/'proof.json');a=read(O/'arm-result.json');parent=read(b['accepted_parent']['path'])
assert ref(Path(b['accepted_parent']['path']))==b['accepted_parent']
parent_pins=[b['accepted_parent'],parent['accepted_parent'],*parent['target'].values(),*parent['refs'].values()]
assert len(parent_pins)==27
for pin in parent_pins:assert ref(Path(pin['path']))==pin
assert read(P/'parent-review-at-seal.json')=={'independent_review_available_at_seal':False}
(O/'postread.json').write_text(json.dumps(dict(status='PASS_FROZEN61_LINEAGE424_LATE_ACCEPTED_PARENT27_AFTER_OWN_REVIEW',FROZEN=ref(P/'FROZEN.json'),verified=postread,late_parent_pins=parent_pins,parent_review_pending_at_seal_preserved=True),indent=2)+'\n')
assert b['rebuilds']==11 and b['d2f256_exactly_preserved']
assert p['partition_sum_2pow32']==1<<32
assert a['fresh_ARM_calls']==26928 and a['unique_inputs']==a['fresh_direct_MPFR_conversions']==3366
assert a['stack_bytes_candidate']==a['SIO_accesses']==0
assert a['actual_path_counts']==dict(candidate=53,intended_source=53,Qfplib=3)
assert [p['author_actual_directed_MPFR_input_conversions'],p['author_NaN_preMPFR_category_shortcuts']]==[124373,8586]
execution=dict(status='ALL_FINAL_REVIEW_PROGRAMS_COMPLETED_EXIT0',commands=[dict(program='binding.py',exit_code=0,session_id=66458,final_chunk='d2580d',HOST=True),dict(program='proof.py',exit_code=0,session_id=57164,final_chunk='a9a24c',HOST=True),dict(program='arm.py',exit_code=0,session_id=31234,final_chunk='cbdfdf',HOST=True,JIT_sandbox_override=True,hardware=False)],own_qualified_ARM_calls=26928,own_direct_MPFR_conversions=3366,author_broad_corpus_not_reexecuted=True)
(O/'execution.json').write_text(json.dumps(execution,indent=2)+'\n')
ledger=dict(status='ACCEPTED_PRIVATE_RP_F2D_CONVERSION_COMPONENT_ONLY',operation='__aeabi_f2d',candidate_ELF=ref(P/'candidate.elf'),accepted_separate_d2f_parent=b['accepted_parent'],exact_widening_all_raw32=True,NaN_return_policy='accepted-parent sign, payload preservation, quiet forced',all_correct_Qfplib_classes_no_slower_in_Thumb_instruction_count=True,author_observed_correct_reference_states=205234,author_observed_wrong_reference_states_retained=60684,old256_comparable249_speed_deficits_before1_after0=True,expanded_four_old_speed_deficits_fixed=['00000000','80000000','7F800000','FF800000'],all_observed_states_strictly_faster_native_parent=True,parent_cost_increases=0,physical_cycles_not_measured=True,original507_unchanged=dict(no_slower=418,strictly_faster=412,equal=6,remaining=89,remaining_by_operation=dict(pow=51,exp=2,sin=22,cos=14)),not_integrated_with_previous_components=True,whole_conversion_math_or_release_goal_not_complete=True)
(O/'conversion-component-receipt.json').write_text(json.dumps(ledger,indent=2)+'\n')
target={k:ref(P/n) for k,n in [('frozen','FROZEN.json'),('result','result.json'),('ASM_include','candidate/native_eabi_m0_f2d.inc'),('convert_include','candidate/native_eabi_m0_convert.inc'),('standalone_source','f2d.S'),('tested_private_leaf_ELF','candidate.elf'),('intended_source_private_leaf_ELF','whole-source.elf'),('patch','qualified-d2f-to-f2d.patch')]}
target['additive_postseal']=b['postseal']
names=['binding.py','binding.json','model.py','proof.py','proof.json','INDEPENDENT-PROOF.md','arm.py','arm-result.json','arm-rows.json','actual-paths.json','own-inputs.bin','candidate.dis','reference.dis','postread.json','execution.json','conversion-component-receipt.json','finalize.py']
refs={n:ref(O/n) for n in names}
d=dict(status='GO_PRIVATE_RP_F2D_LEAF_COMPONENT_ONLY',utc=datetime.now(timezone.utc).isoformat(),blockers=[],accepted_parent=b['accepted_parent'],target=target,
 lineage=dict(frozen_artifacts=61,lineage_pins=424,parent_review_pending_at_seal_preserved=True,late_accepted_d2f_receipt_plus26references_verified=27,postseal_addendum_matches_independent_counts=True,no_frozen_history_rewritten=True),
 source_binding=dict(accepted_parent_control_RP_object_exact=True,resident_parent_entry_and_resolved_BL_bound_to_real_extend=True,standalone_include_full_object_ELF_exact172=True,own_byte_exact_rebuilds=11,only_RP_changed_section='.m0_conversion_fixed.__aeabi_f2d',accepted_d2f256_body_unchanged=True,all_other_RP_allocated_bytes_semantic_relocations_equal=True,generic_M0_selected_bytes_relocations_equal=True,M4_selected_ASM_empty_and_equal=True,whole_M4_firmware_not_built=True,CPP_not_changed_by_component_patch=True,direct_public_ABI_entry='0x10164001',no_interposition_veneer=True),
 mathematical_proof=dict(type='Independent reviewed all-input source proof, mechanical affine/interval certificates, exact cardinality and actual-code correspondence; no formal SMT theorem claim',exact_finite_widening_all_raw32=True,signed_zeros_normals_all_subnormals_Inf_NaN_covered=True,accepted_parent_NaN_payload_sign_quiet_policy_exact=True,all23_subnormal_width_intervals_inductively_verified=True,total_normalization_shift='23-k',subnormal_exact_cost='30+2*popcount(23-k)',complete_raw32_cardinality_sum=str(1<<32),complete_Qfplib_correct_partition=['zero','normal','infinity'],all_correct_reference_paths_no_slower_instructions=True,no_IEEE_exception_flags_claim=True,certificates=p['checks']),
 own_fresh_checks=dict(unique_inputs=3366,ARM_calls=26928,machine_calls=a['machine_calls'],SIO_states=['READY','DIRTY'],direct_MPFR_conversions=3366,MPFR_version=a['MPFR_version'],MPFR_finite_input_from_exact_integer_times_power_of_two=True,MPFR_NaN_category_conversions=264,exact_integer_widening_comparisons=3366,all_parent_raw_bits_including_NaNs_exact=True,actual_candidate_paths=53,actual_Qfplib_paths=3,all23_subnormal_widths_both_signs_states=True,all_modeled_costs_match_actual_ARM=True,old_four_raw_deficits_freshly_closed=True,all_own_states_strictly_faster_native_parent=True,leaf_PC_SP_checked_every_instruction=True,leaf_reads_only_six_in_section_literals=True,leaf_stack_bytes=0,leaf_SIO_accesses=0,all28_SIO_bytes_preserved=True,leaf_external_ROM_firmware_mocks_or_veneers=0,hardware=False),
 inherited_and_author_evidence=dict(own_fresh_not_pooled_with_author=True,author_unique_inputs=132959,author_fresh_qualified_ARM_calls=797754,author_oracle_evaluations=132959,author_actual_directed_MPFR_input_conversions=124373,author_preMPFR_NaN_category_shortcuts=8586,correct_accounting_from_immutable_result_plus_additive_postseal=True,author_smoke41490_excluded=True,author_all265918_existing_states_reconciled_with_own_exact_and_cost_models=True,old9122_raw_inputs_all_present_and_parent_bits_identical=True,old256_reconciliation=p['old256_reconciliation'],author_correct_reference_states=205234,author_comparison_vs_correct_Qfplib=p['author_vs_correct_reference'],author_wrong_reference_states60684_retained=True,wrong_reference_NaN_candidate19_Qfplib12=True,wrong_reference_subnormal_candidate30to38_Qfplib8=True,author_all_states_strictly_faster_native_parent=True,author_parent_cost_increases=0,expanded_parent_raw_deficits4_candidate0_new0=True,broad_old_corpus_not_reexecuted_for_ACK=True),
 size_and_stack=dict(parent_leaf_bytes=34,candidate_leaf_bytes=172,selected_ASM_delta_bytes=138,global_RAM_delta=0,stack_bytes=0,new_tables_external_calls_or_libgcc=0,whole_firmware_size_not_built=True,old_C_slowpath_GC_savings_not_claimed=True,physical_cycles_not_measured=True),
 original507_separate_component_union=dict(no_slower=418,strictly_faster=412,equal=6,remaining=89,remaining_by_operation=dict(pow=51,exp=2,sin=22,cos=14),conversion_not_added_to_original507=True,not_one_integrated_binary=True,parent_ledger=parent['original507_separate_component_union']['parent_ledger']),
 nonblocking_observations=[dict(kind='provenance_and_accounting',detail='Frozen parent review remains pending-at-seal; later d2f GO is verified additively. Frozen 132959 MPFR label is interpreted via postseal as124373 actual directed MPFR inputs plus8586 NaN shortcuts; frozen packet is unchanged.')],
 retained_open_items=['original507 remaining89 (pow51 exp2 sin22 cos14)','expanded pow7904 and exp395','expanded ln5','FMA conversion work and any separately pending conversion components','generalpow1024 totality','one integrated private math image and complete math acceptance','repaired-platform/full firmware relink, section placement/GC size and complete M4 build if integration requested','physical-cycle and hardware acceptance','canonical promotion and release'],
 grants=dict(private_f2d_component_GO=True,all_conversion_or_math_goal_GO=False,hardware_GO=False,canonical_promotion=False,integration_or_EA9_changes=False,release_GO=False),producer_Git_primary_or_device_state_modified=False,refs=refs)
(O/'FINAL-REVIEW.json').write_text(json.dumps(d,indent=2)+'\n')
for group in [target,refs]:
 for pin in group.values():assert ref(Path(pin['path']))==pin
assert ref(Path(d['accepted_parent']['path']))==d['accepted_parent']
print(json.dumps(dict(status=d['status'],FINAL_REVIEW=ref(O/'FINAL-REVIEW.json'),conversion_receipt=ref(O/'conversion-component-receipt.json'),direct_refs_verified=len(target)+len(refs)+1,own_ARM26928_MPFR3366=True,blockers=[],original507_unchanged418=True),indent=2))
