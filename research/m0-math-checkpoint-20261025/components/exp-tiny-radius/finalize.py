from pathlib import Path
import hashlib,json,subprocess
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
F=ROOT/'.build/m0-f2d-leaf-20261024'
B=ROOT/'.build/m0-exp-cached-product-20261024'
P=ROOT/'.build/m0-asin-scaled-bound-v164-20261023'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
load=lambda p:json.loads(p.read_text())
assert not (W/'FROZEN.json').exists()
b=load(W/'build.json');q=load(W/'qualification.json');p=load(W/'proof.json');a=load(W/'remaining-parent-audit.json');r=load(W/'rebuild-proof.json')
assert q['candidate_ELF_sha256']==a['candidate_ELF_sha256']==r['candidate_ELF_sha256']==sha(W/'candidate.elf')
assert q['source_sha256']==p['source_sha256']==sha(W/'candidate/native_eabi_m0.cpp')
assert q['wrong']==a['wrong']==q['new_known_parent_raw_losses']==a['new_raw_losses']==q['all_new_tiny_midpoint_raw_losses']==0
assert q['old48763_parent_raw_losses']==395 and q['old48763_candidate_raw_losses']==154
assert q['unique_inputs']==163675 and q['union_candidate_raw_losses']==669
assert a['all_remaining_parent_states_now_bound'] and q['old_historical16_remaining']==2
assert p['all_midpoint_cells']==49153 and p['all_guard_transition_model_checks']==442299
assert len(r['records'])==6 and b['CPP_code_delta_bytes']==64
assert sha(W/'qualification-records.jsonl.gz')==q['qualification_records_sha256']
assert sha(W/'qualification-inputs.bin')==q['input_words_sha256']

external={}
def pin(path):
 path=Path(path);name=str(path.relative_to(ROOT));v=dict(sha256=sha(path),bytes=path.stat().st_size)
 assert name not in external or external[name]==v
 external[name]=v
for name,entry in load(F/'FROZEN.json')['files'].items():
 path=F/name;assert sha(path)==entry['sha256'] and path.stat().st_size==entry['bytes'];pin(path)
pin(F/'FROZEN.json')
for name,entry in load(F/'source-lineage-pins.json')['files'].items():
 path=ROOT/name;assert sha(path)==entry['sha256'] and path.stat().st_size==entry['bytes'];pin(path)
review_path=ROOT/'.build/m0-f2d-leaf-independent-20261024/FINAL-REVIEW.json'
review=load(review_path)
assert review['status']=='GO_PRIVATE_RP_F2D_LEAF_COMPONENT_ONLY' and review['blockers']==[]
assert review['target']['frozen']['sha256']==sha(F/'FROZEN.json')
refs=[review['accepted_parent'],*review['target'].values(),*review['refs'].values()]
for v in refs:
 path=Path(v['path']);assert sha(path)==v['sha256'] and path.stat().st_size==v['bytes'];pin(path)
pin(review_path)
acceptance=dict(status=review['status'],path=str(review_path.relative_to(ROOT)),sha256=sha(review_path),receipt_and_direct_refs_verified=1+len(refs),own_ARM_calls=26928,own_direct_MPFR_conversions=3366)
(W/'accepted-f2d-parent.json').write_text(json.dumps(acceptance,indent=2)+'\n')
for path in [B/'FROZEN.json',B/'qualification.json',B/'candidate.elf',B/'candidate-full.o',B/'cached-product.o',B/'cached-product.S',B/'candidate-bindings.ld',ROOT/'.build/m0-exp-cached-product-independent-20261024/FINAL-REVIEW.json',P/'build/compile_commands.json']:
 pin(path)
for pattern in ('native_eabi_m0*','compact_math*'):
 for path in (P/'source/code').glob(pattern):
  if path.is_file():pin(path)
math_diff=subprocess.check_output(['git','diff','HEAD','--name-only','--','code/native_eabi_m0*'],cwd=ROOT,text=True).strip()
assert not math_diff,math_diff
fresh=q['fresh_ARM_calls']+a['fresh_parent_ARM_calls']
result=dict(status='FROZEN_AUTHOR_EXACT_TINY_EXP_ALL_CELLS_WITH_REMAINING_SPEED_WORK',
 accepted_source_parent=str(F.relative_to(ROOT)),accepted_parent_review=acceptance,
 source_sha256=b['source_sha256'],candidate_ELF_sha256=b['candidate_ELF_sha256'],
 qualified_unique_inputs=q['unique_inputs'],qualified_state_rows=q['profiled_states'],
 fresh_final_ELF_candidate_ARM_calls=q['fresh_candidate_ARM_calls'],
 fresh_Qfplib_ARM_calls=q['fresh_Qfplib_ARM_calls'],
 fresh_parent_remaining_audit_ARM_calls=a['fresh_parent_ARM_calls'],
 total_qualified_fresh_ARM_calls=fresh,
 oracle_evaluations=q['oracle_evaluations'],actual_directed_MPFR_input_conversions=q['actual_directed_MPFR_input_conversions'],
 NaN_shortcuts_without_MPFR=q['NaN_shortcuts_without_MPFR'],MPFR_version=q['MPFR_version'],
 inherited97526_parent_Qfplib_rows_not_counted_fresh=True,final_smoke10446_not_added=True,rejected_inline_trial_calls_not_added=True,
 candidate_wrong=0,old48763_returned_bits_identical=True,
 old48763_speed_losses=[395,154],old_corpus_additional_fixed=241,
 expanded163675_speed_losses=669,
 expanded_count_scope='Same old48763 inputs:395->154. Larger163675 union:669; extra515 outside old corpus are514 dense2^-38 endpoint neighbors and1 new ordinary input, all confirmed preexisting parent losses. Not an increase on a fixed corpus.',
 all_remaining_losses_parent_bound=True,new_raw_speed_losses=0,
 tiny_domain='2^-54 < abs(x) < 2^-38',tiny_correct_reference_speed_losses=0,
 tiny_instruction_range=[min(map(int,q['tiny_instruction_counts'])),max(map(int,q['tiny_instruction_counts']))],
 example_x='BC90000000000001',example_instructions=dict(parent=17117,candidate=96,Qfplib=527),
 complete_author_tiny_RNE_source_proof=True,all_midpoint_cells=49153,exact_guard_transition_model_checks=442299,
 all_cell_integer_transition_neighbors_fresh_public_ARM_and_direct_MPFR=True,
 correct_Qfplib_comparison=q['correct_Qfplib_comparison'],wrong_Qfplib_state_rows_retained=q['wrong_Qfplib_state_rows_retained'],
 no_nominal_domain_filter=True,
 selected_CPP_code_delta_bytes=64,new_helper_bytes=196,parent_core_bytes=5144,candidate_core_bytes=5012,
 no_new_tables_RAM_libgcc=True,new_helper_external_calls_ROM_or_relocations=0,
 observed_candidate_stack_bytes=q['candidate_stack_bytes'],accepted_parent_same_old_corpus_stack_bytes=736,
 static_core_stack_bytes=[88,96],static_helper_stack_bytes=20,
 known_parent_cost_increase_rows_retained=q['parent_cost_increase_rows'],
 entire_CPP_object_only_exp_core_and_new_tiny_section_changed=True,
 all_other_CPP_allocated_bytes_and_semantic_relocations_identical=True,
 complete_ASM_object_all_RP_sections_and_relocations_equal_accepted_f2d=True,
 generic_M0_M4_selected_CPP_unchanged_and_ASM_source_unchanged=True,
 six_complete_CPP_ASM_object_ELF_rebuilds_byte_exact=True,
 direct_public_exp_ABI_no_artificial_interposition_veneer=True,
 original507_union_unchanged=418,original507_remaining=89,
 original_exp16_remaining=2,
 rejected_inline_trial_new_ordinary_loss_fixed_in_final=True,
 independent_review_pending=True,integration_and_physical_cycles_pending=True,
 whole_M4_firmware_and_combined_firmware_not_built=True,
 no_canonical_Git_device_Flash_lease_or_release_changes=True,
 goal_complete=False)
(W/'result.json').write_text(json.dumps(result,indent=2)+'\n')
trial=load(W/'trial-r1/probe.json')
(W/'trial-r1/REJECTED.json').write_text(json.dumps(dict(status='REJECTED_INLINE_LAYOUT_NOT_A_PARENT',wrong=0,new_raw_speed_losses=trial['new_raw_losses'],candidate_ELF_sha256=trial['candidate_ELF_sha256'],reason='Inline register allocation added5instructions on ordinary40861E1EFFBB4B16:556->561 vsQfp559. Final outlined helper restores ordinary cost; final probe/full qualification have0new losses.',calls_not_added_to_qualified_final_totals=True),indent=2)+'\n')
handoff=f'''Private RP2040 exp tiny-cell rounding component, independent review pending.

Only the RP tiny domain 2^-54<abs(x)<2^-38 changes numerically. Exact
integer midpoint geometry replaces the old uncertain Taylor-cell fallback.
For M0=(2*r+1)*2^(s-1), the quadratic correction is odd_square/2^q,
q1..18. Its integer-distance is >=2^-18; the combined input displacement
and cubic-tail error is <2^-22. Thus its exact floor decides all near
midpoints with one uint32 multiply. Other cells have a strict16385input-ulp
margin. Full author proof is in NUMERIC-PROOF.md/proof.py:49153midpoint
cells,442299model controls, and both actual result-transition neighbors
prepared/executed through the full public exp ABI for every cell.

163675unique inputs/327350states, {fresh}fresh qualified ARM calls =
327350final candidate +229824new Qfplib +{a['fresh_parent_ARM_calls']}parent audit.
163673actual directedMPFR4.2.2 conversions +2preMPFRsNaN shortcuts.
Old97526parent/Qfp rows are pinned inherited measurements, not new calls.
Final10446smoke calls and rejected inline trial are excluded.0wrong,
all old48763 returned bits identical. All incorrect Qfp outputs/costs
retained in qualification-records.jsonl.gz; no nominal-domain filter.

On the exact same old48763 corpus,395raw speed losses->154:241fixed.
The larger163675 corpus has669remaining =154old+514new dense endpoint
controls at2^-38+1new ordinary input. Every669loss is proven preexisting
by old/fresh parent measurements (remaining-parent-audit.json);0new raw
regressions. These different-size corpus counts must not be subtracted.
All tiny-domain correct-Qfp paths are faster; observed public74..96ISA
instructions. BC90000000000001:17117->96 vsQfp527. Original16exp still
has2hardcases, unchanged2268vs649 /2248vs622. Original507union418,
residual89 unchanged. Remaining669 are retained in qualification.json.

New196B helper, core5144->5012B, net+64selected CPP bytes. No new tables,
globalRAM/libgcc/ROM or external helper calls. Static core88->96stack,
new helper20; overall observed max376 vs accepted parent736 on the same
old corpus (eliminated tiny refinement), not a universal max guarantee.
All13234known state cost increases vs parent retained; they remain faster
than Qfp. The rejected inline layout made one new ordinary speed loss;
the final outlined layout fixes it. No numerical failure in either trial.

Every other full CPP allocated section/semantic relocation unchanged;
full ASM allocated bytes/relocations including d2f/f2d equal the accepted
f2d parent. Generic M0/M4soft/hard selected CPP byte exact; ASM source
unchanged, inherited generic controls apply. Six complete CPP/ASM
object/ELF rebuilds byte exact. Exact196B helper bytes bound to the full
intended-source linked function; no relocations/external calls. Explicit
PHDRS load only reserved Flash and the accepted168B RAM product, without
ELF headers/padding overwriting resident neighbors. Direct public ABI,
no artificial interposition veneer. No build-list change: one CPP patch.

Accepted f2d review {acceptance['sha256']} read and all
{acceptance['receipt_and_direct_refs_verified']}receipt/direct refs verified before seal. Source
lineage is composite accepted rsqrt CPP plus accepted d2f/f2d ASM, not
an integrated repaired-platform firmware. Whole firmware/GC size not
claimed. No canonical/Git/USB/device/Flash/lease/EA9/release changes.
Independent review, expanded speed work, generalpow totality, combined
math regression, platform integration and actual physical cycles remain
open. No all-math, production or whole-goal GO.
'''
(W/'HANDOFF.md').write_text(handoff)
(W/'source-lineage-pins.json').write_text(json.dumps(dict(status='PINNED_ACCEPTED_F2D_PARENT_AND_FULL_EXP_REFERENCE_LINEAGE',files=external),indent=2)+'\n')
files={str(path.relative_to(W)):dict(sha256=sha(path),bytes=path.stat().st_size) for path in sorted(W.rglob('*')) if path.is_file() and '__pycache__' not in path.parts}
sealed=dict(status='FROZEN_PRIVATE_AUTHOR_EXP_TINY_CELL_COMPONENT_PENDING_REVIEW',files=files,result_sha256=sha(W/'result.json'),HANDOFF_sha256=sha(W/'HANDOFF.md'),HEAD_at_seal=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),math_worktree_diff_empty=True,goal_complete=False)
(W/'FROZEN.json').write_text(json.dumps(sealed,indent=2)+'\n')
print(json.dumps(dict(status=sealed['status'],artifacts=len(files),external_lineage_pins=len(external),FROZEN_sha256=sha(W/'FROZEN.json'),result_sha256=sealed['result_sha256'],HANDOFF_sha256=sealed['HANDOFF_sha256'],fresh_qualified_ARM=fresh,old_corpus_losses=[395,154],expanded_union_losses=669,accepted_f2d_review=acceptance),indent=2))
