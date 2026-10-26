"""Freeze the qualified private table-product component without canonical writes."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,subprocess
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
assert not (W/'FROZEN.json').exists()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
read=lambda p:json.loads(p.read_text())
source=read(W/'source-proof.json');old=read(W/'old-qualification.json')
new=read(W/'new-qualification.json');unit=read(W/'unit-proof.json')
union=read(W/'union-summary.json');rebuild=read(W/'rebuild-proof.json')
assert source['candidate_ELF_sha256']==old['candidate_ELF_sha256']==new['candidate_ELF_sha256']==unit['candidate_ELF_sha256']==rebuild['candidate_ELF_sha256']==sha(W/'candidate.elf')
assert not old['new_loss_state_variants'] and new['new_raw_loss_pairs']==union['new_raw_loss_pairs']==0
assert union['qualified_fresh_ARM_calls']==314546
assert union['original153']['candidate']==dict(slower=35,strict=118)
assert source['source_ASM_allocated_code_delta']==32
assert not subprocess.check_output(['git','diff','HEAD','--name-only','--','code/native_eabi_m0*'],cwd=ROOT,text=True)

lineage={}
def pin(path,expected=None):
    p=Path(path);p=p if p.is_absolute() else ROOT/p
    value=dict(sha256=sha(p),bytes=p.stat().st_size)
    if expected is not None:assert value==expected,p
    try:name=str(p.relative_to(ROOT))
    except ValueError:name=str(p)
    if name in lineage:assert lineage[name]==value,name
    lineage[name]=value
C=ROOT/'.build/m0-exp-directed-product-20261024'
for name,value in read(C/'source-lineage-pins.json')['files'].items():pin(name,value)
for name,value in read(C/'FROZEN.json')['files'].items():pin(C/name,value)
for name in ['FROZEN.json','source-lineage-pins.json']:pin(C/name)
for name in ['.build/m0-exp-directed-product-independent-20261024/FINAL-REVIEW.json',
             '.build/m0-exp-directed-product-root-acceptance-20261024-001/RECEIPT.json',
             '.build/m0-pow-rsqrt-asm-independent-20261024/FINAL-REVIEW.json',
             '.build/m0-pow-square-ordinary-independent-20261024/FINAL-REVIEW.json',
             '.build/m0-float-fma-qualification-20261023/support/native_eabi_m0_arm_self_test.py',
             '.build/m0-float-fma-qualification-20261023/support/m0_mpfr_oracle.py',
             '.build/m0-float-fma-qualification-20261023/oracles.py',
             'tests/check_stm32_vectors.py',
             '.build/m0-v138-execution-20261023/sources/compositions.c']:
    pin(name)
for name,digest in read(W/'corpus-binding.json')['sources'].items():
    pin(name);assert lineage[name]['sha256']==digest
(W/'source-lineage-pins.json').write_text(json.dumps(dict(status='VERIFIED_PARENT_AND_EXECUTION_LINEAGE',files=lineage),indent=2)+'\n')

result=dict(status='FROZEN_AUTHOR_TABLE_ONLY_POW_PRODUCT_13_ORIGINAL_FIXES_PENDING_REVIEW',
    source_parent=str(C.relative_to(ROOT)),source_parent_FROZEN_sha256=sha(C/'FROZEN.json'),
    candidate_ELF_sha256=sha(W/'candidate.elf'),CPP_sha256=source['CPP_sha256'],ASM_sha256=source['ASM_sha256'],
    source_bound_proof_sha256=sha(W/'source-proof.json'),numeric_proof_sha256=sha(W/'NUMERIC-PROOF.md'),
    original_pow153_remaining=[48,35],original_new_strict_fixes=13,original_candidate_strict=118,
    same_old111912_pair_losses=[7901,7888],same_old_profiled_states=223824,
    old_reference_state_variants=223976,old_wrong_Qfplib_state_variants_retained=51126,
    expanded_union_pairs=union['union_unique_pairs'],expanded_union_losses=[10866,10853],
    expanded_union_states=union['union_states'],expanded_union_reference_state_variants=union['union_reference_state_variants'],
    expanded_count_scope='New independent controls and reference variants add2965 measured preexisting loss pairs; use same-corpus comparisons only.',
    wrong=0,new_raw_speed_losses=0,all_old_raw_return_bits_identical=True,
    universal_table_entry_value_equivalence_to_old_helper=True,all512_table_roots_checked_and_seen_public=True,
    general_product_instructions=77,table_generic_instructions=79,table_dyadic_instructions=10,
    table_generic_cost_increase=2,table_dyadic_cost_reduction=67,new_real_Flash_wrapper_instructions=5,
    retained_union_parent_cost_increase_states=8024,retained_increase_instructions=2,
    retained_increase_scopes=union['retained_increase_scopes'],
    union_wrong_Qfplib_state_variants_retained=union['wrong_Qfplib_state_variants_retained'],
    correct_Qfplib_union_comparison=union['correct_Qfplib_state_variant_comparison'],no_nominal_reference_domain_filter=True,
    fresh_old_candidate_ARM_calls=223824,fresh_new_public_ARM_calls=58332,fresh_bare_ARM_calls=32390,
    total_qualified_fresh_ARM_calls=314546,actual_fresh_directed_MPFR_inputs=4785,sNaN_policy_shortcuts=76,
    fresh_oracle_evaluations=4861,MPFR_version=new['MPFR_version'],pilot3096_calls_and_failed_launch_excluded=True,
    inherited_parent_R_C77_Qfplib_and_old_MPFR_calls_not_fresh=True,known_C77_sensitive_state_costs_rechecked=10081,
    all16_incoming_NZCV_variants_and_PCS_SP_PC_boundedwrites_checked=True,
    source_ASM_allocated_code_delta_bytes=32,CPP_allocated_bytes_and_all_tables_unchanged=True,
    no_new_tables_global_RAM_libgcc_or_ROM_math_dependencies=True,
    reserved_RAM_bytes=4080,generic_leaf_frame_bytes=36,dyadic_leaf_frame_bytes=0,
    full_public_stack_observed_same_corpus_parent_control_candidate=2284,
    smaller_old_corpus_peak2236_not_a_regression_comparator=True,
    CPP_static_frames_identical=True,
    private_diagnostic_Flash_relocated_existing_code_and_data_bytes=source['private_diagnostic_Flash_load_bytes'],
    whole_firmware_GC_size_not_measured=True,
    generic_M0_M4_soft_hard_selected_CPP_ASM_allocated_bytes_and_semantic_relocations_equal=True,
    twenty_complete_object_ELF_rebuilds_byte_exact=True,
    unchanged_old_general154bytes_and_original16byte_Flash_wrapper_preserve_R12_extra_contract=True,
    integrated_release_must_rerun_actual_R12_guard=True,
    integration_must_merge_sources_not_overwrite_new_table_entry_with_old168byte_overlay_padding=True,
    original507_author_separate_union=dict(no_slower=436,strictly_faster=430,equal=6,remaining=71,
        remaining_by_operation=dict(pow=35,sin=22,cos=14),not_one_integrated_binary=True),
    original507_reviewed_union_kept422_per_root=True,independent_review_pending=True,
    general_pow_totality_other_math_speed_integration_physical_cycles_and_release_pending=True,
    no_canonical_Git_USB_device_Flash_lease_EA9_or_release_changes=True,goal_complete=False)
(W/'result.json').write_text(json.dumps(result,indent=2)+'\n')
(W/'HANDOFF.md').write_text('''The RP2040 table-only pow product component is frozen for independent review.

Original pow153:48->35 deficits; all13 new fixes are strict in READY/DIRTY.
The same111912-pair corpus improves7901->7888. The expanded116468-pair
union improves10866->10853,0wrong/0new losses. The additional2965 measured
loss pairs were already slow in the parent. Keep all three Qfplib
compositions, their wrong outputs/costs and all8024 +2 instruction states.

Exact table rowzero uses10 instructions instead of77; other table calls
use79. Other users retain the old77-instruction/154-byte general entry,
including its extra R12 fraction. The real Flash wrapper executes5.
CPP allocated bytes and tables are identical; only3 call relocations
change. ASM allocation adds32B (16RAM including2 alignment +16Flash),
without new tables/global RAM/libgcc. Scratch stays4080B. Static frames
are identical. On the new corpus parent/control/candidate peak2284B;
old2236B was a smaller corpus, not evidence of an increased frame.

314546qualified fresh ARM calls:223824 old candidate +58332 new public
+32390 bare. New validation uses4785 actual directed MPFR inputs +76sNaN
shortcuts. Old MPFR/R/C77/Qfplib rows are inherited, not newly executed.
The3096pilot calls and failed early launcher are excluded. All512 roots,
all16NZCV, PCS/SP/PC and bounded writes are checked. All20 complete
objects/ELFs rebuild byte exactly. See NUMERIC-PROOF/source-proof and
VALIDATION-NOTES for source binding, padding and full reference accounting.

The private diagnostic image relocates existing code/readonly constants
(control58256/candidate58272B). This is not additional algorithmic table
storage or a measured integrated-firmware GC delta. Public entries and
all3 changed call-site sections remain at original addresses. Actual GNU
veneers and real ROM memory/CLZ routines execute; no arithmetic mocks.

Original507 author union436=430strict+6equal;71remain(pow35/sin22/cos14).
Reviewed507 remains422 by ROOT's explicit rule. This is not a combined
library or firmware result. Independent component review, general pow
totality, remaining speed paths, integration, physical cycles and hardware
acceptance remain open. M4/defaultM0 selected CPP/ASM controls are equal;
a complete M4 firmware was not rebuilt. No device or canonical/Git edit.

Integration must merge the source deltas and relink. Loading an old
168-byte product overlay after this new bank would overwrite the new
entry with its old padding. The eventual actual integrated exp image
must rerun its required R12 call/capture/live-range guard.
''')
scope=read(W/'WORK-SCOPE.json');scope['status']='QUALIFIED_PRIVATE_CANDIDATE_FROZEN_PENDING_INDEPENDENT_REVIEW'
scope['source_ASM_allocation_delta']=32;scope['new_math_qualified_ARM_calls']=314546
(W/'WORK-SCOPE.json').write_text(json.dumps(scope,indent=2)+'\n')
(W/'progress.json').write_text(json.dumps(dict(status='TERMINAL_PASS',completed_states=223824,total_states=223824,
    additional_new_states=9722,all_numerical_process_handles_terminal=True),indent=2)+'\n')

excluded={'link.py','link.log','control.ld','candidate.ld','control.map','candidate.map',
          'RAM-control.o','RAM-control-fixture.S','RAM-control-fixture.o','pow-control-asm.o'}
files={}
for p in sorted(W.rglob('*')):
    if not p.is_file() or p.name in excluded or '__pycache__' in p.parts:continue
    files[str(p.relative_to(W))]=dict(bytes=p.stat().st_size,sha256=sha(p))
frozen=dict(status='FROZEN_QUALIFIED_PRIVATE_POW_TABLE_PRODUCT_COMPONENT',files=files,
    excluded_original_layout_trials=sorted(excluded),utc=datetime.now(timezone.utc).isoformat(),
    result_sha256=sha(W/'result.json'),HANDOFF_sha256=sha(W/'HANDOFF.md'),
    HEAD_at_seal=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
    math_worktree_diff_empty=True,goal_complete=False)
(W/'FROZEN.json').write_text(json.dumps(frozen,indent=2)+'\n')
print(json.dumps(dict(files=len(files),external_lineage_pins=len(lineage),FROZEN_sha256=sha(W/'FROZEN.json'),
    result_sha256=sha(W/'result.json'),HANDOFF_sha256=sha(W/'HANDOFF.md'),candidate_ELF_sha256=sha(W/'candidate.elf'),
    original_pow=[48,35],same_old_expanded=[7901,7888],new_union=[10866,10853],qualified_ARM=314546),indent=2))
