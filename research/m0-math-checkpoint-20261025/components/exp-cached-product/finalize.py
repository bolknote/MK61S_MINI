"""Seal author-qualified private exp/product result; never promote to production."""
from pathlib import Path
from collections import Counter
import hashlib,json,subprocess,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
P=ROOT/'.build/m0-asin-scaled-bound-v164-20261023'
assert not (W/'FROZEN.json').exists(),'Never overwrite a sealed packet'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
read=lambda n:json.loads((W/n).read_text())
b=read('build.json');q=read('qualification.json');u=read('unit-proof.json');c=read('certificate.json');i=read('isolation.json');r=read('rebuild-proof.json');callers=read('existing-callers.json');integration=read('integration-source-proof.json')
for record in (q,u,c,i):
 assert record['source_sha256']==b['source_sha256']
 assert record['candidate_ELF_sha256']==b['candidate_ELF_sha256']
assert sha(W/'candidate/native_eabi_m0.cpp')==b['source_sha256']
assert sha(W/'candidate.elf')==b['candidate_ELF_sha256']
assert q['candidate_wrong']==0 and q['all_cases_profiled'] and q['unique_inputs']==48763 and q['public_state_cases']==97526
assert q['original16_fixed']==14 and q['original16_remaining']==2
assert q['correct_Qfplib_candidate_raw_losses']==395 and q['new_correct_Qfplib_raw_losses_vs_resident']==0
assert q['tight_trial_instruction_delta_counts']=={'-7':85012,'0':12514}
assert u['actual_ARM_calls']==411232 and u['product_matches_full_error_and_retained_integer_oracles']
assert u['new_and_old_product_bit_identical_on_all_pairs'] and u['SIO_accesses']==0
assert set(u['profiled_product_instruction_counts']['audit_product'])=={84}
assert set(u['profiled_product_instruction_counts']['audit_parent_product'])=={91}
assert c['runtime_product_bytes']==168 and c['parent_runtime_product_bytes']==182
assert callers['summary']['pow']['parent_slower_raw']==153 and callers['summary']['pow']['candidate_slower_raw']==149
assert callers['original_READY_own_and_reference_instruction_counts_reproduced']
assert all(s['new_slower_raw']==0 for s in callers['summary'].values())
assert i['all_other_CPP_allocated_code_tables_BSS_and_dependencies_identical']
assert all(x['allocated_code_and_data_identical'] for x in i['contexts'])
assert all(x['excluded_product_allocated_bytes']==0 for x in i['assembly_contexts'])
assert r['status']=='PASS_COMPLETE_CPP_ASM_PUBLIC_AND_UNIT_ELF_REBUILDS_BYTE_EXACT'
assert integration['status']=='PASS_INTENDED_INTEGRATION_INCLUDE_PRODUCT_BODY_BYTE_EXACT_FIXTURE'
proof_names=['preparation.json','build.json','certificate.json','unit-build.json','unit-proof.json','isolation.json','rebuild-proof.json','integration-source-proof.json','qualification.json','existing-callers.json']
proofs={n:sha(W/n) for n in proof_names}
loss=lambda row:row['correct']['Qfplib'] and row['instructions']['candidate']>row['instructions']['Qfplib']
old_exp=[row for row in q['rows'] if row['group']=='historical16']
remaining_original_exp=[row for row in old_exp if loss(row)]
fixed_pow_keys={(row['x'],row['y']) for row in callers['rows'] if row['operation']=='pow' and row['correct']['Qfplib'] and row['instructions']['parent']>row['instructions']['Qfplib'] and row['instructions']['candidate']<=row['instructions']['Qfplib']}
fixed_pow=[row for row in callers['rows'] if (row['x'],row['y']) in fixed_pow_keys]
assert len(fixed_pow_keys)==4
calls=q['actual_fresh_public_ARM_calls']+u['actual_ARM_calls']+callers['actual_fresh_public_ARM_calls']
assert calls==509892
# Record every qualified adverse row, including cost increases that still
# beat Qfplib and cases where the reference result is numerically wrong.
regression_rows=[row for row in q['rows'] if row['instructions']['candidate']>row['instructions']['control']]
assert len(regression_rows)==5800
(W/'retained-exp-regressions.json').write_text(json.dumps(dict(status='RETAINED_ALL5800_EXP_STATE_COST_INCREASES_VS_V164',rows=regression_rows),indent=2)+'\n')
result=dict(status='FROZEN_AUTHOR_QUALIFIED_RP_EXP_AND_CACHED_PRODUCT_WITH_REMAINING_SPEED_GAPS',
 scope='Private exp entry plus13-MUL shared RAM product. No merged library, physical cycles, independent review, release or all-input speed GO.',
 source_sha256=b['source_sha256'],product_fixture_source_sha256=b['product_source_sha256'],
 product_intended_include_sha256=integration['integration_product_source_sha256'],
 candidate_ELF_sha256=b['candidate_ELF_sha256'],candidate_full_object_sha256=b['candidate_object_sha256'],unit_ELF_sha256=u['unit_ELF_sha256'],
 exp_unique_inputs=q['unique_inputs'],exp_all_profiled_state_cases=q['public_state_cases'],
 qualified_fresh_public_exp_ARM_calls=q['actual_fresh_public_ARM_calls'],qualified_bare_ARM_calls=u['actual_ARM_calls'],
 qualified_product_only_caller_ARM_calls=callers['actual_fresh_public_ARM_calls'],total_qualified_fresh_ARM_calls=calls,
 excluded_smoke_calls=432,smoke_repeats_not_added=True,inherited_control_reference_calls_not_added=True,
 rejected_reference_selection_trial_not_added=True,failed_initial_old_trial_unit_calls_not_added=True,
 fresh_MPFR_reference_calls=q['actual_fresh_MPFR_reference_calls']+callers['actual_fresh_MPFR_reference_calls'],MPFR_version=q['MPFR_version'],
 candidate_wrong=0,source_bound_and_rational_endpoint_checks=True,
 historical_exp16_fixed=14,historical_exp16_remaining=2,remaining_original_exp_state_rows=remaining_original_exp,
 expanded_exp_resident_raw_losses=6149,expanded_exp_unaccepted_tight_trial_raw_losses=460,expanded_exp_candidate_raw_losses=395,
 new_exp_Qfplib_raw_losses_vs_resident=0,new_exp_Qfplib_raw_losses_vs_tight_trial=0,
 instruction_delta_vs_tight_trial=q['tight_trial_instruction_delta_counts'],exp_vs_resident=q['vs_control'],
 retained_exp_state_regressions_vs_resident=5800,retained_regression_instruction_histogram=q['regressions_vs_control_instruction_histogram'],
 all_remaining_exp_rows_in='qualification.json:remaining_slower_correct_Qfplib',
 all_cost_increase_rows_in='retained-exp-regressions.json',
 product_16bit_instructions=[91,84],product_body_bytes=[182,168],product_leaf_stack_bytes=[32,40],
 CPP_allocated_bytes_delta=44,product_object_section_allocated_bytes_delta=-16,
 total_CPP_product_object_allocated_bytes_delta=28,
 linked_whole_firmware_size_delta_not_measured=True,
 public_exp_stack_bytes_same_corpus=[736,736],product_caller_observed_stack_bytes=[968,968],
 existing_pow_original153_fixed=4,existing_pow_original153_remaining=149,existing_pow_four_fixed_state_rows=fixed_pow,
 existing_sin_original22_remaining=22,existing_cos_original14_remaining=14,
 caller_check_not_full_operation_qualification=True,
 separate_author_observed_original507_union=dict(no_slower=320,strictly_faster=314,equal=6,remaining=187,
   definition='Previously reviewed separate-component302 +14 exp +4 product-only pow cases. Not one merged ELF and no additional independent acceptance.',
   remaining_by_operation=dict(pow=149,exp=2,sin=22,cos=14)),
 independently_reviewed_original507_union_unchanged=302,
 expanded_ln5_outside_original507_unchanged=True,
 original_input_matrix_unchanged=True,new_tables_global_RAM_or_libgcc=False,
 source_table_Q62_Q94_exact_checks=True,RAM_product_address_and_Flash_wrapper_unchanged=True,
 generic_M0_and_M4_allocated_translation_unit_controls_identical=True,
 generic_M0_and_M4_product_excluded=True,whole_M4_firmware_not_built=True,
 complete_public_and_unit_rebuilds_byte_exact=True,
 PCS_SP_bounded_writes_SIO_preservation_every_call=True,
 independent_review_pending=True,canonical_integration=False,Git_changes_by_this_work=False,
 hardware_accessed=False,physical_cycles_measured=False,shipping_GO=False,whole_math_GO=False,goal_complete=False,
 unresolved=['395 expanded exp speed losses, including2 original exp points.',
  '149 original pow speed losses; product-only original-input check is not full pow qualification.',
  '22 original sin and14 cos speed losses.',
  'Expanded ln5 and conversion/FMA items remain separate and unchanged.',
  'General pow1024-bit undecided trap/all-domain totality remains open.',
  'Independent review, integration onto repaired platform base, full combined regression and physical cycles.'],
 previous_unit_failure_fixed='Old trial copied16-byte Flash tailcall wrapper instead of182-byte RAM body. New unit includes actual168-byte candidate and182-byte parent bodies, no firmware/ROM or external calls.',
 proof_sha256=proofs)
(W/'result.json').write_text(json.dumps(result,indent=2)+'\n')
text=f'''# Private RP2040 exp and cached13-MUL RAM product

Frozen author qualification only. Source `{b['source_sha256']}`, product include `{integration['integration_product_source_sha256']}`, ELF `{b['candidate_ELF_sha256']}`.

The shared product caches a3/b3 and rounds column3 before upper-column accumulation. It returns the identical truncated-product half-up integer on the original a<2^63,b<2^54 box, preserving the<=1/2+2^-15 error bound. Source-bound carry maxima and exact integer bare ARM checks cover the changed rounding location; leaf91→84 instructions,182→168 body bytes,32→40 stack. It runs at the original RAM address with the original Flash wrapper. No code-placement shortcut, new table, global RAM or libgcc.

Exp uses the rounded product, strict radius4(normal)/6(normalized), existing Q94 table bias at distance3 and a certified integer tiny-input path. All48763 public inputs/97526 states are freshly rechecked in ARM against fresh directed MPFR4.2.2 references; exact return bits match the old tight numerical trial. Resident/control/Qfplib counts are pinned/inherited, not counted as new calls. Separate54-input/four-machine smoke rechecks original16 and IEEE. Original16:14fixed/2open. Expanded old6149→395raw losses against correctQfplib;0new vs resident and0new vs old tight trial. All61 new losses of the old tight trial close. All5800 state cost regressions versus V164 remain in retained-exp-regressions.json; maximum+39. Exp observed stack736same, CPP code+44B. Product object section184→168(-16B incl alignment); combined object change+28B is not a whole-firmware linked-size result.

Bare units411232ARM calls:135162tiny inputs,21526pack configurations(all512 existing Q94 rows),24464product pairs compared with exact integer oracles and the actual old ARM body. SIO untouched; PCS/SP/input fixture/bounded writes checked. The old trial unit failure was a wrapper-only extraction error. New product units are self-contained actual leaf bodies with no firmware/ROM.

Product-only overlay on all189 original pow/sin/cos inputs:1134freshARM/189MPFR, all original READY own/reference instruction counts reproduce. Use the pinned exact/integer/general Qfplib composition per stream. Pow153→149raw;46states improve by7per product call, no new losses; sin22/cos14 unchanged. Domain checked on every product entry and call traces/returned bits identical. This is not a full new pow/trig corpus or whole-operation acceptance. A rejected wrong-reference-selection trial is retained and excluded from all qualified totals.

Qualified fresh calls:509892ARM(total97526publicexp+411232bare+1134callers),48952freshMPFR references. Smoke/rejected/failed/inherited calls excluded. Whole CPP+ASM/publicELF/unitELF rebuilds byte-exact; intended include yields the exact fixture product bytes. Generic M0/M4 selected translation units unchanged, product excluded. No whole M4 platform build.

The earlier302 independently reviewed separate-component original507 count is unchanged. New author-observed separate union320(314faster/6equal),187original open(pow149/exp2/sin22/cos14), is not a merged binary or new independent acceptance. Expandedln5, conversions/FMA, pow totality, other full-domain proof/review, repaired-base integration and physical cycles remain open. No canonical/Git/device/Flash/USB work. Goal remains active.

V164-exp-and-product.patch targets the exact frozen V164 math sources; it is not automatically applicable to current canonical checkout. Private fixture cached-product.S changes the input section name only; intended include restores .scratch_y.m0_pow_hot. Do not copy the whole V164 firmware over repaired platform code.
'''
(W/'HANDOFF.md').write_text(text)
source_pins={str(p.relative_to(ROOT)):dict(sha256=sha(p),bytes=p.stat().st_size) for p in sorted((P/'source/code').glob('native_eabi_m0*')) if p.is_file()}
extra=[P/'firmware/mk61s-picocalc-pico-h.elf',P/'slower-inputs.json',P/'build/compile_commands.json',ROOT/'tools/certify_m0_exp_fast.py',ROOT/'.build/m0-exp-tight-firstpass-20261024/qualification.json',ROOT/'.build/m0-v138-execution-20261023/reference/reference.elf',ROOT/'research/rp2040-memset-2026-10-21/capture/bootrom.bin']
for p in extra:source_pins[str(p.relative_to(ROOT))]=dict(sha256=sha(p),bytes=p.stat().st_size)
(W/'source-lineage-pins.json').write_text(json.dumps(dict(status='PINNED_UNCHANGED_FROZEN_MATH_SOURCE_AND_REFERENCE_LINEAGE',files=source_pins),indent=2)+'\n')
files={str(p.relative_to(W)):dict(sha256=sha(p),bytes=p.stat().st_size) for p in sorted(W.rglob('*')) if p.is_file()}
seal=dict(status='FROZEN_PRIVATE_AUTHOR_COMPONENT_PENDING_INDEPENDENT_REVIEW',files=files,
 result_sha256=sha(W/'result.json'),HANDOFF_sha256=sha(W/'HANDOFF.md'),
 HEAD_at_seal=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
 math_worktree_diff_empty=subprocess.check_output(['git','diff','--stat','--','code/native_eabi_m0*','third_party/core_math'],cwd=ROOT,text=True).strip()=='',
 scope='Author component only; all named speed/totality/integration/physical-cycle items remain open.',goal_complete=False)
(W/'FROZEN.json').write_text(json.dumps(seal,indent=2)+'\n')
print(json.dumps(dict(status=seal['status'],artifacts=len(files),source_lineage_pins=len(source_pins),
 result_sha256=seal['result_sha256'],HANDOFF_sha256=seal['HANDOFF_sha256'],FROZEN_sha256=sha(W/'FROZEN.json'),
 total_qualified_fresh_ARM_calls=calls,HEAD_at_seal=seal['HEAD_at_seal'],math_worktree_diff_empty=seal['math_worktree_diff_empty']),indent=2))
