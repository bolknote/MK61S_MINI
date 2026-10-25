"""Seal this private author packet; send stdout outside the packet directory."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,subprocess
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
assert not (W/'FROZEN.json').exists()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
load=lambda name:json.loads((W/name).read_bytes())
q=load('qualification.json');fresh=load('new-qualification.json');direct=load('direct-proof.json');summary=load('summary.json');proof=load('source-proof.json');build=load('build.json');rebuild=load('rebuild-proof.json')
elf=sha(W/'candidate.elf')
for d in [q,fresh,direct,proof,build['images']['candidate']]:assert d.get('candidate_ELF_sha256',d.get('ELF_sha256'))==elf
assert summary['fixed_pairs']==summary['strict_fixed_pairs']==48
assert summary['public_instruction_reduction_range']==[311,380]
assert summary['qualified_fresh_ARM_calls']==842693
assert len(rebuild['outputs'])==26
for p,h in rebuild['outputs'].items():assert sha(Path(p))==h
assert not subprocess.check_output(['git','diff','--','code/native_eabi_m0*'],cwd=ROOT)
base=ROOT/'.build/m0-pow-boundary128-20261025';parent=json.loads((base/'FROZEN.json').read_bytes());external={}
def put(path,pin=None):
 p=Path(path);p=p if p.is_absolute()else ROOT/p
 data=p.read_bytes();actual=dict(bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
 if pin:assert actual=={k:pin[k]for k in actual},p
 key=str(p.relative_to(ROOT))
 if key in external:assert external[key]==actual
 external[key]=actual
for p,pin in json.loads((base/'source-lineage-pins.json').read_bytes())['files'].items():put(p,pin)
for p,pin in parent['files'].items():put(base/p,pin)
put(base/'FROZEN.json')
receipt=proof['accepted_parent_ROOT_receipt'];put(receipt['path'],receipt)
for pin in json.loads((ROOT/receipt['path']).read_bytes())['pins']:put(pin['path'],pin)
for name in ['seed17.S','seed17.elf','seed-proof.json','verify-seed.py']:
 put(ROOT/'.build/m0-ddiv-soft-seed17-20261025'/name)
put(ROOT/'third_party/rp2040-softfloat/LICENSE.TXT')
(W/'source-lineage-pins.json').write_text(json.dumps(dict(status='VERIFIED_IMMUTABLE_PARENT_REVIEW_SEED_AND_SOURCE_LINEAGE',files=external),indent=2)+'\n')
result=dict(status='FROZEN_AUTHOR_DIRTY_SOFTWARE_RECIPROCAL_COMPONENT_PENDING_REVIEW',
 source_parent=str(base.relative_to(ROOT)),source_parent_FROZEN_sha256=sha(base/'FROZEN.json'),accepted_parent_ROOT_receipt=receipt,
 candidate_ELF_sha256=elf,source_proof_sha256=sha(W/'source-proof.json'),numeric_proof_sha256=sha(W/'NUMERIC-PROOF.md'),
 same_corpus_pairs=120980,states=241960,reference_state_variants=279522,loss_pairs=[11434,11386],new_strict_fixes=48,
 new_raw_losses=0,candidate_wrong=0,accelerated_DIRTY_states=377,public_instruction_reduction_range=[311,380],parent_cost_increase_states=0,
 READY_instructions_unchanged=True,all_parent_raw_return_bits_and_reciprocal_operands_identical=True,all377_changed_paths_fresh_parent_replayed=True,
 common_hardware_software_RNE_tail_bytes=282,common_tail_byte_identical=True,exact_seed194B_byte_identical_to_exhaustive_parent=True,
 direct_normal_seed_domain_exhaustive_65536=True,direct_join_R0_R6_R12_SP_saved20B_equal_states=66624,
 direct_no_per_divisor_Qfplib_speed_comparison_claim_for_unrecorded_exhaustive_rows=True,
 all936_wrong_direct_Qfplib_variants_raw_outputs_costs_retained=True,
 DIRTY_all7_SIO_words_preserved_and_no_divider_writes=True,seed_call_8byte_stack_alignment_checked=True,
 new_private_code_and_literals_bytes=1050,existing_dyadic32B_constants_duplicated=True,new_mathematical_table_values=False,
 new_global_RAM_or_libgcc_dependencies=False,private_root_reciprocal_call_only_other_ddiv_callers_unchanged=True,
 all_other_resident_code_addresses_scratch_and_veneers_unchanged=True,
 default_M0_M4_selected_root_objects_equal_and12_new_disabled_objects_empty=True,
 twenty_six_original_path_full_source_objects_ELFs_rebuilt_byte_exact=True,
 full_candidate_observed_stack_bytes=2284,fresh_parent_control_candidate_observed_stack_bytes=fresh['observed_stacks'],
 changed_path_parent388_subset_not_comparable_to_full2284=True,
 qualified_fresh_ARM_calls=842693,fresh_full_candidate_ARM_calls=241960,fresh_changed_parent_ARM_calls=377,
 fresh_direct_unit_calibration_ARM_calls=538832,fresh_MPFR_public_ARM_calls=61524,
 actual_directed_MPFR_inputs=6761,sNaN_policy_shortcuts=184,fresh_exact_integer_dyadic_oracle_inputs=65536,
 inherited_seed66288_and_pilot1836_MPFR153_and_preflight0_excluded=True,inherited_old_Qfplib_MPFR_not_fresh=True,
 wrong_public_Qfplib_reference_state_variants_retained=77106,correct_Qfplib_comparison=q['correct_Qfplib_comparison'],
 no_nominal_reference_domain_filter_and_strict_quiet_NaN_policy=True,original_pow153_remaining=[34,34],
 author_separate507_no_slower=437,author_separate507_strict=431,author_separate507_equal=6,reviewed_separate507_no_slower=422,
 general_pow_totality_remaining_math_speed_source_merge_integrated_R12_loader_layout_physical_cycles_and_release_pending=True,
 independent_review_pending=True,canonical_runtime_M4_Git_device_USB_Flash_or_release_changed=False,goal_complete=False)
(W/'result.json').write_text(json.dumps(result,indent=2)+'\n')
handoff='''# Private DIRTY reciprocal continuation: author qualification complete

The same 120980-pair / 241960-state corpus now has 11386 loss pairs versus
11434 previously:48 new strict fixes, zero new losses, wrong results or
parent cost increases.377 DIRTY public states save311–380 instructions.
READY costs and all actual parent return bits remain unchanged. All377
changed paths were also freshly replayed on the accepted boundary parent.
All279522 reference-state variants remain, including77106 wrong Qfplib
outputs and costs; every numerically correct reference is compared.

The private root reciprocal BL selects a guarded BSD-derived ddiv clone.
Only its DIRTY branch changes, to a software continuation. The exact seed17
reproduces the hardware integer quotient. Its194B body matches the earlier
exhaustive seed. The282B Newton/remainder/RNE tail is byte-identical in the
hardware and software bodies. Direct tests matched R0..R6,R12,SP and the
20B saved frame in66624 software/hardware joins, including every17-bit
seed divisor. Seed BL SP is8-aligned and all7 DIRTY SIO words are preserved
without any divider write. This continuation is private and requires the
guarded raw operands,R6 and existing20B frame; it is not a standalone ABI.

Fresh qualification comprises842693 actual ARM calls:241960 full candidates,
377 changed-path parents,61524 fresh public MPFR/control/reference calls,
and538832 direct unit/calibration calls. There are6761 directed MPFR inputs
plus184 sNaN policy shortcuts and65536 exact integer/dyadic oracle inputs.
The1836-call/153-MPFR pilot, failed import preflight0, inherited66288 seed
calls and old references/oracles are excluded. The direct proof retains
all936 wrong Qfplib variants; no per-divisor Qfplib speed claim is made for
the exhaustive unit portion whose timing rows were not retained. All public
reference outputs/costs are retained. All10254 fresh public controls match
the full records exactly. Twenty-six source/object/ELF rebuilds are exact.

The diagnostic division section adds1050B, including duplicated existing
32B dyadic constants and a hardware-body clone. There are no new mathematical
table values, global RAM or libgcc dependencies. It is a private pow-caller
experiment: all other ddiv callers remain at the original resident function.
Default M0/M4 selected controls are equal;12 new disabled objects are empty.
Full-corpus observed stack remains2284B; fresh parent/control/candidate
controls are2148B each. The changed-path parent388B is a subset, not a
comparison against the full candidate. No universal stack bound is claimed.

The original153 pow score remains119 strict /34 slower. Author separate507
remains437 no-slower(431 strict,6equal); reviewed separate507 stays422.
This is not one integrated executable or a universal speed claim. The parent
is now independently accepted by ROOT260cb67e. This new component still
requires independent review. Production source merge/relink, actual integrated
R12 consumer and loader/layout guards, the old168B-overlay/14B-table-entry
hazard, general pow totality, other needed math, physical cycles and release
remain open. No hardware/main/release GO, device access or Git change.

Numerical/relational argument:NUMERIC-PROOF.md. Source and disabled controls:
source-proof.json. Raw recount:summary.json. Historical scripts must never
be executed in this frozen directory. FROZEN.json binds this packet and its
source-lineage-pins.json. Overall goal remains active.
'''
(W/'HANDOFF.md').write_text(handoff)
(W/'progress.json').write_text(json.dumps(dict(status='AUTHOR_QUALIFICATION_COMPLETE_PENDING_REVIEW',completed_states=241960,total_states=241960),indent=2)+'\n')
scope=json.loads((W/'WORK-SCOPE.json').read_bytes());scope.update(status='AUTHOR_QUALIFICATION_COMPLETE_PENDING_REVIEW',this_turn_classification='progress: exact software seed continuation qualified on full corpus, 48 strict Qfplib fixes, 377 faster DIRTY states; READY and IEEE results preserved')
(W/'WORK-SCOPE.json').write_text(json.dumps(scope,indent=2)+'\n')
files={str(p.relative_to(W)):dict(bytes=p.stat().st_size,sha256=sha(p))for p in sorted(W.rglob('*'))if p.is_file()and'__pycache__'not in p.parts}
frozen=dict(status='FROZEN_AUTHOR_COMPONENT_PENDING_INDEPENDENT_REVIEW',utc=datetime.now(timezone.utc).isoformat(),files=files,
 result_sha256=sha(W/'result.json'),HANDOFF_sha256=sha(W/'HANDOFF.md'),goal_complete=False)
(W/'FROZEN.json').write_text(json.dumps(frozen,indent=2)+'\n')
print(json.dumps(dict(status='AUTHOR_COMPONENT_SEALED',local_files=len(files),external_pins=len(external),FROZEN_sha256=sha(W/'FROZEN.json'),result_sha256=sha(W/'result.json'),HANDOFF_sha256=sha(W/'HANDOFF.md'),candidate_ELF_sha256=elf),indent=2))
