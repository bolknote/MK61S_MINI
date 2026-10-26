"""Seal the known-zero component with the expanded campaign kept separate."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,subprocess
W=Path(__file__).resolve().parent;ROOT=W.parents[1];P=ROOT/'.build/m0-pow-reciprocal-certificate-20261025';U=ROOT/'.build/m0-ddiv-remainder-certificate-r3-20261025'
assert not(W/'FROZEN.json').exists()and not(U/'FROZEN.json').exists()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();load=lambda p:json.loads(p.read_bytes())
q=load(W/'qualification.json');f=load(W/'new-qualification.json');d=load(W/'direct-proof.json');e=load(W/'expanded-seed-proof.json');u=load(U/'unit-proof.json');t=load(W/'summary.json');b=load(W/'build.json');rebuild=load(W/'rebuild-proof.json')
elf=sha(W/'candidate.elf')
assert all(r['candidate_ELF_sha256']==elf for r in [q,f,d,e])
assert t['total_qualified_fresh_ARM_calls']==1460246 and t['actual_directed_MPFR_input_evaluations']==157083 and t['sNaN_policy_shortcuts']==110
assert t['scalar_loss_states']==[1,0]and e['candidate_loss_states']==2 and e['new_loss_states']==0
assert t['original153']['candidate']==dict(slower=33,strict=120)and t['loss_pairs']==[11369,11369]
assert not q['new_raw_loss_pairs']and not f['new_raw_loss_pairs']and not q['parent_cost_increase_states']
assert len(rebuild['outputs'])==22
for path,digest in rebuild['outputs'].items():assert sha(Path(path))==digest
assert not subprocess.check_output(['git','diff','--','code/native_eabi_m0*'],cwd=ROOT)
(U/'HANDOFF.md').write_text('''# Bare remainder certificate using dead R3

The arithmetic and sign test are identical to unitr2; only scratch R6 is
renamed R3.100800 actual uint32 test cases/201600 ARM calls, both signed
discontinuities and all16 NZCV combinations. R1/R12/PCS/SP/PC and20B wrapper
stack writes checked; additionally every decisive branch preserves an
arbitrary live R6. Full fallback may clobber R6. The private component uses
this exact macro. No MPFR or device call. Old integer-model work is inherited,
not counted as fresh. Unit wrapper costs are not public division timings.
''')
files={str(p.relative_to(U)):dict(bytes=p.stat().st_size,sha256=sha(p))for p in sorted(U.rglob('*'))if p.is_file()and'__pycache__'not in p.parts}
(U/'FROZEN.json').write_text(json.dumps(dict(status='FROZEN_BARE_R3_REMAINDER_SIGN_UNIT',utc=datetime.now(timezone.utc).isoformat(),files=files,actual_ARM_calls=201600,actual_MPFR_calls=0,hardware_accessed=False,goal_complete=False),indent=2)+'\n')
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
corr=ROOT/'.build/m0-pow-reciprocal-certificate-report-corrigendum-20261025.json';put(corr)
R=ROOT/'.build/m0-pow-reciprocal-inline-independent-20261025'
review=load(R/'FINAL-REVIEW.json');assert review['status']=='TECH_GO_PRIVATE_EXACT_INLINE_SEED_AND_TINY_OVERFLOW_COMPONENT_ONLY'
for name,pin in load(R/'MANIFEST.json')['files'].items():put(R/name,pin)
put(R/'FINAL-REVIEW.json');put(R/'MANIFEST.json')
receipt=ROOT/'.build/m0-pow-reciprocal-inline-root-acceptance-20261025-001/RECEIPT.json';rr=load(receipt)
assert rr['private_component_GO']and not rr['integration_GO']
for pin in rr['pins']:put(pin['path'],pin)
put(receipt)
(W/'source-lineage-pins.json').write_text(json.dumps(dict(status='VERIFIED_PARENT_CORRIGENDUM_R3_UNIT_AND_ADDITIVE_INLINE_REVIEW_ROOT',files=external),indent=2)+'\n')
result=dict(status='FROZEN_AUTHOR_PRIVATE_KNOWN_ZERO_RECIPROCAL_PENDING_REVIEW',source_parent=str(P.relative_to(ROOT)),source_parent_FROZEN_sha256=sha(P/'FROZEN.json'),
 parent_certificate_independent_review_pending=True,parent_report_corrigendum_sha256=sha(corr),earlier_inline_review_sha256=sha(R/'FINAL-REVIEW.json'),earlier_inline_ROOT_sha256=sha(receipt),
 candidate_ELF_sha256=elf,source_proof_sha256=sha(W/'source-proof.json'),numeric_proof_sha256=sha(W/'NUMERIC-PROOF.md'),shared_R3_unit_FROZEN_sha256=sha(U/'FROZEN.json'),
 private_contract='exact positive numerator1, denominator any binary64; not generic division',
 second_product_live_outputs_equal_under_R0_R4_permutation=True,full_after_y_residual_R0_R7_R12_SP_NZCV_frame28_identical=True,
 before_certificate_full_state_equal_and_pack_live_state_equal=True,universal_source_equivalence_to_parent_precision=True,
 same_corpus_pairs=120980,states=241960,loss_pairs=[11369,11369],new_raw_losses=0,candidate_wrong=0,
 accelerated_public_states=754,public_instruction_reduction_range=[2,3],public_parent_cost_increases=0,
 same_scalar_pairs=20994,same_scalar_states=41988,same_scalar_loss_states=[1,0],same_scalar_candidate_comparison=d['correct_Qfplib_comparisons']['candidate'],same_scalar_wrong_Qfplib_retained=9600,
 expanded_seed_divisors=65536,expanded_inputs=131072,expanded_states=262144,expanded_patterns_per_D=2,expanded_loss_states=[14,2],expanded_candidate_comparison=e['correct_Qfplib_comparisons']['candidate'],expanded_wrong_Qfplib_retained=0,
 all65536_actual_software_seed_divisors_observed=True,all_expanded_correct_Qfplib_outputs_and_costs_retained=True,
 remaining_expanded_denominators=['3FF0CEE65125761B','3FF10E0E8502C07D'],remaining_expanded_SIO='DIRTY',remaining_expanded_instruction_lags=[3,1],
 new_scalar_Qfplib_loss_states=0,all_own_parent_cost_increase_states=0,no_nominal_reference_domain_filter=True,wrong_public_Qfplib_variants_retained=77106,
 total_qualified_fresh_ARM_calls=1460246,same_corpus_qualified_fresh_ARM_calls=673814,expanded_scan_fresh_ARM_calls=786432,
 fresh_full_candidate_ARM_calls=241960,fresh_parent_reciprocal_path_ARM_calls=778,fresh_public_MPFR_control_reference_ARM_calls=61524,fresh_scalar_ARM_calls=167952,fresh_bare_unit_ARM_calls=201600,
 actual_directed_MPFR_input_evaluations=157083,sNaN_policy_shortcuts=110,campaign_overlap_not_deduplicated_not_unique_input_count=True,parent_campaigns_not_fresh=True,
 private_code_bytes=[1108,1100],allocated_code_delta_bytes=-8,unchanged256B_table=True,no_new_tables_RAM_libgcc_or_external_calls=True,
 default_M0_M4_selected_controls_and6_disabled_objects_empty=True,twenty_two_original_path_source_object_ELF_rebuilds_exact=True,
 full_observed_stack_bytes=2284,fresh_public_controls_stack_bytes=f['observed_stacks'],same_scalar_stack_bytes=d['observed_stacks'],expanded_normal_scalar_stack_bytes=e['observed_stacks'],parent_subset_not_full_stack_comparator=True,
 original_pow153_remaining=[33,33],author_separate507_no_slower=438,author_separate507_strict=432,author_separate507_equal=6,reviewed_separate507_no_slower=422,
 independent_review_pending=True,general_pow_totality_other_math_unified_source_R12_loader_layout_14B_hazard_physical_cycles_release_pending=True,
 canonical_runtime_M4_Git_device_USB_Flash_or_release_changed=False,goal_complete=False)
(W/'result.json').write_text(json.dumps(result,indent=2)+'\n')
(W/'HANDOFF.md').write_text('''# Private known-zero reciprocal: author qualification complete

Parent certificate99110367 remains pending independent review. Earlier inline
review4d457dfb/ROOT7da9 and the certificate reporting correction5cd5994f are
pinned additively. No prior review or receipt is widened to this new source.
Contract remains exact positive numeratorone, denominator any binary64.
The actual sole root BL/return and all other resident sections are unchanged.

The second product permutes R0/R4 from equal zero inputs, preserving its live
outputs and flags. Dead R1 is used for xH*a0, and the exact signed residual
rejoins with every R0-R7/R12/SP/NZCV and28-byte frame identical. A zero
reconstruction and doubling are omitted. The certificate uses dead R3 in
place of R6, preserving zero R6 on decisive paths, so rounding can omit its
old zero load. The full path explicitly restores R6 before ADC. At pack all
live values/flags agree. NUMERIC-PROOF.md supplies the entire private-contract
equivalence; this is not a generic division API or an inherited unchanged
RNE-suffix claim. Exact source inversion restores both complete parent files.
Actual product projections, complete residual joins and every certificate
decision are checked. Unitr3 performs100800cases/201600ARM with all16flags
at both sign boundaries and arbitrary live R6 on decisive branches.

Same120980 public pairs/241960 states:11369->11369 losses,754 faster states
by2-3 instructions; no wrong result, new loss or own parent cost increase.
The one prior equality variant becomes faster, without a new pair-level
win. Same279522 reference variants including77106 wrong outputs/costs remain.
All778 reciprocal paths have fresh parent replays and all10254 fresh controls
match raw full-corpus records. The separate original153 stays120strict/33slow.
Author separate507 remains438=432strict+6equal; reviewed422 unchanged.

Same20994 scalar input/flag cases/41988 states:correct-Qfplib losses1->0,
32387faster/1equal. All9600 wrong reference variants retained. Expanded test:
every65536 seed divisor with two normal full-mantissa patterns,131072inputs,
262144states,786432freshARM/131072freshMPFR input evaluations. All65536 actual
software seed divisors were seen. Parent14slower states become2, candidate
262131faster/11equal/2slower; all Qfplib outputs in this expanded scan are
correct. The two preexisting remaining DIRTY cases are D3FF0CEE65125761B
(149vs146) and D3FF10E0E8502C07D(147vs146). There is no universal speed claim.
No own parent cost increases or new Qfplib losses occur in either scalar set.

Total1460246 fresh qualified ARM calls:673814 from the same campaigns
(241960candidate+778parent+61524freshpublic+167952scalar+201600unit), plus
786432 expanded scalar calls.157083 directed MPFR input evaluations and
110sNaN policy shortcuts are additive across campaigns, not deduplicated
unique inputs. No inherited campaign is counted as fresh.22 full own source,
object and ELF rebuilds are byte-exact. Numerical campaigns completed once.

Private code1108->1100B(-8), same256Btable/inline seed, no new RAM/libgcc or
external calls. Selected defaultM0/M4 controls equal; six added disabled
objects empty, READY9ALU and all7 DIRTY SIO words/no writes preserved.
Whole observed stack2284B, freshpublic2148B each, same scalar176B each;
expanded normal-only scalar28B each is a different corpus, not a reduction.
No universal stack bound or physical-cycle claim. The older certificate's
32 public parent increases, including two already slow states, are not
retroactively removed by this narrower step; its correction stays binding.

Next source study: both new remaining seed estimates overestimate by exactly3.
With the proved[-1,3] bound, keep one old downward step, then two residual
additions and a borrow-controlled subtraction using private raw R0=0 can
replace the remaining loop steps. Prove exact quotient and dead R7 residual,
check all65536 D/allflags before broad reruns. No input-ID special cases.
CPP near-one and table-product siblings differ only by near-one's two exp
additions; unified source merge/relink and actual R12/loader/layout/14B-overlay
guards are the next integration work. Generalpowtotality/othermath/physical
cycles/release remain open. No canonical/M4/Git/device/USB/Flash changes.
''')
(W/'WORK-SCOPE.json').write_text(json.dumps(dict(status='AUTHOR_QUALIFICATION_COMPLETE_PENDING_REVIEW',previous_goal_turn_classification='progress: exact certificate qualified; same scalar13->1/public11371->11369 with parent increases retained',this_turn_classification='progress: known-zero preservation qualified, same scalar1->0; expanded65536seed scan exposes2preexisting remaining gaps while fixing12states;754fasterpublicstates,0parentincreases',goal_complete=False,canonical_runtime_M4_Git_device_USB_Flash_changed=False),indent=2)+'\n')
for name,progress in [('progress.json',dict(completed_states=241960,total_states=241960)),('seed-progress.json',dict(completed_seed_divisors=65536,total_seed_divisors=65536,completed_inputs=131072,actual_ARM_calls=786432))]:
 (W/name).write_text(json.dumps(dict(status='AUTHOR_QUALIFICATION_COMPLETE_PENDING_REVIEW',**progress),indent=2)+'\n')
files={str(p.relative_to(W)):dict(bytes=p.stat().st_size,sha256=sha(p))for p in sorted(W.rglob('*'))if p.is_file()and'__pycache__'not in p.parts}
(W/'FROZEN.json').write_text(json.dumps(dict(status='FROZEN_AUTHOR_PRIVATE_CALLER_PENDING_REVIEW',utc=datetime.now(timezone.utc).isoformat(),files=files,result_sha256=sha(W/'result.json'),HANDOFF_sha256=sha(W/'HANDOFF.md'),goal_complete=False),indent=2)+'\n')
print(json.dumps(dict(status='AUTHOR_COMPONENT_SEALED',local_files=len(files),external_pins=len(external),FROZEN_sha256=sha(W/'FROZEN.json'),result_sha256=sha(W/'result.json'),HANDOFF_sha256=sha(W/'HANDOFF.md'),candidate_ELF_sha256=elf,R3unit_FROZEN_sha256=sha(U/'FROZEN.json')),indent=2))
