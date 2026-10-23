"""Freeze V145 offline evidence; preserve V144 and the approved V138 transaction."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import subprocess

root=Path.cwd();work=Path(__file__).resolve().parent
parent=root/'.build/m0-pow-small-y-stable-v144-20261023'


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def ref(p):
    return dict(path=str(Path(p).relative_to(root)),sha256=sha(p))


assert sha(parent/'HANDOFF.json')=='58656c2f71974bb55f1d11f56027e165d2262a13f7f2bbe008ca485f33c5b472'
assert sha(parent/'FROZEN.json')=='08ca5b11cd94d0f5628e1b5ad42851575eeca931e27ce4732aa4481e34459772'
parent_info=json.loads((parent/'HANDOFF.json').read_text())
approved=parent_info['approved_V138_package_hashes_unchanged']
for name,digest in approved.items():
    assert sha(root/name)==digest,name
names=dict(validation='validation.json',certificate='certificate.json',
    property='endpoint-property.json',qualification='endpoint-qualification.json',
    random='exp-random.json',matrix='instruction-matrix.json',independent='result.json',
    tiny='tiny-profile.json',expanded='extended-instruction-matrix.json',
    canary='public-canary.json',M4='m4-check/m4-isolation.json',generic_M0='generic-m0-isolation.json')
elf=work/'firmware/mk61s-picocalc-pico-h.elf'
assert sha(elf)=='209ac74c551923630300a4def7d017e90f2a69799bd4b800a8627955c16b5cf6'
reports={}
for label,name in names.items():
    d=json.loads((work/name).read_text())
    assert d['status'].startswith('PASS'),label
    for key in ('elf_sha256','owned_elf_sha256'):
        if key in d:
            assert d[key]==sha(elf),label
    reports[label]=d
assert reports['property']['cases']==176440
assert reports['property']['accepted']==68075 and reports['property']['declined']==108365
assert reports['qualification']['cases']==58302 and reports['qualification']['wrong_rounding']==0
assert reports['random']['operations']['exp']['cases']==40196
assert reports['matrix']['cases']==23352 and len(reports['matrix']['instruction_changes'])==3
assert reports['tiny']['cases']==196 and reports['independent']['cases']==6784
assert reports['canary']['cases']==30
assert reports['expanded']['cases']==30304
assert [reports['expanded']['instruction_groups_'+x] for x in ('faster','equal','slower')]==[156,2,13]
v=reports['validation']
assert v['unchanged_numerical_linked_functions']==248
assert len(v['only_equivalent_BL_relocated_functions'])==70
assert v['new_allocated_Flash_bytes']==392 and v['numerical_exp_calls_outside_public_entry']==[]
assert v['scratch_veneer_target_multiset_identical']
terminal=json.loads((work/'terminal-observations.json').read_text())
assert len(terminal['processes'])==12 and all(x['exit_code']==0 for x in terminal['processes'])
manifest=json.loads((work/'firmware/manifest.json').read_text())
assert manifest['build_id']=='8498b317'
assert manifest['source_sha256']=='707a7c880b92b3f03daf66fd7079cc214a63975bed7c2846ede0a68a0c2c976f'
source=work/'source'
actual={str(p.relative_to(source)):sha(p) for p in source.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
assert len(actual)==646 and actual==json.loads((work/'preparation.json').read_text())['source_file_hashes']
source_hash=hashlib.sha256()
for p in sorted([source/'tools/build_picocalc.py',source/'tools/seal_picocalc.py',
    *(p for folder in ('code','ports/picocalc','third_party/fatfs','third_party/core_math')
      for p in (source/folder).rglob('*') if p.is_file() and
      (p.suffix in ('.c','.cpp','.h','.hpp','.S','.inc','.ld','.pio') or p.name=='CMakeLists.txt'))]):
    source_hash.update(str(p.relative_to(source)).encode()+b'\0');source_hash.update(p.read_bytes())
assert source_hash.hexdigest()==manifest['source_sha256']
producers=['prepare.py','validate.py','certify.py','qualify-endpoints.py','domain-audit.py',
    'tiny-profile.py','extend-matrix.py','M4-isolation.py','generic-isolation.py','freeze.py','verify.py']
handoff=dict(status='FROZEN_PRIVATE_V145_QUALIFIED_NOT_HARDWARE_ACCEPTED',
    recorded_at=datetime.now(timezone.utc).isoformat(),candidate='V145',build='8498B317',
    parent='V144/4CA2268A',parent_handoff=ref(parent/'HANDOFF.json'),parent_seal=ref(parent/'FROZEN.json'),
    source_sha256=manifest['source_sha256'],source_file_count=646,
    preparation=ref(work/'preparation.json'),modified_vs_V144=v['modified_vs_V144'],
    elf=ref(elf),bin=ref(work/'firmware/mk61s-picocalc-pico-h.bin'),
    uf2=ref(work/'firmware/mk61s-picocalc-pico-h.uf2'),firmware_manifest=ref(work/'firmware/manifest.json'),
    reports={label:ref(work/name) for label,name in names.items()},
    producers={name:ref(work/name) for name in producers},terminal=ref(work/'terminal-observations.json'),
    retained_future_timing_vectors=ref(parent/'future-timing-corpus.json'),
    fresh_directed_MPFR_calls=58302+40196+6784+196,
    fresh_directed_MPFR_exp_calls=58302+40196+640,
    actual_ARM_integer_interval_cases=176440,accepted_integer_interval_cases=68075,
    declined_integer_interval_cases=108365,additional_original_matrix_cases=23352,
    additional_retained_oracle_canary_cases=30,own_wrong_rounding=0,
    negative_extreme_exp_128=dict(V144_instructions=3373.015625,
        V145_instructions=593.5703125,Qfplib_instructions=640.515625,Qfplib_wrong_cases=105),
    expanded171_groups=dict(faster=156,equal=2,slower=13,cases=30304),
    original117_groups=dict(faster=115,equal=2,slower=0,exp_groups_improve=3,other_chunk_records_exact=116),
    independent53_groups=dict(faster=40,equal=0,slower=13,exp_groups_improve=5,other_group_records_exact=48),
    all640_independent_exp_vectors_no_added_instructions=True,tiny196_case_records_identical=True,
    new_allocated_Flash_bytes_vs_V144=392,total_new_allocated_Flash_vs_V138=2260,
    exp_entry_delta_bytes=32,new_endpoint_helper_bytes=360,
    main_static_RAM_bytes=198856,heap_bytes=30520,scratch_bytes=4072,image_extent_bytes=1537400,
    new_tables=0,new_global_RAM=0,libgcc_archive_members=0,
    maximum_fresh_observed_exp_stack_bytes=reports['qualification']['maximum_observed_stack_bytes'],
    retained_parent_pow_stack_observation_bytes=2404,
    exp_entry_address_unchanged=True,old_other_exact_numerical_bodies=248,
    other_numerical_bodies_with_only_verified_equivalent_old_BL_relocations=70,
    other_numerical_object_instruction_and_data_payloads_identical=True,
    numerical_calls_to_public_exp_outside_entry=[],complete_scratch_code_byte_identical=False,
    scratch_veneer_target_multiset_identical=True,
    M4_soft_and_hard_preprocessing_code_and_data_identical=True,
    generic_M0_allocated_code_and_data_identical=True,
    approved_V138_package_hashes_unchanged=approved,
    canonical_sources_changed=False,hardware_accessed=False,production_promoted=False,commit_created=False,pushed=False,
    physical_cycle_measurements_available=False,
    hardware_authorization='Only V138/83CF4AC4 and pinned Qfplib are currently approved. V145 is not installed or substituted. /root/v138_hardware is the coordinated sole operator.',
    git_HEAD_at_freeze=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
    build_reproduction_argv=['.build/picocalc-apps-arm-venv/bin/python',str((source/'tools/build_picocalc.py').relative_to(root)),
        '--profile','picocalc-pico-h','--sdk',str(root/'.build/picocalc-deps/pico-sdk'),
        '--toolchain','/Users/bolk/Library/Arduino15/packages/STMicroelectronics/tools/xpack-arm-none-eabi-gcc/14.2.1-1.1/bin',
        '--build-path',str(work/'build'),'--output-dir',str(work/'firmware'),'--jobs','4'],
    reproduction_notice='Copy frozen artifacts and adjust output paths before rerunning writing producers. No command here requests USB/hardware execution.',
    previous_goal_turn='progress: V144 eliminated7 independent pow deficits and froze complete171-group evidence with14 raw deficits retained.',
    current_goal_turn='progress: V145 uses the existing exp enclosure to round gradual-underflow/overflow endpoints; eliminates the negative-extreme raw deficit, all640 new exp vectors no slower; all171 groups retained.',
    general_pow_undecided_1024_trap_retained=True,general_pow_totality_proved=False,
    remaining=['13 raw instruction-mean deficits and individual slow cases remain.',
        'Full-fractional pow loses on its16-vector correct-reference subset despite winning the raw mean.',
        'Physical cycles/cache performance, platform/cold/full-restoration acceptance are not established by offline evidence.',
        'General-pow termination beyond an undecided1024-bit interval remains unproved.',
        'V145 requires its own review and appropriate authorization before installation or promotion.'],goal_complete=False)
assert handoff['fresh_directed_MPFR_calls']==105478 and handoff['fresh_directed_MPFR_exp_calls']==99138
assert handoff['maximum_fresh_observed_exp_stack_bytes']==488
(work/'HANDOFF.json').write_text(json.dumps(handoff,indent=2)+'\n')
files=sorted(set(['HANDOFF.json','README.md','preparation.json','terminal-observations.json',
    *names.values(),*producers,'build.log','endpoint-qualification.log','exp-random.log',
    'domain-audit.log','matrix.log','M4.log','generic.log','tiny-profile.log','extended-matrix.log']))
(work/'FROZEN.json').write_text(json.dumps(dict(status='FROZEN_PRIVATE_V145_EVIDENCE',
    files={name:sha(work/name) for name in files},scope='Read-only qualification seal; no approved hardware packet is changed.',goal_complete=False),indent=2)+'\n')
print('PASS: frozen V145/8498B317;',len(files),'evidence files;105478 fresh MPFR calls;171 groups156/2/13; goal remains open.')
