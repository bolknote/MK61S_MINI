from pathlib import Path
import hashlib,json,struct,subprocess,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
D=ROOT/'.build/m0-exp-adaptive-enclosure-20261024'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
load=lambda p:json.loads(p.read_text())
assert not (W/'FROZEN.json').exists()
b=load(W/'build.json');q=load(W/'qualification.json');a=load(W/'remaining-parent-audit.json')
u=load(W/'unit-proof.json');du=load(W/'dyadic-unit-proof.json');c=load(W/'caller-proof.json')
p=load(W/'pow-loss-replay.json');i=load(W/'isolation-rebuild.json');cert=load(W/'certificate.json')
fixed=load(W/'same-corpus-fixed547.json');frame=load(W/'refine-and-core-frame-binding.json')
assert b['candidate_ELF_sha256']==q['candidate_ELF_sha256']==a['candidate_ELF_sha256']==c['candidate_ELF_sha256']==sha(W/'candidate.elf')
assert b['source_sha256']==q['source_sha256']==cert['source_sha256']==sha(W/'candidate/native_eabi_m0.cpp')
assert q['unique_inputs']==456750 and q['profiled_states']==913500
assert q['wrong']==q['new_known_parent_raw_losses']==a['new_raw_losses']==a['wrong']==0
assert [q['old440007_parent_raw_losses'],q['old440007_candidate_raw_losses']]==[2023,1476]
assert q['union_candidate_raw_losses']==1541 and q['old48763_candidate_raw_losses']==96
assert q['historical_exp16_remaining']==1 and q['tiny_correct_reference_raw_losses']==0
assert fixed['fixed_inputs']==547 and fixed['state_rows']==1094
assert a['fresh_parent_ARM_calls']==130 and a['all_remaining_parent_states_now_bound']
assert u['product']['raw64_pairs']==70660 and u['product']['wrong']==0
assert u['product']['instruction_counts']=={'old':{'81':70660},'new':{'79':70660}}
assert u['product']['stack_bytes']=={'old':40,'new':36}
assert u['product']['stack_bytes_touched']=={'old':36,'new':36}
assert du['actual_ARM_calls']==70094 and du['wrong']==0
assert p['remaining_pairs_after']==7901 and p['fixed_pairs']==3 and p['new_raw_losses']==0
assert p['fresh_candidate_state_calls']==10081
assert {op:v['candidate_slower_raw'] for op,v in c['summary'].items()}=={'pow':48,'sin':22,'cos':14}
assert len(i['records'])==11 and b['CPP_code_delta_bytes']==24
assert frame['push_saved20_plus_alloc76_frame_bytes']==96
assert sha(W/'qualification-records.jsonl.gz')==q['qualification_records_sha256']
assert not subprocess.check_output(['git','diff','HEAD','--name-only','--','code/native_eabi_m0*'],cwd=ROOT,text=True).strip()
external={}
def pin(path,expected=None):
 path=Path(path);value=dict(sha256=sha(path),bytes=path.stat().st_size)
 if expected:assert value==expected,str(path)
 name=str(path.relative_to(ROOT));assert name not in external or external[name]==value
 external[name]=value
for name,value in load(D/'FROZEN.json')['files'].items():pin(D/name,value)
pin(D/'FROZEN.json')
for name,value in load(D/'source-lineage-pins.json')['files'].items():pin(ROOT/name,value)
pin(ROOT/'.build/m0-exp-adaptive-enclosure-postseal-20261024.json')
pin(ROOT/'tools/certify_m0_exp_fast.py')
ancestor_review=load(D/'accepted-parent-review.json')
assert ancestor_review['sha256']=='bdaba8cf9bbe58c8e36dafe9b8f904eb8428fdd42db0abb070b5f4a42e472554'
fresh=q['fresh_ARM_calls']+a['fresh_parent_ARM_calls']+u['total_actual_ARM_calls']+du['actual_ARM_calls']+c['fresh_ARM_calls']+p['fresh_candidate_state_calls']
assert fresh==1169745
actualMPFR=q['actual_directed_MPFR_input_conversions']+c['actual_directed_MPFR_inputs']
assert actualMPFR==456937
result=dict(status='FROZEN_AUTHOR_DYADIC_EXP_EXACT_PRODUCT_AND_SHARED_79_INSTRUCTION_LEAF',
 qualified_source_parent=str(D.relative_to(ROOT)),source_parent_FROZEN_sha256=sha(D/'FROZEN.json'),
 source_parent_independent_review_pending=True,accepted_log_midpoint_ancestor_review=ancestor_review,
 source_sha256=b['source_sha256'],product_include_sha256=b['product_include_sha256'],candidate_ELF_sha256=b['candidate_ELF_sha256'],
 public_exp_unique_inputs=q['unique_inputs'],public_exp_state_rows=q['profiled_states'],
 fresh_public_exp_candidate_ARM_calls=q['fresh_candidate_ARM_calls'],fresh_new_Qfplib_ARM_calls=q['fresh_Qfplib_ARM_calls'],
 fresh_exp_parent_audit_ARM_calls=a['fresh_parent_ARM_calls'],fresh_bare_product_ARM_calls=u['total_actual_ARM_calls'],
 fresh_literal_dyadic_ARM_calls=du['actual_ARM_calls'],fresh_other_caller_ARM_calls=c['fresh_ARM_calls'],
 fresh_expanded_pow_losing_state_ARM_calls=p['fresh_candidate_state_calls'],total_qualified_fresh_ARM_calls=fresh,
 actual_directed_MPFR_exp_inputs=q['actual_directed_MPFR_input_conversions'],actual_directed_MPFR_other_caller_inputs=c['actual_directed_MPFR_inputs'],
 total_actual_directed_MPFR_validation_inputs=actualMPFR,validation_oracle_evaluations=actualMPFR+2,sNaN_shortcuts_without_MPFR=2,
 MPFR_version=q['MPFR_version'],separate_MPFR_log_preimage_generations8404_not_validation=True,
 old880014_exp_parent_Qfplib_rows_inherited_not_fresh=True,old_full111912_pow_pair_expected_outputs_and_reference_costs_inherited=True,
 probe40494_margin336_initial_failed_units141320_excluded_from_qualified_counts=True,
 wrong=0,all_old440007_public_exp_return_bits_identical=True,exact_shift_source_proof_all_valid_index0_displacements=True,
 all_numeric_admission_gates_error_radii_and_IEEE_policy_unchanged=True,
 same_old440007_exp_losses=[2023,1476],same_old_inputs_fixed=547,same_older48763_exp_losses=[126,96],
 expanded456750_exp_losses=1541,expanded_count_scope='Same440007:2023->1476,547fixed. New456750 union1541=1476old+65new controls (53dyadic,12uniform), all losses preexisting in parent. Different-size corpus counts must not be subtracted.',
 all1541remaining_exp_losses_parent_bound=True,new_raw_speed_losses=0,
 correct_Qfplib_comparison=q['correct_Qfplib_comparison'],wrong_Qfplib_state_rows_retained=q['wrong_Qfplib_state_rows_retained'],no_nominal_domain_filter=True,
 public_examples={'3DF0000000000000':dict(parent=520,candidate=439,Qfplib=471),'BDF0000000000000':dict(parent=542,candidate=461,Qfplib=520),
 'C041265824E2113C':dict(parent=599,candidate=596,Qfplib=622),'4085F424184F6DC5':dict(parent=2264,candidate=2266,Qfplib=649)},
 original_exp16_remaining=1,retained_exp_parent_cost_increase_states=13222,retained_exp_cost_increase=2,
 increase_scope=dict(already_losing_correct_Qfplib=200,wrong_Qfplib=11950,still_no_slower_correct_Qfplib=1072),
 shared_product_fixed_instructions=[81,79],shared_product_active_bytes=[162,158],shared_product_RAM_slot_bytes=[168,168],outside_function_Nop_bytes=10,
 shared_product_all_raw64_value_ABI_equivalent_source_proof=True,bare_product_pairs=70660,valid63x54_integer_product_oracles=36781,
 shared_product_stack_frame_bytes=[40,36],shared_product_stack_written_bytes=[36,36],
 literal_dyadic_independent128bit_integer_product_unit_cases=70094,literal_dyadic_instructions=9,
 original_other_callers_summary=c['summary'],original_pow_remaining=[51,48],new_original_pow3_equal_to_Qfplib=True,
 expanded_pow_remaining=[7904,7901],pow_loss_replay_scope='All10085previous losing reference-state variants,10081distinct fresh candidate calls; every call parent minus2per actual product call. Same111912-pair corpus inherited. No freshMPFR/full111912-pair acquisition. Value/ABI equivalence and fixed cost reduction prove other previous nonloss states cannot regress.',
 selected_CPP_code_delta_bytes=24,selected_ASM_allocated_delta_bytes=0,private_Flash_overlay_load_delta_bytes=24,
 whole_firmware_size_and_GC_delta_not_measured=True,no_new_tables_global_RAM_libgcc_ROM_math_or_external_calls=True,
 static_exp_core_frame96_unchanged=True,observed_full_public_exp_stack_bytes=744,universal_stack_or_physical_cycle_bound_not_claimed=True,
 refinement3736bytes_and_tiny472byte_helper_identical=True,all_other_CPP_allocated_bytes_semantic_relocations_unchanged=True,
 all_RP_ASM_outside168byte_slot_bytes_relocations_symbol_addresses_identical=True,
 generic_M0_M4_soft_hard_selected_CPP_and_ASM_equal=True,eleven_complete_object_ELF_rebuilds_byte_exact=True,
 direct_public_ABI_original_RAM_address_and_Flash_wrapper_preserved=True,
 original507_author_separate_union=dict(no_slower=422,strictly_faster=413,equal=9,remaining=85,by_operation=dict(pow=48,exp=1,sin=22,cos=14),not_one_integrated_binary=True),
 original507_independently_reviewed_union_unchanged=418,independent_review_pending=True,
 combined_integration_regression_physical_cycles_totality_and_release_pending=True,
 no_canonical_Git_USB_device_Flash_lease_EA9_or_release_changes=True,goal_complete=False)
(W/'result.json').write_text(json.dumps(result,indent=2)+'\n')
handoff=f'''Private RP2040 exact dyadic exp product and79-instruction shared leaf.
Source parent .build/m0-exp-adaptive-enclosure-20261024 is frozen de974c59;
its independent review and this child's review remain pending. The accepted
log-midpoint ancestor bdaba8cf receipt is pinned unchanged. No hardware GO.

Row0 has A=2^62 exactly, all omitted terms zero: the old rounded product is
(|delta|+2)>>2 for every valid displacement. The re-evaluated source bound
proves |delta|+2<2^54. No error radius, gate, endpoint, refinement or IEEE
policy changes. NUMERIC-PROOF.md/certificate.json bind the full source.
70094 literal ARM unit cases use exact128-bit integer product references.

The shared leaf removes SUBsp4/ADDr3,4; argument base and saved registers
retain identical absolute addresses.144 arithmetic bytes and finalPOP are
identical; epilogue ADDsp20->16 restores the same SP and registers. All raw
returns/ABI equivalent.81->79 fixed instructions, active162->158B, allocated
168B slot unchanged with10 nonexecuted outside NOP bytes. Frame40->36B;
actual bytes touched remain36. Word alignment always/public8 alignment at
entry/return; no calls while frame active.70660 old/new raw pair units,
36781 valid exact integer products,0wrong. See validation notes for initial
failed legacy touched-byte counter run, excluded from qualified counts.

Public exp456750 inputs/913500states,0wrong.913500fresh candidate+33486fresh
Qfplib+130parent-audit ARM calls; old880014 parent/reference rows inherited.
456748 actual directedMPFR exp inputs+2sNaN shortcuts.8404 MPFR log-preimage
generations are separate, not validation exp references. Every old440007
raw return identical. Same440007 losses2023->1476:547fixed, all1094states
bound in same-corpus-fixed547.json. Same older48763:126->96. Expanded456750
union1541=1476old+65new measured preexisting losses(53dyadic/12uniform), all
parent-bound,0new losses. All392688wrong-Qfplibstate outputs/costs retained,
no nominal-domain filter. Do not subtract counts from different corpus sizes.
Examples: +2^-32:520->439vsQfp471; -2^-32:542->461vs520. Prior fixed hard
negative599->596vs622; remaining original positive2264->2266vs649.13222
parent state costs+2 retained:200already losing,11950wrongQfp,1072still no
slower than correctQfp. Not a universal per-input parent speed improvement.

Other callers189 originalpow/sin/cos jobs:1134freshARM,189actualMPFR inputs,
raw values/argument traces identical andminus2per actual shared-product call.
Three originalpow gaps become ties:1346->1344vs1344,1322->1320vs1320,
1313->1311vs1311. Pow original51->48, sin22/cos14 unchanged. All prior10085
expandedpow losing reference-state variants replayed by10081distinct fresh
candidate calls:7904->7901pairs,0new,0wrong. Full111912pair references/costs
inherited; no fresh full acquisition/MPFR claim. Nonlosses cannot regress by
the universal monotone callee proof. Pow replay observed1208 stack, original
callers968; no universal fullmath stack bound claimed.

Fresh qualified ARM total{fresh}=946986mainexp+130parentaudit+141320bare
product+70094literal shift+1134othercallers+10081powlossreplay. Actual directed
MPFR validation456937=456748exp+189callers, plus2sNaN shortcuts. Probe40494,
margin336 and failed initial bare141320 calls excluded; logs and notes pinned.

CPP core5064->5088B(+24), private Flashload16336->16360(+24), RAM code slot
168 same, no new tables/globalRAM/libgcc/ROMmath. Staticcore96same; observed
full publicexp stack744. All3736refine bytes/tiny472helper unchanged. All
other CPP allocated bytes/semantic relocs and all RP ASM bytes/relocs/symbol
addresses outside product slot identical. GenericM0/M4soft/hard selectedCPP
and ASM equal.11 completeobject/ELF rebuilds byte-exact. Actual fullsource
slot==unit==publicoverlay at20038ee4, Flashwrapper and directpublicABI kept.
Two-file patch; no build-list change or wholeM4/platform firmware build.

Author separateoriginal507 union422(413strict9equal),85remain:pow48/exp1/
sin22/cos14. Independently reviewed418 unchanged pending both new reviews.
Expandedexp1541/pow7901/ln5, FMA review, generalpow/exp totality, combined
integration/regression, physicalcycles and release remain open. No canonical,
Git, USB, device, Flash, lease, EA9 or release mutations; goal remains active.
'''
(W/'HANDOFF.md').write_text(handoff)
(W/'source-lineage-pins.json').write_text(json.dumps(dict(status='PINNED_FROZEN_ADAPTIVE_EXP_PARENT_AND_ALL_PRIOR_LINEAGE',files=external),indent=2)+'\n')
files={str(path.relative_to(W)):dict(sha256=sha(path),bytes=path.stat().st_size) for path in sorted(W.rglob('*')) if path.is_file() and '__pycache__' not in path.parts}
sealed=dict(status='FROZEN_PRIVATE_AUTHOR_DYADIC_EXP_AND_79_PRODUCT_PENDING_REVIEW',files=files,
 result_sha256=sha(W/'result.json'),HANDOFF_sha256=sha(W/'HANDOFF.md'),
 HEAD_at_seal=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),math_worktree_diff_empty=True,goal_complete=False)
(W/'FROZEN.json').write_text(json.dumps(sealed,indent=2)+'\n')
print(json.dumps(dict(status=sealed['status'],artifacts=len(files),external_lineage_pins=len(external),FROZEN_sha256=sha(W/'FROZEN.json'),
 result_sha256=sealed['result_sha256'],HANDOFF_sha256=sealed['HANDOFF_sha256'],candidate_ELF_sha256=b['candidate_ELF_sha256'],fresh_qualified_ARM=fresh,
 same_old_exp_losses=[2023,1476],expanded_exp1541=True,pow_remaining=[7904,7901]),indent=2))
