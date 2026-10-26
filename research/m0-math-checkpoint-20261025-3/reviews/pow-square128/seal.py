"""Seal completed square128 private-component checks; no numerical rerun."""
import hashlib,json
from pathlib import Path
R=Path('/Users/bolk/Projects/MK61S_MINI');O=Path(__file__).resolve().parent;W=R/'.build/m0-pow-square128-r2-20261025'
def ref(p):p=Path(p);d=p.read_bytes();return dict(path=str(p),bytes=len(d),sha256=hashlib.sha256(d).hexdigest())
def save(n,d):
 with (O/n).open('x')as f:json.dump(d,f,indent=2);f.write('\n')
 return ref(O/n)
def load(n):return json.loads((O/n).read_text())
b=load('binding.json');p=load('proof.json');u=load('bare-arm.json');a=load('public-arm-mpfr.json');c=load('accounting.json');strict=load('strict-fixes.json')
assert b['local_count']==69 and b['external_count']==1585
assert u['qualified_calls']+a['qualified_calls']==764 and a['directed_MPFR_inputs']==15 and a['sNaN_shortcuts']==2
assert u['peak_with_helper']==dict(control=68,candidate=60)
assert all(a['observed_stack_bytes'][n]==2148 for n in ['parent','control','candidate'])
requirements=save('INTEGRATION-REQUIREMENTS.json',dict(status='REQUIREMENTS_ONLY_NO_ACTIVATION_AUTHORITY',
 actual_parent='accepted table-product dd0ec366 / ROOT09b8c732',authoritative_package=str(W),
 rejected_historical_seal='2f8310755224d63b246743976692f13b396d40bedfc31a619711f6926791d80c',
 requirements=['Merge source deltas with the separate near-one sibling and relink; private ELF overlays are not a combined release image.',
  'Rerun the actual integrated exp R12 producer/real16-byte wrapper/postcall-marker/consumer guard on fresh linked disassembly and actual compiler flags.',
  'Validate actual scratch-bank layout, new table entry, overlay-loader ordering and bounds. Reject the old168-byte exp overlay that overwrites14 bytes of the table entry.',
  'Retain all24-byte square transform semantics, radius16/nonzero boolean rules,310-byte slot and ordinary void caller ABI.',
  'Preserve the accepted R qualified-probe lineage correction, r2 reissue record, rejected first seal and historical7bf WIP snapshot without rewriting history.',
  'Do not convert this private component receipt into general-pow totality, physical cycles, hardware, whole507 or main/release GO.'],
 reviewed_whole507=dict(no_slower=422,strict=413,equal=9),author437_not_promoted=True,integration_GO=False,hardware_GO=False,release_GO=False))
notes=save('EXECUTION-NOTES.json',dict(status='COMPLETED_SQUARE128_CPU_ONLY_REVIEW',
 initial_metadata_assertion=dict(start='71e373',completion='d58896',exit=1,
  cause='Reviewer expected only HANDOFF to differ. Actual r2 also amplifies lineage metadata, retaining1516 old pins and adding69 historical producer/sealer pins; product/numerical bytes are unchanged.'),
 initial_rebuild=dict(tool='7294a1',exit=1,cause='R2 path/cwd changes DWARF only; all allocated sections remain identical. Unmapped object retained for audit.',
  correction='Authoritative r2 input paths and own output paths, with explicit fdebug-prefix-map to historical producer paths, reproduce entire objects/ELFs exactly.'),
 resume_directory_assertion=dict(tool='9b10d0',exit=1,cause='Existing own rebuild directory before any compiler action; exist_ok enabled.'),
 completed_binding=dict(tool='562f37',exit=0,four_whole_byteexact_rebuilds=True,producer_outputs_not_touched=True),
 static_proof_initial_filter=dict(tool='42e4c8',exit=1,cause='Initial scan included an unwind reference to the function; restricting to actual THM_CALL relocations identifies the two callers.'),
 static_proof_completed=dict(tool='6e2f69',exit=0),
 own_ARM=dict(bare_tool='1bf682',public_tool='d3b16a',all_exit0=True,qualified_calls=764,MPFR_inputs=15,sNaN_shortcuts_separate=2,
  Unicorn='Existing runtime; scoped CPU-only require_escalated JIT approved. No default/rejected runs or installations.',
  ROM_initializer_calls_excluded=True),
 saved_accounting=dict(start='9b13eb',completion='836b00',exit=0,ARM_calls=0,MPFR_inputs=0),
 strict_fix_validation=dict(tool='8609e2',exit=0,ARM_calls=0,MPFR_inputs=0),
 failed_harness_checks_not_qualified_numerical_runs=True,full_corpus_not_reexecuted=True,
 device_IO=0,Git_operations=0,canonical_access=0,network_operations=0,product_source_edits=0))
evidence={n:ref(O/n)for n in ['binding.json','seal-lineage.json','proof.json','NUMERIC-REVIEW.md','bare-arm.json','public-arm-mpfr.json','accounting.json','strict-fixes.json','INTEGRATION-REQUIREMENTS.json','EXECUTION-NOTES.json']}
review=dict(schema='independent-private-pow-square128-component-v1',status='TECH_GO_PRIVATE_EXACT_SQUARE128_COMPONENT_ONLY',
 reviewer='/root/rtc_helper_review',scope='Authoritative r2 single-function 24-byte transform replacement, based on accepted table-product. Not integrated firmware or whole math.',
 findings=[],blocking_component_findings=[],accepted_frozen_target=b['accepted_refs'],
 seal_reissue=dict(authoritative_r2_FROZEN31de9242=True,first_seal2f831075_rejected_not_accepted=True,
  independently_found_only_bad_original_pin='finalize.log: claimed0B/emptySHA; completed376B/03b995e5',
  all_sources_binaries_raw_proofs_results_bytecopy=True,HANDOFF_append_and_lineage_metadata_amplification_only=True,
  old1516_external_pins_unchanged_plus69_historical_refs_equals1585=True,
  r2_copy_not_fresh_ARM_or_MPFR=True,original_frozen_producer_not_rewritten=True,historical7bf_WIP_not_rewritten=True),
 provenance=dict(all69_local_and1585_external_hash_size_pins_verified=True,exact_one_root_prefix_function_patch=True,
  actual_parent_table_product_dd0ec366_ROOT09b8c732=True,near_one_separate_sibling=True,
  own_four_whole_source_object_helper_ELF_unit_rebuilds_byteexact=True,
  authoritative_r2_inputs_own_outputs_explicit_DWARF_prefix_mapping=True,
  author13_rebuilds_verified_as_saved_evidence_not_own_runs=True,
  all_other_RP_allocated_bytes_addresses_semantic_relocations_BSS_and_selected_M0_M4soft_hard_ASM_unchanged=True),
 numeric_proof=dict(arbitrary_input_fields_all24_bytes_equivalent_to_old_transform=True,
  identity='P=H^2+2*C mod2^128; C is the unchanged94-byte helper(L,H) for L!=0, otherwise0.',
  exact_square32_and_cross32_radix_carry_schedules=True,four_word_Hsquare_and_twiceC_add_chains=True,
  radius='2*radius+(16 if L!=0 else bool(radius)), mod2^32',exponent_double_upper_increment_and_low_shift_exact=True,
  normalized_upper_branch_and_all_wrap_bits_preserved=True,old_interval_radius_policy_not_reinterpreted=True,
  fresh_two_actual_resident_callers_void_result_flags_unused=True,ordinary_void_PCS_no_extra_R12_return=True,
  unchanged_public_RNE_enclosures_and_fallbacks_inherited=True,general_pow_totality_not_established=True),
 own_bounded_checks=dict(qualified_actual_ARM_calls=764,bare_tests=280,bare_calls=560,
  all24_output_bytes_old_new_integer_model_equal=True,all16NZCV_and_noisy_volatile_registers=True,
  PCS_R4_R11_SP_PC_bounded_struct_stack_writes_and_activePC_ranges=True,
  independent_static_CFG_and_actual_cost_classes=p['static_CFG_costs'],
  kernel_frames=dict(control=48,candidate=40),unchanged_helper_frame20=True,including_helper=dict(control=68,candidate=60),
  public_pairs17_bothSIO=True,public_calls204=True,actual_directed_MPFR_inputs=15,sNaN_shortcuts_separate=2,MPFR_version='4.2.2',
  all3_actual_Qfplib_compositions_and_wrong_outputs_retained=True,strict_quietNaN_reference_policy=True,
  parent_control_candidate_rawbits_and_kernel_input_sequences_equal=True,
  all_four_kernel_cost_classes_seen_public=True,total_cost_change_exact_sum_of_kernel_deltas=True,
  old_three_fixes_checked_strict_bothSIO_in_own_actual_public=True,new_original153_fix_checked_strict_bothSIO=True,
  captured_ROM_initializer_calls_excluded_from_qualified_calls=True,no_other_math_qualification=True),
 saved_raw_accounting=dict(ARM_or_MPFR_reexecutions=0,all_parent232936_states252450variants_bound_to_accepted_parent_raw=True,
  all_parent_result_bits_identical=True,all756_old_kernel_call_cost_classes_independently_recomputed=True,
  old116468_losses=[10853,10850],old_three_fixes_strict_bothSIO_against_every_correct_reference=True,
  expanded120980_pairs241960_states279522_reference_variants=True,expanded_losses=[11449,11434],expanded15strict_bothSIO=True,
  additional596_loss_pairs_preexisting=True,new_loss_pairs=0,parent_instruction_increase_states=0,
  wrong_Qfplib_variants77106_retained=True,strict_quietNaN_and_no_nominal_domain_filter=True,
  correct_Qfplib_comparison=c['correct_Qfplib_comparison'],original153_deficits=[35,34],
  author330880_ARM_and5051_MPFR_plus76sNaN_only_inherited_evidence=True,pilot918_and_route70_excluded=True),
 resources=dict(old_function310_new232_bytes=True,retained_slot310_padding78_unused=True,allocated_code_delta_bytes=0,
  no_new_tables_global_RAM_libgcc_or_ROM_math=True,other_resident_code_and_veneers_not_relinked=True,
  static_kernel_stack48_to40_with_helper68_to60=True,
  old_corpus_observed_full_stack2284_unchanged=True,fresh_controls_observed2148_same_parent_control_candidate=True,
  no_universal_full_stack_drop_or_physical_cycle_claim=True),
 integration_requirements=requirements,reviewed_whole507_preserved=dict(no_slower=422,strict=413,equal=9),author437_not_promoted=True,
 evidence=evidence,authority=dict(private_component_HOST_GO=True,integration_GO=False,hardware_GO=False,whole_math_or507_GO=False,
  main_release_or_publication_GO=False,goal_complete=False,device_USB_ports_Git_canonical_network_actions=0),
 remaining='Expanded11434 pow losses, general-pow totality, other operations, source merge/relink with near-one, actual integrated R12 and loader/layout guards, physical measurements and release remain outside this component verdict.')
final=save('FINAL-REVIEW.json',review)
assert ref(W/'FROZEN.json')['sha256']=='31de9242e96642ed7de050a2a7a51a5baeacdd9c8842e4b0d7f3f2c74e2e681d'
assert ref(W/'candidate.elf')['sha256']=='6325d6e1d2d619028f9cb7d156c688ead1795331513941207e9c3de2c1214898'
manifest=save('MANIFEST.json',dict(status='SEALED_PRIVATE_COMPONENT_ONLY_REVIEW',files={str(p.relative_to(O)):ref(p)for p in sorted(O.rglob('*'))if p.is_file()}))
for p in O.rglob('*'):
 if p.is_file():p.chmod(0o444)
print(json.dumps(dict(final=final,manifest=manifest,requirements=requirements),indent=2))
