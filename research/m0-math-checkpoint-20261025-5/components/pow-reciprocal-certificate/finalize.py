"""Seal completed private evidence without touching historical packets."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,subprocess
W=Path(__file__).resolve().parent;ROOT=W.parents[1];P=ROOT/'.build/m0-pow-reciprocal-inline-20261025';U=ROOT/'.build/m0-ddiv-remainder-certificate-r2-20261025'
assert not(W/'FROZEN.json').exists()and not(U/'FROZEN.json').exists()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();load=lambda p:json.loads(p.read_bytes())
q=load(W/'qualification.json');f=load(W/'new-qualification.json');d=load(W/'direct-proof.json');u=load(U/'unit-proof.json');t=load(W/'summary.json');b=load(W/'build.json');proof=load(W/'source-proof.json');rebuild=load(W/'rebuild-proof.json')
elf=sha(W/'candidate.elf')
for report in [q,f,d]:assert report['candidate_ELF_sha256']==elf
assert t['total_qualified_fresh_ARM_calls']==673814 and t['actual_directed_MPFR_inputs']==26011 and t['sNaN_policy_shortcuts']==110
assert t['strict_fixes']==1 and t['equal_fixes']==1 and t['original153']['candidate']==dict(slower=33,strict=120)
assert not q['new_raw_loss_pairs']and not f['new_raw_loss_pairs']and t['new_scalar_loss_states']==0
assert len(rebuild['outputs'])==22
for path,digest in rebuild['outputs'].items():assert sha(Path(path))==digest
assert not subprocess.check_output(['git','diff','--','code/native_eabi_m0*'],cwd=ROOT)
(U/'LICENSE.TXT').write_bytes((P/'LICENSE.TXT').read_bytes())
(U/'HANDOFF.md').write_text('''# Bare exact remainder-sign macro: qualification complete

The exact model is the complete uint32 high product and low-word borrow.
100800 actual test cases,201600 control/candidate ARM calls. Both sign
discontinuities and all16 NZCV combinations are tested. Live R1/R12,
PCS/SP/PC and only20B wrapper stack writes are checked. Certified cases
save12/15 wrapper instructions; uncertain cases add8. This is not a public
division speed claim. The macro is shared byte-for-byte with the new private
reciprocal component. No MPFR or device call was made. The earlier338416
integer-model cases are inherited from the archived source parent, not new
calls in this packet. Its integer proof covers the entire uint32 domain.
''')
files={str(p.relative_to(U)):dict(bytes=p.stat().st_size,sha256=sha(p))for p in sorted(U.rglob('*'))if p.is_file()and'__pycache__'not in p.parts}
(U/'FROZEN.json').write_text(json.dumps(dict(status='FROZEN_BARE_EXACT_REMAINDER_SIGN_UNIT',utc=datetime.now(timezone.utc).isoformat(),files=files,actual_ARM_calls=201600,actual_MPFR_calls=0,hardware_accessed=False,goal_complete=False),indent=2)+'\n')
external={}
def put(path,pin=None):
 p=Path(path);p=p if p.is_absolute()else ROOT/p;data=p.read_bytes();value=dict(bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
 if pin:assert value=={k:pin[k]for k in value},p
 key=str(p.relative_to(ROOT))
 if key in external:assert external[key]==value
 external[key]=value
for path,pin in load(P/'source-lineage-pins.json')['files'].items():put(path,pin)
for folder in [P,U]:
 for path,pin in load(folder/'FROZEN.json')['files'].items():put(folder/path,pin)
 put(folder/'FROZEN.json')
for path in ['.build/m0-ddiv-remainder-certificate-20261025/study.json','.build/m0-ddiv-remainder-certificate-20261025/study.py',
             'research/m0-math-checkpoint-20261025-4/checkpoint.json']:
 put(path)
roots={}
for name in ['soft','lut','one']:
 receipt=ROOT/('.build/m0-pow-reciprocal-'+name+'-root-acceptance-20261025-001/RECEIPT.json')
 rr=load(receipt);assert rr['status'].startswith('ACCEPTED_PRIVATE_')
 for pin in rr['pins']:put(pin['path'],pin)
 put(receipt);roots[name]=dict(path=str(receipt.relative_to(ROOT)),bytes=receipt.stat().st_size,sha256=sha(receipt))
(W/'source-lineage-pins.json').write_text(json.dumps(dict(status='VERIFIED_PARENT_AND_SHARED_BARE_MACRO_SOURCE_LINEAGE',files=external),indent=2)+'\n')
result=dict(status='FROZEN_AUTHOR_PRIVATE_EXACT_REMAINDER_CERTIFICATE_PENDING_REVIEW',source_parent=str(P.relative_to(ROOT)),source_parent_FROZEN_sha256=sha(P/'FROZEN.json'),
 parent_inline_independent_review_pending=True,ROOT_receipts_present_at_seal=roots,candidate_ELF_sha256=elf,
 source_proof_sha256=sha(W/'source-proof.json'),numeric_proof_sha256=sha(W/'NUMERIC-PROOF.md'),shared_bare_unit_FROZEN_sha256=sha(U/'FROZEN.json'),
 private_contract='exact positive numerator1, denominator any binary64; not general division',other_resident_ddiv_callers_unchanged=True,
 omitted_high_product_plus_borrow_bound=131071,uncertain_intervals_near_zero_and_INT32_MIN_use_parent_full_product=True,all_actual_certificate_decisions_checked=True,
 bare_unit_tests=u['tests'],bare_unit_ARM_calls=u['actual_ARM_calls'],live_R1_R12_SP_PCS_and_flags_checked=True,
 before_certificate_actual_R0_R7_R12_SP_NZCV_frame28_identical=True,known_zero_yL_shift_removed=True,
 same_corpus_pairs=120980,states=241960,reference_state_variants=279522,loss_pairs=t['loss_pairs'],strict_fixes=1,equal_fixes=1,new_raw_losses=0,candidate_wrong=0,
 accelerated_public_states=354,public_instruction_reduction_range=[12,15],public_parent_cost_increase_states=32,public_parent_increase_histogram=q['parent_increase_histogram'],
 direct_expanded_pairs=d['pairs'],direct_states=d['states'],direct_loss_states=[13,1],new_direct_Qfplib_loss_states=0,direct_correct_Qfplib_comparisons=d['correct_Qfplib_comparisons'],
 direct_parent_cost_increase_states=1132,direct_parent_increase_histogram=t['scalar_parent_increase_histogram'],remaining_direct_denominator='3FF27D0DF6735E90',remaining_direct_state='DIRTY',remaining_direct_lag_instructions=3,
 all_correct_incorrect_Qfplib_outputs_costs_and_parent_increases_retained=True,no_nominal_reference_domain_filter=True,wrong_direct_Qfplib_variants=9600,wrong_public_Qfplib_variants=77106,
 public_correct_Qfplib_comparison=q['correct_Qfplib_comparison'],total_qualified_fresh_ARM_calls=673814,
 fresh_full_candidate_ARM_calls=241960,fresh_parent_reciprocal_path_ARM_calls=778,fresh_public_MPFR_control_reference_ARM_calls=61524,fresh_scalar_ARM_calls=167952,fresh_bare_unit_ARM_calls=201600,
 actual_directed_MPFR_inputs=26011,sNaN_policy_shortcuts=110,parent_campaigns_and_integer_model_not_fresh=True,
 host_build_selector_preflight0_ARM0_MPFR_excluded=True,host_tally_NaN_policy_preflight0_ARM0_MPFR_excluded=True,
 private_code_bytes=[1072,1108],allocated_code_delta_bytes=36,unchanged256B_table=True,no_new_tables_RAM_or_libgcc=True,
 default_M0_M4_selected_controls_and6_disabled_objects_empty=True,twenty_two_original_path_source_object_ELF_rebuilds_exact=True,
 full_observed_stack_bytes=2284,fresh_public_controls_stack_bytes=f['observed_stacks'],direct_stack_bytes=d['observed_stacks'],parent_subset_not_full_stack_comparator=True,
 original_pow153_remaining=[34,33],author_separate507_no_slower=438,author_separate507_strict=432,author_separate507_equal=6,reviewed_separate507_no_slower=422,
 independent_review_pending=True,other_needed_math_general_totality_source_merge_actual_R12_loader_layout_14B_overlay_physical_cycles_release_pending=True,
 canonical_runtime_M4_Git_device_USB_Flash_or_release_changed=False,goal_complete=False)
(W/'result.json').write_text(json.dumps(result,indent=2)+'\n')
(W/'HANDOFF.md').write_text('''# Private exact reciprocal remainder certificate: author qualification complete

Parent is inline0be351d5, itself pending separate review. Existing soft/LUT/one
reviews and ROOT receipts are pinned without extending their acceptance.
Contract is exact positive numerator1, denominator any binary64; not general
ddiv or a one-argument C ABI. The sole actual root caller remains unchanged.

The certificate omits a bounded part of one high product: its correction is
always between0 and131071. Its integer interval check excludes both signed
discontinuities. A decisive sign uses the cheap path; otherwise the original
complete product, borrow and sign check run. Zero retains the parent tie
behavior. NUMERIC-PROOF.md supplies the whole uint32 proof. The same exact
macro is used in production and100800 bare test cases /201600 ARM calls,
including all16 NZCV at both boundaries. R1/R12/PCS/SP/PC and only wrapper
stack writes are checked. Private numerator+1 additionally proves yL=0 and
removes one dead shift. All actual before-certificate and after-second-product
R0-R7/R12/SP/NZCV/frame28 joins match. Every certificate branch is audited.

Same120980 pairs /241960 public states:11371->11369 raw loss pairs, one strict
fix and one equality fix; no new loss or wrong result.354 states save12-15
instructions.32 states add7-8; all remain no slower than their correct Qfplib
references. All778 reciprocal paths have fresh parent replays, including
unchanged controls. The complete corpus retains279522 reference-state
variants, including77106 incorrect Qfplib variants and costs, without domain
filtering. All10254 fresh public controls match the full saved records.

Same expanded scalar corpus:20994 input/flag cases /41988 SIO states,
correct-Qfplib losses13->1,32382faster/5equal/1slower. The remaining state is
DIRTY denominator3FF27D0DF6735E90:149instructions vsQfplib146. All9600 wrong
reference variants are retained.1132 scalar states add7-8 parent instructions,
with zero new Qfplib losses. This is not universal reciprocal speed parity.

673814 fresh qualified ARM calls:241960full candidates+778parent paths+
61524fresh public controls/references+167952scalar+201600bare unit.
26011 directed MPFR inputs plus110 separately reported sNaN policy shortcuts.
Two host-only preflights are preserved/excluded: incorrect section selector
before compilation, and exact NaN payload comparison in the first recount.
Neither executed ARM/MPFR; all numerical campaigns completed once. Parent
campaigns and the old integer model are inherited, not fresh.22 own source,
object and ELF rebuild outputs are byte-exact.

Private code1072->1108B (+36B), no new tables/RAM/libgcc; the same256B table,
inline seed and READY9ALU gap remain. Six added disabled objects are empty;
selected defaultM0/M4 and all other resident sections are unchanged. Full
observed stack2284B, fresh public controls2148B each, scalar176B each, unchanged.
The parent path subset is not a full stack comparator. Original153pow now
120strict/33slower. Author separate507union438=432strict+6equal; reviewed422
unchanged. These are separate components, not one integrated executable.

Next work: preserve the known zero through the second product and reuse it
for rounding, seeking the last three scalar instructions; then source merge
and relink with near-one exp, actual integrated R12/loader/layout guards and
the14B old-overlay hazard. Other math, general pow totality, physical cycles
and release remain open. No canonical/M4/Git/device/USB/Flash mutation or
integration/hardware/main/release GO. Frozen producers must not be rerun.
''')
(W/'WORK-SCOPE.json').write_text(json.dumps(dict(status='AUTHOR_QUALIFICATION_COMPLETE_PENDING_REVIEW',previous_goal_turn_classification='progress: committed intermediate source/evidence archive with102 exact source rebuild outputs',this_turn_classification='progress: exact remainder certificate qualified; scalar13->1 and public11371->11369, known parent cost increases retained',goal_complete=False,canonical_runtime_M4_Git_device_USB_Flash_changed=False),indent=2)+'\n')
(W/'progress.json').write_text(json.dumps(dict(status='AUTHOR_QUALIFICATION_COMPLETE_PENDING_REVIEW',completed_states=241960,total_states=241960),indent=2)+'\n')
files={str(p.relative_to(W)):dict(bytes=p.stat().st_size,sha256=sha(p))for p in sorted(W.rglob('*'))if p.is_file()and'__pycache__'not in p.parts}
(W/'FROZEN.json').write_text(json.dumps(dict(status='FROZEN_AUTHOR_PRIVATE_CALLER_PENDING_REVIEW',utc=datetime.now(timezone.utc).isoformat(),files=files,result_sha256=sha(W/'result.json'),HANDOFF_sha256=sha(W/'HANDOFF.md'),goal_complete=False),indent=2)+'\n')
print(json.dumps(dict(status='AUTHOR_COMPONENT_SEALED',local_files=len(files),external_pins=len(external),FROZEN_sha256=sha(W/'FROZEN.json'),result_sha256=sha(W/'result.json'),HANDOFF_sha256=sha(W/'HANDOFF.md'),candidate_ELF_sha256=elf,bare_unit_FROZEN_sha256=sha(U/'FROZEN.json')),indent=2))
