"""Seal qualified square128 evidence without modifying parent packets or Git."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib, json, subprocess, sys
sys.dont_write_bytecode = True
W = Path(__file__).resolve().parent
ROOT = W.parents[1]
BASE = ROOT / '.build/m0-pow-exp-table-product-20261025'
assert not (W / 'FROZEN.json').exists()
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
q = json.loads((W / 'qualification.json').read_bytes())
n = json.loads((W / 'new-qualification.json').read_bytes())
u = json.loads((W / 'union-summary.json').read_bytes())
s = json.loads((W / 'source-proof.json').read_bytes())
r = json.loads((W / 'rebuild-proof.json').read_bytes())
assert q['candidate_wrong'] == n['candidate_wrong'] == u['candidate_wrong'] == 0
assert q['new_raw_losses'] == n['new_raw_losses'] == u['new_raw_losses'] == 0
assert r['status'].startswith('PASS_THIRTEEN') and len(r['outputs']) == 13
assert q['record_sha256'] == sha(W / 'qualification-records.jsonl.gz')
assert q['candidate_ELF_sha256'] == n['candidate_ELF_sha256'] == sha(W / 'candidate.elf')
external = {}
def pin(path, expected=None):
    path = Path(path)
    key = str(path.relative_to(ROOT))
    value = dict(bytes=path.stat().st_size, sha256=sha(path))
    if expected:
        assert value == {k: expected[k] for k in ['bytes', 'sha256']}, key
    if key in external:
        assert external[key] == value
    external[key] = value
for rel, value in json.loads((BASE / 'FROZEN.json').read_bytes())['files'].items():
    pin(BASE / rel, value)
for rel, value in json.loads((BASE / 'source-lineage-pins.json').read_bytes())['files'].items():
    pin(ROOT / rel, value)
pin(BASE / 'FROZEN.json')
root_receipt = ROOT / '.build/m0-pow-exp-table-product-root-acceptance-20261025-001/RECEIPT.json'
receipt = json.loads(root_receipt.read_bytes())
assert receipt['validated_unique_pins'] == len(receipt['pins']) == 44
for value in receipt['pins']:
    pin(value['path'], value)
pin(root_receipt)
for name in ['README.md','checkpoint.json','verify.py','rebuild-recipes.json']:
    pin(ROOT / 'research/m0-math-checkpoint-20261025-2' / name)
pin(ROOT / '.build/m0-math-checkpoint-r6-replay-20261025-r3/verification.json')
(W / 'source-lineage-pins.json').write_text(json.dumps(dict(status='VERIFIED_EXECUTION_AND_ACCEPTED_PARENT_LINEAGE', files=external), indent=2) + '\n')
scope = dict(status='QUALIFIED_PRIVATE_EXACT_SQUARE128_COMPONENT_PENDING_INDEPENDENT_REVIEW',
             previous_goal_turn_classification='progress: committed checkpoint7bfad29cf with explicit unfinished kernel',
             this_turn_classification='progress: full replay, fresh MPFR controls, universal transform/cost proof and frozen component',
             HEAD=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
             canonical_runtime_changed=False, M4_changed=False, device_or_Flash_accessed=False,
             independent_review_pending=True, integration_and_release_GO=False, goal_complete=False)
assert not subprocess.check_output(['git','diff','--','code/native_eabi_m0*'],cwd=ROOT)
(W / 'WORK-SCOPE.json').write_text(json.dumps(scope, indent=2) + '\n')
result = dict(status='FROZEN_AUTHOR_EXACT_SQUARE128_POW_COMPONENT_PENDING_REVIEW',
              candidate_ELF_sha256=sha(W / 'candidate.elf'),
              source_parent=str(BASE.relative_to(ROOT)), source_parent_FROZEN_sha256=sha(BASE/'FROZEN.json'),
              accepted_parent_ROOT_receipt_sha256=sha(root_receipt),
              source_proof_sha256=sha(W / 'source-proof.json'), numeric_proof_sha256=sha(W / 'NUMERIC-PROOF.md'),
              original_pow153_remaining=[35,34], original_new_strict_fixes=1,
              same_old116468_pairs_losses=[10853,10850], old_new_strict_fixes=3,
              expanded_union_pairs=u['union_unique_pairs'], expanded_union_states=u['union_states'],
              expanded_union_reference_state_variants=u['union_reference_state_variants'],
              expanded_union_losses=[u['parent_raw_loss_pairs'],u['candidate_raw_loss_pairs']],
              expanded_union_strict_fixes=u['fixed_raw_pairs'],
              newly_measured_preexisting_loss_pairs=u['additional_measured_preexisting_loss_pairs'],
              candidate_wrong=0, new_raw_losses=0, parent_cost_increase_states=0,
              all_parent_raw_bits_identical=True, exact_old24byte_transform_and_radius_rules_preserved=True,
              all_actual_public_costs_match_static_kernel_delta=True,
              kernel_cost_classes={'low_zero_lower':[129,94], 'low_zero_upper':[116,89],
                                   'low_nonzero_lower':[195,154], 'low_nonzero_upper':[182,149]},
              kernel_frame_bytes=[48,40], kernel_plus_helper_peak_bytes=[68,60],
              new_function_bytes=232, old_function_and_retained_slot_bytes=310,
              allocated_code_size_delta_bytes=0, new_tables_RAM_or_libgcc_dependencies=False,
              full_old_corpus_candidate_observed_stack_bytes=2284,
              fresh_controls_parent_control_candidate_observed_stack_bytes=n['observed_stacks'],
              qualified_fresh_ARM_calls=u['qualified_fresh_ARM_calls'],
              fresh_full_old_candidate_ARM_calls=q['fresh_candidate_ARM_calls'],
              fresh_new_public_ARM_calls=n['fresh_ARM_calls'], fresh_bare_ARM_calls=36420,
              fresh_actual_directed_MPFR_inputs=n['actual_directed_MPFR_inputs'],
              sNaN_policy_shortcuts=n['sNaN_policy_shortcuts'], oracle_evaluations=n['oracle_evaluations'],
              pilot918_and_route70_excluded=True, inherited_parent_Qfplib_MPFR_not_fresh=True,
              wrong_Qfplib_reference_state_variants_retained=u['wrong_Qfplib_state_variants_retained'],
              correct_Qfplib_comparison=u['correct_Qfplib_comparison'],
              strict_quiet_NaN_reference_policy_and_no_nominal_domain_filter=True,
              thirteen_complete_source_object_ELF_rebuilds_byte_exact=True,
              generic_M0_M4_soft_hard_selected_assembly_bytes_relocations_equal=True,
              no_other_resident_code_layout_or_veneer_change=True,
              original507_author_separate_union=dict(no_slower=437,strictly_faster=431,equal=6,
                  remaining=70,remaining_by_operation=dict(pow=34,sin=22,cos=14),not_one_integrated_binary=True),
              original507_reviewed_union_kept422_per_root=True,
              independent_review_pending=True,
              general_pow_totality_other_math_speed_source_merge_R12_loader_guards_cycles_release_pending=True,
              canonical_runtime_Git_device_USB_Flash_or_release_changed=False,goal_complete=False)
(W / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
text = f'''# Exact M0+ square128 component: author qualification complete, review pending

Candidate ELF SHA256 `{result['candidate_ELF_sha256']}`. Parent table-product
FROZEN `{result['source_parent_FROZEN_sha256']}` is independently accepted;
its ROOT receipt is `{result['accepted_parent_ROOT_receipt_sha256']}`.
That acceptance is not a review of this new kernel.

The one changed function reproduces all24 old output bytes and error rules.
Four instruction classes:129→94,116→89,195→154,182→149. Kernel stack48→40;
with unchanged helper68→60. Function310→232B, old310B slot retained with padding.
No new table, global RAM, libgcc or ROM-math dependency. Other resident code,
addresses and veneers remain unchanged. GenericM0/M4soft/M4hard selected
assembly controls are equal; no production M4 build or modification is claimed.

The complete old116468-pair corpus /232936states is freshly reexecuted:
all parent raw results identical, exact expected cost reduction, no increases,
losses10853→10850. Fresh5127-pair independent controls use parent/control/
candidate and all3Qfplib compositions, 61524 actual ARM calls,5051 directedMPFR
inputs plus76sNaN shortcuts. All existing public RNE enclosures are unchanged.
Qualification totals330880 fresh ARM calls including36420 bare unit calls;
pilot918 and earlier route70 excluded. Inherited oracle/reference calls are
not fresh. All16NZCV, noisy volatile registers, PCS/SP/PC and bounded writes
are verified in the unit campaign; public SIO READY/DIRTY is checked every call.

Expanded union:{u['union_unique_pairs']}pairs/{u['union_states']}states/
{u['union_reference_state_variants']}reference-state variants, same-corpus losses
{u['parent_raw_loss_pairs']}→{u['candidate_raw_loss_pairs']},15 fixes,0 new.
The expansion adds596 measured preexisting loss pairs; do not compare counts
across different corpora. All{u['wrong_Qfplib_state_variants_retained']}wrong Qfplib
variants remain, with strict quiet-NaN classification and no nominal filtering.
Original153 pow deficits35→34, one additional strict fix. Author separate507
union437=431strict+6equal,70remain(pow34/sin22/cos14); reviewed507 stays422.

Thirteen full source objects/ELFs rebuilt byte exact at original paths. Unlike
the larger parent table packet, this one-slot replacement does not change
linker veneer placement. The public old-corpus observed stack peak remains2284;
fresh controls have the same parent/control/candidate2148 peak.

The earlier committed checkpoint correctly recorded this kernel as unfinished
at that time. This later packet supersedes its qualification status only.
Independent review, remaining speed paths, general-pow totality, source merge
with the separately accepted near-one exp sibling, actual merged R12/loader/
layout guards, physical cycles and release remain open. The destructive old
168B table overlay remains forbidden. No canonical source, Git, USB, device,
Flash, hardware lease or release was changed. Overall goal incomplete.
'''
(W / 'HANDOFF.md').write_text(text)
(W / 'progress.json').write_text(json.dumps(dict(status='FROZEN_QUALIFIED_AUTHOR_COMPONENT_PENDING_REVIEW',completed_states=232936,new_control_pairs=5127,goal_complete=False),indent=2)+'\n')
files = {str(p.relative_to(W)):dict(bytes=p.stat().st_size,sha256=sha(p))
         for p in sorted(W.rglob('*')) if p.is_file() and '__pycache__' not in p.parts}
frozen = dict(status='FROZEN_QUALIFIED_PRIVATE_EXACT_SQUARE128_COMPONENT',
              utc=datetime.now(timezone.utc).isoformat(),files=files,
              result_sha256=sha(W/'result.json'),HANDOFF_sha256=sha(W/'HANDOFF.md'),
              HEAD_at_seal=scope['HEAD'],canonical_math_diff_empty=True,goal_complete=False)
(W / 'FROZEN.json').write_text(json.dumps(frozen,indent=2)+'\n')
print(json.dumps(dict(status=frozen['status'],local_pins=len(files),external_pins=len(external),
                     FROZEN_sha256=sha(W/'FROZEN.json'),result_sha256=sha(W/'result.json'),
                     HANDOFF_sha256=sha(W/'HANDOFF.md')),indent=2))
