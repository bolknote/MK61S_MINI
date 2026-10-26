from pathlib import Path
from collections import Counter
import hashlib,json,subprocess
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
R=ROOT/'.build/m0-pow-rsqrt-asm-20261024';Q=ROOT/'.build/m0-float-fma-qualification-20261023'
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
assert sha(R/'FROZEN.json')=='21abcd41787ea53463b755b8f82138947ed9296b93831e00cfeac649b9408963'
for name,value in read(R/'FROZEN.json')['files'].items():pin(R/name,value)
for name,value in read(R/'source-lineage-pins.json')['files'].items():pin(ROOT/name,value)
pin(R/'FROZEN.json');pin(R/'source-lineage-pins.json')
review=ROOT/'.build/m0-pow-rsqrt-asm-independent-20261024/FINAL-REVIEW.json'
assert sha(review)=='90181e2ed18e8d312fc301ccfde8e93d1c63eced161883dee49fd9840ca86928'
receipt=read(review);assert not receipt['blockers']
for item in [receipt['accepted_parent'],*receipt['target'].values(),*receipt['refs']]:pin(Path(item['path']),{k:item[k] for k in ('sha256','bytes')})
pin(review)
qf=read(Q/'FROZEN.json')
for name in ('FROZEN.json','HANDOFF.json','instruction-summary.json','float.json','addendum.json','float-d2f.records.bin.gz','addendum/float-d2f.records.bin.gz','oracles.py','qualify.py'):
 pin(Q/name,qf['files'].get(name))
for name in ('reference/reference.elf','sources/qfplib-linked.S'):
 pin(ROOT/'.build/m0-v138-execution-20261023'/name)
b=read(W/'build.json');q=read(W/'qualification.json');proof=read(W/'proof.json');iso=read(W/'isolation.json');rebuild=read(W/'rebuild-proof.json')
assert q['candidate_ELF_sha256']==iso['candidate_ELF_sha256']==sha(W/'candidate.elf')
assert q['wrong']==q['candidate_raw_losses']==q['new_raw_losses']==0
assert q['unique_inputs']==231984 and q['fresh_ARM_calls']==1391904
assert q['candidate_stack_bytes']==q['candidate_SIO_accesses']==0
assert proof['old512_sample_deficits']==[426,0] and len(rebuild['records'])==4
assert iso['new_body_bytes']==256 and iso['code_delta_bytes']==188
costs=proof['instruction_table'];correct=sum(v['state_rows'] for v in costs.values());faster=sum(v['state_rows'] for v in costs.values() if v['candidate']<v['Qfplib']);equal=correct-faster
deltas=Counter(r['instructions']['candidate']-r['instructions']['parent'] for r in q['rows'])
assert sum(deltas.values())==2*q['unique_inputs'] and sum(v for k,v in deltas.items() if k>0)==110782 and max(deltas)==1
source_partition={'status':'AUTHOR_COMPLETE_QFPLIB_CORRECT_INPUT_AND_INSTRUCTION_PATH_PARTITION_PENDING_INDEPENDENT_REVIEW','reference_ELF':ref(ROOT/'.build/m0-v138-execution-20261023/reference/reference.elf'),'reference_source':ref(ROOT/'.build/m0-v138-execution-20261023/sources/qfplib-linked.S'),'classes':costs,'all_observed_flags_and_counts_match':True,'observed_correct_reference_state_rows':correct,'candidate_faster':faster,'candidate_equal':equal,'candidate_slower':0,'not_physical_cycle_measurement':True}
write('instruction-partition.json',source_partition)
result={'status':'FROZEN_AUTHOR_RP_D2F_LEAF_ZERO_OBSERVED_SPEED_LOSSES_WITH_ALL_DOMAIN_SOURCE_PROOF','accepted_parent':str(R.relative_to(ROOT)),'parent_independent_receipt':{'path':str(review.relative_to(ROOT)),'sha256':sha(review)},'source_sha256':sha(W/'d2f.S'),'convert_include_sha256':iso['convert_include_sha256'],'candidate_ELF_sha256':sha(W/'candidate.elf'),'whole_source_ELF_sha256':sha(W/'whole-source.elf'),'unique_inputs':q['unique_inputs'],'profiled_states':2*q['unique_inputs'],'fresh_qualified_ARM_calls':q['fresh_ARM_calls'],'fresh_MPFR_references':q['fresh_MPFR_references'],'MPFR_version':q['MPFR_version'],'exact_integer_reference_every_input':True,'smoke_probe_calls11004_not_added':True,'wrong':0,'all_raw_return_bits_identical_parent_including_NaNs':True,'parent_observed_raw_speed_losses':q['parent_raw_losses'],'candidate_observed_raw_speed_losses':0,'new_raw_speed_losses':0,'correct_reference_state_rows':correct,'vs_correct_Qfplib':{'faster':faster,'equal':equal,'slower':0},'reference_wrong_state_rows_retained':proof['wrong_reference_state_rows_retained'],'no_nominal_domain_filter':True,'old512_sample_comparable':510,'old512_deficits':[426,0],'all2048_exponents_both_signs':True,'normal_actual_half_inputs_generated':q['normal_actual_half_inputs_generated'],'subnormal_actual_half_inputs_generated':q['subnormal_actual_half_inputs_generated'],'source_proof':'Complete binary64 RNE and complete correct-Qfplib instruction path partition in NUMERIC-PROOF.md/proof.json, pending independent review. Not a physical-cycle claim.','body_bytes':256,'old_body_bytes':68,'selected_ASM_code_delta_bytes':188,'whole_firmware_linked_size_delta_not_measured':True,'old_C_slow_routine_GC_size_effect_not_claimed':True,'new_tables_global_RAM_libgcc_external_calls':False,'stack_bytes':0,'SIO_accesses':0,'R4_R11_SP_bounded_writes_every_call':True,'parent_cost_increase_state_rows_retained':110782,'parent_cost_increase_delta':1,'parent_cost_increases_all_no_slower_correct_Qfplib':True,'vs_parent':{'faster':sum(v for k,v in deltas.items() if k<0),'equal':deltas[0],'slower':110782},'full_ASM_source_unchanged':True,'only_convert_include_plus_new_RP_leaf_include':True,'full_source_256byte_body_exactly_tested':True,'generic_M0_M4_all_allocated_bytes_relocations_identical':True,'CPP_unchanged':True,'complete_object_ELF_rebuilds_byte_exact':4,'direct_public_ABI_entry_at_new_private_link_address_no_fake_veneer':True,'full_repaired_platform_relink_not_done':True,'independent_review_pending':True,'original507_accepted_union_unchanged':418,'no_canonical_Git_device_release_change':True,'goal_complete':False}
write('result.json',result)
handoff='''Private RP2040 double-to-float leaf, frozen for independent review.

All231984 inputs are freshly profiled in READY/DIRTY on candidate, parent
and native Qfplib:1391904 ARM calls,231984 directed MPFR4.2.2 references,
and exact integer RNE every input.0wrong; all raw results match parent,
including NaN sign/payload/quieting. The11004 preliminary probe calls are
excluded. All2048 exponent fields, both signs,20320 generated actual normal
midpoints and1292 subnormal midpoints, all prior28423 raw acquisition
records, payload controls and65536 additional uniform raw bits are included.
Generated midpoint counts are not disjoint corpus sizes.

Observed comparable raw losses103496 ->0; all old512 sample counts/results
reproduce, with426/510 comparable losses ->0. No nominal-domain filter.
All incorrect Qfplib outputs and costs remain in qualification.json.
NUMERIC-PROOF.md gives the author's whole-input RNE proof and a complete
source-derived Qfplib-correct input/instruction partition. proof.json checks
all observed correctness flags and counts against that partition. This is
pending independent mathematical/code acceptance, not a physical-cycle GO.

Instruction paths: zero9 vs Qfplib9; overflow/Inf13 vs13; subnormal-to-normal
19 vs20; lower normal19/22/tie22 vs20/22/tie23..24; upper normal14/17/tie17
vs20/22/tie23..24. Incorrect-reference NaN and other subnormal costs are
also retained. Compared with the old parent,110782 lower-normal state rows
increase by1 instruction; all remain <=correct Qfplib and are preserved
verbatim in retained-parent-regressions.json.

The whole function is256 bytes, previously68 (+188 selected ASM bytes).
No stack, external call, new table/global RAM/libgcc, firmware/ROM/mocks or
SIO access in the candidate. Overall linked firmware size is unmeasured;
possible GC of the old C slow path is not counted. Direct ABI tests use
the newly linked function entry, with no artificial interposition veneer.

Only native_eabi_m0_convert.inc and the new native_eabi_m0_d2f.inc change
relative to the accepted rsqrt parent. Full native_eabi_m0.S and CPP remain
unchanged. Full intended ASM emits the exact256 tested bytes; all other RP
allocated sections and semantic relocations match. Generic M0 and M4
soft/hard selected ASM bytes/relocations match. Four complete object/ELF
rebuilds are byte exact. The source patch requires no build-list changes.

The parent rsqrt90181e2e independent receipt and all22 direct refs were
verified. Original507 reviewed union418 remains unchanged; d2f cold losses
are additional conversion cases. Other open work includes f2d's sampled
loss, FMA acceptance, pow7904 expanded/general1024-bit totality, exp395/ln5,
sin22/cos14 original, combined repaired-platform integration/regression,
hardware cycles and device acceptance. No canonical/Git/device/Flash/release
change and no hardware lease; no whole-math or whole-goal GO.
'''
(W/'HANDOFF.md').write_text(handoff)
write('source-lineage-pins.json',{'status':'FROZEN_ACCEPTED_PARENT_REVIEW_AND_FLOAT_REFERENCE_INPUTS_PINNED','files':dict(sorted(lineage.items()))})
head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
assert not subprocess.check_output(['git','diff','HEAD','--name-only','--','code/native_eabi_m0*'],cwd=ROOT,text=True)
files={str(p.relative_to(W)):ref(p) for p in sorted(W.rglob('*')) if p.is_file() and '__pycache__' not in p.parts and p.name!='FROZEN.json'}
write('FROZEN.json',{'status':'IMMUTABLE_AUTHOR_D2F_COMPONENT_PENDING_INDEPENDENT_REVIEW','files':files,'result_sha256':sha(W/'result.json'),'HANDOFF_sha256':sha(W/'HANDOFF.md'),'HEAD_at_seal':head,'math_worktree_diff_empty':True,'goal_complete':False})
print(json.dumps({'status':result['status'],'files':len(files),'lineage_pins':len(lineage),'FROZEN_sha256':sha(W/'FROZEN.json'),'result_sha256':sha(W/'result.json'),'HANDOFF_sha256':sha(W/'HANDOFF.md'),'candidate_ELF':result['candidate_ELF_sha256'],'whole_source_ELF':result['whole_source_ELF_sha256'],'input_cases':q['unique_inputs'],'qualified_ARM_calls':q['fresh_ARM_calls'],'MPFR':q['fresh_MPFR_references'],'vs_correct_Qfplib':result['vs_correct_Qfplib'],'old_sample':[426,0]},indent=2))
