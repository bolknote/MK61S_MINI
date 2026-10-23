"""Preserve the zero-deficit finite software gate without claiming hardware/totality."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
root=Path.cwd();work=Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
load=lambda p:json.loads(Path(p).read_text())
artifact=lambda p:dict(path=str(Path(p).relative_to(root)),sha256=sha(p))
manifest=load(work/'firmware/manifest.json');elf=work/'firmware/mk61s-picocalc-pico-h.elf'
reports={}
for name,path in [('all12','all12.json'),('affected_pow','affected.json'),('extra_endpoints','endpoints.json'),
                  ('raw_endpoints','raw-endpoints.json'),('retained128_states','cores.json'),
                  ('certificate','certificate.json'),('GNU_reference','gnu-equivalence.json'),
                  ('source_kernel_resources','validation.json'),('source_scope','source-scope.json'),
                  ('M4_isolation','m4-check/m4-isolation.json'),('generic_M0_isolation','generic-m0-isolation.json'),
                  ('matrix','instruction-matrix.json'),('profile','profile.json'),('cache','cache-probe.json'),
                  ('runtime','runtime-memory.json')]:
    p=work/path;report=load(p);assert report['status'].startswith('PASS'),name
    if 'elf_sha256' in report:assert report['elf_sha256']==sha(elf),name
    reports[name]=artifact(p)
matrix=load(work/'instruction-matrix.json');all12=load(work/'all12.json');affected=load(work/'affected.json')
assert matrix['owned_elf_sha256']==sha(elf) and matrix['owned_wrong_rounding']==0
assert [matrix['instruction_groups_faster'],matrix['instruction_groups_equal'],matrix['instruction_groups_slower']]==[115,2,0]
assert sum(r['cases'] for r in all12['operations'].values())==494206
assert affected['cases']==75229 and affected['complete_corpus'] and affected['wrong_rounding']==0
terminal=load(work/'qualification-terminal.json')
assert len(terminal)==11 and all(r['exit_code']==0 for r in terminal)
scope=load(work/'source-scope.json');validation=load(work/'validation.json');certificate=load(work/'certificate.json')
assert scope['current_source_sha256']==manifest['source_sha256']
assert len(scope['bases']['V122']['modified'])==5 and not scope['bases']['V122']['added']
assert len(scope['bases']['final_2EABB2A2']['modified'])==15 and len(scope['bases']['final_2EABB2A2']['added'])==7
assert scope['unchanged_non_math']['count']==568
assert validation['additional_immutable_Root64_identity_bytes']==0
cache=load(work/'cache-probe.json');assert len(cache['groups'])==19
assert all(r['elf_sha256']==sha(elf) for r in cache['groups'])
hard=[dict(stream=r['stream'],cases=r['cases'],mean_instructions=r['mean_instructions'],qfplib_wrong_results=r['qfplib_wrong_results'])
      for r in matrix['chunks'] if r['stream'].startswith('hard_pow_')]
prior=load(root/'.build/m0-pow-root-prefix-v122-20261023/instruction-matrix.json')
for row in hard:
    old=next(r for r in prior['chunks'] if r['stream']==row['stream'])
    row['V122_mean_instructions']=old['mean_instructions']['own']
    row['reduction_vs_V122_percent']=100*(old['mean_instructions']['own']-row['mean_instructions']['own'])/old['mean_instructions']['own']
sys.path.insert(0,str(root/'tests'));from check_stm32_vectors import ElfImage
def allocated(path):
    e=ElfImage(path)
    return sum(s[5] for s in e.sections if s[2]&2 and s[1]!=8 and 0x10000000<=s[3]<0x10200000)
before_path=root/'.build/m0-pow-root-prefix-v122-20261023/firmware/mk61s-picocalc-pico-h.elf'
allocated_now,allocated_before=allocated(elf),allocated(before_path)
state=load(root/'.build/m0-pow-checkpoint-20261023/pre-commit-state.json')
head=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
assert head=='5d682046fa30046771a744ef5dd63e96d8cf1637'
assert not subprocess.check_output(['git','diff','--cached','--name-only'],text=True).strip()
assert all(sha(root/name)==digest for name,digest in state['tracked_dirty'].items())
producers={name:artifact(work/name) for name in ['prepare.py','certify.py','validate.py','endpoints.py','compare-cores.py','preserve-scope.py','cache-probe.py','M4-isolation.py','generic-isolation.py','preserve-handoff.py']}
external={name:artifact(root/name) for name in ['tests/qualify_m0_rounding.py','tests/qualify_m0_pow_worst.py',
    'tests/profile_m0_math_matrix.py','tests/native_eabi_m0_arm_self_test.py','tests/m0_mpfr_oracle.py',
    'tests/picocalc_memory_arm_self_test.py','research/m0-pow-root-prefix-20261023/raw-arm.py',
    'research/m0-pow-integer64-20261023/profile-hard.py']}
record=dict(status='PASS_FINITE_SOFTWARE_RESEARCH_GATE_NOT_PROMOTED',candidate='V138',build=manifest['build_id'].upper(),
    source_sha256=manifest['source_sha256'],elf=artifact(elf),bin=artifact(work/'firmware/mk61s-picocalc-pico-h.bin'),
    uf2=artifact(work/'firmware/mk61s-picocalc-pico-h.uf2'),manifest=artifact(work/'firmware/manifest.json'),
    patch=scope['patch'],scopes=scope['bases'],regular_source_files=646,unchanged_non_math=scope['unchanged_non_math'],
    reports=reports,producers=producers,external_producers=external,terminal_jobs=artifact(work/'qualification-terminal.json'),
    fresh_all12_cases=494206,fresh_selected_pow_cases=75229,fresh_matrix_cases=23352,
    instruction_groups=dict(faster=115,equal=2,slower=0),hard_streams=hard,
    pow_reference='Pinned Qfplib exp(mul(y,ln(x))) composition; there is no standalone pow in that reference.',
    fresh_extra_endpoints=load(work/'endpoints.json'),fresh_retained128_states=load(work/'cores.json')['counts'],
    algorithm='Positive fractions use a Horner ladder: a root followed by an exact-base product for each set numerator bit. Proper negative fractions retain the bounded inverse-root ladder. Full128-bit numerator construction is lazy and strict ambiguous cases retain exact midpoint refinement.',
    raw_root_point_error_bound=certificate['raw_root_total_point_error_bound'],raw_root_radius=3,
    positive_horner_radius_bound=certificate['positive_horner_radius_maximum'],negative_factor_radius_bound=certificate['negative_factor_radius_maximum'],
    new_arithmetic_tables=0,additional_global_RAM_bytes=0,additional_identity_literal_bytes=0,
    static_main_RAM_bytes=198856,heap_bytes=30520,scratch_used_bytes=4072,scratch_reserved_bytes=4096,
    image_extent_bytes=1537008,allocated_XIP_bytes=allocated_now,V122_allocated_XIP_bytes=allocated_before,
    allocated_XIP_delta_bytes=allocated_now-allocated_before,linked_libgcc_archive_members=0,new_compiler_dependency=False,
    unchanged_non_pow_linked_bodies=206,unchanged_full_numerical_object_payloads=4,
    cache_assumptions=cache['assumptions'],cache_scope=cache['scope'],cache_vs_V122=cache['differences_vs_V122'],
    cache_interpretation='The four models still show more misses than V122 in the two hard streams. Fewer instructions do not prove physical cycle parity; on-device measurements remain required.',
    remaining=['Physical cycle parity against Qfplib on the actual PicoCalc, including XIP/ROM/SIO effects.',
               'Complete hardware acceptance of the full22-path delta from the final2EABB2A2 platform and production promotion.',
               'General pow totality: the final undecided1024-bit path still traps. Finite successful tests and the new guarded fast paths do not prove all-input correctness/termination.'],
    full_million_scope='The older full1,003,177-case run belongs to V86. This exact ELF has a fresh complete75,229-case affected-subset run, not a new full-million run.',
    physical_timing_available=False,hardware_ready=False,hardware_accessed=False,USB_ownership_transferred=False,
    root_promoted=False,commit_created=False,pushed=False,git_head=head,unrelated_tracked_hashes_preserved=len(state['tracked_dirty']),
    index_empty=True,goal_complete=False)
(work/'HANDOFF.json').write_text(json.dumps(record,indent=2)+'\n')
print('PASS: V138',record['build'],'115/2/0 finite instruction gate; all11 jobs terminal; source646 files; side WIP37 and empty index preserved.',flush=True)
