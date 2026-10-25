"""Seal completed selected LUT private component evidence only."""
import ast,hashlib,json,struct,sys
from pathlib import Path
sys.dont_write_bytecode=True
R=Path('/Users/bolk/Projects/MK61S_MINI');O=Path(__file__).resolve().parent;W=R/'.build/m0-pow-reciprocal-lut-20261025';P=R/'.build/m0-pow-reciprocal-soft-20261025'
sys.path.insert(0,str(R/'tests'));from check_stm32_vectors import ElfImage
def ref(p):
 p=Path(p);b=p.read_bytes();return dict(path=str(p),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def save(n,d):
 with (O/n).open('x')as f:json.dump(d,f,indent=2);f.write('\n')
 return ref(O/n)
b=json.loads((O/'binding.json').read_text());proof=json.loads((O/'proof.json').read_text());a=json.loads((O/'accounting.json').read_text());c=json.loads((O/'caller-layout.json').read_text())
se=json.loads((O/'seed-arm.json').read_text());di=json.loads((O/'ddiv-arm-mpfr.json').read_text());pu=json.loads((O/'public-arm-mpfr.json').read_text())
assert len(b['own_nine_byteexact_rebuilds'])==9 and [se['actual_ARM_calls'],di['actual_ARM_calls'],pu['actual_ARM_calls']]==[1054,248,276]
assert di['directed_MPFR_inputs']+pu['directed_MPFR_inputs']==50 and di['sNaN_shortcuts']+pu['sNaN_shortcuts']==4 and c['count']==25
# Recheck exact semantic relocations of every selected context, not DWARF
# symbol indices. All runtime source other than the leaf is the parent copy.
tree=ast.parse((R/'.build/m0-exp-cached-product-independent-20261024/bind_rebuild.py').read_text());fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name=='relocs')
exec(compile(ast.Module(body=[fn],type_ignores=[]),'<accepted-relocations>','exec'),globals())
for context in ['RP','generic_M0','M4_soft','M4_hard']:
 old=ElfImage(P/(context+'-candidate.o'));base=relocs(old)
 for label in ['control','candidate']:
  new=ElfImage(W/(context+'-'+label+'.o'));nr=relocs(new)
  for sec,s in old.named_sections.items():
   if s[2]&2:assert base.get(sec)==nr.get(sec),(context,label,sec)
eq=save('source-equivalence.json',dict(status='PASS_ALL_SELECTED_ALLOCATED_SEMANTIC_RELOCATIONS_TO_SOFT_PARENT',contexts=['RP','generic_M0','M4_soft','M4_hard'],both_labels=True,ARM_calls=0,MPFR_inputs=0,device_IO=0))
req=save('INTEGRATION-REQUIREMENTS.json',dict(status='MANDATORY_BEFORE_ANY_MERGED_FIRMWARE_QUALIFICATION',
 exact_supplier=b['refs']['FROZEN'],actual_parent='soft13dc / independent211cf / later ROOTde2f; child remains separately qualified',
 source_merge='Merge exact selected source and NEW128-u16 table; relink whole target. Do not mechanically combine private overlays or diagnostic fixed addresses with the separate near-one sibling.',
 selected_leaf='Qualify actual56B code+256B table and D17 domain; old literal194B is the parent implementation, not a required child layout. Preserve exact quotient, aligned bounded lookup, signed/modular correction, R1/R12/PCS/SP/PC.',
 R3_contract='Leaf may clobber R3 only where actual caller saves/pops original R0-R3. Keep quotient consumption before POP. Private continuation requires raw operands, guarded R6[0,2043], original20B frame and8-aligned seed BL; no generic scalar C/ddiv ABI.',
 RNE='Retain common282B NR/exact-remainder/RNE semantics, IEEE/dyadic guards, selection and fallback. No relaxed precision.',
 integrated_R12='Run actual integrated shared-product producer/consumer and veneer guards on fresh linked consumers after source merges; reciprocal private R12-tag proofs are not that contract. Keep the separate near-one guard if merged.',
 loader_layout='Fresh final target/loader/table/address/Flash/RAM/stack/scratch4080 checks. Old168B exp overlay corrupts14B of the new table entry and cannot be loaded over the new bank.',
 exclusions='Other3 studied variants are unqualified here. Failed24ARM/3MPFR calibration and parent/historical calls are not fresh. Public-report own key all48 is corrected additively to all9; carry its corrigendum.',
 limits='Instruction counts in CPU emulation are not physical cycles/Flash-latency measurements. General pow totality and remaining math/speed work stay separate.',
 reviewed507=422,author437_not_promoted=True,integration_GO=False,hardware_GO=False,main_GO=False,release_GO=False))
files={p.relative_to(O).as_posix():ref(p)for p in sorted(O.rglob('*'))if p.is_file()and p.name not in ['MANIFEST.json','FINAL-REVIEW.json','VALIDATION.json']}
manifest=save('MANIFEST.json',dict(status='IMMUTABLE_COMPLETED_SELECTED_PRIVATE_LUT_COMPONENT',file_count=len(files),files=files,
 no_running_logs_or_processes=True,all_generated_outputs_own_directory=True,device_IO=0,Git=0,canonical=0,network=0))
final=save('FINAL-REVIEW.json',dict(status='TECH_GO_PRIVATE_EXACT_LUT_ROOT_RECIPROCAL_COMPONENT_ONLY',component_review_complete=True,
 exact_supplier=b['refs'],parent_ROOT_stamp_at_child_seal_None_preserved_later_receipt_additive_only=True,new_child_review_not_inherited_parent_GO=True,
 integrity=dict(local_pins=67,external_pins=1978,separate_seed_study_FROZEN_verified=True,own9full_source_object_ELF_rebuilds_byte_exact=True,
  all_sources_and_allocated_semantic_relocations_except_new_seed_identical_to_parent=True,all_other_bytes_addresses_root_BL_and_other_ddiv_callers_unchanged=True,
  selected_M0_M4_controls_unchanged_and3_added_disabled_objects_empty=True,selected312blob_exact_to_full_domain_tested_unit=True),
 new_supplier_resources=dict(function_bytes=56,table_bytes=256,NEW_integer_table_values=128,total_seed_bytes=312,parent_seed_bytes=194,
  private_allocation=[1050,1168],net_growth118=True,no_new_global_RAM_libgcc=True,table4aligned_lookup_halfword_aligned=True),
 exact_integer_proof=dict(HOST_full_divisor_domain=65536,D_domain=[65536,131071],table_generation_allbytes_exact=True,
  actual_ADR_LDRH_index0to127_offsets0to254_bound=True,
  signed_fold_multiply_and_floor_shifts_proved=True,initial_error_range=[-1,3],initial_error_histogram=proof['error_histogram'],ranges=proof['ranges'],
  low32_product_MVN_yields_exact_signed_residual_despite_wrap=True,max_down3_up1=True,Euclidean_invariant_floor_FFFFFFFF_over_D_exact=True,
  intentional_modular_operations_explicit=True,incoming_flags_not_consumed=True,five_adversarial_table_binding_controls_HOST_only=True,
  no_new_binary64_error_bound_or_relaxed_RNE=True),
 selection_and_author_unit_binding=dict(all77840_saved_bare_rows_recounted=True,all65536D_covered=True,selected_unique_best_full_domain_worst_instructions27=True,
  other_worst_instruction_counts=[34,42,86],selected_instruction_range=[20,27],parent_range=[82,97],
  selected='lut128_floor',sample_only_historical='lut32_ceil_outer',nine_fix_forecast_common_to_all_variants_not_selection_or_qualification=True,
  selected_oldplusnew155680_calls=True,other3variants233520_exploratory_calls_excluded=True,other_variants_not_component_GO=True),
 fresh_private_caller_contract=dict(new_R3_clobber_independently_qualified_not_old_ABI_inheritance=True,
  actual_push_R0_R3_R7_before_seed_BL_and_POP_before_join=True,quotient_consumed_in_R6_before_POP_restores_R0=True,
  actual_saved_R3_differs_from_leaf_R3_then_POP_restores_at_join_count=25,
  raw_operands_guardedR6_original20B_R12_SP_and8aligned_seed_BL_checked=True,
  common_R0_R6_R12_SP_frame_and_reestablished_flags_equal_to_READY_hardware=True,
  common282RNE_and_other856prefix_bytes_bound_fresh=True,R1_R12_PCS_SP_PC_SIO7words_preserved=True,
  private_continuation_and_leaf_not_generic_C_ABI_or_global_ddiv=True),
 independent_CPU_qualification=dict(actual_Thumb_calls_in_Unicorn=1578,paired_leaf_calls=1054,leaf_pairs=527,direct_calls=248,public_calls=276,
  leaf32_bin_edges_each16NZCV_plus15_exact_domain_extremes=True,PC56_excludes_table256_and_only_one_aligned_LDRH_no_writes=True,
  R3_actual_remainder_clobber_only_no_public_return_contract=True,direct_pairs31_public_pairs23=True,directed_MPFR_inputs=50,sNaN_shortcuts=4,MPFR_version='4.2.2',
  actual_join_and_R3_checks25=True,all9_new_strict_fixes_bothSIO_actually_reproduced=True,
  READY_unchanged_DIRTY_CSR_only_no_divider_writes=True,all3_real_Qfplib_public_compositions_wrong_outputs_and_costs_retained=True,strict_quietNaN=True,
  immediate_parent_direct_private_hint_alias_explicit_not_original_resident_symbol=True,ROM_initializers_excluded=True,
  no_failed_preflights_or_discarded_own_calls=True,no_complete476k_or241960_state_ARM_repeat=True),
 independent_saved_raw=dict(pairs=120980,states=241960,reference_variants=279522,wrong_public_Qfplib_variants=77106,
  loss_pairs=[11386,11377],strict_fixes9=True,new_losses0_wrong0_increases0=True,faster_DIRTY377=True,public_instruction_savings=[59,73],READY_equal=True,
  every_public_and_direct_delta_equals_measured_selected_seed_delta=True,
  immediate_parent_field='parent_reciprocal_instructions overwritten with current soft-parent candidate cost; older historical value not used',
  all10254_fresh_public_rows_overlap_exact=True,all4148_direct_output_timing_rows_kept_wrong936=True,no_nominal_filter=True,
  correct_reference_comparison=dict(slower=21044,faster=178667,equal=2705),original153=dict(strict119=True,slower34=True,unchanged=True)),
 honest_evidence_counts=dict(author476133_partition=[155680,241960,377,61524,16592],author6761MPFR_plus184sNaN=True,
  author256_direct_exact_dyadic_inputs_separate_from_full_bare_integer_domain=True,
  failed_author24ARM3MPFR_old_parent_symbol_excluded=True,parent_qualification_pilot_old66288_not_fresh=True,new_original153pilot_not_run=True,
  own_report_original_all48_keyword_label_typo_corrected_to_all9_additively=True,metadata_correction=ref(O/'PUBLIC-REPORT-CORRIGENDUM.json'),
  own_raw_reports_and_executed_source_unchanged_no_new_calls_from_correction=True),
 stack_and_layout=dict(same_full_saved_peak2284=True,author_controls2148_each=True,changed_parent388_subset_not_full_comparator=True,
  own_selected_public_peaks=[968,968,968],own_direct_peaks=[176,176,176],no_universal_stack_reduction=True,
  allocation1168_no_overlap_below2MiB_no_writable_RAM=True,scratch4080_unchanged=True,old168overlay14B_hazard_persists=True),
 limits=dict(component_only=True,near_one_separate_sibling=True,reviewed507_stays422=True,author437_separate_union_not_promoted=True,
  source_merge_relink_actual_integrated_R12_loader_layout_required=True,general_pow_totality=False,physical_cycles=False,
  integration_GO=False,hardware_GO=False,main_GO=False,release_GO=False,overall_goal_complete=False),
 requirements=req,evidence_manifest=manifest,evidence={n:ref(O/n)for n in ['binding.json','proof.json','accounting.json','caller-layout.json','seed-arm.json','ddiv-arm-mpfr.json','public-arm-mpfr.json','PUBLIC-REPORT-CORRIGENDUM.json','source-equivalence.json','NOTES.md']},
 scope=dict(device_IO=0,USB=0,Flash=0,network=0,install=0,Git=0,canonical=0,product_source_edits=0)))
for n,d in files.items():assert ref(O/n)==d,n
assert json.loads((O/'FINAL-REVIEW.json').read_text())['evidence_manifest']==ref(O/'MANIFEST.json')
validation=save('VALIDATION.json',dict(status='PASS_FINAL_RECEIPT_MANIFEST_ALL_ARTIFACTS_AND_LABEL_CORRIGENDUM',final_review=final,manifest=manifest,
 verified_manifest_files=len(files),own_ARM1578_MPFR50_plus4shortcuts=True,own_failed_preflights0_discarded0=True,all9_not48_fix_claim_correct=True,
 no_required_review_work_remaining=True,integration_hardware_main_release_all_false=True,device_IO=0))
for p in O.rglob('*'):
 if p.is_file():p.chmod(0o444)
print(json.dumps(dict(final_review=final,manifest=manifest,requirements=req,validation=validation),indent=2),flush=True)
