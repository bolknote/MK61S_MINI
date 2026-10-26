"""Seal bounded-correction evidence with failures and cycle limits explicit."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,subprocess
W=Path(__file__).resolve().parent;ROOT=W.parents[1];P=ROOT/'.build/m0-pow-reciprocal-zero-20261025';U=ROOT/'.build/m0-ddiv-seed-bound3-20261025'
assert not(W/'FROZEN.json').exists()and not(U/'FROZEN.json').exists()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();load=lambda p:json.loads(p.read_bytes())
q=load(W/'qualification.json');f=load(W/'new-qualification.json');d=load(W/'direct-proof.json');e=load(W/'expanded-seed-proof.json');u=load(U/'unit-proof.json');t=load(W/'summary.json');b=load(W/'build.json');rebuild=load(W/'rebuild-proof.json');failed=load(W/'HOST-PREFLIGHT-001.json')
elf=sha(W/'candidate.elf');assert all(r['candidate_ELF_sha256']==elf for r in [q,f,d,e])
assert t['total_qualified_fresh_ARM_calls']==3355798 and t['actual_directed_MPFR_input_evaluations']==157083 and t['sNaN_policy_shortcuts']==110
assert t['scalar_loss_states']==[0,0]and e['candidate_loss_states']==0 and e['parent_loss_states']==2
assert q['candidate_raw_loss_pairs']==11369 and not q['new_raw_loss_pairs']and not q['parent_cost_increase_states']and not f['new_raw_loss_pairs']
assert len(rebuild['outputs'])==22
for path,digest in rebuild['outputs'].items():assert sha(Path(path))==digest
assert not subprocess.check_output(['git','diff','--','code/native_eabi_m0*'],cwd=ROOT)
(U/'LICENSE.TXT').write_bytes((P/'LICENSE.TXT').read_bytes())
(U/'HANDOFF.md').write_text('''# Exact seed correction bounded by three downward steps

The fixed table estimate error is[-1,3] for every65536 D. Negative residual
requires one,two or three decrements. One explicit decrement exits at BPL
for error1; a second ADD supplies unsigned carry for SBC with private R0=0.
The exact floor quotient is unchanged. Only error3 leaves R7 residual minusD,
which is dead before the production second product. This is not a generic
seed ABI: raw R0 must be zero. Shared production macro tested for all65536D
under every16NZCV:1048576tests/2097152ARM. All R0/R1/R2/R3/R5/R12/SP and PCS,
SP/PC/only20B wrapper writes checked.18592unit cases save3 instructions,
1029984 unchanged;0increases. The branch direction for error1 changes, so
these are instruction counts, not measured cycles. No MPFR/device call.
''')
files={str(p.relative_to(U)):dict(bytes=p.stat().st_size,sha256=sha(p))for p in sorted(U.rglob('*'))if p.is_file()and'__pycache__'not in p.parts}
(U/'FROZEN.json').write_text(json.dumps(dict(status='FROZEN_BARE_BOUND3_PRIVATE_ZERO_SEED_UNIT',utc=datetime.now(timezone.utc).isoformat(),files=files,actual_ARM_calls=2097152,actual_MPFR_calls=0,hardware_accessed=False,goal_complete=False),indent=2)+'\n')
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
R=ROOT/'.build/m0-pow-reciprocal-certificate-independent-20261025';review=load(R/'FINAL-REVIEW.json')
assert review['status']=='TECH_GO_PRIVATE_EXACT_REMAINDER_SIGN_CERTIFICATE_COMPONENT_ONLY_WITH_RETAINED_TRADEOFF'
for name,pin in load(R/'MANIFEST.json')['files'].items():put(R/name,pin)
put(R/'FINAL-REVIEW.json');put(R/'MANIFEST.json')
receipt=ROOT/'.build/m0-pow-reciprocal-certificate-root-acceptance-20261025-001/RECEIPT.json';rr=load(receipt)
assert not rr['integration_GO']and not rr['performance_adoption_GO']
for pin in rr['pins']:put(pin['path'],pin)
put(receipt)
(W/'source-lineage-pins.json').write_text(json.dumps(dict(status='VERIFIED_PARENT_SHARED_UNIT_AND_ADDITIVE_CERTIFICATE_REVIEW_ROOT',files=external),indent=2)+'\n')
result=dict(status='FROZEN_AUTHOR_PRIVATE_BOUND3_SEED_PENDING_REVIEW',source_parent=str(P.relative_to(ROOT)),source_parent_FROZEN_sha256=sha(P/'FROZEN.json'),
 parent_zero_independent_review_pending=True,earlier_certificate_review_sha256=sha(R/'FINAL-REVIEW.json'),earlier_certificate_ROOT_sha256=sha(receipt),earlier_certificate_performance_adoption_GO=False,
 candidate_ELF_sha256=elf,source_proof_sha256=sha(W/'source-proof.json'),numeric_proof_sha256=sha(W/'NUMERIC-PROOF.md'),shared_unit_FROZEN_sha256=sha(U/'FROZEN.json'),
 private_contract='exact positive numerator1, denominator any binary64; inline seed requires rawR0=0; not generic division',exact_floor_seed_quotient_unchanged=True,
 changed_R7_for_error3_dead_before_second_product=True,all_full_after_second_product_and_later_live_joins_identical=True,
 bare_unit_tests=1048576,bare_unit_ARM_calls=2097152,all65536_D_each_all16_NZCV_checked=True,
 same_scalar_pairs=20994,same_scalar_states=41988,same_scalar_loss_states=[0,0],same_scalar_candidate_comparison=d['correct_Qfplib_comparisons']['candidate'],same_scalar_wrong_Qfplib_retained=9600,
 expanded_seed_divisors=65536,expanded_inputs=131072,expanded_states=262144,expanded_patterns_per_D=2,expanded_loss_states=[2,0],expanded_candidate_comparison=e['correct_Qfplib_comparisons']['candidate'],expanded_wrong_Qfplib_retained=0,
 remaining_sampled_scalar_losses=0,new_scalar_Qfplib_loss_states=0,all_own_parent_instruction_cost_increases=0,
 same_pow_pairs=120980,pow_states=241960,pow_loss_pairs=[11369,11369],pow_faster_states=10,pow_instruction_saving=3,pow_wrong=0,new_pow_losses=0,
 all_reference_outputs_costs_and_inherited_tradeoffs_retained=True,no_nominal_reference_domain_filter=True,wrong_public_Qfplib_variants_retained=77106,
 total_qualified_fresh_ARM_calls=3355798,same_corpus_and_unit_qualified_fresh_ARM_calls=2569366,expanded_scan_fresh_ARM_calls=786432,
 fresh_full_candidate_ARM_calls=241960,fresh_parent_reciprocal_path_ARM_calls=778,fresh_public_MPFR_control_reference_ARM_calls=61524,fresh_scalar_ARM_calls=167952,fresh_bare_unit_ARM_calls=2097152,
 actual_directed_MPFR_input_evaluations=157083,sNaN_policy_shortcuts=110,campaign_overlap_not_deduplicated_not_unique_input_count=True,parent_campaigns_not_fresh=True,
 failed_host_trace_completed_ARM_calls_excluded=failed['completed_ARM_calls'],failed_host_trace_directed_MPFR_inputs_excluded=failed['directed_MPFR_input_evaluations'],failed_host_trace_sNaN_shortcuts_excluded=failed['sNaN_policy_shortcuts'],failed_partial_ARM_calls=0,
 private_code_bytes=[1100,1108],allocated_code_delta_bytes=8,same256B_table=True,no_new_tables_RAM_libgcc_or_external_calls=True,
 default_M0_M4_selected_controls_and6_disabled_objects_empty=True,twenty_two_original_path_source_object_ELF_rebuilds_exact=True,
 full_observed_stack_bytes=2284,fresh_public_controls_stack_bytes=f['observed_stacks'],same_scalar_stack_bytes=d['observed_stacks'],expanded_normal_scalar_stack_bytes=e['observed_stacks'],parent_subset_not_full_stack_comparator=True,
 instruction_parity_on_current_scalar_sets_not_universal_cycles_or_full_library_GO=True,error1_branch_direction_cycle_effect_requires_measurement=True,
 original_pow153_remaining=[33,33],author_separate507_no_slower=438,author_separate507_strict=432,author_separate507_equal=6,reviewed_separate507_no_slower=422,
 independent_review_pending=True,general_pow_totality_other_math_unified_source_R12_loader_layout_14B_hazard_physical_cycles_release_pending=True,
 canonical_runtime_M4_Git_device_USB_Flash_or_release_changed=False,goal_complete=False)
(W/'result.json').write_text(json.dumps(result,indent=2)+'\n')
(W/'HANDOFF.md').write_text('''# Private bounded seed correction: author qualification complete

Parent zero98efecf0 remains pending independent review. Earlier certificate
review6cfdc886/ROOTaa392 is correctness-only, with performance adoption false;
its32public/1132scalar increases and additive correction remain binding.
No acceptance is inherited for this new source. Private numerator+1 and sole
root caller remain unchanged. This is not generic division or a seed C ABI.

The full65536 seed estimate errors are[-1,3]. For a negative residual the
new first decrement exits at BPL exactly for error1. The next ADD carries at
error2 and does not at error3; immediate SBC with raw R0=0 subtracts0/1.
Exact q=floor((2^32-1)/D) remains equal. Error3 alone leaves R7=oldresidue-D;
there is no read of that dead register before its second-product overwrite.
ADD1/LSR before NR restores identical flags as well as the quotient. Every
other inline live register/SP is preserved. All1048576 D/flag cases execute
both actual macro wrappers,2097152ARM, including live context/PCS/SP/PC,
only20B wrapper writes and exact specified R7 differences. Production and
unit share the exact source; table256B is unchanged. Whole source proof and
actual full joins after the second product are retained. DefaultM0/M4
controls and six added disabled objects remain equal/empty; READY9ALU and
all7 DIRTY SIO words/no writes are unchanged. No new RAM/libgcc/calls.

Same scalar20994 input/flag cases/41988states remains32387fast/1equal,
0correct-Qfp losses,9600wrongrefs retained. Expanded all65536D/two full normal
mantissa patterns:131072inputs/262144states,2old losses->0,262132faster and
12equal, all Qfp outputs correct. Every actual software D is observed.
This is instruction parity on these sets, not every binary64 mantissa or
measured device cycles. Error1 reverses branch direction and needs physical
timing validation. No input-ID special case or reference-domain filter.
No own parent instruction increase or new Qfp loss in either scalar set.

Same120980pow pairs/241960states:11369losses unchanged,10states save3
instructions,0wrong/newloss/parentincrease. Every778 reciprocal path has a
fresh parent replay, all10254 fresh public control rows agree. All279522
reference variants, including77106 wrong Qfp outputs/costs, are retained.
Original153 stays120strict/33slow, author separate507438=432strict+6equal,
reviewed422 unchanged. There is still no single integrated executable.

3355798 fresh qualifiedARM:2097152unit+241960fullcandidate+778parent+
61524freshpublic+167952samescalar+786432expandedscalar.157083directedMPFR
input evaluations plus110sNaN shortcuts are additive, overlapping campaigns,
not unique-input counts. One host trace preflight incorrectly applied the
old/new dead-R7 rule to byte-identical parent/control.14184completed ARM,
1106MPFR inputs+76sNaN are preserved/excluded,0partial aborts. Numeric values
were correct. Only that terminal public-control run was repeated; ongoing
full/expanded runs kept their handles. Their default-true trace semantics
are unchanged by adding the explicit parent/control mode. Parent campaigns
are inherited, not fresh.22 whole own rebuild outputs are byte-exact.

Code1100->1108B(+8), no new table/RAM. Whole observed stack2284B, freshpublic
2148B each, same scalar176B each; expanded normal28B each is a different
corpus, not a reduction or universal bound. Numerical equivalence does not
satisfy general pow totality. Existing certificate tradeoffs do not vanish.

Next phase is one private source snapshot and actual relink with near-one
exp/table-product/square/boundary/reciprocal sources; fresh actual linked
R12/loader/layout/Flash/RAM/stack/scratch guards and the old168B-overlay14B
hazard must be checked. Other needed math, physical cycles and release
remain open. No canonical/M4/Git/device/USB/Flash mutation or adoption GO.
''')
(W/'WORK-SCOPE.json').write_text(json.dumps(dict(status='AUTHOR_QUALIFICATION_COMPLETE_PENDING_REVIEW',previous_goal_turn_classification='progress: known-zero transform and stronger all65536D/two-mantissa scan qualified,2remainingpreexistingstates',this_turn_classification='progress: bounded exactseed qualified allD/allflags; both scalar sets0observedQfplosses,10fasterpowstates; failedhosttrace excluded',goal_complete=False,canonical_runtime_M4_Git_device_USB_Flash_changed=False),indent=2)+'\n')
for name,progress in [('progress.json',dict(completed_states=241960,total_states=241960)),('seed-progress.json',dict(completed_seed_divisors=65536,total_seed_divisors=65536,completed_inputs=131072,actual_ARM_calls=786432))]:
 (W/name).write_text(json.dumps(dict(status='AUTHOR_QUALIFICATION_COMPLETE_PENDING_REVIEW',**progress),indent=2)+'\n')
files={str(p.relative_to(W)):dict(bytes=p.stat().st_size,sha256=sha(p))for p in sorted(W.rglob('*'))if p.is_file()and'__pycache__'not in p.parts}
(W/'FROZEN.json').write_text(json.dumps(dict(status='FROZEN_AUTHOR_PRIVATE_CALLER_PENDING_REVIEW',utc=datetime.now(timezone.utc).isoformat(),files=files,result_sha256=sha(W/'result.json'),HANDOFF_sha256=sha(W/'HANDOFF.md'),goal_complete=False),indent=2)+'\n')
print(json.dumps(dict(status='AUTHOR_COMPONENT_SEALED',local_files=len(files),external_pins=len(external),FROZEN_sha256=sha(W/'FROZEN.json'),result_sha256=sha(W/'result.json'),HANDOFF_sha256=sha(W/'HANDOFF.md'),candidate_ELF_sha256=elf,unit_FROZEN_sha256=sha(U/'FROZEN.json')),indent=2))
