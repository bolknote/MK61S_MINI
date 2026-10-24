from pathlib import Path
import hashlib,json,subprocess
W=Path(__file__).resolve().parent;ROOT=W.parents[1];C=ROOT/'.build/m0-exp-tiny-log-midpoint-20261024';R=ROOT/'.build/m0-pow-rsqrt-asm-20261024'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
load=lambda p:json.loads(p.read_text())
assert not (W/'FROZEN.json').exists()
b=load(W/'build.json');q=load(W/'qualification.json');a=load(W/'remaining-parent-audit.json');u=load(W/'unit-proof.json');c=load(W/'caller-proof.json');p=load(W/'pow-loss-replay.json');i=load(W/'isolation-rebuild.json');cert=load(W/'certificate.json');fixed=load(W/'same-corpus-fixed29.json');stack=load(W/'stack-deep-diagnostic.json')
assert b['candidate_ELF_sha256']==q['candidate_ELF_sha256']==a['candidate_ELF_sha256']==c['candidate_ELF_sha256']==sha(W/'candidate.elf')
assert b['source_sha256']==q['source_sha256']==cert['source_sha256']==sha(W/'candidate/native_eabi_m0.cpp')
assert q['wrong']==a['wrong']==q['new_known_parent_raw_losses']==a['new_raw_losses']==q['tiny_correct_reference_raw_losses']==0
assert q['unique_inputs']==440007 and q['profiled_states']==880014
assert [q['old428231_parent_raw_losses'],q['old428231_candidate_raw_losses']]==[671,642]
assert q['union_candidate_raw_losses']==2023 and q['old48763_candidate_raw_losses']==126
assert q['historical_exp16_remaining']==1 and fixed['fixed_inputs']==29 and fixed['state_rows']==58
assert a['all_remaining_parent_states_now_bound'] and a['fresh_parent_ARM_calls']==2762
assert u['gate']['actual_ARM_calls']==595004 and u['gate']['unsafe_admissions']==0
assert u['product']['raw64_pairs']==70660 and u['product']['wrong']==0
assert u['product']['instruction_counts']=={'old':{'84':70660},'new':{'81':70660}}
assert u['product']['stack_bytes']=={'old':40,'new':40} and u['product']['stack_bytes_touched']=={'old':40,'new':36}
assert p['remaining_pairs_after']==7904 and p['new_raw_losses']==0 and p['fresh_candidate_state_calls']==10081
assert {op:v['candidate_slower_raw'] for op,v in c['summary'].items()}=={'pow':51,'sin':22,'cos':14}
assert len(i['records'])==11 and b['CPP_code_delta_bytes']==52
assert stack['maximum_frame_bytes']=={'parent':744,'candidate':744}
assert sha(W/'qualification-records.jsonl.gz')==q['qualification_records_sha256']

external={}
def pin(path):
 path=Path(path);name=str(path.relative_to(ROOT));v=dict(sha256=sha(path),bytes=path.stat().st_size)
 assert name not in external or external[name]==v
 external[name]=v
for name,v in load(C/'FROZEN.json')['files'].items():
 path=C/name;assert sha(path)==v['sha256'] and path.stat().st_size==v['bytes'];pin(path)
pin(C/'FROZEN.json')
for name,v in load(C/'source-lineage-pins.json')['files'].items():
 path=ROOT/name;assert sha(path)==v['sha256'] and path.stat().st_size==v['bytes'];pin(path)
review_path=ROOT/'.build/m0-exp-tiny-log-midpoint-independent-20261024/FINAL-REVIEW.json';review=load(review_path)
assert review['status']=='GO_PRIVATE_RP_EXP_TINY_LOG_MIDPOINT_COMPONENT_ONLY' and review['blockers']==[]
assert review['target']['frozen']['sha256']==sha(C/'FROZEN.json')
refs={}
def find_refs(value):
 if isinstance(value,dict):
  if all(k in value for k in ('path','bytes','sha256')):refs[value['path']]=value
  else:
   for v in value.values():find_refs(v)
 elif isinstance(value,list):
  for v in value:find_refs(v)
find_refs(review)
for path,v in refs.items():
 f=Path(path);assert f.stat().st_size==v['bytes'] and sha(f)==v['sha256'];pin(f)
pin(review_path)
assert len(refs)==48
parent_review=dict(status=review['status'],path=str(review_path.relative_to(ROOT)),sha256=sha(review_path),unique_direct_refs_verified=48,receipt_plus_refs_verified=49,own_ARM_calls=13636,own_direct_MPFR_inputs=1374,sNaN_shortcuts=2)
(W/'accepted-parent-review.json').write_text(json.dumps(parent_review,indent=2)+'\n')
for name in ('FROZEN.json','candidate.elf','remaining-expanded.json','expanded-union-summary.json','qualification.json','targeted.json'):
 pin(R/name)
pin(ROOT/'.build/m0-pow-rsqrt-asm-independent-20261024/FINAL-REVIEW.json')
assert not subprocess.check_output(['git','diff','HEAD','--name-only','--','code/native_eabi_m0*'],cwd=ROOT,text=True).strip()
fresh=q['fresh_ARM_calls']+a['fresh_parent_ARM_calls']+u['total_actual_ARM_calls']+c['fresh_ARM_calls']+p['fresh_candidate_state_calls']
assert fresh==1653867
result=dict(status='FROZEN_AUTHOR_ADAPTIVE_EXP_ENCLOSURE_AND_SHARED_81_INSTRUCTION_PRODUCT',
 accepted_source_parent=str(C.relative_to(ROOT)),accepted_parent_review=parent_review,
 source_sha256=b['source_sha256'],product_include_sha256=b['product_include_sha256'],candidate_ELF_sha256=b['candidate_ELF_sha256'],
 public_exp_unique_inputs=440007,public_exp_state_rows=880014,
 fresh_public_exp_candidate_ARM_calls=q['fresh_candidate_ARM_calls'],fresh_new_Qfplib_ARM_calls=q['fresh_Qfplib_ARM_calls'],fresh_exp_parent_audit_ARM_calls=2762,
 fresh_bare_gate_and_product_ARM_calls=736324,fresh_original_pow_sin_cos_ARM_calls=1134,fresh_expanded_pow_loss_state_ARM_calls=10081,
 total_qualified_fresh_ARM_calls=fresh,
 actual_directed_MPFR_exp_inputs=440005,actual_directed_MPFR_other_caller_inputs=189,total_actual_directed_MPFR_validation_inputs=440194,
 validation_oracle_evaluations=440196,sNaN_shortcuts_without_MPFR=2,MPFR_version=q['MPFR_version'],
 separate_MPFR_log_preimage_generation_inputs1536_not_pooled_with_validation=True,
 inherited856462_exp_parent_Qfplib_rows_not_fresh=True,inherited_pow_full111912_pair_references_not_fresh=True,
 final_probe32208_margin336_stack640_and_rejected_or_failed_trials_not_added=True,
 wrong=0,all_old428231_public_raw_bits_identical=True,
 same_old428231_exp_losses=[671,642],same_old_corpus_fixed=29,same_older48763_exp_losses=[154,126],
 expanded440007_exp_losses=2023,
 expanded_exp_count_scope='Same428231:671->642. Expanded440007:2023=642old+1381new control inputs (1353small true-midpoint preimages,15uniform,13normal/endpoints), every loss preexisting in parent; not an increase on a fixed corpus.',
 all2023_exp_losses_parent_bound=True,new_exp_raw_speed_losses=0,
 original_exp16_losses=[2,1],new_original_exp_fixed=dict(x='C041265824E2113C',parent=2248,candidate=599,Qfplib=622),
 remaining_original_exp=dict(x='4085F424184F6DC5',parent=2268,candidate=2264,Qfplib=649),
 correct_Qfplib_comparison=q['correct_Qfplib_comparison'],wrong_Qfplib_state_rows_retained=q['wrong_Qfplib_state_rows_retained'],no_nominal_domain_filter=True,
 adaptive_all_normal_error4_cells_source_enclosure_proof=True,literal_gate_unit_cases=595004,literal_gate_unit_unsafe_admissions=0,
 all512_Q62_Q94_tables_recertified=True,old_distance3_safe_predicate_retained=True,
 shared_product_instructions=[84,81],shared_product_body_bytes=[168,162],shared_product_RAM_slot_bytes=[168,168],outside_function_padding_bytes=6,
 shared_product_all_raw64_ABI_value_equivalence_source_proof=True,product_unit_raw_pairs=70660,product_valid63x54_integer_oracles=36781,
 product_stack_frame_bytes=[40,40],product_stack_written_bytes=[40,36],shared_product_argument_trace_and_minus3_per_call_verified=True,
 original_other_callers_summary=c['summary'],expanded_pow_losses_unchanged=7904,
 pow_loss_replay_scope='All10085prior losing reference-state variants,10081distinct candidate state calls on the accepted111912-pair union. Old expected bits/Qfplib counts inherited, no freshMPFR or full111912-pair rerun claim. All other old states cannot regress under value/ABI equivalence and constant minus3 per product call.',
 retained_exp_parent_cost_increase_state_rows=200,retained_increase_deltas=[2,29],no_new_correct_Qfplib_losses_after_full_parent_audit=True,
 selected_CPP_allocated_delta_bytes=52,selected_ASM_allocated_delta_bytes=0,private_Flash_overlay_load_delta_bytes=48,
 whole_firmware_size_and_GC_delta_not_measured=True,no_new_tables_global_RAM_libgcc_ROM_math_or_external_calls=True,
 static_exp_core_frame96_unchanged=True,observed_candidate_stack744_on_new_corpus=True,focused_same_input_parent_and_candidate_peak744=True,old376_peak_on_smaller_corpus_not_a_comparator=True,
 all_other_CPP_allocated_bytes_semantic_relocations_equal=True,preexisting_refine3736bytes_identical=True,
 all_RP_ASM_outside_product168byte_slot_bytes_relocations_symbol_addresses_equal=True,
 generic_M0_M4_CPP_and_ASM_selected_bytes_semantic_relocations_equal=True,
 eleven_complete_object_ELF_rebuilds_byte_exact=True,direct_public_ABI_and_original_RAM_address_wrapper_preserved=True,
 original507_author_separate_union=dict(no_slower=419,strictly_faster=413,equal=6,remaining=88,by_operation=dict(pow=51,exp=1,sin=22,cos=14),not_one_integrated_binary=True),
 original507_independently_reviewed_union_unchanged=418,
 independent_review_pending=True,combined_math_platform_integration_physical_cycles_and_release_pending=True,
 no_canonical_Git_USB_device_Flash_lease_EA9_or_release_changes=True,goal_complete=False)
(W/'result.json').write_text(json.dumps(result,indent=2)+'\n')
handoff=f'''Private RP2040 adaptive exp enclosure and81-instruction shared product.
Independent review pending. Accepted source parent is frozen log-midpoint
5dfdd55…; independent receipt{parent_review['sha256']} read and48direct
refs verified (49including receipt). Prior frozen packets are unchanged.

Normal error4 cells use the actual Q62 table magnitude instead of a
global1/2 upper multiplier. A<(floor(q/2^48)+24)*2^48, reduction/polynomial
delta<275/64, and all remaining product/table/cross errors<129/256.
Signed Q94 bias and a strict integer margin certify distance2/3 cells;
the old distance3 predicate remains intact. NUMERIC-PROOF.md and
certificate.json prove the source-bound enclosure for the full qualifying
normal domain.595004literal actualARM gate cases:0unsafe; all512existing
Q62/Q94table roots recertified. No new table or approximated return mode.

The shared product uses PUSHr0-r7,LR/SUBsp4/baseSP+4 in place of separate
argument stores. Its148-byte arithmetic suffix is byte-identical; all
argument bits, saved registers,SP/return and values are preserved by the
PCS proof. Active body168->162B,84->81fixed instructions for every raw
input.6outside-function NOPbytes retain the168B RAM slot and all following
addresses; they never execute. Frame40same, bytes touched40->36 because
the new4-byte alignment word is unused.70660bare old/new raw pairs,
36781valid63x54integer references,0wrong, constant84/81costs. No external
calls, ROM, globalRAM, new tables or SIO added.

440007public exp inputs/880014states:880014newcandidate+23552newQfp+
2762parentaudit.440005actualdirectedMPFR+2sNaNshortcuts.856462old
parent/Qfp measurements inherited/notnew. New input generation includes
1536directedMPFRlog preimages, not validation exp references.0wrong;
everyold428231rawbit identical. All390568wrong-Qfpstate outputs/costs
retained, no nominal-domain filter. Same428231corpus671->642losses,
29fixed (same older48763:154->126). New440007corpus2023=642old+
1381new controls, every2023loss already lost in parent:0new losses.
Do not subtract counts from different corpus sizes. Every fixed29input
has both states bound in same-corpus-fixed29.json. Originalhardnegative
C041265824E2113C:2248->599vsQfp622. Positive4085F424184F6DC5remains
2264vs649 (parent2268). Originalexp16now1loss instead2.

Product-only callers189originalpow/sin/cosjobs:1134freshARM/189actual
directedMPFR; all argument traces/rawresults identical and every call
saves3instructions. Originalremainingpow51/sin22/cos14 unchanged. All
7904old expandedpowlosses replayed:10081fresh candidate states across
10085reference variants, inherited expectedbits/Qfpcosts,0wrong,7904
remain. Unchanged states cannot regress by monotone callee proof; this
is not a full111912-pair fresh acquisition or newMPFR run. Sin/cos had
no calls to this shared kernel on these original jobs.

Qualified freshARM total{fresh}=903566mainexp+2762parentaudit+736324
bareunits+1134othercallers+10081powlossreplay. ActualdirectedMPFRvalidation
440194=440005exp+189othercallers, plus2sNaNshortcuts. Final32208probe,
336marginprobe,640stack repeats and rejected/failed trials excluded.
The first numerical unit run completed then failed a deepest-write
versusSPframe accounting assertion; final clean repeat measures both
directly. Logs/VALIDATION-NOTES.json records exclusions. The two earlier
CPP layouts had31new hot-path losses and are rejected, not parents.
Final oldmargin56 and completeoldcorpus pass with0new losses. All200
remaining parent state cost increases(+2/+29) retained;44were already
slower than correctQfp,70have wrongQfp,86remain no slower.

CPP core5012->5064B(+52), existing refine3736B/tiny472B unchanged.
ASM allocatedsize unchanged by retainedslot; privateFlashload+48incl
alignment, fullfirmware/GC size unmeasured. Staticcoreframe96same.
New corpus observed744stack; focused same-input deep parent/child are
both744, not a regression from the old376peak on a smaller corpus.
This is not a universal fullmath stack bound. All other fullCPPsections/
relocations and allRPASMbytes/relocations/symboladdresses outside the
168Bproductslot identical. GenericM0/M4soft/hard selectedCPP+ASM exact.
11completeCPP/ASM/unitobject+ELFrebuildsbyteexact. Actual fullsource
productslot==unit==publicRAM overlay; original20038ee4address/Flash
wrapper and directpublicABI preserved, no artificial veneer. Two-file
patch, no buildlistchange. No wholeM4/repaired-platform firmware build.

New author separateoriginal507union419(413strict6equal),remaining88:
pow51/exp1/sin22/cos14; reviewed418unchanged until this child is accepted.
Expandedexp2023/pow7904/ln5,FMA,generalpow/exp totality,combined math
regression,integration,physicalcycles and release remain open. No
canonical/Git/USB/device/Flash/lease/EA9/release mutations or whole-goalGO.
'''
(W/'HANDOFF.md').write_text(handoff)
(W/'source-lineage-pins.json').write_text(json.dumps(dict(status='PINNED_ACCEPTED_LOG_MIDPOINT_AND_POW_SHARED_PRODUCT_LINEAGE',files=external),indent=2)+'\n')
files={str(p.relative_to(W)):dict(sha256=sha(p),bytes=p.stat().st_size) for p in sorted(W.rglob('*')) if p.is_file() and '__pycache__' not in p.parts}
sealed=dict(status='FROZEN_PRIVATE_AUTHOR_ADAPTIVE_EXP_AND_81_PRODUCT_PENDING_REVIEW',files=files,result_sha256=sha(W/'result.json'),HANDOFF_sha256=sha(W/'HANDOFF.md'),HEAD_at_seal=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),math_worktree_diff_empty=True,goal_complete=False)
(W/'FROZEN.json').write_text(json.dumps(sealed,indent=2)+'\n')
print(json.dumps(dict(status=sealed['status'],artifacts=len(files),external_lineage_pins=len(external),FROZEN_sha256=sha(W/'FROZEN.json'),result_sha256=sealed['result_sha256'],HANDOFF_sha256=sealed['HANDOFF_sha256'],candidate_ELF_sha256=b['candidate_ELF_sha256'],fresh_qualified_ARM=fresh,same_old_exp_losses=[671,642],new_expanded_losses=2023,original_exp_remaining=1,parent_review=parent_review),indent=2))
