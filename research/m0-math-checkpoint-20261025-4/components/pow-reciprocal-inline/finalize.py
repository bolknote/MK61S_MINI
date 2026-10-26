"""Seal the author component; write stdout only outside the packet."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,subprocess
W=Path(__file__).resolve().parent;ROOT=W.parents[1];P=ROOT/'.build/m0-pow-reciprocal-one-20261025';R=ROOT/'.build/m0-pow-reciprocal-one-independent-20261025'
assert not(W/'FROZEN.json').exists()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();load=lambda p:json.loads(p.read_bytes())
q=load(W/'qualification.json');f=load(W/'new-qualification.json');d=load(W/'direct-proof.json');u=load(W/'unit-proof.json');t=load(W/'summary.json');b=load(W/'build.json');proof=load(W/'source-proof.json');rebuild=load(W/'rebuild-proof.json');loss=load(W/'direct-loss-accounting.json')
elf=sha(W/'candidate.elf')
for x in[q,f,d,proof,b['images']['candidate']]:assert x.get('candidate_ELF_sha256',x.get('ELF_sha256'))==elf
assert t['strict_fixed_pairs']==1 and t['total_qualified_fresh_ARM_calls']==615606 and t['public_instruction_reduction_range']==[2,7]
assert loss['candidate_loss_states']==13 and loss['new_loss_states']==0 and sum(loss['parent_increases'].values())==9664
assert len(rebuild['outputs'])==24
for p,h in rebuild['outputs'].items():assert sha(Path(p))==h
assert not subprocess.check_output(['git','diff','--','code/native_eabi_m0*'],cwd=ROOT)
external={}
def put(path,pin=None):
 p=Path(path);p=p if p.is_absolute()else ROOT/p;data=p.read_bytes();value=dict(bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
 if pin:assert value=={k:pin[k]for k in value},p
 key=str(p.relative_to(ROOT))
 if key in external:assert external[key]==value
 external[key]=value
for p,pin in load(P/'source-lineage-pins.json')['files'].items():put(p,pin)
for p,pin in load(P/'FROZEN.json')['files'].items():put(P/p,pin)
put(P/'FROZEN.json');put(ROOT/'.build/m0-pow-reciprocal-one-report-corrigendum-20261025.json')
review=load(R/'FINAL-REVIEW.json');assert review['status']=='TECH_GO_PRIVATE_EXACT_NUMERATOR_ONE_RECIPROCAL_COMPONENT_ONLY'and sha(P/'FROZEN.json')in json.dumps(review)
for p,pin in load(R/'MANIFEST.json')['files'].items():put(R/p,pin)
put(R/'FINAL-REVIEW.json');put(R/'MANIFEST.json')
roots={}
for name in['soft','lut','one']:
 receipt=ROOT/('.build/m0-pow-reciprocal-'+name+'-root-acceptance-20261025-001/RECEIPT.json')
 if receipt.exists():
  rr=load(receipt);assert rr['status'].startswith('ACCEPTED_PRIVATE_')
  for pin in rr['pins']:put(pin['path'],pin)
  put(receipt);roots[name]=dict(path=str(receipt.relative_to(ROOT)),bytes=receipt.stat().st_size,sha256=sha(receipt))
(W/'source-lineage-pins.json').write_text(json.dumps(dict(status='VERIFIED_PARENT_REVIEW_CORRIGENDUM_AND_SOURCE_LINEAGE',files=external),indent=2)+'\n')
result=dict(status='FROZEN_AUTHOR_PRIVATE_INLINE_SEED_TINY_OVERFLOW_PENDING_REVIEW',source_parent=str(P.relative_to(ROOT)),source_parent_FROZEN_sha256=sha(P/'FROZEN.json'),
 parent_independent_review=dict(path=str((R/'FINAL-REVIEW.json').relative_to(ROOT)),sha256=sha(R/'FINAL-REVIEW.json'),status=review['status']),ROOT_receipts_present_at_seal=roots,
 candidate_ELF_sha256=elf,source_proof_sha256=sha(W/'source-proof.json'),numeric_proof_sha256=sha(W/'NUMERIC-PROOF.md'),
 private_contract='exact positive numerator1, denominator any binary64; not general division',other_resident_ddiv_callers_unchanged=True,
 exact_subnormal_integer_overflow_threshold=1<<50,exact_endpoint_products_prove_all_integer_magnitudes=True,
 inline_seed_exhaustive_divisors=65536,bare_context_tests=u['tests'],bare_context_ARM_calls=u['actual_ARM_calls'],all16_NZCV_table_edges_checked=True,
 inline_R0_R1_R2_R3_R5_R12_and_SP_unchanged=True,no_inline_memory_writes_or_C_ABI_calls=True,inline_SP_is_own_entry_minus20=True,
 unchanged256B_table_relocated_into_software_body=True,old312B_standalone_seed_not_allocated=True,unchanged4_after_second_product_186B_RNE_suffixes=True,
 hardware_nine_ALU_latency_gap_preserved=True,DIRTY_all7_SIO_words_unchanged_no_writes=True,
 same_corpus_pairs=120980,states=241960,reference_state_variants=279522,loss_pairs=[11372,11371],new_strict_fixes=1,new_raw_losses=0,candidate_wrong=0,
 accelerated_public_states=754,accelerated_public_states_by_SIO=t['accelerated_states_by_SIO'],public_instruction_reduction_range=[2,7],public_parent_cost_increases=0,
 fresh_parent_reciprocal_path_calls=778,fresh_parent_changed_subset_calls=754,unchanged_power_of_two_parent_controls=24,
 all_public_costs_match_exact_model=True,all10254_fresh_controls_match_full_records=True,
 direct_expanded_pairs=d['pairs'],direct_states=d['states'],direct_loss_states=[7422,13],new_direct_Qfplib_loss_states=0,
 direct_correct_Qfplib_comparisons=d['correct_Qfplib_comparisons'],direct_parent_cost_increase_states=9664,direct_parent_increase_histogram=loss['parent_increases'],
 all_correct_incorrect_Qfplib_outputs_costs_and_parent_increases_retained=True,no_nominal_reference_domain_filter=True,wrong_direct_Qfplib_variants=9600,wrong_public_Qfplib_variants=77106,
 public_correct_Qfplib_comparison=q['correct_Qfplib_comparison'],total_qualified_fresh_ARM_calls=615606,
 fresh_full_candidate_ARM_calls=241960,fresh_parent_reciprocal_path_ARM_calls=778,fresh_public_MPFR_control_reference_ARM_calls=61524,fresh_scalar_ARM_calls=167952,fresh_bare_context_ARM_calls=143392,
 actual_directed_MPFR_inputs=26011,sNaN_policy_shortcuts=110,failed_symbol_lookup0_scalar0_MPFR_excluded=True,failed_relative_stack_trace318_completed_ARM2partial23_MPFR_excluded=True,parent_campaigns_not_fresh=True,
 private_code_bytes=proof['private_code_bytes'],allocated_code_delta_bytes=12,no_new_table_values_RAM_or_libgcc=True,
 default_M0_M4_selected_controls_and6_disabled_objects_empty=True,twenty_four_original_path_source_object_ELF_rebuilds_exact=True,
 full_observed_stack_bytes=2284,fresh_public_controls_stack_bytes=f['observed_stacks'],direct_stack_bytes=d['observed_stacks'],parent_changed_subset_not_complete_comparator=True,
 original_pow153_remaining=[34,34],author_separate507_no_slower=437,reviewed_separate507_no_slower=422,
 independent_review_pending=True,remaining_scalar_deficits_other_needed_math_general_totality_source_merge_actual_R12_loader_layout_14B_overlay_cycles_release_pending=True,
 canonical_runtime_M4_Git_device_USB_Flash_or_release_changed=False,goal_complete=False)
(W/'result.json').write_text(json.dumps(result,indent=2)+'\n')
(W/'HANDOFF.md').write_text('''# Private inline seed and exact tiny overflow: author qualification complete

Contract remains exact positive numerator1, denominator any binary64. The
actual sole root caller and its positive-one loads are unchanged. This is
not a general ddiv/C ABI replacement. Parent numerator-one has independent
TECH_GO; the new component still needs separate review. Parent receipts
available at seal are pinned without widening their scope.

For subnormal magnitude k*2^-1074, exact endpoint products prove reciprocal
RNE overflow for every integer0<=k<=2^50. The new cold path returns signed
infinity; all other special inputs retain the original IEEE fallback. The
threshold and both neighbours are checked under both signs and all16 flags,
with random subnormals and all denominator exponent/sign classes. The exact
seed is inlined in R4/R6/R7/R1, retaining R0/R2/R3/R5/R12/SP. Complete65536
domain plus all16 table-edge flags passes71696 unit tests /143392 actual
old+new ARM calls. The wrapper's20B stack/speed is not production evidence.
Production inline SP is exactly its own entrySP-20 and makes no C ABI call.
The new macro and unit share the same source/table. Old312B standalone seed
is not allocated. The256B table and four186B RNE suffixes are unchanged.
Hardware retains nine independent ALU operations before SIO quotient read;
all seven DIRTY SIO words are preserved without writes.

Same120980 pairs /241960 states:11372->11371 raw loss pairs, one new strict
fix,0newloss/0wrong/0public parent increases.754 states (377 READY,377 DIRTY)
save2-7 instructions. All754 changed paths have fresh parent replays; the
778 parent-call counter also includes24 unchanged powers-of-two controls.
All10254 fresh controls match full records, all actual public costs match
the exact model. Every279522 reference-state variant, including77106 wrong
Qfplib outputs/costs, is retained without a nominal-domain filter.

Expanded scalar1/x corpus:20994 pairs /41988 states, correct-Qfplib losses
7422->13, no new Qfplib losses;32370 faster,5equal,13slower. All9600 wrong
reference variants remain. There are9664 scalar parent cost increases:
3168 states +8,352 +2,6144 +11 instructions, from cold fallback checks;
these are explicit and none creates a new loss against correct Qfplib.
This is not a universal reciprocal or whole-library speed claim.

615606 fresh qualified ARM calls:241960 full candidates,778 parent paths,
61524 fresh public controls/references,167952 scalar calls and143392 bare
context calls.26011 directed MPFR inputs plus110 sNaN policy shortcuts.
The first driver symbol lookup failed before scalar/MPFR calls. Initial
nested public trace runs stopped on an absolute rather than relative stack
assertion after318 completed calls, two partial aborts and23 MPFR calls;
these are preserved/excluded. Kernel/scalar results were already correct.
Parent qualification and old seed campaigns are inherited, not fresh.
Twenty-four full source/object/ELF rebuilds are byte-exact.

Private code1060->1072B (+12B), no new table values/global RAM/libgcc. Default
M0/M4 controls and six new disabled objects remain empty. Full observed stack
2284B, fresh controls2148B each, scalar176B each unchanged. The parent path
subset is not a full comparator; no universal stack bound is claimed.
Original153 stays119strict/34slower, author separate507437 and reviewed422.

Remaining work includes13 scalar states, other needed operations, general
pow totality, source merge/relink and actual integrated R12/loader/layout
guards, the14B old-overlay hazard, physical cycles and release. No canonical,
M4, Git, device, USB or Flash change, and no integration/hardware/main/release
GO. Historical producers must not run inside frozen packets. Goal is active.
''')
(W/'WORK-SCOPE.json').write_text(json.dumps(dict(status='AUTHOR_QUALIFICATION_COMPLETE_PENDING_REVIEW',previous_goal_turn_classification='progress: private numerator-one contract/product/guards qualified,5 strict fixes and778 faster states',this_turn_classification='progress: exact tiny overflow guard and register-only seed qualified; scalar7422->13 losses, one strict pow fix and754 faster public states; cold parent increases retained',goal_complete=False,canonical_runtime_M4_Git_device_USB_Flash_changed=False),indent=2)+'\n')
(W/'progress.json').write_text(json.dumps(dict(status='AUTHOR_QUALIFICATION_COMPLETE_PENDING_REVIEW',completed_states=241960,total_states=241960),indent=2)+'\n')
files={str(p.relative_to(W)):dict(bytes=p.stat().st_size,sha256=sha(p))for p in sorted(W.rglob('*'))if p.is_file()and'__pycache__'not in p.parts}
(W/'FROZEN.json').write_text(json.dumps(dict(status='FROZEN_AUTHOR_PRIVATE_CALLER_PENDING_REVIEW',utc=datetime.now(timezone.utc).isoformat(),files=files,result_sha256=sha(W/'result.json'),HANDOFF_sha256=sha(W/'HANDOFF.md'),goal_complete=False),indent=2)+'\n')
print(json.dumps(dict(status='AUTHOR_COMPONENT_SEALED',local_files=len(files),external_pins=len(external),FROZEN_sha256=sha(W/'FROZEN.json'),result_sha256=sha(W/'result.json'),HANDOFF_sha256=sha(W/'HANDOFF.md'),candidate_ELF_sha256=elf,ROOT_receipts=roots),indent=2))
