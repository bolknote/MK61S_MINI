"""Assemble the completed evidence; no test or build is rerun here."""
import hashlib,json,struct,sys
from pathlib import Path
sys.dont_write_bytecode=True
R=Path('/Users/bolk/Projects/MK61S_MINI');O=Path(__file__).resolve().parent;W=R/'.build/m0-exp-near-one-20261024';P=R/'.build/m0-exp-directed-product-20261024'
sys.path.insert(0,str(R/'tests'))
from check_stm32_vectors import ElfImage
def ref(p):p=Path(p);data=p.read_bytes();return dict(path=str(p),bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
def save(n,v):
 with (O/n).open('x')as f:json.dump(v,f,indent=2);f.write('\n')
 return ref(O/n)
def load(n):return json.loads((O/n).read_text())
def undefined(im):
 out=set()
 for s in im.sections:
  if s[1]!=2:continue
  strings=im.bytes_at(im.sections[s[6]])
  for off in range(0,s[5],s[9]):
   n,value,size,info,other,index=struct.unpack_from('<IIIBBH',im.bytes_at(s),off)
   if index==0 and n:out.add(im.string(strings,n))
 return out
def allocated_bytes(im):return sum(s[5]for s in im.sections if s[2]&2 and s[1]!=8)
binding=load('binding.json');proof=load('proof.json');bare=load('bare-arm.json');pack=load('pack-arm.json');public=load('public-arm-mpfr.json');guard=load('private-guard-controls.json');account=load('accounting.json')
assert binding['local_count']==167 and binding['external_count']==1389 and binding['own_exact_rebuild_count']==3
assert ref(W/'FROZEN.json')['sha256']=='1e5a757a3116d4803330b0e554ad1dffbe0aea838c7a75126460f79dcf4d5de0'
assert ref(W/'candidate.elf')['sha256']=='e6f2f7e0c55b7d7f2547badb00eacef444a1575eb59bdae7d530eec0ea340fcc'
assert bare['qualified_calls']+pack['qualified_calls']+public['qualified_ARM_calls']==1587
actual={(row['x'],row['SIO']):row for row in public['rows']}
original={row['x']for row in json.loads((W/'original-exp16.json').read_text())['rows']}
assert len(original)==16
for x in original:
 for state in ['READY','DIRTY']:
  row=actual[x,state];assert row['Qfplib_correct']and row['costs']['candidate']<row['costs']['Qfplib']
control,candidate=[ElfImage(W/('RP-'+label+'.o'))for label in ['control','candidate']]
assert undefined(control)==undefined(candidate)
old,new=[ElfImage(W/(label+'.elf'))for label in ['control','candidate']]
load_bytes=[allocated_bytes(old),allocated_bytes(new)]
assert load_bytes==[16648,17784]
flash_bytes=[sum(s[5]for s in im.sections if s[2]&2 and s[1]!=8 and 0x10000000<=s[3]<0x10200000)for im in [old,new]]
assert flash_bytes==[16480,17616]
def frame(path,needle):
 rows=[line for line in path.read_text().splitlines()if needle in line]
 assert len(rows)==1
 return int(rows[0].split('\t')[1])
assert frame(W/'RP-control.su','double mk61_m0_exp(double)')==96
assert frame(O/'rebuild/RP-candidate.su','double mk61_m0_exp(double)')==88
assert frame(O/'rebuild/RP-candidate.su','exp_small_rne(m0_eabi::U)')==72
assert public['observed_stack_bytes']==dict(candidate=808,parent=744)
resources=save('resources.json',dict(status='PASS_PRIVATE_RESOURCE_AND_ISOLATION_RECHECK',
 private_all_allocated_section_bytes=load_bytes,private_Flash_section_bytes=flash_bytes,inherited_RAM_slot_bytes=168,
 private_delta_bytes=1136,undefined_symbol_set_unchanged=True,
 no_new_libgcc_ROM_math_tables_or_BSS=True,shared77_instruction_body154_slot168_padding14_unchanged=True,
 unchanged_existing_ASM_source_count=len(binding['unchanged_ASM_sources']),
 generic_M0_M4soft_hard_selected_objects_unchanged=True,
 static_public_frame=[96,88],new_helper_frame=72,integer_leaf_frame=36,
 observed_public_stack_bytes=dict(parent=744,candidate=808),observed_reference_stack_bytes=32,
 whole_firmware_GC_size_not_measured=True,universal_stack_bound_not_established=True,physical_cycles_not_measured=True))
notes=save('EXECUTION-NOTES.json',dict(status='COMPLETED_CPU_ONLY_REVIEW_EXECUTION_RECORD',
 completed_before_restart=dict(binding_start='174026',binding_completion='a86bff',binding_exit=0,proof='f9d5e4',proof_exit=0),
 guard_and_initial_literal_wrapper=dict(tool='ef541a',exit=1,guard_controls_completed=True,
  cause='Reviewer literal wrapper expected two indentation spaces; frozen producer wrapper contains one. The assertion failed before any unit rebuild or ARM execution.',
  correction='literal_binding.py matches exact wrapper whitespace and resumes only literal binding. Completed guard controls were not rerun.'),
 resumed_literal_binding=dict(tool='05f763',exit=0,two_whole_exact_rebuilds=True),
 initial_seal_aggregation=dict(tool='0ce7d6',exit=1,cause='Reviewer initially compared all allocated sections against the producer Flash-only metric. The unchanged168-byte RAM product slot explains the exact difference.',
  correction='Report both all allocated16648/17784 and Flash-only16480/17616; delta1136 is identical. No evidence had been written by the failed seal attempt and no test was rerun.'),
 own_ARM=dict(bare_tool='891862',pack_tool='55144a',public_tool='e3b77e',all_exit0=True,
  Unicorn_runtime=str(R/'.build/picocalc-apps-arm-venv/bin/python'),Unicorn_JIT='scoped require_escalated CPU-only approved; no rejected/default attempt or installation',
  qualified_calls=1587,directed_MPFR_rounded_inputs=176,sNaN_shortcuts_separate=2,additional_correction_enclosures=138),
 raw_accounting=dict(start='25e4cf',completion='872945',exit=0,ARM_calls=0,MPFR_evaluations=0),
 no_completed_check_repeated_after_technical_restarts=True,physical_IO=0,Git_operations=0,canonical_access=0,network_operations=0))
evidence={n:ref(O/n)for n in ['binding.json','NUMERIC-REVIEW.md','proof.json','private-guard-controls.json','literal-unit-binding.json','bare-arm.json','pack-arm.json','public-arm-mpfr.json','accounting.json','resources.json','EXECUTION-NOTES.json']}
review=dict(
 schema='independent-private-exp-near-one-component-v1',status='TECH_GO_PRIVATE_NEAR_ONE_EXP_COMPONENT_ONLY',reviewer='/root/rtc_helper_review',
 scope='Frozen one-CPP-file RP2040 near-one exp helper/dispatch against independently accepted directed-product parent. No hardware or integrated binary qualification.',
 findings=[],blocking_component_findings=[],accepted_target=binding['accepted_refs'],
 accepted_CPP=ref(W/'candidate/native_eabi_m0.cpp'),accepted_parent_FROZEN=ref(P/'FROZEN.json'),
 provenance=dict(all167_local_and1389_external_hash_size_pins_verified=True,
  one_CPP_patch_byteexact=True,only_new_helper_and_dispatch_added=True,existing_ASM_source_count_unchanged=len(binding['unchanged_ASM_sources']),
  own_entire_RP_object_product_object_ELF_rebuilds=3,own_literal_pack_object_ELF_rebuilds=2,
  all_five_complete_artifacts_byteexact=True,author_eleven_rebuilds_verified_as_saved_evidence_not_own_runs=True,
  all_other_CPP_allocated_bytes_semantic_relocations_BSS_unchanged=True),
 numeric_proof=dict(new_domain_e=[-32,-12],new_magnitude_domain='2^-32 <= |x| < 2^-11',
  exact_linear_significand_retained=True,source_Q16_nonlinear_correction_enclosure=True,
  high_product_six_retained_terms_error_bound=proof['high_product_absolute_bound'],middle_nine_terms_error_in_open_minus3_to0=True,
  square_six_MULS_exact_floor_Xsquare_shift38to58=True,first_non_ADC_add_strict32bit_bound=proof['first_non_ADC_column4_add_max'],
  Horner_Q48_strict4=proof['horner_Q48_error'],other_error_strict27=proof['remaining_rounding_square_and_Taylor_error'],
  coarse_fifth_all64_class_binade_intervals=True,division_full242295_value_domain_proved_algebraically=True,
  error_guard='E=4*floor(Z/2^48)+32+extra+fifth_error',maximum_E=5148,
  all_product_domains_unsigned_carries_and_variable_shift_ranges_checked=True,
  all_three_actual_pack_branches_bound_to_literal_source=True,
  rounding='Strict enclosure plus exact modular midpoint veto proves every admitted result RNE. Declines use unchanged accepted refinement.',
  exact_IEEE_tiny_endpoints_tables_and_refinement_inherited_by_source_object_relocation_binding=True),
 fresh_bounded_checks=dict(qualified_actual_ARM_calls=1587,
  bare_integer_calls=267,bare_products_pairs30_square_pairs63=True,all16_incoming_NZCV_on3_adversarial_triples=True,
  actual_leaf_instruction_counts=[45,62,47],actual_leaf_frame36=True,
  literal_pack_calls=252,pack_accepted=168,pack_declined=84,unsafe_admissions=0,all21binades_signs_and3branches=True,
  public_exp_inputs=178,public_calls=1068,public_candidate_parent_Qfplib_bothSIO=True,
  directed_MPFR_rounded_inputs=176,sNaN_shortcuts_separate=2,MPFR_version='4.2.2',
  additional256bit_directed_correction_enclosures=138,small_model_fast134_declined4=True,
  original16_exact_source_IDs_both_states_strict=True,old_new_bits_identical_on_bounded_inputs=True,
  DIRTY28byte_preservation_and_READY_not_DIRTY_checked=True,R4_R11_SP_checked_each_call=True,
  captured_ROM_initializers_executed_but_excluded_from_qualified_calls=True,no_arithmetic_ROM_models=True),
 private_R12_contract=dict(shared77_product_168byte_slot_unchanged=True,scalar_C_ABI_does_not_supply_extra_result=True,
  fresh_actual_private_linked_ELF_guard_PASS=True,private_ELF_sha256=ref(W/'candidate.elf')['sha256'],
  real_Flash_tail_veneer_bytes16=True,two_postcall_stores_before_zero_byte_marker=True,marker_to_actual_consumer_live_instructions88=True,
  all17_negative_production_AST_controls_PASS=True,
  mandatory_integration_requirement='Install/adapt and rerun the producer/veneer/postcall-marker/consumer guard on every changed actual integrated ELF, fresh linked disassembly, compiler and flags. A private unit ELF, scalar prototype or stale receipt cannot qualify integration.',
  integration_approval=False),
 frozen_corpus_accounting=dict(read_only_saved_records_recount=True,fresh_ARM_or_MPFR_for_recount=0,
  old467366_losses=[1896,196],same_inputs_fixed1700=True,union490031_remaining214_equals196old_plus18new_preexisting=True,
  all428_remaining_state_rows_parent_bound=True,new_measured_speed_losses=0,
  all_old934732_candidate_raw_bits_expected_and_Qfp_cost_rows_preserved=True,
  correct_Qfplib_state_comparison=account['correct_Qfplib_comparison'],wrong_Qfplib_state_rows_retained=407820,
  all5712_parent_cost_increase_rows_retained=True,positive_instruction_deltas=account['positive_deltas'],cost_increase_scopes=account['cost_increase_scopes'],
  original16_both_states_strict_from_saved_raw=True,no_nominal_domain_filter=True,
  author_fresh_ARM1203570_and_MPFR490029_not_own_runs=True,probes_and_rejected_trials_not_pooled=True),
 resources=dict(private_Flash_section_bytes=[16480,17616],all_allocated_section_bytes=[16648,17784],inherited_RAM_slot_bytes168=True,
  code_increase1136=True,static_public_frame=[96,88],new_helper_frame72=True,
  observed_peak_stack_parent744_candidate808=True,no_universal_stack_physical_cycle_or_whole_firmware_GC_size_claim=True),
 whole507=dict(reviewed_ledger_preserved=dict(no_slower=422,strictly_faster=413,equal=9),
  author_separate423_union_not_promoted=True,not_one_integrated_binary=True,other_math_qualifications_inherited_not_fresh=True),
 evidence=evidence,
 authority=dict(private_component_HOST_GO=True,integration_GO=False,whole_math_or507_GO=False,hardware_GO=False,
  main_release_or_publication_GO=False,canonical_changes=False,goal_complete=False),
 remaining='214 expanded exp losses, separate other-operation work, combined integration, required actual linked R12 guard, general totality/FMA/regression, physical measurements and release remain outside this component acceptance.'
)
final=save('FINAL-REVIEW.json',review)
recheck=save('final-seal-recheck.json',dict(status='PASS_FINAL_FROZEN_INPUT_RECHECK',
 FROZEN=ref(W/'FROZEN.json'),result=ref(W/'result.json'),HANDOFF=ref(W/'HANDOFF.md'),candidate_ELF=ref(W/'candidate.elf'),
 inputs_and_completed_outputs_not_modified=True))
files={str(p.relative_to(O)):ref(p)for p in sorted(O.rglob('*'))if p.is_file()}
manifest=save('MANIFEST.json',dict(status='SEALED_PRIVATE_COMPONENT_REVIEW_ONLY',files=files))
for p in O.rglob('*'):
 if p.is_file():p.chmod(0o444)
print(json.dumps(dict(final=final,manifest=manifest,recheck=recheck),indent=2))
