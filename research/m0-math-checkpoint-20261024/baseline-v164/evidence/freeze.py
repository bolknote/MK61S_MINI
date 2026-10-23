"""Freeze the fixed V164 math packet without rebuilding or promoting its image."""
import hashlib,json
from datetime import datetime,timezone
from pathlib import Path
root=Path.cwd();work=Path(__file__).resolve().parent;parent=root/'.build/m0-sqrt-zero-tail-v163-20261023'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def pin(p):return dict(path=str(Path(p).resolve().relative_to(root)),sha256=sha(p))
def read(p):return json.loads(Path(p).read_text())
manifest=read(work/'firmware/manifest.json');prep=read(work/'preparation.json')
validation=read(work/'validation.json');matrix=read(work/'extended-instruction-matrix.json');cases=read(work/'case-comparison.json')
endpoint=read(work/'endpoint-qualification.json');random=read(work/'asin-acos-random.json');edges=read(work/'asin-edges.json')
assert manifest['build_id'].upper()=='0B3BE556'
elf=work/'firmware/mk61s-picocalc-pico-h.elf'
assert sha(elf)=='3b92d7dc30cc860c0b1f17943f1cd626f94112a98adaf165ec4f9cd300364db1'
assert sha(parent/'HANDOFF.json')=='18c62e836191354f5608d14e8452e7bf365416ec5e586f4803b705c17097ffc3'
assert sha(parent/'FROZEN.json')=='c6833b2810e6226c835a5071f4bc2efff97e0a850e988216b853afa0fdf4404c'
reports={n:pin(work/n) for n in ('preparation.json','certificate.json','nearest-root-certificate.json','validation.json',
    'endpoint-qualification.json','asin-acos-random.json','asin-edges.json','matrix-subsets.json','result.json',
    'case-comparison.json','extended-instruction-matrix.json','slower-inputs.json','generic-m0-isolation.json',
    'm4-check/m4-isolation.json','candidate-probe.json','terminal-observations.json','integration-contract.json')}
references={}
for name in ('tests/native_eabi_m0_arm_self_test.py','tests/check_stm32_vectors.py','tests/m0_mpfr_oracle.py',
    'tests/qualify_m0_rounding.py','tests/qualify_m0_asin_edges.py','.build/m0-pow-stable-v87-20261022/link-equivalence.py',
    '.build/m0-math-paused-20261023/checkpoint.json','.build/m0-math-resumed-20261023/checkpoint.json'):
    p=pin(root/name);references[p['path']]=p['sha256']
for name in ('HANDOFF.json','FROZEN.json','verify.py','matrix-subsets.json','result.json','special-profile.json','tiny-profile.json','public-canary.json'):
    p=pin(parent/name);references[p['path']]=p['sha256']
files=[p for p in work.iterdir() if p.is_file() and p.name not in ('HANDOFF.json','FROZEN.json')]
files.extend(p for p in (work/'proof').iterdir() if p.is_file())
files.extend(work/n for n in ('m4-check/m4-isolation.json','firmware/manifest.json','firmware/mk61s-picocalc-pico-h.elf',
    'firmware/mk61s-picocalc-pico-h.bin','firmware/mk61s-picocalc-pico-h.uf2'))
for name in ('compact_math.cpp.o','native_eabi_m0.cpp.o','native_eabi_m0_cr.cpp.o','native_eabi_m0.S.o','native_eabi_m0_rp2040.S.o'):
    files.append(next((work/'build/CMakeFiles/mk61s-picocalc-pico-h.dir').rglob(name)))
edge_cases=sum(v['cases'] for v in edges['operations'].values())
random_cases=sum(v['cases'] for v in random['operations'].values())
assert edge_cases==173326 and random_cases==80140
public_cases=edge_cases+random_cases+endpoint['public_RNE_calls']+6784
assert public_cases==548294
handoff=dict(status='FROZEN_PRIVATE_V164_REVIEWABLE_OFFLINE_MATH_NOT_HARDWARE_GO',candidate='V164',build='0B3BE556',
    recorded_at=datetime.now(timezone.utc).isoformat(),source_sha256=manifest['source_sha256'],source_file_count=654,
    source_file_hashes=prep['source_file_hashes'],references=references,reports=reports,
    elf=pin(elf),bin=pin(work/'firmware/mk61s-picocalc-pico-h.bin'),uf2=pin(work/'firmware/mk61s-picocalc-pico-h.uf2'),
    upstream_V163=dict(handoff=pin(parent/'HANDOFF.json'),seal=pin(parent/'FROZEN.json'),
        sealed_files=52,source_files=654,transitive_V161_required=True,
        scope='Parent52-file seal, all654 sources and its V161 seal/dependency trees remain immutable. Inherited statistics explicitly keep their parent ELF identity.'),
    authorization=dict(pause=pin(root/'.build/m0-math-paused-20261023/checkpoint.json'),
        resume=pin(root/'.build/m0-math-resumed-20261023/checkpoint.json'),
        scope='Human resumed the fixed offline V164 handoff stage. Old pause history retained; no new optimization versions, firmware rebuild, device access or Git mutation in this stage.'),
    only_changed_source='code/native_eabi_m0_asin.inc',changed_numeric_body='asin_checked',
    change='At relative endpoint exponent<=-13 the proven Q70 angle radius becomes2 instead of128. Approximation, tables and strict rounding-cell test retained; all other domains retain prior radius.',
    bound=dict(conservative_asin_Q70='11/8',conservative_negative_acos_Q70='15/8',returned_radius_Q70=2),
    exact_linked_symbol_body_records=validation['exact_linked_symbol_body_records'],
    equivalent_linked_fixup_symbol_records=len(validation['equivalent_linked_symbol_body_records']),
    equivalent_physical_wrappers=2,wrapper_alias_records=4,allocated_bytes_delta=32,
    new_tables=0,new_global_RAM=0,static_RAM_bytes=198856,heap_bytes=30520,scratch_bytes=4080,
    complete_scratch_bytes_identical=True,image_extent_bytes=1560704,libgcc_archive_members=0,
    M4_soft_and_hard_preprocessing_code_and_data_identical=True,generic_M0_code_and_data_identical=True,
    expanded174_groups=dict(faster=167,equal=2,slower=5,cases=30355),original117_groups=dict(faster=115,equal=2,slower=0),
    correct_reference_subsets=dict(nonempty_groups=155,empty_groups=19,mean_deficits=0,
        baseline_V163_distinct_slower_inputs=508,V164_distinct_slower_inputs=matrix['correct_reference_distinct_individual_slower_inputs'],
        resolved_inputs=matrix['resolved_individual_deficits'],introduced_inputs=matrix['introduced_individual_deficits']),
    raw_deficits=matrix['raw_deficits'],higher_means_vs_V163=matrix['groups_with_higher_mean_vs_V163'],
    changed_original_chunks=5,reexecuted_changed_original_cases=608,unchanged_original_chunks=114,
    changed_independent_groups=5,unchanged_independent_groups=48,
    qualified_V164_public_corpus_calls=public_cases,
    public_corpus_breakdown=dict(random_asin_acos=80140,endpoint_public=288044,inverse_midpoint_and_edge=173326,independent_domains=6784),
    oracle_scope='Directed MPFR-backed RNE references; negative asin endpoint references additionally use exact odd symmetry. Counts are calls, not unique inputs or an all-input proof.',
    actual_fixed_point_interval_checks=144022,endpoint_inputs=72011,endpoint_dirty_SIO_checks=125,
    additional_edge_dirty_SIO_public_calls=10,maximum_observed_edge_stack_bytes=edges['maximum_stack_bytes'],
    original_matrix_calls=23352,comparison_calls='608 old +608 new owned calls, plus608 pinned Qfplib calls; exact old/new stored digests reproduced.',
    inherited_V163_calls=dict(tiny_pow=196,cold_IEEE=51,pow_canaries=30,
        reason='Relevant linked bodies, tables/data and scratch are byte-identical; these are not fresh V164 calls.'),
    own_wrong_rounding_on_qualified_corpora=0,
    representative_change=dict(operation='asin',input_bits='3FEFFFFFFFFFFF9F',V163_instructions=7401,V164_instructions=2233,qfplib_instructions=2532),
    finite_case_regressions_retained=True,
    integration_contract=pin(work/'integration-contract.json'),math_only_review_patch=pin(work/'V163-to-V164-math-only.patch'),
    cumulative_component_inventory=pin(work/'math-component-manifest.json'),
    accepted_repaired_Pico_base_integrated=False,old_RAM_fault_resolved_by_this_math_candidate=False,
    remaining=['Five raw-mean deficits and507 distinct slower exact-reference inputs remain in the finite174-group matrix.',
        'General pow still traps on an undecided1024-bit enclosure; full-domain totality/correctness is not proved.',
        'Full float/FMA qualification and actual required-entry inventory remain open.',
        'Independent review and integration onto the accepted repaired Pico RAM/USB/preservation/M0-memory base are required; do not copy the old port wholesale.',
        'Physical cycle/cache/platform acceptance, hardware preservation/restoration gates and eventual release remain open.'],
    stage_result='Author V164 packet ready for independent review; no universal speed/correctness or hardware GO.',
    reproduction='Verify recursively, copy the complete source and producers to a fresh private directory, adjust output paths and use the pinned SDK/toolchain manifest. Existing image is historical offline qualification only; production integration follows integration-contract.json.',
    source_or_firmware_mutated_after_resume=False,hardware_accessed=False,physical_cycle_measurements_available=False,
    canonical_sources_changed=False,production_promoted=False,commit_created=False,pushed=False,
    general_pow_totality_proved=False,goal_complete=False)
(work/'HANDOFF.json').write_text(json.dumps(handoff,indent=2)+'\n');files.append(work/'HANDOFF.json')
(work/'FROZEN.json').write_text(json.dumps(dict(status='FROZEN_PRIVATE_V164_REVIEW_PACKET',
    files={str(p.relative_to(work)):sha(p) for p in sorted(files)},
    source_file_hashes='HANDOFF.json:654 files',
    scope='Fixed V164 author packet with complete174 merge, all per-case regressions and transitive V16352-file/V161 provenance. No hardware/release/all-input claim.',goal_complete=False),indent=2)+'\n')
print('FROZEN V164:',len(files),'files;',len(references),'explicit references;654 sources;V163/V161 retained;author review packet only.')
