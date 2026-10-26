from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,shutil,struct,subprocess
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
C=ROOT/'.build/m0-exp-dyadic-product-20261024'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
load=lambda p:json.loads(p.read_text())
assert not (W/'FROZEN.json').exists()
b=load(W/'build.json');q=load(W/'qualification.json');a=load(W/'remaining-parent-audit.json')
u=load(W/'unit-proof.json');g=load(W/'direction-unit-proof.json');flags=load(W/'product-flags-proof.json')
c=load(W/'caller-proof.json');p=load(W/'pow-loss-replay.json');i=load(W/'isolation-rebuild.json')
cert=load(W/'certificate.json');abi=load(W/'private-return-proof.json');fixed=load(W/'same-corpus-fixed11.json')
original=load(W/'original-exp16.json');frame=load(W/'refine-and-frame-binding.json')
assert b['candidate_ELF_sha256']==q['candidate_ELF_sha256']==a['candidate_ELF_sha256']==c['candidate_ELF_sha256']==abi['candidate_ELF_sha256']==sha(W/'candidate.elf')
assert b['source_sha256']==q['source_sha256']==cert['source_sha256']==abi['source_sha256']==sha(W/'candidate/native_eabi_m0.cpp')
assert b['required_postbuild_private_return_guard'] is True
assert cert['private_return_proof_sha256']==sha(W/'private-return-proof.json')
assert abi['all_post_call_paths_reach_marker_before_R12_write_call_or_return']
assert len(abi['call_to_marker_instructions'])==2
assert q['unique_inputs']==467366 and q['profiled_states']==934732
assert q['wrong']==q['new_known_parent_raw_losses']==a['new_raw_losses']==a['wrong']==0
assert [q['old456750_parent_raw_losses'],q['old456750_candidate_raw_losses']]==[1541,1530]
assert q['union_candidate_raw_losses']==1896 and q['old48763_candidate_raw_losses']==88
assert q['historical_exp16_remaining']==0 and q['tiny_correct_reference_raw_losses']==0
assert fixed['fixed_inputs']==11 and fixed['state_rows']==22
assert original['input_count']==16 and original['state_rows']==32
assert a['fresh_parent_ARM_calls']==732 and a['all_remaining_parent_states_now_bound']
assert u['product']['raw64_pairs']==70660 and u['product']['wrong']==0
assert u['product']['instruction_counts']=={'old':{'79':70660},'new':{'77':70660}}
assert u['product']['stack_bytes']=={'old':36,'new':36}
assert u['product']['stack_bytes_touched']=={'old':36,'new':36}
assert g['actual_ARM_calls']==275672 and g['unsafe_admissions']==0
assert flags['fresh_ARM_calls']==2048 and flags['initial_NZCV_variants']==16
assert p['remaining_pairs_after']==7901 and p['fixed_pairs']==0 and p['new_raw_losses']==0
assert p['fresh_candidate_state_calls']==10081 and p['current_parent_losing_reference_state_variants']==10078
assert {op:v['candidate_slower_raw'] for op,v in c['summary'].items()}=={'pow':48,'sin':22,'cos':14}
assert len(i['records'])==11 and b['CPP_code_delta_bytes']==120
assert frame['public_static_frame_bytes']==96
assert sha(W/'qualification-records.jsonl.gz')==q['qualification_records_sha256']
assert not subprocess.check_output(['git','diff','HEAD','--name-only','--','code/native_eabi_m0*'],cwd=ROOT,text=True).strip()
for r in i['records']:assert sha(W/r['original'])==r['sha256'],r['original']

external={}
def pin(path,expected=None):
 path=Path(path);value=dict(sha256=sha(path),bytes=path.stat().st_size)
 if expected:assert value==expected,str(path)
 name=str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)
 assert name not in external or external[name]==value
 external[name]=value
for name,value in load(C/'FROZEN.json')['files'].items():pin(C/name,value)
pin(C/'FROZEN.json')
for name,value in load(C/'source-lineage-pins.json')['files'].items():pin(ROOT/name,value)
pin(ROOT/'.build/m0-exp-dyadic-product-postseal-20261024.json')
review_path=ROOT/'.build/m0-exp-dyadic-product-independent-20261024/FINAL-REVIEW.json'
review=load(review_path);assert review['status']=='GO_PRIVATE_RP_DYADIC_EXP_AND_SHARED79_PRODUCT_COMPONENT_ONLY' and review['blockers']==[]
assert sha(review_path)=='c6aef2f9683f8d234f850363cbfda7f687d65c7ba9581987b723a14db37c536a'
refs={}
def collect(value):
 if isinstance(value,dict):
  if all(k in value for k in ('path','bytes','sha256')):
   meta={k:value[k] for k in ('bytes','sha256')}
   assert value['path'] not in refs or refs[value['path']]==meta
   refs[value['path']]=meta
  for v in value.values():collect(v)
 elif isinstance(value,list):
  for v in value:collect(v)
collect(review)
for name,value in refs.items():pin(name,value)
pin(review_path);assert len(refs)==58
pin(ROOT/'.build/m0-exp-adaptive-enclosure-independent-20261024/FINAL-REVIEW.json')
pin(ROOT/'tools/certify_m0_exp_fast.py')
parent_review=load(W/'verified-dyadic-review.json')
fresh=q['fresh_ARM_calls']+a['fresh_parent_ARM_calls']+u['total_actual_ARM_calls']+g['actual_ARM_calls']+flags['fresh_ARM_calls']+c['fresh_ARM_calls']+p['fresh_candidate_state_calls']
assert fresh==1386951
actual_MPFR=q['actual_directed_MPFR_input_conversions']+c['actual_directed_MPFR_inputs'];assert actual_MPFR==467553
examples={r['x']:dict(parent=r['parent_instructions'],candidate=r['candidate_instructions'],Qfplib=r['Qfplib_instructions']) for r in load(W/'selected-examples.json')['rows'] if r['SIO']=='READY'}
assert examples['4085F424184F6DC5']==dict(parent=2266,candidate=612,Qfplib=649)
pow_ties=[r for r in c['rows'] if r['operation']=='pow' and r['SIO']=='READY' and r['instructions']['parent']==r['instructions']['Qfplib'] and r['instructions']['candidate']<r['instructions']['Qfplib']]
assert len(pow_ties)==3
def loads(path):
 data=path.read_bytes();off=struct.unpack_from('<I',data,28)[0];size,count=struct.unpack_from('<HH',data,42)
 return [struct.unpack_from('<8I',data,off+k*size) for k in range(count)]
before,after=loads(C/'candidate.elf'),loads(W/'candidate.elf')
assert [row[4] for row in before if row[0]==1]==[16360,168]
assert [row[4] for row in after if row[0]==1]==[16480,168]
result=dict(status='FROZEN_AUTHOR_DIRECTED_EXP_ENCLOSURE_AND_77_INSTRUCTION_PRODUCT_ALL_ORIGINAL_EXP16_STRICT',
 accepted_source_parent=str(C.relative_to(ROOT)),accepted_source_parent_FROZEN_sha256=sha(C/'FROZEN.json'),accepted_parent_review=parent_review,
 source_sha256=b['source_sha256'],product_include_sha256=b['product_include_sha256'],candidate_ELF_sha256=b['candidate_ELF_sha256'],
 public_exp_unique_inputs=q['unique_inputs'],public_exp_state_rows=q['profiled_states'],
 fresh_public_exp_candidate_ARM_calls=q['fresh_candidate_ARM_calls'],fresh_new_Qfplib_ARM_calls=q['fresh_Qfplib_ARM_calls'],
 fresh_exp_parent_audit_ARM_calls=a['fresh_parent_ARM_calls'],qualified_bare_product_ARM_calls_bound_by_actual_byte_identity=u['total_actual_ARM_calls'],
 fresh_literal_directional_gate_ARM_calls=g['actual_ARM_calls'],fresh_all16NZCV_product_ARM_calls=flags['fresh_ARM_calls'],
 fresh_other_caller_ARM_calls=c['fresh_ARM_calls'],fresh_expanded_pow_replay_ARM_calls=p['fresh_candidate_state_calls'],total_qualified_fresh_ARM_calls=fresh,
 actual_directed_MPFR_exp_inputs=q['actual_directed_MPFR_input_conversions'],actual_directed_MPFR_other_caller_inputs=c['actual_directed_MPFR_inputs'],
 total_actual_directed_MPFR_validation_inputs=actual_MPFR,validation_oracle_evaluations=actual_MPFR+2,sNaN_shortcuts_without_MPFR=2,
 MPFR_version=q['MPFR_version'],separate_directed_MPFR_log_preimage_generations_not_validation=1919,
 inherited913500_exp_parent_Qfplib_rows_not_fresh=True,inherited_full111912_pow_pair_MPFR_references_not_fresh=True,
 all_public_probes_diagnostics_rejected_layouts_and_initial10081_pow_scope_counter_run_excluded=True,
 wrong=0,all_old456750_public_exp_return_bits_identical=True,
 all_domain_source_bound_for_new_directional_normal_error4_tail511_positive_below_acceptance=True,
 exact_coefficient_reduction_curvature_rounding_and_signed_Q94_bias_proof=True,all512_Q62_Q94_table_roots_recertified=True,
 literal_directional_gate_unit_cases=275672,unsafe_unit_admissions=0,
 private_R12_result_is_not_generic_scalar_C_ABI=True,
 required_linked_code_call_to_capture_marker_audit_passed=True,component_builder_runs_required_audit_automatically=True,
 marker_allocated_bytes=0,actual_post_call_instructions_before_marker=2,
 original_real16byte_Flash_to_RAM_tail_veneer_unchanged=True,required_again_after_every_changed_release_object=True,
 integration_must_install_guard_against_its_actual_linked_image=True,
 same_old456750_exp_losses=[1541,1530],same_old_inputs_fixed=11,same_older48763_exp_losses=[96,88],
 expanded467366_exp_losses=1896,
 expanded_count_scope='Same456750:1541->1530,11fixed. New467366 union1896=1530old+366new controls(347small preimages,11positive normal preimages,3table-row,3uniform,2broad endpoint), all already lost in accepted parent. Do not subtract different-size corpus counts.',
 all1896remaining_exp_losses_parent_bound=True,new_raw_speed_losses=0,
 correct_Qfplib_comparison=q['correct_Qfplib_comparison'],wrong_Qfplib_state_rows_retained=q['wrong_Qfplib_state_rows_retained'],no_nominal_domain_filter=True,
 public_examples=examples,original_exp16_remaining=[1,0],all_original_exp16_both_states_strictly_faster_than_correct_Qfplib=True,
 retained_exp_parent_cost_increase_state_rows=3448,retained_increase_deltas={1:3348,2:34,4:6,5:22,7:34,50:4},
 increase_scope=dict(already_losing_correct_Qfplib=1392,wrong_Qfplib=2022,still_no_slower_correct_Qfplib=34),
 shared_product_fixed_instructions=[79,77],shared_product_active_bytes=[158,154],shared_product_RAM_slot_bytes=[168,168],outside_function_padding_bytes=14,
 shared_product_all_raw64_return_value_and_PCS_equivalence_source_proof=True,retained_product_fraction_R12_extra_return_source_proof=True,
 bare_product_pairs=70660,valid63x54_exact_integer_product_oracles=36781,raw_retained_fraction_checks=70660,
 all16_incoming_NZCV_variants_and_arbitrary_initial_R12_checked=True,product_stack_frame_bytes=[36,36],product_stack_written_bytes=[36,36],
 original_other_callers_summary=c['summary'],original_pow_remaining_unchanged=48,prior_three_original_pow_ties_now_strict=pow_ties,
 expanded_pow_remaining_unchanged=7901,
 pow_replay_scope='10085historical reference-state variants including accepted-parent ties,10078currently-losing reference-state variants,10081distinct fresh candidate calls. Current7901losing raw pairs remain7901. Three prior raw-pair ties now strict, not new fixed losses. All costs parent minus2per actual product call; full111912-pair references inherited, no freshMPFR/full reacquisition.',
 selected_CPP_code_delta_bytes=120,selected_ASM_allocated_delta_bytes=0,private_Flash_overlay_load_delta_bytes=120,
 whole_firmware_size_and_GC_delta_not_measured=True,no_new_tables_global_RAM_libgcc_ROM_math_or_external_runtime_dependencies=True,
 public_exp_static_frame96_unchanged=True,observed_full_public_exp_stack_bytes=744,universal_full_math_stack_or_physical_cycle_bound_not_claimed=True,
 refinement3736bytes_13relocations_and_tiny472byte_helper_identical=True,
 all_other_CPP_allocated_bytes_semantic_relocations_unchanged=True,all_RP_ASM_outside168byte_slot_bytes_relocations_symbol_addresses_identical=True,
 generic_M0_M4_soft_hard_selected_CPP_and_ASM_equal=True,eleven_complete_object_ELF_rebuilds_byte_exact=True,
 direct_public_ABI_and_original_RAM_address_preserved=True,
 original507_author_separate_union=dict(no_slower=423,strictly_faster=417,equal=6,remaining=84,by_operation=dict(pow=48,exp=0,sin=22,cos=14),not_one_integrated_binary=True),
 original507_independently_reviewed_union_unchanged=422,independent_review_pending=True,
 combined_integration_regression_FMA_general_totality_physical_cycles_and_release_pending=True,
 no_canonical_Git_USB_device_Flash_lease_EA9_or_release_changes=True,goal_complete=False)
(W/'result.json').write_text(json.dumps(result,indent=2)+'\n')
handoff=f'''Private RP2040 directed exp enclosure and77-instruction shared product.
Accepted parent is dyadic acdaac62, independent GOc6aef2f9;58unique direct
refs verified,59with receipt. New component independent review pending.

All original16exp cases are now strictly faster than correct Qfplib in both
SIO states. Last positive4085F424184F6DC5:2266->612vs649; prior hard negative
596->593vs622. Same456750corpus1541->1530loss inputs,11fixed. New467366union
1896=1530old+366new controls(347small/11positive normal/3table-row/3uniform/
2broad endpoint), every loss parent-bound,0new. Different-size corpus counts
must not be subtracted. Same older48763:96->88.0wrong, every old456750raw
return identical. All394356wrong-Qfplibstate outputs/costs retained; no
nominal-domain filter.3448parent state increases retained(+1,+2,+4,+5,+7,
+50);1392already lost,2022wrong-reference,34still no slower than correctQfp.

New normal error4/tail511/positive-input/negative-displacement predicate uses
the signed reduction fraction, negative polynomial truncation direction and
exact retained product fraction. NUMERIC-PROOF.md/certificate.json establish
the strict upper to the midpoint throughout the qualifying source domain;
all512Q62/Q94 roots/biases re-certified.275672literal ARM unit calls against
an independent exact rational enclosure:215856accept/59816reject,0unsafe.
Other error radii/gates/refinement/endpoints/IEEE policies are unchanged.

Arithmetic register renaming removes3copies and adds MOVr12,r4 before the
rounding shift:79->77fixed instructions for every raw pair. ReturnP/PCS
equivalent; R12additionally carries retained F. Active158->154B,14outside
NOP bytes keep168B RAM slot and every later address. Frame/touched36same.
70660raw-pair old/new bare tests,36781valid exact integer products and70660
exact F checks,141320calls. This bare kernel was tested with rejected R1CPP
layout but its actual bytes are identical to final full-source/unit/public
slot, explicitly bound; no claim of a freshR9repeat.2048additional fresh
calls cover all16NZCV variants and arbitrary incomingR12,0wrong/ABI failure.

The extra R12result is a private producer/consumer contract beyond the scalar
C ABI. The zero-byte hidden global marker locates its C++ asm definition.
verify-private-return.py proves the real16B tail veneer restoresr0/SP and
BXes to RAM without changingLR; the producer returns directly to the caller.
Exactly two STRs occur between its BLreturn and the marker, with no R12write
or intervening call on any path. The component builder runs this REQUIRED
audit automatically. It must be installed/rerun on every changed integrated
release object; no generic future-compiler/flags C-ABI guarantee is claimed.
The marker adds0bytes/instructions; no artificial timed veneer or arithmetic
mock is introduced. Verifier reruns are read-only after this packet is sealed.

Other callers189originalpow/sin/cos jobs:1134freshARM/189actualMPFR, all raw
values/argument traces identical andminus2per product call. Pow original48
remain;3prior ties become strict1342vs1344/1318vs1320/1309vs1311. Sin22/cos14
original gaps unchanged. Pow replay:10085historical reference-state variants
(10078currently losing),10081fresh distinct state calls,7901raw loss pairs
remain7901,0new. This includes old3ties to verify strict improvement, not new
fixed losses. Full111912pair oracle/reference data inherited, no freshMPFR/
full reacquisition. Other old nonlosses cannot regress by monotone callee
equivalence. An initial10081call replay had a summary-scope counter mistake;
all numerical loops passed, final clean repeat corrects the counter, initial
calls excluded. Rejected/diagnostic/probe runs are excluded; see notes/logs.

Exp467366inputs/934732states:934732fresh candidate+21232fresh Qfp+732parent
audit calls.913500old baseline rows inherited/not new.467364actualdirected
MPFR exp inputs+2sNaN shortcuts;1919log generations separate from validation.
Total qualified freshARM{fresh}=955964main+732parent+141320bare+275672gate+
2048flags+1134callers+10081pow. Actual directedMPFRvalidation{actual_MPFR}
=467364exp+189callers, plus2sNaNshortcuts. Independent-parent reviewer counts
are not pooled into these totals.

CPP core5088->5208(+120), privateFlashload16360->16480(+120), RAMslot168same;
no new tables/globalRAM/libgcc/ROMmath. Staticcore96same, observed exp744.
Existing3736refine bytes/13relocs and472tiny helper unchanged. All other CPP
allocated bytes/semantic relocs and allRPASM outside productslot bytes/relocs/
symbol addresses identical. Selected genericM0/M4soft/hard CPP+ASM equal;
11completeobject/ELF rebuilds byte-exact. OriginalRAMaddress/directpublicABI
kept. Two-file patch, no build-list/canonical/integration/device changes.

Author original507separate union423=417strict+6equal;84remain(pow48/sin22/
cos14,exp0). Reviewed422unchanged pending this review. Expandedexp1896/pow7901/
ln5, FMA acceptance, generalpow/exp totality, combined integration/regression,
mandatory integrated R12guard, physicalcycles and release remain OPEN. No
canonical/Git/USB/device/Flash/lease/EA9/release mutations; goal stays active.
'''
(W/'HANDOFF.md').write_text(handoff)
notes=load(W/'VALIDATION-NOTES.json')
notes['initial_pow_replay_scope_counter']+=' Final clean replay completed:7901remaining,0new fixed raw pairs,0new losses;10085source variants/10078current losing variants/10081fresh states.'
(W/'VALIDATION-NOTES.json').write_text(json.dumps(notes,indent=2)+'\n')
scope=load(W/'WORK-SCOPE.json');scope['status_at_creation']=scope.pop('status');scope['status_at_seal']='FROZEN_AUTHOR_QUALIFIED_PENDING_REVIEW';scope['source_parent_review_pending_at_creation']=scope.pop('source_parent_review_pending');scope['source_parent_review_at_seal']=parent_review
(W/'WORK-SCOPE.json').write_text(json.dumps(scope,indent=2)+'\n')
logs=W/'logs';logs.mkdir(exist_ok=True)
for path in (ROOT/'.build').glob('m0-exp-directed-*-20261024.log'):
 if 'finalize' not in path.name:shutil.copyfile(path,logs/path.name)
(W/'source-lineage-pins.json').write_text(json.dumps(dict(status='PINNED_ACCEPTED_DYADIC_PARENT_REVIEW_AND_ALL_PRIOR_LINEAGE',files=external),indent=2)+'\n')
files={str(path.relative_to(W)):dict(sha256=sha(path),bytes=path.stat().st_size) for path in sorted(W.rglob('*')) if path.is_file() and '__pycache__' not in path.parts}
sealed=dict(status='FROZEN_PRIVATE_AUTHOR_DIRECTED_EXP_AND_SHARED77_PRODUCT_PENDING_REVIEW',files=files,
 utc=datetime.now(timezone.utc).isoformat(),result_sha256=sha(W/'result.json'),HANDOFF_sha256=sha(W/'HANDOFF.md'),
 HEAD_at_seal=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),math_worktree_diff_empty=True,goal_complete=False)
(W/'FROZEN.json').write_text(json.dumps(sealed,indent=2)+'\n')
print(json.dumps(dict(status=sealed['status'],artifacts=len(files),external_lineage_pins=len(external),FROZEN_sha256=sha(W/'FROZEN.json'),
 result_sha256=sealed['result_sha256'],HANDOFF_sha256=sealed['HANDOFF_sha256'],candidate_ELF_sha256=b['candidate_ELF_sha256'],fresh_qualified_ARM=fresh,
 same_old_exp_losses=[1541,1530],expanded_exp1896=True,original_exp16_remaining=0,pow_remaining7901=True),indent=2))
