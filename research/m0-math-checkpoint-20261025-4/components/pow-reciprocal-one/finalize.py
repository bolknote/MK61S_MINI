"""Seal the private numerator-one caller; send stdout outside this directory."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,subprocess
W=Path(__file__).resolve().parent;ROOT=W.parents[1];P=ROOT/'.build/m0-pow-reciprocal-lut-20261025';V=ROOT/'.build/m0-pow-reciprocal-one-v1-20261025';R=ROOT/'.build/m0-pow-reciprocal-lut-independent-20261025'
assert not(W/'FROZEN.json').exists()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();load=lambda p:json.loads(p.read_bytes())
q=load(W/'qualification.json');f=load(W/'new-qualification.json');d=load(W/'direct-proof.json');t=load(W/'summary.json');b=load(W/'build.json');proof=load(W/'source-proof.json');rebuild=load(W/'rebuild-proof.json')
elf=sha(W/'candidate.elf')
for obj in[q,f,d,proof,b['images']['candidate']]:assert obj.get('candidate_ELF_sha256',obj.get('ELF_sha256'))==elf
assert t['strict_fixed_pairs']==5 and t['total_qualified_fresh_ARM_calls']==406406 and t['public_instruction_reduction_range']==[11,34]
assert len(rebuild['outputs'])==22
for p,h in rebuild['outputs'].items():assert sha(Path(p))==h
assert not subprocess.check_output(['git','diff','--','code/native_eabi_m0*'],cwd=ROOT)
external={}
def put(path,pin=None):
 p=Path(path);p=p if p.is_absolute()else ROOT/p
 data=p.read_bytes();value=dict(bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
 if pin:assert value=={k:pin[k]for k in value},p
 key=str(p.relative_to(ROOT))
 if key in external:assert external[key]==value
 external[key]=value
for p,pin in load(P/'source-lineage-pins.json')['files'].items():put(p,pin)
for base in[P,V]:
 for p,pin in load(base/'FROZEN.json')['files'].items():put(base/p,pin)
 put(base/'FROZEN.json')
review=load(R/'FINAL-REVIEW.json');assert review['status']=='TECH_GO_PRIVATE_EXACT_LUT_ROOT_RECIPROCAL_COMPONENT_ONLY'and sha(P/'FROZEN.json')in json.dumps(review)
for p,pin in load(R/'MANIFEST.json')['files'].items():put(R/p,pin)
put(R/'FINAL-REVIEW.json');put(R/'MANIFEST.json')
roots={}
for name in['soft','lut']:
 receipt=ROOT/('.build/m0-pow-reciprocal-'+name+'-root-acceptance-20261025-001/RECEIPT.json')
 if receipt.exists():
  rr=load(receipt);assert rr['status'].startswith('ACCEPTED_PRIVATE_')
  for pin in rr['pins']:put(pin['path'],pin)
  put(receipt);roots[name]=dict(path=str(receipt.relative_to(ROOT)),bytes=receipt.stat().st_size,sha256=sha(receipt))
(W/'source-lineage-pins.json').write_text(json.dumps(dict(status='VERIFIED_PARENT_REVIEW_SUPERSEDED_TRIAL_AND_SOURCE_LINEAGE',files=external),indent=2)+'\n')
result=dict(status='FROZEN_AUTHOR_PRIVATE_NUMERATOR_ONE_RECIPROCAL_PENDING_REVIEW',source_parent=str(P.relative_to(ROOT)),source_parent_FROZEN_sha256=sha(P/'FROZEN.json'),
 parent_independent_review=dict(path=str((R/'FINAL-REVIEW.json').relative_to(ROOT)),sha256=sha(R/'FINAL-REVIEW.json'),status=review['status']),ROOT_receipts_present_at_seal=roots,
 candidate_ELF_sha256=elf,source_proof_sha256=sha(W/'source-proof.json'),numeric_proof_sha256=sha(W/'NUMERIC-PROOF.md'),
 private_precondition='R0=0,R1=0x3ff00000; denominator R2:R3 any binary64',actual_root_source_and_every_dynamic_entry_prove_precondition=True,
 not_a_general_division_or_public_ABI=True,other_resident_ddiv_callers_unchanged=True,
 same_corpus_pairs=120980,states=241960,reference_state_variants=279522,loss_pairs=[11377,11372],new_strict_fixes=5,new_raw_losses=0,candidate_wrong=0,
 accelerated_states=778,accelerated_states_by_SIO=t['accelerated_states_by_SIO'],public_instruction_reduction_range=[11,34],parent_cost_increase_states=0,
 all778_changed_paths_fresh_parent_replayed=True,all_parent_return_bits_and_internal_sequences_identical=True,
 all_actual_deltas_match_guard_plus15_product_plus8_software_formula=True,all2048_exponent_guards_equivalent_and_R6_identical=True,
 common_after_second_product_RNE_suffix_bytes=186,common4_suffixes_byte_identical=True,
 all_direct_after_second_product_R0_R7_R12_SP_NZCV_saved28B_identical=True,READY_nine_ALU_SIO_latency_block_preserved=True,
 unchanged312B_exact_seed_and_table=True,no_new_table_values_RAM_or_libgcc=True,private_code_bytes=[1168,1060],allocated_code_delta_bytes=-108,
 default_M0_M4_selected_controls_and6_disabled_objects_empty=True,twenty_two_complete_source_rebuilds_byte_exact=True,
 total_qualified_fresh_ARM_calls=406406,fresh_full_candidate_calls=241960,fresh_changed_parent_calls=778,fresh_MPFR_public_controls_reference_calls=61524,fresh_scalar_calls=102144,
 actual_directed_MPFR_inputs=17785,sNaN_policy_shortcuts=110,all10254_fresh_controls_match_full_records=True,
 v1_superseded102144_ARM12734_MPFR34sNaN_excluded=True,failed_trace308_completed_ARM2partial23_oracles_excluded=True,tally_import_failure0_ARM_MPFR_excluded=True,parent_qualification_and_seed_units_not_fresh=True,
 all_public_and_scalar_correct_wrong_Qfplib_outputs_costs_retained=True,wrong_public_Qfplib_variants=77106,wrong_direct_Qfplib_variants=354,
 public_correct_Qfplib_comparison=q['correct_Qfplib_comparison'],direct_correct_Qfplib_comparisons=d['correct_Qfplib_comparisons'],direct_remaining_loss_states=216,direct_remaining_unique_denominators=18,
 direct_remaining_exponents={'0':198,'908':2,'1915':2,'162':2,'1023':12},no_nominal_reference_domain_filter=True,
 full_observed_stack_bytes=2284,fresh_controls_observed_stack_bytes=f['observed_stacks'],direct_observed_stack_bytes=d['observed_stacks'],changed_parent_subset_not_comparable=True,
 original_pow153_remaining=[34,34],author_separate507_no_slower=437,reviewed_separate507_no_slower=422,
 independent_review_pending=True,remaining_needed_math_general_totality_source_merge_actual_R12_loader_layout_14B_overlay_cycles_release_pending=True,
 canonical_runtime_M4_Git_device_USB_Flash_or_release_changed=False,goal_complete=False)
(W/'result.json').write_text(json.dumps(result,indent=2)+'\n')
(W/'HANDOFF.md').write_text('''# Private numerator-one reciprocal: author qualification complete

The new hidden mk61_m0_reciprocal1 contract is exact positive numerator1,
R0=0/R1=0x3ff00000; denominator R2:R3 is any binary64. This is not a general
ddiv ABI. The sole root call has verified zero/one loads immediately before
BL and every actual entry is checked. Other resident ddiv callers remain
unchanged. Parent LUT has independent TECH_GO; this new caller requires its
own independent review and inherits no integration/hardware/release GO.

Same120980 pairs/241960states:11377->11372 loss pairs,5 new strict fixes,
0wrong/0newloss/0parentcostincrease.778 states (389 READY,389 DIRTY) save
11-34 instructions. All778 changed paths also have fresh parent calls;
all10254 fresh controls match the full records. All279522 reference-state
variants, including77106 wrong Qfplib outputs/costs, are retained without a
nominal-domain filter. Original153 stays119strict/34slower; author separate
507 stays437, reviewed422. This is not one integrated math executable.

For numerator1, both guarded exponent tests accept exactly1<=E<=2044 and
give R6=2044-E. The guard saves11 accepted /12 E2045,2046 /5 E0,2047
instructions. The exact first product is double(2^31*u1)=(low0,highu1),
saving15 instructions. Eight dead software instructions are removed; READY
retains its nine independent ALU operations before SIO quotient read. Every
actual scalar/public cost matches that formula. After the second product,
R0..R7,R12,SP,NZCV and28 saved bytes match the parent, and all four186B
rounding suffixes are byte-identical.312B exact seed/table unchanged.
Private code1168->1060B (-108B), no new table values, RAM or libgcc. M4/
default M0 controls and six new disabled objects are empty.22 rebuilds exact.

406406 fresh qualified ARM calls:241960 full candidates,778 changed parents,
61524 fresh public MPFR/controls/references and102144 scalar calls.17785
directed MPFR inputs plus110 sNaN policy shortcuts. Superseded product-only
v1 (102144 ARM /12734 MPFR /34sNaN) is separately frozen and excluded. A
missing R6 import stopped the first full/fresh trace preflight after308
completed calls plus two partial aborts and23 oracle evaluations; these are
preserved and excluded. A system-Python recount import failed before any
ARM/MPFR call and was fixed by loading only the pure cost formula. No kernel
fault caused those driver failures. Parent qualification and bare seed
campaigns are inherited, not fresh. Historical producers must not run inside
frozen packets or their superseded snapshots.

Direct1/x denominator coverage includes every exponent/sign, random bits,
4096 normal seed samples and all16 NZCV on IEEE edges. Against numerically
correct Qfplib, parent12560 slow states becomes216 (18 unique denominators),
with24966 faster and no equal. All354 wrong direct Qfplib states remain.
The remaining216 states are explicit in direct-remaining.json:198 with
subnormal denominators and18 normal states lagging2-5 instructions. There
is no universal reciprocal speed claim. Candidate/parent/control direct
stack peaks176B, fresh public controls2148B, full candidate2284B unchanged;
changed-parent subset is not a complete comparison or universal stack bound.

Remaining work includes these scalar deficits, other needed operations,
general pow totality, production source merge/relink and actual R12/loader/
layout guards, the14B old-overlay hazard, physical cycles and release.
No canonical/M4/Git/device/USB/Flash change. Overall goal stays active.
''')
(W/'WORK-SCOPE.json').write_text(json.dumps(dict(status='AUTHOR_QUALIFICATION_COMPLETE_PENDING_REVIEW',previous_goal_turn_classification='progress: exact LUT seed qualified,9 strict fixes,377 faster states',this_turn_classification='progress: prove private1/x source contract and exact first product, equivalent exponent guards/dead unpack, qualify778 faster states and5 strict fixes with108B less code',canonical_runtime_M4_Git_device_USB_Flash_changed=False,goal_complete=False),indent=2)+'\n')
(W/'progress.json').write_text(json.dumps(dict(status='AUTHOR_QUALIFICATION_COMPLETE_PENDING_REVIEW',completed_states=241960,total_states=241960),indent=2)+'\n')
files={str(p.relative_to(W)):dict(bytes=p.stat().st_size,sha256=sha(p))for p in sorted(W.rglob('*'))if p.is_file()and'__pycache__'not in p.parts}
(W/'FROZEN.json').write_text(json.dumps(dict(status='FROZEN_AUTHOR_PRIVATE_CALLER_PENDING_INDEPENDENT_REVIEW',utc=datetime.now(timezone.utc).isoformat(),files=files,result_sha256=sha(W/'result.json'),HANDOFF_sha256=sha(W/'HANDOFF.md'),goal_complete=False),indent=2)+'\n')
print(json.dumps(dict(status='AUTHOR_COMPONENT_SEALED',local_files=len(files),external_pins=len(external),FROZEN_sha256=sha(W/'FROZEN.json'),result_sha256=sha(W/'result.json'),HANDOFF_sha256=sha(W/'HANDOFF.md'),candidate_ELF_sha256=elf,ROOT_receipts=roots),indent=2))
