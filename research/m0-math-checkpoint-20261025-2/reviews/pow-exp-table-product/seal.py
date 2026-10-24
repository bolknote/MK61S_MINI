"""Seal completed private-component evidence without rerunning tests."""
import hashlib,json,re,sys
from pathlib import Path
sys.dont_write_bytecode=True
R=Path('/Users/bolk/Projects/MK61S_MINI');O=Path(__file__).resolve().parent;W=R/'.build/m0-pow-exp-table-product-20261025'
def ref(p):p=Path(p);d=p.read_bytes();return dict(path=str(p),bytes=len(d),sha256=hashlib.sha256(d).hexdigest())
def save(n,d):
 with (O/n).open('x')as f:json.dump(d,f,indent=2);f.write('\n')
 return ref(O/n)
def load(n):return json.loads((O/n).read_text())
binding=load('binding.json');linked=load('linked-proof.json');bare=load('bare-arm.json');public=load('public-arm-mpfr.json');policy=load('public-reference-policy.json');account=load('accounting.json')
assert binding['local_count']==123 and binding['external_count']==1349 and binding['own_whole_exact_rebuild_count']==4
assert bare['qualified_calls']+public['qualified_calls']==1966 and policy['candidate_parent_control_wrong']==0
assert not policy['derived_reference_flag_corrections']
def frames(p):
 result=[]
 for line in p.read_text().splitlines():
  key,size,kind=line.split('\t');key=re.split(r':\d+:\d+:',key,maxsplit=1)[1];result.append([key,int(size),kind])
 return sorted(result)
assert frames(W/'RP-control-cpp.su')==frames(W/'RP-candidate-cpp.su')==frames(O/'rebuild/RP-candidate-cpp.su')
assert public['observed_stack_bytes']['parent']==public['observed_stack_bytes']['control']==public['observed_stack_bytes']['candidate']==2284
requirements=save('INTEGRATION-REQUIREMENTS.json',dict(status='REQUIREMENTS_ONLY_NO_ACTIVATION_AUTHORITY',
 requirements=linked['future_requirements'],actual_source_basis='directed-product e6ce/CPP575da330',
 accepted_near_one_is_separate_sibling_not_in_this_ELF=True,
 table_domain='Use new entry only when A is one of the exact certified512 literal roots; low32==0 is not a generic dyadic detector.',
 scalar_ABI='New dyadic entry supplies only the standard U64 result. R12 extra is retained only by the unchanged general entry.',
 old_overlay_hazard=dict(old_bytes=168,new_entry_offset=154,destructive_overlap_bytes=14,negative_preflight_rejected=True),
 lineage='Preserve qualified R/probe.json losslessly in future tracked/portable checkpoints. Keep the historical omitted r5 archive and old frozen evidence unchanged.',
 reviewed_whole507=dict(no_slower=422,strict=413,equal=9),author436_not_accepted_as_union=True,
 integration_GO=False,hardware_GO=False,main_or_release_GO=False))
notes=save('EXECUTION-NOTES.json',dict(status='COMPLETED_PRIVATE_CPU_ONLY_EXECUTION_EVIDENCE',
 binding=dict(start='4b74ad',completion='c46e34',exit0=True,whole_byteexact_rebuilds=4),
 linked_source_proof=dict(tool='ad1e3e',exit0=True),
 own_ARM=dict(bare='4bb994',public_start='98d4f2',public_completion='1a8150',all_exit0=True,qualified_calls=1966,
  Unicorn='existing runtime, scoped require_escalated CPU-only JIT approved; no installations or rejected/default runs',
  MPFR_inputs=51,sNaN_shortcuts=2,captured_ROM_initializers_excluded=True),
 saved_recount_policy_correction=dict(initial_tool='707eda',initial_exit=1,record_index=618,
  cause='Reviewer initially treated every NaN output as equivalent. Saved sNaN reference output must count as wrong unless quiet, matching the accepted policy.',
  corrected_recount_start='64749e',corrected_completion='b6143d',corrected_exit0=True,
  strict_saved_public_postcheck='27d3e0',corrected_public_reference_flags=0,ARM_or_MPFR_reexecution=0,
  original_executed_harness_and_raw_outputs_retained=True),
 device_IO=0,Git_operations=0,canonical_access=0,network_operations=0,product_source_edits=0))
evidence={n:ref(O/n)for n in ['binding.json','linked-proof.json','NUMERIC-REVIEW.md','bare-arm.json','public-arm-mpfr.json','public-reference-policy.json','accounting.json','INTEGRATION-REQUIREMENTS.json','EXECUTION-NOTES.json']}
result=json.loads((W/'result.json').read_text())
review=dict(schema='independent-private-pow-exp-table-product-component-v1',status='TECH_GO_PRIVATE_TABLE_ONLY_POW_PRODUCT_COMPONENT',
 reviewer='/root/rtc_helper_review',scope='Five-file private RP2040 table-only scalar product delta; actual source base directed e6ce/CPP575da330, with independently accepted near-one as separate sibling.',
 findings=[],blocking_component_findings=[],accepted_frozen_target=binding['accepted_refs'],
 provenance=dict(all123_local_and1349_external_hash_size_pins_verified=True,exact_five_file_patch=True,
  CPP_source_matches_directed_parent575da330=True,near_one_source_not_in_this_pow_ELF=True,
  own_four_full_source_object_fixture_ELF_rebuilds_byteexact=True,author20_rebuilds_verified_as_saved_evidence_not_own_runs=True,
  CPP_allocated_bytes_tables_and_public_enclosures_unchanged=True,only_three_literal_table_call_relocations_changed=True,
  other_semantic_relocations_BSS_defaultM0_M4soft_hard_selected_objects_unchanged=True),
 numeric_proof=dict(all512_actual_linked_table_constants_byteexact_parent=True,only_low32zero_row_is_index0_A2pow62=True,
  domain_requires_literal_table_A=True,universal_B64_scalar_identity='(B>>2)+bit1(B)',
  exact_internal_half_up_not_a_new_public_IEEE_rounding_rule=True,
  generic_table_selector_preserves_all_arguments_into_old77_body=True,dyadic_carry_identity_full64_and_no_overflow=True,
  existing_public_RNE_enclosures_and_packing_unchanged=True,general_pow_totality_not_established=True),
 fresh_linked_checks=dict(actual_callers=3,actual_routes='Direct RAM / real GNU tail veneer / new explicit Flash wrapper',
  all_scalar_R0_R1_return_captures_verified=True,tail_wrappers_restore_R0_SP_and_preserve_LR=True,
  general154bytes_same_address_and_R12_fraction_capture=True,original16byte_wrapper_still_targets_general=True,
  new_dyadic_R12_extra_not_promised=True,exp_consumer_absent_in_this_pow_ELF=True,fresh_integrated_exp_consumer_guard_claim=False,
  old168overlay_destructive_overlap14bytes_negative_preflight_rejected=True),
 independent_bounded_actual_checks=dict(qualified_ARM_calls=1966,bare_calls=1330,all512_roots_actual=True,
  all16NZCV_on4roots2Bvalues_and_arbitraryR12=True,dyadic_B64_carry_edges=True,generic_extra_R12_matches_old=True,
  gate_instructions=dict(dyadic=10,generic=79,old_general=77),new_Flash_wrapper_instructions=5,
  PCS_R4_R11_SP_PC_boundedwrites_and_activePCs_checked=True,
  public_pairs53_bothSIO=True,public_ARM_calls636=True,actual_directed_MPFR_inputs=51,sNaN_shortcuts_separate=2,MPFR_version='4.2.2',
  three_actual_Qfplib_compositions_retained=True,strict_quiet_NaN_saved_output_policy_rechecked=True,
  candidate_parent_control_bits_and_layout_control_costs_equal=True,all13_original_fixes_strict_bothSIO=True,
  actual_cost_law_candidate_minus_parent='2*g-67*d',public_table_roots_seen=public['table_rows_seen'],
  no_other_math_qualification=True,captured_ROM_initializers_excluded_from_qualified_calls=True),
 saved_raw_accounting=dict(ARM_and_MPFR_calls=0,old111912_pairs223824states=True,old_reference_variants223976=True,
  old7901_to7888=True,expanded116468_pairs232936states=True,expanded_reference_variants252450=True,
  expanded10866_to10853=True,additional2965loss_pairs_preexisting=True,new_raw_speed_losses=0,
  original153_parent48_to_candidate35_and13newstrict=True,all10081_C77_sensitive_state_costs_bound_to_saved_actual_replay=True,
  all_saved_actual_costs_match_R_minus7n_plus2g_minus67d=True,
  all8024_plus2_cost_increase_states_retained=True,increase_scopes=result['retained_increase_scopes'],
  all60686_wrongQfplib_reference_variants_retained=True,correct_Qfplib_variant_comparison=result['correct_Qfplib_union_comparison'],
  all3_reference_symbols_and_all512_roots_in_saved_public_calls_verified=True,no_nominal_domain_filter=True,
  producer_fresh314546_ARM_and4785_MPFR_plus76shortcuts_not_own_runs=True,pilot3096_and_failed_pre_execution_launcher_excluded=True),
 lineage_correction=dict(R_qualification_targeted_and_qualified_probe_reconstructed=True,
  without_probe223826_plus150qualified_probe_only_equals223976=True,
  lossless_focus_archive_verified=True,uncompressed_bytes=547596,uncompressed_sha256='340318b19b6d4bae44d5317019af900ef06c00e88f1a6e23fb64691a589fc6a2',
  R_qualified_probe_distinct_from_this_packet_unqualified_pilot=True,
  earlier_r5_archive_omission_not_rewritten=True,future_checkpoint_must_preserve_lossless_correction=True),
 resources=dict(source_ASM_allocated_delta_bytes32_includes_RAM16_and_Flash16=True,reserved_scratch4080_unchanged=True,
  no_new_table_global_RAM_libgcc_or_ROM_math_dependency=True,CPP_static_frames_identical=True,
  general_leaf_frame36_dyadic0_wrapper_transient4=True,
  observed_same_corpus_parent_control_candidate_stack2284=True,old_smaller_corpus2236_not_a_frame_regression_comparator=True,
  private_diagnostic_relocated_existing_code_and_data_Flash_bytes=[58256,58272],
  whole_firmware_GC_size_universal_stack_or_physical_cycles_not_measured=True),
 integration_requirements=requirements,reviewed_whole507_preserved=dict(no_slower=422,strict=413,equal=9),
 author436_separate_union_not_promoted=True,evidence=evidence,
 authority=dict(private_component_HOST_GO=True,integration_GO=False,hardware_GO=False,whole_math_or507_GO=False,
  main_release_or_publication_GO=False,goal_complete=False,devices_ports_USB_Git_canonical_network_actions=0),
 remaining='Expanded10853 pow losses, general-pow totality, other operation work, source merge/relink, actual integrated R12 and overlay/loader guards, physical measurement and release remain outside this component acceptance.')
final=save('FINAL-REVIEW.json',review)
assert ref(W/'FROZEN.json')['sha256']=='dd0ec3663009cd390c710611e57ccc23d18c733201911471feae6e52e58e7d1c'
assert ref(W/'candidate.elf')['sha256']=='e94a79c49895a7f5328d8ef0d9185d88fe920a3101433c771e31759fac936d98'
manifest=save('MANIFEST.json',dict(status='SEALED_PRIVATE_COMPONENT_ONLY_REVIEW',files={str(p.relative_to(O)):ref(p)for p in sorted(O.rglob('*'))if p.is_file()}))
for p in O.rglob('*'):
 if p.is_file():p.chmod(0o444)
print(json.dumps(dict(final=final,manifest=manifest,requirements=requirements),indent=2))
