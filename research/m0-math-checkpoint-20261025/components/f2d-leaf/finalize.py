from pathlib import Path
from collections import Counter
import hashlib,json,subprocess
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
D=ROOT/'.build/m0-d2f-leaf-20261024';Q=ROOT/'.build/m0-float-fma-qualification-20261023'
assert not (W/'FROZEN.json').exists(),'Never rewrite a frozen packet'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
def ref(p):p=Path(p);return {'sha256':sha(p),'bytes':p.stat().st_size}
def write(name,value):(W/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
lineage={}
def pin(path,expected=None):
 path=Path(path);value=ref(path)
 if isinstance(expected,str):assert value['sha256']==expected,str(path)
 elif expected is not None:assert value==expected,str(path)
 name=str(path.relative_to(ROOT));assert name not in lineage or lineage[name]==value
 lineage[name]=value
assert sha(D/'FROZEN.json')=='87c989edfe183f894ad87a833aed18f7b47172366c6362cf2276c3023a6375cb'
for name,value in read(D/'FROZEN.json')['files'].items():pin(D/name,value)
for name,value in read(D/'source-lineage-pins.json')['files'].items():pin(ROOT/name,value)
pin(D/'FROZEN.json');pin(D/'source-lineage-pins.json')
qf=read(Q/'FROZEN.json')
for name in ('FROZEN.json','HANDOFF.json','instruction-summary.json','float.json','float-f2d.records.bin.gz','oracles.py','qualify.py'):pin(Q/name,qf['files'].get(name))
b=read(W/'build.json');q=read(W/'qualification.json');proof=read(W/'proof.json');iso=read(W/'isolation.json');rebuild=read(W/'rebuild-proof.json')
assert q['candidate_ELF_sha256']==iso['candidate_ELF_sha256']==sha(W/'candidate.elf')
assert q['wrong']==q['candidate_raw_losses']==q['new_raw_losses']==0
assert q['unique_inputs']==132959 and q['fresh_ARM_calls']==797754
assert q['candidate_stack_bytes']==q['candidate_SIO_accesses']==0
assert proof['old_sample_deficits']==[1,0] and len(rebuild['records'])==4
assert iso['old_body_bytes']==34 and iso['new_body_bytes']==172 and iso['code_delta_bytes']==138
assert iso['d2f_256byte_leaf_unchanged']
costs=proof['reference_correct_classes'];correct=sum(v['state_rows'] for v in costs.values());faster=sum(v['state_rows'] for v in costs.values() if v['candidate']<v['Qfplib']);equal=correct-faster
deltas=Counter(r['instructions']['candidate']-r['instructions']['parent'] for r in q['rows']);assert max(deltas)<0
write('instruction-partition.json',{'status':'AUTHOR_WHOLE_BINARY32_RNE_AND_CORRECT_REFERENCE_INSTRUCTION_PARTITION_PENDING_REVIEW','classes':costs,'observed_correct_reference_state_rows':correct,'faster':faster,'equal':equal,'slower':0,'wrong_reference_state_rows_retained':proof['wrong_reference_state_rows_retained'],'no_nominal_domain_filter':True,'physical_cycles_not_measured':True})
parent_review=ROOT/'.build/m0-d2f-leaf-independent-20261024/FINAL-REVIEW.json';parent_review_info={'independent_review_available_at_seal':False}
if parent_review.exists():
 review=read(parent_review)
 assert review['status'].startswith('GO_') and not review['blockers']
 assert review['target']['frozen']['sha256']==sha(D/'FROZEN.json')
 refs=[review['accepted_parent'],*review['target'].values(),*review['refs']]
 for item in refs:pin(Path(item['path']),{k:item[k] for k in ('sha256','bytes')})
 pin(parent_review)
 parent_review_info={'independent_review_available_at_seal':True,'path':str(parent_review.relative_to(ROOT)),'sha256':sha(parent_review),'status':review['status'],'direct_refs_verified':len(refs),'no_hardware_or_integration_GO':True}
write('parent-review-at-seal.json',parent_review_info)
result={'status':'FROZEN_AUTHOR_RP_F2D_LEAF_ZERO_OBSERVED_SPEED_LOSSES_WITH_WHOLE_DOMAIN_SOURCE_PROOF','qualified_parent':str(D.relative_to(ROOT)),'parent_review_at_seal':parent_review_info,'source_sha256':sha(W/'f2d.S'),'convert_include_sha256':iso['convert_include_sha256'],'candidate_ELF_sha256':sha(W/'candidate.elf'),'whole_source_ELF_sha256':sha(W/'whole-source.elf'),'unique_inputs':132959,'profiled_states':265918,'fresh_qualified_ARM_calls':797754,'fresh_MPFR_references':132959,'MPFR_version':q['MPFR_version'],'exact_integer_reference_every_input':True,'smoke_probe_calls41490_not_added':True,'wrong':0,'raw_return_bits_identical_parent_including_NaNs':True,'parent_raw_speed_losses':q['parent_raw_losses'],'candidate_raw_speed_losses':0,'new_raw_speed_losses':0,'correct_reference_state_rows':correct,'vs_correct_Qfplib':{'faster':faster,'equal':equal,'slower':0},'wrong_reference_state_rows_retained':proof['wrong_reference_state_rows_retained'],'no_nominal_domain_filter':True,'old256_sample_comparable':249,'old_sample_deficits':[1,0],'all256_exponent_fields_both_signs':True,'all23_nonzero_subnormal_fraction_widths':True,'source_proof':'NUMERIC-PROOF.md/proof.json: whole binary32 exact returned-value widening and complete correct-Qfplib instruction path partition, pending independent review. Not physical cycles.','instructions':{'normal':[12,13],'signed_zero':[5,8],'infinity':[12,12]},'body_bytes':172,'old_body_bytes':34,'selected_ASM_code_delta_bytes':138,'whole_firmware_size_delta_not_measured':True,'old_C_slow_path_GC_size_effect_not_claimed':True,'stack_bytes':0,'SIO_accesses':0,'new_tables_RAM_libgcc_external_calls':False,'all_observed_candidate_states_strictly_faster_parent':True,'parent_cost_increase_rows':0,'all_R4_R11_SP_boundedwrites_checked':True,'full_source_exact172byte_body_bound':True,'d2f_256byte_leaf_and_all_other_RP_sections_relocations_unchanged':True,'generic_M0_M4_selected_ASM_bytes_relocations_identical':True,'full_native_ASM_and_CPP_source_unchanged':True,'four_complete_object_ELF_rebuilds_byte_exact':True,'private_direct_ABI_entry_no_interposition_veneer':True,'combined_repaired_platform_relink_not_done':True,'independent_review_pending':True,'original507_union_unchanged':418,'no_canonical_Git_device_or_release_changes':True,'goal_complete':False}
write('result.json',result)
(W/'HANDOFF.md').write_text('''Private RP2040 float-to-double leaf, frozen for independent review.

132959 unique inputs, every case profiled READY/DIRTY on candidate, parent
and native Qfplib:797754 fresh ARM calls,132959 directed MPFR4.2.2 and
exact integer widening references.0wrong, every raw result bit matches
parent including NaN sign/payload/quieting. The41490 smoke probe calls are
not added. All256 exponent fields/both signs, all23 subnormal widths with
dense heads/tails and random values, every prior9122 raw record, normal
payload split classes, NaN controls and65536 extra uniform words included.

Normal12 instructions vs old13 / Qfplib13. Either zero5 vs old28 / Qfplib8.
Infinity12 vs Qfplib12. All old256 sample costs/results reproduce and the
one deficit among249 correct references is fixed. Expanded parent4 raw
losses (both zeros and infinities) ->0,0new. Every observed candidate
state is strictly faster than parent; no parent cost increase. Incorrect
reference NaN and subnormal returns/costs remain in qualification.json.
No nominal-domain filter. NUMERIC-PROOF.md gives the author's whole-domain
exact widening proof and complete correct-Qfplib instruction partition.
This is pending independent review, not physical-cycle acceptance.

New function172 bytes vs old ASM34 (+138 selected ASM bytes),0stack,
tables/global RAM/libgcc/external calls/SIO/ROM/mocks. Overall linked size
and GC removal of the old C slow helper are not measured or counted.
Full intended ASM emits exact tested172B; only RP f2d section changes.
The complete d2f256B leaf and every other RP allocated section/semantic
relocation are unchanged. Generic M0/M4 selected ASM bytes/relocations
match; full native_eabi_m0.S and CPP source unchanged. Four complete
object/ELF rebuilds byte exact. Tests use direct new private link address,
no artificial interposition veneer. No build-list addition required.

Qualified parent is .build/m0-d2f-leaf-20261024, pinned unchanged. Its
independent-review availability at seal is recorded separately; do not
infer acceptance from its use as a qualified source parent. Independent
review, combined repaired-platform integration/regression, device/physical
cycles and release remain open. Original507 union418 unchanged; FMA and
pow/exp/ln/sin/cos open work unchanged. No canonical/Git/device/Flash/lease
or release change; no whole-math or whole-goal GO.
''')
write('source-lineage-pins.json',{'status':'QUALIFIED_PARENT_AND_FLOAT_REFERENCE_INPUTS_PINNED','files':dict(sorted(lineage.items()))})
head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
assert not subprocess.check_output(['git','diff','HEAD','--name-only','--','code/native_eabi_m0*'],cwd=ROOT,text=True)
files={str(p.relative_to(W)):ref(p) for p in sorted(W.rglob('*')) if p.is_file() and '__pycache__' not in p.parts and p.name!='FROZEN.json'}
write('FROZEN.json',{'status':'IMMUTABLE_AUTHOR_F2D_COMPONENT_PENDING_INDEPENDENT_REVIEW','files':files,'result_sha256':sha(W/'result.json'),'HANDOFF_sha256':sha(W/'HANDOFF.md'),'HEAD_at_seal':head,'math_worktree_diff_empty':True,'goal_complete':False})
print(json.dumps({'status':result['status'],'files':len(files),'lineage_pins':len(lineage),'FROZEN_sha256':sha(W/'FROZEN.json'),'result_sha256':sha(W/'result.json'),'HANDOFF_sha256':sha(W/'HANDOFF.md'),'candidate_ELF':result['candidate_ELF_sha256'],'whole_source_ELF':result['whole_source_ELF_sha256'],'vs_correct_Qfplib':result['vs_correct_Qfplib'],'parent_review':parent_review_info},indent=2))
