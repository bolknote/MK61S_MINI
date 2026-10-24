"""Freeze component-only review and additive original507 reconciliation."""
from pathlib import Path
import hashlib,json,datetime,sys
sys.dont_write_bytecode=True
R=Path('/Users/bolk/Projects/MK61S_MINI');P=R/'.build/m0-exp-cached-product-20261024';O=Path(__file__).resolve().parent
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def ref(p):return dict(path=str(p),bytes=Path(p).stat().st_size,sha256=sha(p))
for anchor,base in [(P/'FROZEN.json',P),(P/'source-lineage-pins.json',R)]:
 for n,v in read(anchor)['files'].items():assert sha(base/n)==v['sha256'] and (base/n).stat().st_size==v['bytes']
assert sha(P/'FROZEN.json')=='765df6f87358d53a2d10d3b4c673fe8e4e85771c56e7d39b79bfe9df2ce5381c'
binding=read(O/'binding-rebuild.json');bound=read(O/'bounds-result.json');arm=read(O/'focused-arm.json')
assert all(d['status'].startswith('PASS_') for d in [binding,bound,arm])
baseline_path=R/'.build/m0-original507-count-independent-20261024/focused-current-count.json'
assert sha(baseline_path)=='eb94b00220552e9ede55c2f16c7d0ab285436785e8c4d1890fccb25fe07ee42f'
base=read(baseline_path)['current_distinct_input_union_ledger']
assert (base['no_slower_than_correct_Qfplib'],base['strictly_faster'],base['equal'])==(302,296,6)
old=read(R/'.build/m0-asin-scaled-bound-v164-20261023/slower-inputs.json')['rows']
assert len(old)==507
orig={(r['operation'],r['x'],r.get('y') if r['operation']=='pow' else None):r for r in old}
er=read(O/'public-results.json')['rows'];pr=read(O/'caller-results.json')['rows'];fixes=[]
for r in er:
 if r['group']!='all_historical16' or r['SIO']!='READY':continue
 origrow=orig[('exp',r['x'],None)]
 assert r['instructions']['control']==origrow['own_instructions'] and r['instructions']['Qfplib']==origrow['qfplib_instructions']
 if r['instructions']['candidate']<r['instructions']['Qfplib']:
  assert r['correct']['Qfplib'] and r['correct']['candidate']
  fixes.append(dict(operation='exp',x=r['x'],y=None,expected=r['expected'],instructions=r['instructions'],independent_READY_and_DIRTY_replayed=True))
for r in pr:
 if r['SIO']!='READY' or r['operation']!='pow':continue
 if r['instructions']['candidate']<r['instructions']['Qfplib']<r['instructions']['parent']:
  o=orig[('pow',r['x'],r['y'])]
  assert r['instructions']['parent']==o['own_instructions'] and r['instructions']['Qfplib']==o['qfplib_instructions']
  assert r['correct']['Qfplib'] and r['correct']['candidate']
  fixes.append(dict(operation='pow',x=r['x'],y=r['y'],expected=r['expected'],instructions=r['instructions'],independent_READY_and_DIRTY_replayed=True))
assert len(fixes)==18 and sum(r['operation']=='exp' for r in fixes)==14
assert len({(r['operation'],r['x'],r['y']) for r in fixes})==18
ledger=dict(status='PASS_ADDITIVE_INDEPENDENT_SEPARATE_COMPONENT_ORIGINAL507_UNION',baseline=ref(baseline_path),immutable_original507=ref(R/'.build/m0-asin-scaled-bound-v164-20261023/slower-inputs.json'),accepted_new_fixes=fixes,new_strict_fixes=18,new_equal=0,current=dict(no_slower_than_correct_Qfplib=320,strictly_faster=314,equal=6,remaining=187,remaining_by_operation=dict(pow=149,exp=2,sin=22,cos=14)),definition='Distinct operation/x/y union of accepted separate components. Newly accepted14 exp points and4 product-only pow points all have fresh independent READY+DIRTY public ARM/MPFR proof. These sources have not been merged with earlier accepted components or run as one507-input binary.',historical_receipts_unchanged=True,whole_math_GO=False,integration_GO=False,hardware_GO=False)
(O/'original507-component-delta.json').write_text(json.dumps(ledger,indent=2)+'\n')
notes=dict(
 product_exactness=[
  'For limbs ai,bi in base2^16, only a0*b0 and the two column1 terms are omitted. Their maximum is562937068519425 <2^49.',
  'Column2 is a0*b2+a1*b1+a2*b0. Column3 is a0*b3+a1*b2+a2*b1+a3*b0. All13 retained products are present in the emitted straight-line Thumb body.',
  'After columns2/3, r4:r5 represents C2+2^16*C3 exactly. Shifting r4 once exposes bit63 of the full retained product; ADC adds its half-up round to r5. r6 is still zero.',
  'Columns4/5/6 are all multiples of2^64 in the original product, so rounding early commutes with these exact integer additions. Cached a3 in r2 and b3 in r7 remain live until their last products.',
  'Rounded column3 high word is at most163900. Its first column4 addition is at most4292605, so dropping that first carry is safe. The remaining ADC chains preserve every carry; high after column5 is at most32830, and adding a3*b3 cannot overflow32bits.',
  'The final integer equals floor((a*b-omitted+2^63)/2^64) on a<2^63,b<2^54. Its distance from a*b/2^64 is <=1/2+omitted_max/2^64 <1/2+2^-15. No M0 FPU, wide multiply or runtime helper is used.'
 ],
 exp_rounding=[
  'Own rational proof reconstructs Q96 ln2-step, Q31 inverse, Q44 coefficient quantization, square compensation, Taylor tail and reduction error from frozen source constants; it never calls author certify.py or tools/certificate().',
  'The new high-product error plus nearest-table error and polynomial/reduction error is <3.143875 Q62 units. Integer distance>=4 from the binary64 midpoint is strictly safe.',
  'Subtracting the known Q94 table-centre bias leaves <2.643875 units. At distance3 the source threshold admits only biases within11/32 on the relevant side, giving worst margin2.987625<3. All512 Q62 and Q94 centres satisfy independent integer root inequalities.',
  'Only index0 can normalize, and that table centre is exactly1. Removing table half-error before doubling gives <5.287750 units; distance>=6 is strictly safe. Doubling the unspecialized3.143875 bound would not justify radius6.',
  'All admitted tails exclude the exact midpoint. tail>512 therefore equals nearest-even on every admitted interval, including retained-parity, binade and normal-endpoint controls. Uncertain cases retain the unchanged exp_refine/CR fallback.',
  'For2^-54<abs(x)<2^-40, the exp(x)-1-x remainder is strictly positive and <4097 input-significand units. The changed tiny path declines exactly the potentially crossing side within4096 units and handles exact midpoints in the direction of this positive correction. Other points stay strictly in one rounding cell.'
 ],
 old_unit_failure='The old isolated trial copied a16-byte Flash tailcall wrapper and omitted its RAM target. That old trial unit evidence is not accepted. The present standalone unit includes exact168-byte candidate and182-byte V164 RAM bodies and the literal tiny/normal source with exact6144-byte Q94 table. Its ELF has no firmware/ROM dependencies. Own PC restriction, bounded stack writes, PCS/SP preservation and zero SIO accesses passed.',
 baseline_evidence='All97526 saved control/resident/Qfplib rows were checked for exact inheritance from pinned prior qualification. They are not fresh full-corpus executions in this review or in the author cached-product run. All61 old-tight new-loss inputs, every retained cost-regression type, all16 original exp points and all4 new pow fixes were selected for own fresh runs. No wrong-reference trial, sandbox failure, smoke or inherited baseline calls were added to qualified own totals.',
 sizes='Candidate TU .m0_exp_core grows44bytes; product object section184→168(-16 including alignment), so combined allocated objects+28bytes. Product body182→168(-14), leaf instructions91→84, leaf stack32→40. Own public exp subset observed736bytes same as author full corpus; author original callers observed968same. These are not whole-firmware size/cycle claims.',
 platform_scope='Only RP2040 conditional exp code and the existing RP2040 product body change. GenericM0 allocated sections and semantic relocations are equal; M4 soft/hard selected TUs are empty under MK61_USE_M0_EABI=0 and product is excluded. No wholeM4 build or hardware acceptance was performed.',
 integration_scope='candidate.elf is the whole compiled math TU linked as a private overlay onto exact frozenV164 symbols, not a new complete shipping firmware. The patch targets V164 math only; repaired platform sources, earlier accepted math changes and final publicationea9 are not overwritten or integrated.'
)
(O/'proof-notes.json').write_text(json.dumps(notes,indent=2)+'\n')
environment=dict(status='QUALIFIED_OWN_RUN_EXIT0',python=str(R/'.build/picocalc-apps-arm-venv/bin/python'),MPFR='4.2.2',actual_exec_session=97947,actual_completion_chunk='45ea68',returncode=0,qualified_own_ARM_calls=5900,qualified_own_MPFR_calls=316,sandbox_attempts_excluded=2,sandbox_failure='Both exited132/SIGILL in Unicorn mem_map during machine construction before the first public test; faulthandler located native_eabi_m0_arm_self_test.py:49. The authorised host-only JIT run completed EXIT0. No USB, Flash, lease or Git action occurs in the script.',reproduction=[str(R/'.build/picocalc-apps-arm-venv/bin/python')+' '+str(O/'bind_rebuild.py'),str(R/'.build/picocalc-apps-arm-venv/bin/python')+' '+str(O/'bounds.py'),str(R/'.build/picocalc-apps-arm-venv/bin/python')+' -u -X faulthandler '+str(O/'check_arm.py')],hardware=False)
(O/'review-execution.json').write_text(json.dumps(environment,indent=2)+'\n')
own_names=['bind_rebuild.py','bounds.py','check_arm.py','finalize.py','binding-rebuild.json','bounds-result.json','public-results.json','bare-results.json','caller-results.json','focused-arm.json','product.dis','original507-component-delta.json','proof-notes.json','review-execution.json']
final=dict(status='GO_PRIVATE_EXP_AND_CACHED_PRODUCT_COMPONENT_ONLY',utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),blockers=[],target=dict(author_frozen=ref(P/'FROZEN.json'),author_result=ref(P/'result.json'),CPP=ref(P/'candidate/native_eabi_m0.cpp'),intended_product_include=ref(P/'candidate/native_eabi_m0_pow_exp_product.inc'),private_public_overlay_ELF=ref(P/'candidate.elf'),standalone_unit_ELF=ref(P/'unit.elf'),patch_for_exact_V164=ref(P/'V164-exp-and-product.patch')),source_and_artifact_binding=dict(frozen_artifacts=91,external_lineage=68,all_hashes_sizes_pass=True,independent_rebuilds=9,full_CPP_ASM_overlay_and_unit_ELF_byte_exact=True,product_actual_RAM_bytes=True,original_Flash_wrapper_preserved=True,all_OTHER_allocated_code_tables_BSS_and_semantic_relocations_equal=True,only_CPP_allocated_change='.m0_exp_core',new_global_RAM_tables_or_libgcc=False,postflight159_pins_unchanged=True),independent_evidence=dict(own_ARM_calls=5900,own_MPFR_references=316,public_exp_unique_inputs=307,bare_product_pairs=663,bare_calls=4004,exact_rational_endpoint_checks=918,product_leaf_instructions=[91,84],product_leaf_body_bytes=[182,168],product_leaf_stack=[32,40],own_exp_stack=[736,736],all_historical_exp16_and4_pow_fixes_fresh=True,all61_old_tight_new_losses_and11_regression_cost_types_replayed=True,zero_candidate_wrong=True,PCS_SP_boundedwrites_SIO_contract_pass=True,counts_are_synthetic_instructions_not_physical_cycles=True),fast_path_proof=dict(normal_bound_lt=float(bound['general_radius_float']),normal_integer_radius=4,table_bias_distance3_bound_lt=bound['distance3_worst_upper'],normalized_bound_lt=bound['normalized_radius_float'],normalized_integer_radius=6,strict_tiny_remainder_lt4097=True,all512_Q62_Q94_centres_proven=True,source_to_emitted_code_checked=True),retained_limits=dict(exp395_expanded_raw_Qfplib_deficits=True,exp2_original_deficits=True,exp5800_state_regressions_vs_V164='1..39 instructions, all retained and reported',pow149_original_deficits=True,sin22_original_deficits=True,cos14_original_deficits=True,expanded_ln5_unchanged=True,conversions_FMA_unchanged=True,general_pow1024_totality_open=True,combined_accepted_math_binary_not_built=True,whole_pow_trig_full_domain_qualification_not_replaced=True,whole_M4_firmware_not_built=True,whole_firmware_linked_size_not_measured=True,physical_cycles_not_measured=True),original507_separate_component_union=dict(no_slower=320,strictly_faster=314,equal=6,remaining=187,delta_strict=18,receipt=ref(O/'original507-component-delta.json'),not_one_integrated_binary=True),grants=dict(private_component=True,canonical_integration=False,whole_math=False,all_input_speed_GO=False,hardware=False,publication=False,lease=False),source_Git_primary_modified=False,producer_packets_modified=False,refs=[ref(O/n) for n in own_names])
(O/'FINAL-REVIEW.json').write_text(json.dumps(final,indent=2)+'\n')
print(json.dumps(dict(status=final['status'],review=ref(O/'FINAL-REVIEW.json'),blockers=[],original507=final['original507_separate_component_union'],own_ARM_calls=5900,own_MPFR_references=316),indent=2))
