"""Seal the qualified private rsqrt component; preserve every remaining loss."""
from pathlib import Path
from collections import Counter
import hashlib,json,subprocess
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
S=ROOT/'.build/m0-pow-square-ordinary-20261024'
assert not (W/'FROZEN.json').exists(),'A sealed packet must never be rewritten'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
def write(n,d):(W/n).write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
def ref(p):p=Path(p);return {'sha256':sha(p),'bytes':p.stat().st_size}
lineage={}
def pin(p,expected=None):
 p=Path(p);value=ref(p)
 if expected is not None:assert value==expected,str(p)
 key=str(p.relative_to(ROOT));assert key not in lineage or lineage[key]==value
 lineage[key]=value
assert sha(S/'FROZEN.json')=='f1d64d6955b8a9b96af272a6191196a39709c6896617f8557d555a78e35e478e'
for name,value in read(S/'FROZEN.json')['files'].items():pin(S/name,value)
for name,value in read(S/'source-lineage-pins.json')['files'].items():pin(ROOT/name,value)
for name in ('FROZEN.json','source-lineage-pins.json'):pin(S/name)
review=ROOT/'.build/m0-pow-square-ordinary-independent-20261024/FINAL-REVIEW.json'
assert sha(review)=='4fb68e5ea8dbc4539befb483277ac2ce8e301bc23f1447c8b72de312fbbcdde1'
receipt=read(review);assert not receipt['blockers']
direct=[receipt['accepted_parent'],*receipt['target'].values(),*receipt['refs']]
for item in direct:pin(Path(item['path']),{k:item[k] for k in ('sha256','bytes')})
pin(review)
write('prior-independent-postread.json',{'status':'PASS_PRIOR_POW_COMPONENT_INDEPENDENT_RECEIPT_AND_ALL26_DIRECT_REFS','receipt':str(review.relative_to(ROOT)),'sha256':sha(review),'verified_direct_refs':len(direct),'reviewed_original507_union':receipt['original507_separate_component_union'],'this_is_not_independent_acceptance_of_new_rsqrt':True})
b=read(W/'build.json');q=read(W/'qualification.json');t=read(W/'targeted.json');p=read(W/'probe.json');u=read(W/'unit-proof.json');iso=read(W/'isolation.json');reb=read(W/'rebuild-proof.json');cert=read(W/'certificate.json')
for d in (q,t):assert d['candidate_ELF_sha256']==sha(W/'candidate.elf')
assert p['build_sha256']==sha(W/'build.json')
assert q['candidate_wrong']==t['wrong']==p['wrong']==0
assert q['new_candidate_raw_losses']==t['new_raw_losses']==p['new_raw_losses']==0
assert q['vs_parent']['slower']==t['vs_parent']['slower']==0
assert reb['rebuilds']==10 and cert['unsafe_tail_interval_inclusive']==[497,514]
assert iso['whole_intended_source_emits_tested_allocated_bytes'] and iso['unit_quotient_macro_equals_inline_runtime_bytes']
assert iso['allocated_object_bytes_delta']==776
variants={};pairs=set();candidate_checks={};new_losses=[]
for label,data in (('full',q),('targeted',t),('focused',p)):
 for row in data['rows']:
  pair=(row['x'],row['y']);key=pair+(row['SIO'],);pairs.add(pair)
  check=(row['outputs']['candidate'],row['instructions']['candidate'])
  if key in candidate_checks:assert candidate_checks[key]==check
  candidate_checks[key]=check
  reference=row.get('reference','qfp_composed_pow_exact');vkey=key+(reference,)
  value={'x':row['x'],'y':row['y'],'SIO':row['SIO'],'reference':reference,'expected':row['expected'],'outputs':{n:row['outputs'][n] for n in ('parent','candidate','Qfplib')},'instructions':{n:row['instructions'][n] for n in ('parent','candidate','Qfplib')},'correct_Qfplib':row['correct']['Qfplib']}
  if vkey in variants:assert variants[vkey]==value
  variants[vkey]=value
def loss(r,label):return r['correct_Qfplib'] and r['instructions'][label]>r['instructions']['Qfplib']
remaining=[r for r in variants.values() if loss(r,'candidate')]
new=[r for r in remaining if not loss(r,'parent')];assert not new
parent_losses={(r['x'],r['y']) for r in variants.values() if loss(r,'parent')}
current_losses={(r['x'],r['y']) for r in remaining}
assert len(pairs)==111912 and len(candidate_checks)==223824 and len(current_losses)==7904
write('remaining-expanded.json',{'status':'ALL_OBSERVED_CORRECT_QFPLIB_DEFICITS_RETAINED_NO_DOMAIN_FILTER','raw_input_pairs':len(current_losses),'variant_state_rows':len(remaining),'rows':remaining})
old_original=[r for r in q['rows'] if r['group']=='historical153']
fixed=[r for r in old_original if r['correct']['Qfplib'] and r['instructions']['parent']>r['instructions']['Qfplib'] and r['instructions']['candidate']<=r['instructions']['Qfplib']]
assert len({(r['x'],r['y']) for r in fixed})==31 and len(fixed)==62
assert all(r['y']=='BFE0000000000000' and r['instructions']['candidate']<r['instructions']['Qfplib'] for r in fixed)
write('historical31-fixed.json',{'status':'31_NEW_STRICT_ORIGINAL_POW_FIXES_BOTH_SIO_STATES','rows':fixed})
public_calls=q['fresh_public_ARM_calls']+t['fresh_ARM_calls']+p['fresh_ARM_calls']
mpfr_calls=q['fresh_MPFR_calls']+t['fresh_MPFR_references']+p['fresh_MPFR_references']
write('expanded-union-summary.json',{'status':'QUALIFIED_DEDUPLICATED_PUBLIC_POW_UNION','unique_input_pairs':len(pairs),'distinct_profiled_states':len(candidate_checks),'distinct_reference_state_variants':len(variants),'same_input_candidate_bits_and_counts_match_across_corpora':True,'parent_raw_speed_losses':len(parent_losses),'candidate_raw_speed_losses':len(current_losses),'new_raw_speed_losses':len(new),'correct_Qfplib_comparison_has_no_domain_filter':True,'old63795_corpus':{'parent':8078,'candidate':5912},'new52215_targeted_corpus':{'parent':t['all_parent_raw_losses'],'candidate':t['all_candidate_raw_losses']},'targeted1992_losses_are_outside_previous_remaining5912':True,'all_wrong_reference_records_retained_in_raw_reports':True})
assert u['fresh_ARM_calls']==149484 and u['SIO_reads_or_writes']==0
for name in ('trial-pre-alias-v3/unit.elf','trial-pre-alias-v3/rsqrt.S','trial-pre-alias-v3/unit-proof.json','trial-pre-alias-v3/build.json','trial-symmetric-v4/certificate.json'):pin(W/name)
assert sha(W/'trial-pre-alias-v3/unit.elf')==u['unit_ELF_sha256']
assert sha(W/'trial-pre-alias-v3/rsqrt.S')==u['rsqrt_source_sha256']
assert sha(W/'trial-symmetric-v4/certificate.json')==u['certificate_sha256']
write('unit-proof-binding.json',{'status':'PASS_EXECUTED_QUOTIENT_MODULE_EQUALS_FINAL_UNIT_AND_INLINE_RUNTIME','unit_calls':149484,'calls_not_repeated_after_alias_and_guard_only_edits':True,'executed_unit':str((W/'trial-pre-alias-v3/unit.elf').relative_to(ROOT)),'executed_source':str((W/'trial-pre-alias-v3/rsqrt.S').relative_to(ROOT)),'unit_proof':ref(W/'unit-proof.json'),'executed_code_binding':ref(W/'executed-code-binding.json'),'final_source_isolation':ref(W/'isolation.json'),'actual_macro_bytes':iso['quotient_macro_bytes'],'all_other_trial_and_failed_launcher_calls_excluded':True})
result={'status':'FROZEN_AUTHOR_QUALIFIED_RP_POW_RSQRT_EXACT_COORDINATE_AND_ASYMMETRIC_BOUND','parent':str(S.relative_to(ROOT)),'parent_independent_review':{'path':str(review.relative_to(ROOT)),'sha256':sha(review)},'CPP_sha256':sha(W/'candidate/native_eabi_m0.cpp'),'ASM_sha256':sha(W/'candidate/native_eabi_m0.S'),'include_sha256':sha(W/'candidate/native_eabi_m0_pow_rsqrt.inc'),'candidate_ELF_sha256':sha(W/'candidate.elf'),'whole_source_ELF_sha256':sha(W/'whole-source.elf'),'certificate_sha256':sha(W/'certificate.json'),'public_unique_pair_union':len(pairs),'public_distinct_states':len(candidate_checks),'fresh_final_public_ARM_calls':public_calls,'fresh_MPFR_references':mpfr_calls,'MPFR_version':q['MPFR_version'],'qualified_bare_quotient_ARM_calls':149484,'bare_quotient_calls_bound_by_identical_actual_module_not_repeated':True,'total_qualified_ARM_calls_including_bound_unit':public_calls+149484,'inherited_prior_public_baseline_rows_not_added':q['inherited_parent_control_Qfplib_count_rows'],'trials_smokes_failed_launchers_and_prior_component_calls_excluded':True,'wrong':0,'new_Qfplib_raw_losses':0,'observed_parent_instruction_regressions':0,'original_pow_remaining_before':82,'original_pow_remaining_after':51,'new_original_strict_fixes':31,'original507_author_separate_component_union':{'no_slower':418,'strictly_faster':412,'equal':6,'remaining':89,'by_operation':{'pow':51,'exp':2,'sin':22,'cos':14},'not_one_integrated_binary':True},'original507_reviewed_prior_union':{'no_slower':387,'strictly_faster':381,'equal':6,'remaining':120},'old63795_corpus_remaining':[8078,5912],'expanded_union_unique_pairs':len(pairs),'expanded_union_remaining_before':len(parent_losses),'expanded_union_remaining_after':len(current_losses),'new_targeted1992_losses_retained_outside_old5912':True,'normal_original_fast_counts_READY':[298,309],'normal_original_parent_READY':[385,386],'normal_original_parent_DIRTY':[552,642],'normal_original_Qfplib':[307,368],'old_hard_case_READY':{'x':'5B27CF4AC334ECB8','parent':822,'candidate':304,'Qfplib':341},'old_hard_case_DIRTY':{'parent':1067,'candidate':304,'Qfplib':341},'new_tables_RAM_libgcc':False,'code_bytes_delta':776,'full_pow_public_stack_bytes':[2236,2236],'targeted_rsqrt_stack_bytes':[196,172],'new_helper_static_frame':64,'targeted_candidate_SIO_reads_or_writes':0,'all512_cells_and_target_tails_covered':t['all512_cells_have_every_target_tail'],'all2046_normal_exponents':True,'full_source_binding_and_ten_rebuilds_byte_exact':True,'generic_M0_M4_selected_CPP_ASM_bytes_relocations_identical':True,'whole_M4_firmware_not_built':True,'source_proof_scope':'Positive normal reciprocal-root path only; exact old boundary retained for18 integer tails. Does not prove general pow totality or all-input speed.','still_open':['7904 observed expanded pow speed inputs, including1992 newly sampled exact-boundary paths','general pow undecided1024-bit totality','independent acceptance of this new component','combined repaired-platform integration and regression','physical cycle and device acceptance','exp395 expanded, ln5 expanded, sin22/cos14 original, conversions and FMA work'],'canonical_Git_device_or_publication_changed':False,'goal_complete':False}
assert public_calls==443784 and mpfr_calls==116373
write('result.json',result)
handoff=f'''The private RP2040 reciprocal-root pow component is frozen for independent review.

Original pow deficits82 ->51; all31 new fixes are strict in READY and DIRTY.
The original507 separate-component author union is418=412strict+6equal;89
remain(pow51/exp2/sin22/cos14). The accepted prior independent union is387.
These are separate-component results, not one integrated firmware.

On the same63795-input corpus:8078 ->5912 expanded deficits,0new. The
additional52215-input all-cell/rounding corpus has1992 remaining deficits.
The deduplicated111912-pair/223824-state union has42790 parent deficits
and7904 candidate deficits,0new and0 parent-cost increases. All remaining
correct-reference losses and all wrong-reference returns/costs are retained.
No nominal domain filter is applied. pow has no native Qfplib routine:
the pinned comparator follows each original stream; targeted rsqrt uses
qfp_composed_pow_exact(sqrt then divide).

Fresh final public calls443784 ARM/116373 MPFR4.2.2;0wrong. Prior baseline
rows are pinned/inherited and not added. The149484 earlier bare quotient
calls bind through exact actual-module identity to the final unit and
inline runtime; they were not repeated after symbol/guard-only changes.
Trials and the syntax-error launcher are excluded from qualified totals.

Normal original paths298..309 vs old385..386 READY/552..642 DIRTY and
Qfplib307..368. Old hard input5B27CF4AC334ECB8 is304 vs old822/1067 and
Qfplib341. These are instructions in Cortex-M0 Unicorn, not physical cycles.

The two-MUL reciprocal from the existing512 rsqrt seeds yields an exact
uint32 quotient after at most2 remainder corrections. The integer Newton
point is bit-identical to the old pipeline. Exact rational bounds give
seed error<25/8, point error down<15.649/up<3. Only tails[497,514] use the
original exact161-bit boundary. Full proof is RATIONAL-PROOF.md; all512
seed inequalities/reciprocals and exact fractions are in certificate.json.

Extra code776 bytes; no new table, global RAM or libgcc. Static helper
frame64; targeted observed196 ->172, full public stack2236 unchanged.
Targeted candidate executes0 SIO reads/writes in both contexts. Full
intended CPP/ASM emits the tested code; ten complete object/ELF rebuilds
are byte exact. All existing CPP allocated bytes and semantic relocations
match the parent; the new boundary export is storage-free. Only the RP
ASM dispatch section changes. Generic M0 and M4 soft/hard selected CPP/ASM
bytes and relocations match; no whole-M4 firmware was built.

Source patch accepted-pow-to-rsqrt.patch targets the exact accepted parent
source, using an include in the existing ASM TU; no build-list addition.
candidate/ contains the full intended CPP/ASM and includes. whole-source.elf
is a private function overlay, not a bootable/released firmware image.

Open:7904 expanded speed inputs(1992 additional sampled boundary paths),
general pow1024-bit undecided trap/totality, new independent review, combined
repaired-platform integration/regression and device cycles/acceptance. No
canonical/Git/device/Flash/network/release change; the full goal remains open.
'''
(W/'HANDOFF.md').write_text(handoff)
write('source-lineage-pins.json',{'status':'ALL_FROZEN_PARENT_AND_DIRECT_REVIEW_AND_BOUND_UNIT_INPUTS_PINNED','files':dict(sorted(lineage.items()))})
head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
diff=subprocess.check_output(['git','diff','--name-only','--','code/native_eabi_m0*'],cwd=ROOT,text=True)
assert not diff
files={}
for path in sorted(W.rglob('*')):
 if not path.is_file():continue
 relative=path.relative_to(W)
 if relative.parts[0].startswith('trial-') or '__pycache__' in relative.parts or relative.name=='FROZEN.json':continue
 files[str(relative)]=ref(path)
write('FROZEN.json',{'status':'IMMUTABLE_AUTHOR_RSQRT_COMPONENT_FOR_INDEPENDENT_REVIEW','files':files,'result_sha256':sha(W/'result.json'),'HANDOFF_sha256':sha(W/'HANDOFF.md'),'HEAD_at_seal':head,'math_worktree_diff_empty':True,'excluded_trial_directories_not_qualified_except_explicit_unit_bindings':True,'goal_complete':False})
print(json.dumps({'status':result['status'],'files':len(files),'lineage_pins':len(lineage),'FROZEN_sha256':sha(W/'FROZEN.json'),'result_sha256':sha(W/'result.json'),'HANDOFF_sha256':sha(W/'HANDOFF.md'),'candidate_ELF':result['candidate_ELF_sha256'],'whole_source_ELF':result['whole_source_ELF_sha256'],'original_pow':[82,51],'old_expanded':[8078,5912],'union_expanded':[len(parent_losses),len(current_losses)],'fresh_public_ARM':public_calls,'fresh_MPFR':mpfr_calls},indent=2))
