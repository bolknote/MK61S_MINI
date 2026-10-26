"""Seal the completed private component; never edit or rerun after sealing."""
from pathlib import Path
from datetime import datetime,timezone
from collections import Counter
import hashlib,json,shutil,subprocess,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
C=ROOT/'.build/m0-exp-directed-product-20261024'
sys.path.insert(0,str(ROOT/'tests'))
from check_stm32_vectors import ElfImage
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
read=lambda n:json.loads((W/n).read_text())
assert not (W/'FROZEN.json').exists()
b=read('build.json');q=read('qualification.json');a=read('remaining-parent-audit.json');c=read('certificate.json')
u=read('small-unit-proof.json');p=read('pack-unit-proof.json');g=read('private-return-proof.json')
binding=read('corpus-binding.json');rebuild=read('rebuild-proof.json');controls=read('private-guard-controls.json')
assert q['unique_inputs']==490031 and q['profiled_states']==980062
assert q['wrong']==q['new_known_parent_raw_losses']==a['new_raw_losses']==a['wrong']==0
assert q['old467366_parent_raw_losses']==1896 and q['old467366_candidate_raw_losses']==196
assert q['union_candidate_raw_losses']==214 and a['all_remaining_parent_states_now_bound']
assert q['old467366_raw_return_bits_identical'] and q['historical_exp16_remaining']==0
assert u['scalar_return_integer_oracles_wrong']==p['unsafe_admissions']==0
assert len(controls['postcall_negative_controls'])+len(controls['marker_to_consumer_negative_controls'])==17
assert g['marker_to_consumer_live_instructions']==88 and len(g['call_to_marker_instructions'])==2
assert g['all_marker_to_consumer_paths_preserve_R12_without_call_or_touch']
assert sha(W/'candidate.elf')==b['candidate_ELF_sha256']==q['candidate_ELF_sha256']==u['candidate_ELF_sha256']==g['candidate_ELF_sha256']
assert sha(W/'candidate/native_eabi_m0.cpp')==b['source_sha256']==q['source_sha256']==c['source_sha256']
assert sha(W/'private-return-proof.json')==c['private_return_proof_sha256']
assert sha(W/'pack-unit.elf')==p['unit_ELF_sha256']==c['pack_unit_ELF_sha256']
assert sha(W/'qualification-records.jsonl.gz')==q['qualification_records_sha256']
assert len(rebuild['outputs'])==11 and all(sha(Path(path))==digest for path,digest in rebuild['outputs'].items())
assert (W/'candidate/native_eabi_m0_pow_exp_product.inc').read_bytes()==(C/'candidate/native_eabi_m0_pow_exp_product.inc').read_bytes()
for n in ('native_eabi_m0.S','native_eabi_m0.hpp'):
 if (W/'candidate'/n).exists():assert (W/'candidate'/n).read_bytes()==(C/'candidate'/n).read_bytes()
def extent(im):
 sections=[s for s in im.named_sections.values() if s[2]&2 and s[1]!=8 and 0x10000000<=s[3]<0x10200000 and s[5]]
 return max(s[3]+s[5] for s in sections)-min(s[3] for s in sections)
oldflash=extent(ElfImage(C/'candidate.elf'));newflash=extent(ElfImage(W/'candidate.elf'))
assert newflash-oldflash==1136 and b['CPP_code_delta_bytes']==1136
fresh=q['fresh_ARM_calls']+a['fresh_parent_ARM_calls']+u['qualified_fresh_ARM_calls']+p['qualified_fresh_ARM_calls']
assert fresh==1203570
examples=read('selected-examples.json')['rows']
example_map={r['x']:{'parent':r['parent_instructions'],'candidate':r['candidate_instructions'],'Qfplib':r['Qfplib_instructions']} for r in examples if r['SIO']=='READY'}
out=dict(status='FROZEN_AUTHOR_NEAR_ONE_EXP_EXACT_INPUT_ULP_ENCLOSURE_PENDING_INDEPENDENT_REVIEW',
 accepted_source_parent=str(C.relative_to(ROOT)),accepted_source_parent_FROZEN_sha256=sha(C/'FROZEN.json'),
 accepted_parent_independent_review=read('verified-directed-parent-review.json'),
 source_sha256=b['source_sha256'],candidate_ELF_sha256=b['candidate_ELF_sha256'],
 only_RP_CPP_small_helper_and_dispatch_changed=True,one_CPP_file_patch='directed-to-near-one-exp.patch',
 exact_RNE_source_enclosure='NUMERIC-PROOF.md and certificate.json',
 all_old467366_raw_return_bits_identical=True,wrong=0,new_raw_speed_losses=0,
 same_old467366_exp_losses=[1896,196],old_inputs_fixed=1700,
 expanded490031_exp_losses=214,expanded_count_scope='Same467366:1896->196,1700fixed. New490031union214=196old+18new measured preexisting losses; every remaining state parent-bound. Different-size corpus counts must not be subtracted.',
 all_remaining_parent_states_bound=True,new_parent_audit_ARM_calls=a['fresh_parent_ARM_calls'],
 old_subcorpus_remaining=binding['same_subset_remaining'],original_exp16_remaining=0,
 all_original_exp16_both_states_still_strict=True,
 public_unique_inputs=q['unique_inputs'],public_state_rows=q['profiled_states'],
 fresh_public_candidate_ARM_calls=q['fresh_candidate_ARM_calls'],fresh_new_Qfplib_ARM_calls=q['fresh_Qfplib_ARM_calls'],
 qualified_fresh_small_arithmetic_ARM_calls=u['qualified_fresh_ARM_calls'],qualified_fresh_literal_pack_ARM_calls=p['qualified_fresh_ARM_calls'],
 total_qualified_fresh_ARM_calls=fresh,actual_directed_MPFR_validation_inputs=q['actual_directed_MPFR_input_conversions'],
 sNaN_shortcuts_without_MPFR=q['NaN_shortcuts_without_MPFR'],oracle_evaluations=q['oracle_evaluations'],MPFR_version=q['MPFR_version'],
 separate_MPFR_log_preimage_generations=read('public-input-preparation.json')['MPFR_directed_log_preimage_generations'],
 inherited934732_parent_and_Qfplib_state_rows_not_fresh=True,
 all_probes_diagnostics_and_rejected_variants_excluded_from_qualified_totals=True,
 correct_Qfplib_state_comparison=q['correct_Qfplib_comparison'],wrong_Qfplib_state_rows_retained=q['wrong_Qfplib_state_rows_retained'],
 no_nominal_domain_filter=True,public_examples=example_map,
 retained_parent_cost_increase_state_rows=binding['known_parent_regression_rows'],retained_positive_instruction_deltas=binding['positive_instruction_delta_histogram'],
 retained_cost_increase_scopes=binding['regression_scopes'],
 small_high_product_instructions=list(u['instruction_counts']['mk61_m0_exp_small_product64'])[0],
 small_middle_product_instructions=list(u['instruction_counts']['mk61_m0_exp_small_product48'])[0],
 small_square_instructions=list(u['instruction_counts']['mk61_m0_exp_small_square48'])[0],
 small_assembly_frames36=True,small_pack_literal_calls=p['qualified_fresh_ARM_calls'],unsafe_literal_pack_admissions=0,
 exact_HOST_div15_values_not_ARM_calls=c['exact_div15_exhaustive_host_values'],
 code_delta_bytes=1136,private_Flash_load_bytes=[oldflash,newflash],whole_firmware_GC_size_not_measured=True,
 no_new_tables_global_RAM_libgcc_or_ROM_math=True,
 public_exp_static_frames=[96,88],new_small_helper_static_frame72=True,observed_public_stack_bytes=[744,q['candidate_stack_bytes']],
 stack_peaks_observed_not_universal=True,physical_cycles_not_measured=True,
 shared77_product_168byte_RAM_slot_and_all_existing_ASM_sources_unchanged=True,
 all_other_CPP_allocated_bytes_semantic_relocations_equal=True,generic_M0_M4_soft_hard_selected_CPP_equal=True,
 eleven_actual_object_ELF_rebuilds_byte_exact=True,
 required_actual_linked_R12_guard_in_builder=True,guard_reads_fresh_actual_disassembly=True,
 private_R12_scalar_C_ABI_not_sufficient=True,post_call_instructions2_live_instructions88=True,
 private_guard_negative_AST_controls17=True,required_again_on_every_changed_integrated_object=True,
 other_operation_qualifications_inherited_not_fresh=True,pow_expanded_remaining7901_unchanged=True,ln_expanded_remaining5_unchanged=True,
 original507_author_separate_union=dict(no_slower=423,strictly_faster=417,equal=6,remaining=84,remaining_by_operation=dict(pow=48,sin=22,cos=14,exp=0),not_one_integrated_binary=True),
 original507_independently_reviewed_union_kept422_per_root=True,
 independent_review_pending=True,combined_integration_general_totality_FMA_physical_cycles_and_release_pending=True,
 no_canonical_Git_USB_device_Flash_lease_EA9_or_release_mutations=True,goal_complete=False)
(W/'result.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
notes=dict(status='VALIDATION_SCOPE_AND_EXCLUDED_TRIALS',selected='six-term high product, nine-term bit48 product, six-MULS square, exact32bit packing',
 prevalidation_scale37to36_corrected_before_any_ARM_oracle_calls=True,
 rejected_variants=dict(CXX_products='7180inputs,0wrong,514new raw losses; rejected',ASM_products='12diagnostic inputs only; still too slow',sixmul_square='7180inputs,0wrong/0new within probe; new power controls exposed later, not full qualification',coarse_fifth='12diagnostic inputs only; source superseded',skip_fifth='11205inputs,0wrong,4new raw losses; rejected'),
 selected_probe=dict(inputs=11205,fresh_ARM_calls=67230,wrong=0,new_losses=0,excluded_from_qualified_totals=True),
 rejected_tight_curvature='../m0-exp-tight-curvature-20261024/REJECTED.json',
 qualified_counts=dict(public=q['fresh_ARM_calls'],parent_audit=a['fresh_parent_ARM_calls'],small_integer_units=u['qualified_fresh_ARM_calls'],pack_units=p['qualified_fresh_ARM_calls'],total=fresh),
 no_new_other_caller_or_MPFR_runs_pooled=True)
(W/'VALIDATION-NOTES.json').write_text(json.dumps(notes,indent=2)+'\n')
handoff=f'''Private RP2040 near-one exp candidate; accepted parent directed product e6ce7678,
independent TECH_GO0d6073f3 and ROOT7ec53f3c directly reverified. New review pending.

Same467366exp inputs:1896->196 speed losses,1700fixed. Full490031union214
=196old+18new measured preexisting; all428remaining states parent-bound,
36fresh parent ARM calls,0new losses. All old raw result bits identical,
0wrong. All16originalexp remain strictly faster in both SIO states.
Example3E9049F06E7592B7:18068->444vs494;3EC1BD399F566C29:2149->444vs544;
negativeBE99A94473BFE892:18448->467vs612. Power2^-16:438->426vs474.
Some5712parentstate cost increases retained(+1..44):5662still no slower
than correctQfp,34wrong-reference,16already lost.407820wrongQfpstate
outputs/costs retained; no nominal-domain filter. See raw gzip and bindings.

The new helper retains exact linear M and encloses the nonlinear correction
in input-ulp Q16 for e=-32..-12. Short high product keeps6terms, bit48
product9terms, square uses6MULS. Explicit full-source rational error guard
4*floor(Z/2^48)+32+extra+fifth_error; exact modular interval packing.
Declines use unchanged exp_refine(x,0). All operand bounds/carries/shift
ranges/coarse fifth and exact/15 proven in NUMERIC-PROOF/certificate.
104054bare arithmetic ARM checks including all16NZCV;74088literal pack
checks across21binades/both signs/carry/admission boundaries,0unsafe.

Full public validation:980062fresh candidate+45330fresh newQfp ARM;
934732parent/reference rows inherited, not fresh.490029actual directed
MPFR inputs+2sNaN shortcuts.2688log generations separate. Total qualified
fresh ARM1203570=1025392public+36parent+104054integer+74088pack.
Probes/trials/diagnostics not pooled; see VALIDATION-NOTES and archived trials.

Code/privateFlash+1136B,{oldflash}->{newflash}; no new tables/globalRAM/
libgcc/ROMmath. Shared77product,168B RAMslot and every existing ASM source
unchanged. All other CPP allocated bytes/semantic relocs equal; selected
genericM0/M4soft/hard CPP equal;11whole object/ELF rebuilds byte-exact.
Public static frame96->88, new helper72; observed full exp peak744->808,
not a universal stack bound. One CPP file patch; no build-list changes.

PrivateR12 guard now reads fresh actual disassembly and validates producer
through2postcall instructions/zero-byte definition marker to actual88-
instruction consumer live range, unchanged real16BFlash tailveneer.
Builder automatically runs it;17negative AST controls pass. It must be
installed/adapted/rerun on each changed actual integrated object. Scalar
C prototype or this private receipt alone is insufficient for integration.

Original507author separate union unchanged423=417strict+6equal;84remain
(pow48/sin22/cos14,exp0). Reviewed422kept by ROOT instruction. Pow7901,
ln5 inherited separate qualifications, no fresh other-caller tests claimed.
Expandedexp214,FMA/general totality/combined integration/regression/physical
cycles/release remain open. No canonical/Git/USB/device/Flash/lease/EA9/
release mutations. Goal active; no hardware or production GO.
'''
(W/'HANDOFF.md').write_text(handoff)
if (W/'WORK-SCOPE.json').exists():(W/'WORK-SCOPE.json').rename(W/'WORK-SCOPE-AT-START.json')
(W/'WORK-SCOPE.json').write_text(json.dumps(dict(status='FROZEN_AUTHOR_QUALIFIED_PRIVATE_NEAR_ONE_EXP_PENDING_REVIEW',source_parent=str(C.relative_to(ROOT)),source_parent_independent_review_pending=False,current_independent_review_pending=True,no_canonical_Git_USB_device_Flash_changes=True,goal_complete=False),indent=2)+'\n')
logs=W/'logs';logs.mkdir()
for log in sorted((ROOT/'.build').glob('m0-exp-near-one-*.log')):
 if 'finalize' not in log.name:shutil.copyfile(log,logs/log.name)
pins={}
def pin(path,expected=None):
 path=Path(path)
 if not path.is_absolute():path=ROOT/path
 row=dict(bytes=path.stat().st_size,sha256=sha(path))
 if expected:assert row=={k:expected[k] for k in ('bytes','sha256')},path
 try:name=str(path.relative_to(ROOT))
 except ValueError:name=str(path)
 assert name not in pins or pins[name]==row,(name,pins.get(name),row)
 pins[name]=row
parentpins=json.loads((C/'source-lineage-pins.json').read_text())
for name,row in parentpins['files'].items():pin(name,row)
parentf=json.loads((C/'FROZEN.json').read_text())
for name,row in parentf['files'].items():pin(C/name,row)
pin(C/'FROZEN.json');pin(ROOT/'.build/m0-exp-directed-product-postseal-20261024.json')
def references(x):
 if isinstance(x,dict):
  if all(k in x for k in ['path','bytes','sha256']):pin(x['path'],x)
  for v in x.values():references(v)
 elif isinstance(x,list):
  for v in x:references(v)
for name in ['.build/m0-exp-directed-product-independent-20261024/FINAL-REVIEW.json','.build/m0-exp-directed-product-root-acceptance-20261024-001/RECEIPT.json']:
 pin(name);references(json.loads((ROOT/name).read_text()))
(W/'source-lineage-pins.json').write_text(json.dumps(dict(status='PASS_ALL_EXTERNAL_PARENT_REVIEW_AND_SOURCE_LINEAGE_SHA_SIZE_PINS',files=dict(sorted(pins.items()))),indent=2)+'\n')
diff=subprocess.check_output(['git','diff','HEAD','--name-only','--','code/native_eabi_m0*'],cwd=ROOT,text=True)
assert not diff,'Canonical math changed during private work; inspect before claiming scope'
head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
files={str(path.relative_to(W)):dict(bytes=path.stat().st_size,sha256=sha(path)) for path in sorted(W.rglob('*')) if path.is_file() and path.name!='FROZEN.json'}
frozen=dict(status='FROZEN_PRIVATE_AUTHOR_NEAR_ONE_EXP_COMPONENT_PENDING_REVIEW',files=files,utc=datetime.now(timezone.utc).isoformat(),result_sha256=sha(W/'result.json'),HANDOFF_sha256=sha(W/'HANDOFF.md'),HEAD_at_seal=head,math_worktree_diff_empty=True,goal_complete=False)
(W/'FROZEN.json').write_text(json.dumps(frozen,indent=2)+'\n')
print(json.dumps(dict(status=frozen['status'],artifacts=len(files),external_lineage_pins=len(pins),FROZEN_sha256=sha(W/'FROZEN.json'),result_sha256=frozen['result_sha256'],HANDOFF_sha256=frozen['HANDOFF_sha256'],candidate_ELF_sha256=b['candidate_ELF_sha256'],fresh_qualified_ARM=fresh,same_old_exp_losses=[1896,196],expanded_exp214=True),indent=2))
