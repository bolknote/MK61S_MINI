"""Freeze only the author-qualified private pow component and explicit limits."""
from pathlib import Path
import difflib,hashlib,json,subprocess,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1];P=ROOT/'.build/m0-asin-scaled-bound-v164-20261023';B=ROOT/'.build/m0-exp-cached-product-20261024';T=ROOT/'.build/m0-pow-square-exact-20261024'
assert not (W/'FROZEN.json').exists()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
load=lambda n:json.loads((W/n).read_text())
b=load('build.json');q=load('qualification.json');c=load('certificate.json');i=load('isolation.json');r=load('rebuild-proof.json');f=load('focused-final.json')
assert q['candidate_ELF_sha256']==b['images']['candidate']['ELF_sha256']==c['candidate_ELF_sha256']==i['candidate_ELF_sha256']==f['candidate_ELF_sha256']
assert q['candidate_wrong']==0 and q['all_cases_profiled'] and q['unique_inputs']==63795 and q['public_state_cases']==127590
assert q['original153_parent_remaining']==149 and q['original153_candidate_remaining']==82
assert q['all_parent_raw_losses']==27414 and q['all_candidate_raw_losses']==8078 and q['new_candidate_raw_losses']==0
assert f['candidate_wrong']==0 and f['new_candidate_raw_losses']==0 and f['control_counts_equal_parent']
assert i['whole_intended_sources_emit_identical_public_allocated_bytes']
assert all(x['allocated_code_data_identical'] for x in i['contexts'])
assert r['status']=='PASS_COMPLETE_CPP_ASM_PARTIAL_AND_WHOLE_SOURCE_ELF_REBUILDS_BYTE_EXACT'
assert c['all_guard_sticky_and_tie_parity_bits_retained']
assert sha(W/'candidate.elf')==b['images']['candidate']['ELF_sha256']
assert sha(W/'candidate/native_eabi_m0.cpp')==q['source_alias_CPP_sha256']
assert sha(W/'square.S')==q['square_source_sha256']
loss=lambda row,which:row['correct']['Qfplib'] and row['instructions'][which]>row['instructions']['Qfplib']
historical=[row for row in q['rows'] if row['group']=='historical153']
keys={(row['x'],row['y']) for row in historical if loss(row,'parent') and not loss(row,'candidate')}
assert len(keys)==67
fixed=[row for row in historical if (row['x'],row['y']) in keys]
assert all(row['instructions']['candidate']<row['instructions']['Qfplib'] for row in fixed)
assert {row['y'] for row in fixed}=={'0000000000000000','4000000000000000'}
assert len({(row['x'],row['y']) for row in fixed if row['y']=='0000000000000000'})==19
assert len({(row['x'],row['y']) for row in fixed if row['y']=='4000000000000000'})==48
(W/'historical67-fixed.json').write_text(json.dumps(dict(status='ALL67_NEW_ORIGINAL_POW_FIXES_STRICTLY_FASTER_BOTH_SIO_STATES',rows=fixed),indent=2)+'\n')
regressions=[row for row in q['rows'] if row['instructions']['candidate']>row['instructions']['parent']]
assert len(regressions)==63976
max_reg=max(row['instructions']['candidate']-row['instructions']['parent'] for row in regressions)
(W/'retained-parent-regressions.json').write_text(json.dumps(dict(status='ALL63976_STATE_COST_INCREASES_RETAINED',rows=regressions),indent=2)+'\n')
# The numerical square trial is frozen separately; bind actual code bytes,
# not only the source hash, and do not add its old calls to fresh totals.
sys.path.insert(0,str(ROOT/'tests'))
from check_stm32_vectors import ElfImage
unit=json.loads((T/'unit-proof.json').read_text());mid=json.loads((T/'midpoint-proof.json').read_text());seal=json.loads((T/'FROZEN-NUMERIC-TRIAL.json').read_text())
for name,pin in seal['files'].items():assert (T/name).stat().st_size==pin['bytes'] and sha(T/name)==pin['sha256']
images=[ElfImage(T/'unit.elf'),ElfImage(T/'candidate.elf'),ElfImage(W/'candidate.elf'),ElfImage(W/'whole-source.elf')]
module_bytes=[im.bytes_at(im.named_sections['.square']) for im in images]
assert all(x==module_bytes[0] for x in module_bytes) and len(module_bytes[0])==328
assert unit['candidate_wrong']==mid['candidate_wrong']==0 and unit['actual_ARM_calls']+mid['actual_ARM_calls']==572776
assert unit['exact_midpoint_input_count']==0 and mid['exact_midpoint_input_count']==18432
inherit=dict(status='PASS_INHERITED_ACTUAL_SQUARE_MODULE_BYTE_BINDING',square_source_sha256=sha(W/'square.S'),
 module_sha256=hashlib.sha256(module_bytes[0]).hexdigest(),module_bytes=328,
 unit_proof=dict(path=str((T/'unit-proof.json').relative_to(ROOT)),sha256=sha(T/'unit-proof.json'),ARM_calls=462184,unique_inputs=231092),
 midpoint_proof=dict(path=str((T/'midpoint-proof.json').relative_to(ROOT)),sha256=sha(T/'midpoint-proof.json'),ARM_calls=110592,unique_inputs=55296,actual_exact_midpoint_inputs=18432),
 trial_seal_sha256=sha(T/'FROZEN-NUMERIC-TRIAL.json'),inherited_ARM_calls_not_added=572776,
 main_unit_had_zero_actual_half_cells=True,supplemental_midpoint_proof_covers_actual_half_cells=True,
 unit_private_trial_current_public_and_whole_source_modules_identical=True,hardware_accessed=False)
(W/'inherited-kernel-proof-binding.json').write_text(json.dumps(inherit,indent=2)+'\n')
# A reviewable patch against the exact accepted exp/product source lineage.
patch=''
for name in ('native_eabi_m0.cpp','native_eabi_m0.S'):
 old=(W/'control'/name).read_text().splitlines(keepends=True);new=(W/'candidate'/name).read_text().splitlines(keepends=True)
 patch+=''.join(difflib.unified_diff(old,new,fromfile='a/code/'+name,tofile='b/code/'+name))
for name in ('native_eabi_m0_pow_ordinary.inc','native_eabi_m0_pow_square.inc'):
 new=(W/'candidate'/name).read_text().splitlines(keepends=True)
 patch+=''.join(difflib.unified_diff([],new,fromfile='/dev/null',tofile='b/code/'+name))
(W/'accepted-exp-product-to-pow.patch').write_text(patch)
proof_names=['preparation.json','build.json','certificate.json','isolation.json','rebuild-proof.json','qualification.json','focused-final.json','inherited-kernel-proof-binding.json','historical67-fixed.json','retained-parent-regressions.json']
result=dict(status='FROZEN_AUTHOR_QUALIFIED_RP_POW_EXACT_SQUARE_AND_ORDINARY_DISPATCH',
 scope='Private function overlays and complete intended source objects. No canonical/repaired-platform firmware integration, all-domain pow totality, physical cycles or independent review GO.',
 wrapper_source_sha256=b['images']['candidate']['source_sha256'],full_CPP_source_sha256=q['source_alias_CPP_sha256'],
 full_ASM_source_sha256=i['full_ASM_source_sha256'],square_source_sha256=q['square_source_sha256'],ordinary_include_sha256=i['ordinary_include_sha256'],
 candidate_ELF_sha256=q['candidate_ELF_sha256'],whole_source_ELF_sha256=i['whole_source_ELF_sha256'],patch_sha256=sha(W/'accepted-exp-product-to-pow.patch'),
 public_unique_inputs=63795,fully_profiled_public_states=127590,qualified_fresh_public_ARM_calls=127590,fresh_directed_MPFR_references=63795,MPFR_version=q['MPFR_version'],candidate_wrong=0,
 original_pow153_remaining_before=149,original_pow153_remaining_after=82,new_original_pow_fixes=67,zero_exponent_fixed=19,square_exponent_fixed=48,
 expanded_pow_raw_losses_before=27414,expanded_pow_raw_losses_after=8078,new_correct_Qfplib_raw_losses=0,
 comparison_has_no_reference_domain_filter=True,all_numerically_wrong_reference_rows_retained=True,
 vs_parent=q['vs_parent'],retained_parent_regression_states=63976,maximum_retained_parent_cost_increase=max_reg,
 positive_exponent_zero_ordinary_path_removes_duplicate_checks=True,nonzero_low_exponent_word_counts_identical_parent=True,
 observed_public_stack_bytes=[2236,2236],exact_square_static_and_observed_stack_bytes=32,
 new_square_16bit_partial_multiplications=10,full_significand_product_bits=106,all_discarded_guard_round_sticky_bits_retained=True,
 gradual_underflow_and_all_IEEE_input_classes_covered=True,exact_squares_correctly_round_to_nearest_even=True,
 inherited_square_unit_ARM_calls_not_added=572776,inherited_live_exact_product_trace_calls=492666,
 inherited_actual_normal_half_cell_inputs=18432,
 fresh_four_machine_focused_verification_calls=f['actual_fresh_ARM_calls'],focused_repeats_excluded_from_qualified_totals=True,
 inherited_parent_control_reference_rows_not_counted_as_fresh=127590,
 all_existing_CPP_allocated_bytes_identical_parent=True,new_CPP_section_bytes=272,
 only_existing_ASM_section_changed='.m0_pow_dispatch_extension',ASM_object_code_delta=320,
 combined_CPP_ASM_object_allocated_code_delta=592,private_linked_function_overlay_allocated_code_delta=608,
 no_new_tables_global_RAM_or_libgcc=True,storage_free_aliases=True,
 complete_intended_source_allocated_bytes_identical_tested_overlays=True,
 complete_rebuilds_byte_exact=len(r['matched']),generic_M0_M4_CPP_ASM_controls_byte_identical=True,
 whole_M4_firmware_not_built=True,
 author_separate_original507_union=dict(no_slower=387,strictly_faster=381,equal=6,remaining=120,remaining_by_operation=dict(pow=82,exp=2,sin=22,cos=14),not_one_merged_ELF=True,new_independent_acceptance=False),
 independently_reviewed_original507_union_unchanged=320,
 accepted_exp_cached_product_parent_receipt='.build/m0-exp-cached-product-independent-20261024/FINAL-REVIEW.json',
 independent_review_pending=True,canonical_or_Git_changes=False,hardware_accessed=False,physical_cycles_measured=False,whole_math_GO=False,shipping_GO=False,goal_complete=False,
 remaining=['82 original pow gaps, including31 inverse-square-root exponents and51 other pow inputs.',
 '8078 expanded comparable pow input pairs still lose; known cost increases vs parent retained.',
 'Original exp2/sin22/cos14 plus expanded exp395/ln5, conversions/FMA remain separate and open.',
 'General pow1024-bit undecided trap/all-domain totality unchanged and unproved.',
 'Independent review, integration on repaired platform base, combined regressions and physical timing.'],
 proof_sha256={n:sha(W/n) for n in proof_names})
(W/'result.json').write_text(json.dumps(result,indent=2)+'\n')
text=f'''# Private RP2040 pow exact-square and ordinary dispatch

Frozen author component, independent review pending. Public overlay ELF `{q['candidate_ELF_sha256']}`; complete intended-source ELF `{i['whole_source_ELF_sha256']}`. Full CPP `{q['source_alias_CPP_sha256']}`, full ASM `{i['full_ASM_source_sha256']}`, exact square `{q['square_source_sha256']}`.

The assembly handles signed-zero exponents before allocating a dispatcher frame. `pow(x,+/-0)` returns1 except for correctly quieted signalling NaN. Identity, reciprocal and half-power cold semantics remain exact. The square computes the full106-bit53x53 significand product with10 partial16x16 products (two32-bit squares and one cross product), retains every rounding/sticky bit and rounds to binary64 RNE on normal or gradual-underflow grids. Inputs whose squares deterministically vanish or overflow return early; NaNs retain the input payload/sign and are quieted. The new ordinary low-word-zero dispatcher uses the byte-identical common source tail, skipping only checks disproved by the assembly precondition. Three exported aliases add no storage. Nonzero low exponent words retain the old dispatcher/counts. Cold half-power cases also retain the old dispatcher.

Fresh public qualification:63795pairs/127590fullyprofiledstates,127590new candidate ARM calls and63795fresh directed MPFR4.2.2 references,0wrong; exact returned bits match parent. Parent/control/Qfplib counts are inherited from a pinned prior full four-machine run and are not added as fresh calls. A separate final four-machine focused check ({f['actual_fresh_ARM_calls']}calls) rechecks historical/IEEE and the3 old trial losses; repeats excluded from qualified totals. Speed comparisons include every numerically correct reference result without a nominal-domain filter; wrong-reference outcomes and costs remain in full rows.

Original pow153: parent had149open after the earlier product improvement; now82open. New67strictfixes=19zero-exponent+48square inputs, both SIO states. Expanded27414→8078raw losses,0new. All63976state cost increases vs parent, maximum+{max_reg}, retained in retained-parent-regressions.json. Public maximum2236stack unchanged; exact-square leaf32. Code+592B in full source objects/+608B in private function overlay including a veneer, no new tables/globalRAM/libgcc. This is not a whole-firmware size result.

Exact unit proof inherited by actual module bytes:462184bareARM calls/231092inputs covering all2048input exponents and both signs, live product/shift/bias compared to integer arithmetic; the main unit had0actual midpoint inputs. Separate midpoint proof110592ARM/55296inputs contains18432actual normal half cells plus adjacent input ulps. The572776old calls are not counted as fresh in this component. All four bare/trial/current/complete-source square bodies are byte-identical. Source-bound integer proof covers the full product identity, carry bounds, normal/subnormal grid and complete RNE guard/sticky/parity logic;83160arbitrary128-bit word/shift model checks supplement actual square traces.

All old CPP allocated code/data remain byte-exact; only the new272Bordinary section is added. The existing ASM dispatch section changes, with square appended. Entire intended CPP+ASM source emits the same allocated bytes as the tested private overlays; {len(r['matched'])}complete object/ELF rebuilds are byte-exact. GenericM0/M4 soft/hard selected CPP+ASM controls unchanged. No whole M4 or repaired-platform firmware build, no device/USB/Flash/lease/Git/canonical actions.

Earlier exp/product parent received independent component GO857e13f2…; current reviewed separate count remains320. New author separate union387(381strict/6equal),120historical open(pow82 exp2 sin22 cos14), not one integrated library or new independent acceptance. Expanded exp395/ln5, conversions/FMA, general pow totality and physical timing remain open. The82original pow cases include31inverse-square-root inputs;51other cases remain. Goal remains active.

accepted-exp-product-to-pow.patch targets the exact accepted private exp/product math source lineage over frozenV164, not arbitrary current canonical sources. No build-list change is needed: two new includes are used by existing CPP/ASM translation units. Function overlays are not bootable firmware. Preserve the repaired platform base during later integration.
'''
(W/'HANDOFF.md').write_text(text)
# Pin the complete source/reference lineage and inherited proof targets.
external={}
paths=[p for p in (P/'source/code').glob('native_eabi_m0*') if p.is_file()]
paths += [P/'firmware/mk61s-picocalc-pico-h.elf',P/'slower-inputs.json',P/'build/compile_commands.json',B/'FROZEN.json',B/'candidate.elf',B/'candidate-full.o',B/'candidate/native_eabi_m0.cpp',B/'candidate/native_eabi_m0_pow_exp_product.inc',ROOT/'.build/m0-exp-cached-product-independent-20261024/FINAL-REVIEW.json',T/'FROZEN-NUMERIC-TRIAL.json']
paths += [T/n for n in seal['files']]
paths += [ROOT/'.build/m0-v138-execution-20261023/reference/reference.elf',ROOT/'research/rp2040-memset-2026-10-21/capture/bootrom.bin']
paths += [ROOT/n for n in q['corpus_pins']]
for p in paths:external[str(p.relative_to(ROOT))]=dict(sha256=sha(p),bytes=p.stat().st_size)
(W/'source-lineage-pins.json').write_text(json.dumps(dict(status='PINNED_ACCEPTED_PARENT_AND_NUMERICAL_KERNEL_PROOF_LINEAGE',files=external),indent=2)+'\n')
files={str(p.relative_to(W)):dict(sha256=sha(p),bytes=p.stat().st_size) for p in sorted(W.rglob('*')) if p.is_file()}
sealed=dict(status='FROZEN_PRIVATE_AUTHOR_POW_COMPONENT_PENDING_INDEPENDENT_REVIEW',files=files,result_sha256=sha(W/'result.json'),HANDOFF_sha256=sha(W/'HANDOFF.md'),HEAD_at_seal=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),math_worktree_diff_empty=subprocess.check_output(['git','diff','--stat','--','code/native_eabi_m0*'],cwd=ROOT,text=True).strip()=='',goal_complete=False)
(W/'FROZEN.json').write_text(json.dumps(sealed,indent=2)+'\n')
print(json.dumps(dict(status=sealed['status'],artifacts=len(files),external_lineage_pins=len(external),result_sha256=sealed['result_sha256'],HANDOFF_sha256=sealed['HANDOFF_sha256'],FROZEN_sha256=sha(W/'FROZEN.json'),new_original_pow_fixes=67,remaining_original_pow=82,expanded_pow_remaining=8078,new_Qfplib_losses=0,maximum_parent_cost_increase=max_reg,HEAD_at_seal=sealed['HEAD_at_seal'],math_worktree_diff_empty=sealed['math_worktree_diff_empty']),indent=2))
