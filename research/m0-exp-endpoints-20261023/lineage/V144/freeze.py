"""Freeze an offline candidate without promoting sources or accessing hardware."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

root = Path.cwd()
work = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def ref(path):
    return dict(path=str(Path(path).relative_to(root)), sha256=sha(path))


elf = work/'firmware/mk61s-picocalc-pico-h.elf'
manifest = json.loads((work/'firmware/manifest.json').read_text())
assert manifest['build_id'] == '4ca2268a'
assert manifest['source_sha256'] == 'a0bb69978f4a071c5cf60b90d7732d9b85f57edf8e51818920a9bde1c46fed26'
assert sha(elf) == 'ea22f818cac9f01690474d1ff27f752d26646b9a2e8fbbe5e6c4d0dea405ddde'
names = dict(validation='validation.json', certificate='certificate.json',
             upstream='upstream-pow-certificate.json', tiny='tiny-profile.json',
             small_qualification='small-qualification.json', argument='argument-property.json',
             matrix='instruction-matrix.json', expanded='extended-instruction-matrix.json',
             independent='result.json', affected='affected.json', random='pow-random.json',
             public_canary='public-canary.json', M4='m4-check/m4-isolation.json',
             generic_M0='generic-m0-isolation.json')
reports = {}
for label, name in names.items():
    d = json.loads((work/name).read_text())
    assert d['status'].startswith('PASS'), label
    for field in ('owned_elf_sha256', 'elf_sha256'):
        if field in d:
            assert d[field] == sha(elf), label
    reports[label] = d
assert reports['matrix']['instruction_changes'] == []
assert reports['affected']['cases'] == 75229 and reports['affected']['complete_corpus']
assert reports['random']['operations']['pow']['cases'] == 40395
assert reports['small_qualification']['cases'] == 39022
assert reports['tiny']['cases'] == 196
assert reports['argument']['cases'] == 15072
assert reports['public_canary']['cases'] == 30
assert [reports['expanded']['instruction_groups_'+k] for k in ('faster','equal','slower')] == [155,2,14]
assert reports['expanded']['cases'] == 30304 and len(reports['expanded']['newly_improved_groups']) == 7
assert reports['expanded']['original119_chunk_records_identical_V142']
v = reports['validation']
assert v['original_numerical_object_instructions_and_tables_identical']
assert v['unchanged_numerical_linked_functions'] == 250
assert len(v['only_equivalent_BL_relocated_numerical_functions']) == 66
assert len(v['only_linked_call_changes']) == 1
assert v['scratch_veneer_target_multiset_identical']
assert v['complete_scratch_code_byte_identical'] is False
assert v['new_allocated_Flash_bytes'] == 1868
terminal = json.loads((work/'terminal-observations.json').read_text())
assert len(terminal['processes']) == 13 and all(p['exit_code']==0 for p in terminal['processes'])

source = work/'source'
actual = {str(p.relative_to(source)):sha(p) for p in source.rglob('*')
          if p.is_file() and '__pycache__' not in p.parts}
assert actual == json.loads((work/'preparation.json').read_text())['source_file_hashes']
assert len(actual) == 646
source_hash = hashlib.sha256()
for p in sorted([source/'tools/build_picocalc.py', source/'tools/seal_picocalc.py',
                 *(p for folder in ('code','ports/picocalc','third_party/fatfs','third_party/core_math')
                   for p in (source/folder).rglob('*') if p.is_file() and
                   (p.suffix in ('.c','.cpp','.h','.hpp','.S','.inc','.ld','.pio') or p.name=='CMakeLists.txt'))]):
    source_hash.update(str(p.relative_to(source)).encode()+b'\0')
    source_hash.update(p.read_bytes())
assert source_hash.hexdigest() == manifest['source_sha256']

approved = {
    '.build/m0-pow-horner-final-v138-20261023/HANDOFF.json':'5492a7943e4d5bc00fd001e6f19853df05de547e66e74a82665ed13f854dae21',
    '.build/m0-pow-horner-final-v138-20261023/firmware/mk61s-picocalc-pico-h.elf':'f4010ce9153d8b9776b236751fcfe67da5e528c2bff5725f87478fec74a42895',
    '.build/m0-v138-execution-20261023/execution-manifest.json':'fd584f3e2b9a1387ff236eabdac66b888c452b16cb73c21449c6cb0b8262b18c',
    '.build/picocalc-v138-hil-20261023/EXECUTION-PACKAGE.json':'c53edcff67d5a31a587203c01b1e1aae4be5c3c235e0e224fe1b4d9f80489ff6',
    '.build/picocalc-v138-hil-20261023/plan.json':'bdeb5f59f594b93e68d5f3f997632d679da42996197b45c7619d66f7a41359b1',
    '.build/picocalc-v138-hil-20261023/pins.json':'bb584fa19cb54df06d7fce493df092e646ccaa2a305d78d5ebd2fb7aa38afc6c',
}
for name, digest in approved.items():
    assert sha(root/name) == digest, name

pow_audit_calls = sum(g['cases'] for g in reports['independent']['groups'] if g['operation']=='pow')
assert pow_audit_calls == 1408
compiler = '/Users/bolk/Library/Arduino15/packages/STMicroelectronics/tools/xpack-arm-none-eabi-gcc/14.2.1-1.1/bin'
producers = ['prepare.py','validate.py','certify.py','qualify-small.py','argument-property.py',
             'tiny-profile.py','domain-audit.py','extend-matrix.py','M4-isolation.py',
             'generic-isolation.py','freeze.py','verify.py']
handoff = dict(
    status='FROZEN_PRIVATE_V144_QUALIFIED_NOT_HARDWARE_ACCEPTED',
    recorded_at=datetime.now(timezone.utc).isoformat(), candidate='V144', build='4CA2268A',
    lineage='V138/83CF4AC4 -> V142/A2AF7297 -> exploratoryV143 -> V144/4CA2268A',
    source_sha256=manifest['source_sha256'], source_file_count=646,
    preparation=ref(work/'preparation.json'), modified_files=v['modified_vs_V138'], added_files=[],
    elf=ref(elf), bin=ref(work/'firmware/mk61s-picocalc-pico-h.bin'),
    uf2=ref(work/'firmware/mk61s-picocalc-pico-h.uf2'), firmware_manifest=ref(work/'firmware/manifest.json'),
    reports={label:ref(work/name) for label,name in names.items()},
    producers={name:ref(work/name) for name in producers},
    terminal_observations=ref(work/'terminal-observations.json'),
    future_timing_corpus=ref(work/'future-timing-corpus.json'),
    original117_groups=dict(faster=115,equal=2,slower=0,all119_chunk_records_identical_V142=True),
    expanded171_groups=dict(faster=155,equal=2,slower=14,cases=30304),
    newly_improved_groups=reports['expanded']['newly_improved_groups'],
    fresh_directed_MPFR_calls=75229+40395+39022+196+6784,
    fresh_directed_MPFR_pow_calls=75229+40395+39022+196+pow_audit_calls,
    actual_ARM_exact_integer_product_cases=15072, additional_public_canary_cases=30,
    own_wrong_rounding=0, new_allocated_Flash_code_bytes=1868,
    new_tables=0, new_global_RAM_bytes=0, libgcc_archive_members=0,
    main_static_RAM_bytes=198856, heap_bytes=30520, scratch_used_bytes=4072,
    image_extent_bytes=1537008, maximum_observed_pow_stack_bytes=2404,
    original_V138_observed_pow_stack_bytes=2252,
    original_numerical_object_payloads_identical=True, exact_old_numerical_linked_bodies=250,
    old_numerical_bodies_with_only_verified_equivalent_veneer_BL_relocations=66,
    original_function_addresses_and_sizes_identical=True, changed_old_cold_call_targets=1,
    complete_scratch_code_byte_identical=False, scratch_veneer_target_multiset_identical=True,
    M4_soft_and_hard_preprocessing_code_and_data_identical=True,
    generic_M0_allocated_code_and_data_identical=True,
    build_reproduction_argv=['.build/picocalc-apps-arm-venv/bin/python',
        str((source/'tools/build_picocalc.py').relative_to(root)), '--profile','picocalc-pico-h',
        '--sdk',str(root/'.build/picocalc-deps/pico-sdk'),'--toolchain',compiler,
        '--build-path',str(work/'build'),'--output-dir',str(work/'firmware'),'--jobs','4'],
    reproduction_notice='Copy the frozen package and adjust output paths before rerunning producers; the command is a reproduction recipe, not a new execution request.',
    approved_V138_package_hashes_unchanged=approved,
    hardware_accessed=False, physical_cycle_measurements_available=False,
    hardware_authorization='The direct local human grant names V138/83CF4AC4 and pinned Qfplib. V144 is not covered, installed or substituted. Coordinated /root/v138_hardware retains the device.',
    canonical_sources_changed=False, production_promoted=False, commit_created=False, pushed=False,
    git_HEAD_at_freeze=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
    previous_goal_turn='progress: frozen V142 eliminated inclusive2^-65 tiny-y deficit without changing existing numerical bodies.',
    current_goal_turn='progress: independent53-domain audit identified21 raw deficits; V144 eliminates7 while preserving all119 original chunk records; all expanded171 groups are retained including14 raw deficits.',
    general_pow_undecided_1024_trap_retained=True, general_pow_totality_proved=False,
    remaining=['14 raw-mean instruction deficits and additional individual slow cases remain in the independent audit.',
               'Full-fractional pow also loses on the16-case correct-reference subset despite winning its raw mean.',
               'Physical cycle/cache measurements and platform/cold/full-restoration acceptance remain with the coordinated V138 operator.',
               'A terminating correctly rounded general-pow path beyond an undecided1024-bit enclosure is unproved.',
               'Installing or promoting V144 requires its own independent review and appropriate authorization.'],
    goal_complete=False)
assert handoff['fresh_directed_MPFR_calls'] == 161626
assert handoff['fresh_directed_MPFR_pow_calls'] == 156250
(work/'HANDOFF.json').write_text(json.dumps(handoff,indent=2)+'\n')
files = ['HANDOFF.json','README.md','preparation.json','terminal-observations.json',
         'future-timing-corpus.json','ARGCHECK.cpp','ARGCHECK.elf',
         'build-first-tail-name-failure.log','argument-first-ABI-mask-failure.log',
         'validate-initial-strict.py',*names.values(),*producers]
files = sorted(set(files))
seal = dict(status='FROZEN_PRIVATE_V144_EVIDENCE',files={name:sha(work/name) for name in files},
            source_files_sha256='See preparation.json for all646 exact source files.',
            scope='Read-only qualification seal; no approved hardware packet is changed.',goal_complete=False)
(work/'FROZEN.json').write_text(json.dumps(seal,indent=2)+'\n')
print('PASS: frozen V144/4CA2268A;',len(files),'evidence files;161626 fresh MPFR calls; expanded171 groups155/2/14; goal remains open.')
