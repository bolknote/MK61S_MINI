from pathlib import Path
import hashlib,json,subprocess
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
E=ROOT/'.build/m0-exp-tiny-radius-20261024'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
load=lambda p:json.loads(p.read_text())
assert not (W/'FROZEN.json').exists()
b=load(W/'build.json');q=load(W/'qualification.json');p=load(W/'proof.json');a=load(W/'remaining-parent-audit.json');r=load(W/'rebuild-proof.json');c=load(W/'correction-cell-arm-binding.json');core=load(W/'core-dispatch-comparison.json')
assert q['candidate_ELF_sha256']==a['candidate_ELF_sha256']==r['candidate_ELF_sha256']==c['candidate_ELF_sha256']==sha(W/'candidate.elf')
assert q['source_sha256']==p['source_sha256']==sha(W/'candidate/native_eabi_m0.cpp')
assert q['unique_inputs']==428231 and q['profiled_states']==856462
assert q['old163675_parent_raw_losses']==669 and q['old163675_candidate_raw_losses']==155
assert q['union_candidate_raw_losses']==671 and q['old48763_candidate_raw_losses']==154
assert q['wrong']==a['wrong']==q['new_known_parent_raw_losses']==a['new_raw_losses']==q['tiny_correct_reference_raw_losses']==0
assert a['all_remaining_parent_states_now_bound'] and q['historical_exp16_remaining']==2
assert p['exhaustive_odd_class_certificates']==3145728 and p['integer_reciprocal_divide3_certificates']==65536
assert p['all_cubic_threshold_correction_cells']==154 and c['unique_actual_results_requiring_cubic_correction']==154
assert len(r['records'])==6 and b['CPP_code_delta_bytes']==276
assert core['changes']==[[3916,38,32]]
assert sha(W/'qualification-records.jsonl.gz')==q['qualification_records_sha256']
reg=load(W/'retained-parent-regressions.json')
assert len(reg)==239986 and all(t['candidate_instructions']<t['Qfplib_instructions'] for t in reg)
del reg
external={}
def pin(path):
 path=Path(path);name=str(path.relative_to(ROOT));v=dict(sha256=sha(path),bytes=path.stat().st_size)
 assert name not in external or external[name]==v
 external[name]=v
for name,entry in load(E/'FROZEN.json')['files'].items():
 path=E/name;assert sha(path)==entry['sha256'] and path.stat().st_size==entry['bytes'];pin(path)
pin(E/'FROZEN.json')
for name,entry in load(E/'source-lineage-pins.json')['files'].items():
 path=ROOT/name;assert sha(path)==entry['sha256'] and path.stat().st_size==entry['bytes'];pin(path)
review_path=ROOT/'.build/m0-exp-tiny-radius-independent-20261024/FINAL-REVIEW.json'
parent_review=dict(independent_review_available_at_seal=review_path.exists())
if review_path.exists():
 review=load(review_path);assert review['status'].startswith('GO_') and review.get('blockers')==[]
 assert review['target']['frozen']['sha256']==sha(E/'FROZEN.json')
 refs=[review['accepted_parent'],*review['target'].values(),*review['refs'].values()]
 for v in refs:
  path=Path(v['path']);assert sha(path)==v['sha256'] and path.stat().st_size==v['bytes'];pin(path)
 pin(review_path);parent_review.update(path=str(review_path.relative_to(ROOT)),sha256=sha(review_path),status=review['status'],receipt_and_direct_refs_verified=1+len(refs))
(W/'parent-review-at-seal.json').write_text(json.dumps(parent_review,indent=2)+'\n')
assert not subprocess.check_output(['git','diff','HEAD','--name-only','--','code/native_eabi_m0*'],cwd=ROOT,text=True).strip()
fresh=q['fresh_ARM_calls']+a['fresh_parent_ARM_calls']
result=dict(status='FROZEN_AUTHOR_EXACT_LOG_MIDPOINT_EXP_RNE_EXPANDED_TINY_DOMAIN',
 qualified_source_parent=str(E.relative_to(ROOT)),parent_review_at_seal=parent_review,
 source_sha256=b['source_sha256'],candidate_ELF_sha256=b['candidate_ELF_sha256'],
 qualified_inputs=428231,qualified_states=856462,
 fresh_final_candidate_ARM_calls=q['fresh_candidate_ARM_calls'],fresh_Qfplib_ARM_calls=q['fresh_Qfplib_ARM_calls'],
 fresh_parent_remaining_audit_ARM_calls=a['fresh_parent_ARM_calls'],total_qualified_fresh_ARM_calls=fresh,
 inherited327350_parent_Qfplib_rows_not_counted_fresh=True,
 oracle_evaluations=428231,actual_directed_MPFR_input_conversions=428229,NaN_shortcuts_without_MPFR=2,MPFR_version=q['MPFR_version'],
 final_probe24898_superseded_trial24854_and_diagnostic2_calls_not_added=True,
 wrong=0,old163675_raw_returned_bits_identical=True,
 same_old163675_speed_losses=[669,155],same_old_corpus_additional_fixed=514,
 same_older48763_speed_losses_unchanged=154,
 expanded428231_speed_losses=671,
 expanded_count_scope='Same163675:669->155; new428231 corpus671=155old+514new2^-32endpointcontrols+2newordinarycontrols, all preexisting parent losses. Different-size corpus counts must not be subtracted.',
 all671remaining_losses_parent_cost_bound=True,new_raw_speed_losses=0,
 tiny_domain='2^-54 < abs(x) < 2^-32',tiny_range_expanded_factor=64,
 author_whole_tiny_domain_returned_value_RNE_source_proof=True,
 exhaustive_integer_log_tail_odd_classes=3145728,exact_uint32_divide3_cases=65536,
 cubic_threshold_correction_cells=154,all154critical_results_actual_ARM_and_directed_MPFR_bound=True,
 complete_integer_odd_class_certificate_not_same_as_complete_ARM_input_exhaustion=True,
 observed_tiny_instructions=[83,200],observed_tiny_correct_Qfplib_speed_losses=0,
 examples=[dict(x='3D90000000000000',parent=520,candidate=88,Qfplib=466),dict(x='BD90000000000000',parent=542,candidate=84,Qfplib=528)],
 correct_Qfplib_comparison=q['correct_Qfplib_comparison'],wrong_Qfplib_state_rows_retained=q['wrong_Qfplib_state_rows_retained'],no_nominal_domain_filter=True,
 selected_CPP_code_delta_bytes=276,private_Flash_overlay_load_delta_bytes=280,
 whole_firmware_size_and_GC_delta_not_measured=True,
 helper_bytes=[196,472],core_bytes=[5012,5012],core_only_change='adds r6,#38 -> adds r6,#32 at offset3916; all5011otherbytes andsemanticrelocations equal',
 static_core_stack_bytes=[96,96],static_helper_stack_bytes=[20,56],
 observed_full_corpus_stack_bytes=[376,376],
 known_parent_cost_increase_rows_retained=239986,all_these_states_still_faster_Qfplib=True,
 no_new_tables_global_RAM_libgcc_ROM_external_helper_calls=True,
 all_other_CPP_allocated_bytes_semantic_relocations_unchanged=True,
 complete_RP_ASM_allocated_bytes_semantic_relocations_unchanged=True,
 generic_M0_M4_selected_CPP_bytes_semantic_relocations_equal_and_ASM_sources_unchanged=True,
 six_complete_CPP_ASM_object_ELF_rebuilds_byte_exact=True,
 direct_public_exp_ABI_no_artificial_interposition_veneer=True,
 original507_union_unchanged=418,original507_remaining=89,original_exp16_remaining=2,
 hard_exp_diagnostic_first_refine_entry_costs=[546,558],hard_exp_total_instructions=[2268,2248],
 independent_review_pending=True,combined_integration_physical_cycles_and_release_pending=True,
 no_canonical_Git_USB_device_Flash_lease_EA9_or_release_changes=True,goal_complete=False)
(W/'result.json').write_text(json.dumps(result,indent=2)+'\n')
handoff=f'''Private RP2040 exp exact log-midpoint component; independent review pending.

Qualified parent .build/m0-exp-tiny-radius-20261024 is frozen unchanged.
Parent independent-review availability at seal is recorded separately:
{json.dumps(parent_review)}. Do not infer accepted status just from using
its qualified source. Its accepted f2d ancestor and complete lineage are
pinned. This is a function overlay, not a combined or bootable firmware.

Fast domain expands64fold:2^-54<abs(x)<2^-32. Exact input rounding
thresholds are log(1+u)/log(1-u), evaluated symbolically by integer floor
identities, not by runtime logarithms. A=odd²/2^q; the exact cubic floor
and exhaustively certified log-tail separation determine floor(D).
All3145728odd classes have strict rational certificates, all65536/3
reciprocal inputs are exact. This is not3million emulated inputs. The154
cells where the cubic changes a threshold all have both transitions in
the actual public ARM/MPFR corpus:308inputs/616states, including154
actual results that would be wrong with the quadratic-only shortcut.
For odd<65536 one uint32MUL suffices; others use exact44bit square/
66bit cube via accepted wide32, no runtime division or external calls.
NUMERIC-PROOF.md/proof.json give the full author tiny-domain RNE proof.

428231inputs/856462fullyprofiledstates: {fresh}fresh qualified ARM =
856462finalcandidate+529112newQfp+{a['fresh_parent_ARM_calls']}freshparentremainingaudit.
428229actualdirectedMPFR4.2.2+2preMPFRsNaNshortcuts. All327350previous
parent/Qfprows pinned/inherited, not newly executed.24898finalprobe,
24854supersededtrial and2diagnosticARM calls excluded.0wrong, rawbits
match parent on allold163675inputs. WrongQfp385334state outputs/costs
retained in qualification-records.jsonl.gz. No nominal-domain filter.

Same163675corpus:669->155rawlosses,514fixed. Older48763corpus remains
154. New428231corpus has671=155old+514newdense2^-32endpointneighbors
+2newordinarycontrols; all671losses have old/freshparent costs bound
and all preexisted,0new losses. Counts across different corpus sizes
must not be subtracted. All remaining rows are in qualification.json;
remaining-parent-audit.json binds every new remaining loss. Observed
tinypublic83..200ISA,0losses to numerically correctQfp.3D90000000000000:
520->88vsQfp466;negative counterpart542->84vs528. Original exp2hard
cases remain2268/2248vs649/622. Diagnostic shows546/558instructions
before entering refinement, so their next repair needs a cheap middle
decision or an earlier algorithm; no new algorithm claimed here.

Helper196->472B, net+276selectedCPPbytes, privateFlashload+280including
alignment; fullfirmware/GC size not measured. Core5012B unchangedsize;
only byte3916changes38->32 in ADDSr6,#cutoff. All other core bytes and
relocations match, so ordinary instruction paths outside the expanded
domain are unchanged. All239986knownparentcostincreases retained and
all still fasterQfp. Staticcore96same, helper20->56stack; fullobserved
max376same. No new tables/globalRAM/libgcc/ROM/externalhelpercalls.

All other fullCPPallocatedsections/semanticrelocations unchanged.
FullRPASM including d2f/f2d exactparent. GenericM0/M4soft/hard selected
CPPbytes/relocations exact; ASM source unchanged and inherited controls
apply.6completeCPP/ASMobject+ELFrebuildsbyteexact. Full472Bhelper source
and linked body bound exactly; no helperrelocations. ExplicitPHDRS and
directpublicABI, no artificialveneer. One CPPpatch, no buildlistchange.

Original507separateunion418/residual89 unchanged. Expandedexp671,
pow7904/ln5/sin22/cos14/FMA/generalpowtotality, wholemathregression,
repairedplatform integration, physicalcycles and release remain open.
No canonical/Git/USB/device/Flash/lease/EA9/release mutation. No whole
M4 or integratedfirmware build, productionGO or whole-goalGO.
'''
(W/'HANDOFF.md').write_text(handoff)
(W/'source-lineage-pins.json').write_text(json.dumps(dict(status='PINNED_QUALIFIED_TINY_PARENT_AND_COMPLETE_REFERENCE_LINEAGE',files=external),indent=2)+'\n')
files={str(path.relative_to(W)):dict(sha256=sha(path),bytes=path.stat().st_size) for path in sorted(W.rglob('*')) if path.is_file() and '__pycache__' not in path.parts}
sealed=dict(status='FROZEN_PRIVATE_AUTHOR_LOG_MIDPOINT_EXP_COMPONENT_PENDING_REVIEW',files=files,result_sha256=sha(W/'result.json'),HANDOFF_sha256=sha(W/'HANDOFF.md'),HEAD_at_seal=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),math_worktree_diff_empty=True,goal_complete=False)
(W/'FROZEN.json').write_text(json.dumps(sealed,indent=2)+'\n')
print(json.dumps(dict(status=sealed['status'],artifacts=len(files),external_lineage_pins=len(external),FROZEN_sha256=sha(W/'FROZEN.json'),result_sha256=sealed['result_sha256'],HANDOFF_sha256=sealed['HANDOFF_sha256'],fresh_qualified_ARM=fresh,same_old_corpus_losses=[669,155],expanded_union_losses=671,parent_review_at_seal=parent_review),indent=2))
