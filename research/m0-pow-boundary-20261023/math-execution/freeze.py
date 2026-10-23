"""Freeze a complete math-stage contract for the separately owned transaction."""
import ast
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys
ROOT=Path.cwd();WORK=Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
load=lambda p:json.loads(Path(p).read_text())
cfg=load(WORK/'benchmark.json');artifacts=[];seen=set()
def add(path,role):
    path=Path(path).resolve()
    if path in seen:return
    assert path.is_file(),path
    artifacts.append(dict(path=str(path),sha256=sha(path),role=role));seen.add(path)
for name in ['TIMING.APP','TIMING.elf','TIMING.json','TIMING.bin','TIMING.rel','TIMING.map']:
    add(WORK/'app'/name,'math_APP')
for name in ['reference.elf','reference.bin','reference-sectors.bin','reference-only.uf2','reference.ld','reference.map']:
    add(WORK/'reference'/name,'separate_Flash_reference')
for chunk in cfg['chunks']+cfg['verification_canaries']:add(chunk['input'],'input_with_oracle')
for name in ['benchmark.json','oracle.json','canary-oracle.json','reference-proof.json','layout-proof.json',
             'path-coverage.json','app-self-test/result.json','TIMING-fixture.c','TIMING.c','prepare.py',
             'make-canaries.py','layout-proof.py','coverage.py','app-self-test.py','run-math.py','freeze.py','README.md',
             'freeze-helpers.py','frozen_helpers.py','helper-proof.json',
             'runner-self-test.py','runner-self-test/result.json']:
    add(WORK/name,'runner_config_source_evidence')
for file in sorted((WORK/'sources').iterdir()):
    if file.is_file():add(file,'frozen_source_or_prior_harness')
base=Path(cfg['firmware_elf']).parent
for name in ['mk61s-picocalc-pico-h.elf','mk61s-picocalc-pico-h.bin','mk61s-picocalc-pico-h.uf2','manifest.json']:
    add(base/name,'immutable_V138')
add(base.parent/'HANDOFF.json','immutable_V138_handoff')
add(cfg['bootrom'],'captured_BootROM')
for name in ['tools/build_portable_app.py','sdk/portable/start.c','sdk/portable/memory.c',
             'sdk/portable/shared_runtime.c','sdk/portable/system/runtime.S','sdk/portable/include/mk61_app.h',
             'code/loadable_app_api.h','code/loadable_app_services.h','code/loadable_system_runtime.def',
             'tests/hil_m0_math_compare.py','tests/hil_c5_stack.py','tests/hil_picocalc_apps.py',
             'tests/hil_picocalc_parity.py','tests/hil_portable_apps.py','tests/hil_rtc_alarm.py',
             'tests/hil_usb_disk_transaction.py','tests/hil_portable_system_apps.py',
             'tests/m0_mpfr_oracle.py','tests/native_eabi_m0_arm_self_test.py','tests/check_stm32_vectors.py']:
    frozen=WORK/'offline-dependencies'/name;frozen.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(ROOT/name,frozen)
    add(frozen,'frozen_offline_build_or_qualification_dependency')
for filename in ['device_settings.cpp']:
    add(base.parent/'source/ports/picocalc'/filename,'semantic_layout_dependency')
proof=load(WORK/'layout-proof.json');test=load(WORK/'app-self-test/result.json');coverage=load(WORK/'path-coverage.json')
assert proof['status'].startswith('PASS') and test['status']=='PASS' and coverage['all_required_paths_observed']
assert test['packed_APP_abi_kinds']==list(range(13)) and len(test['negative_guard_rejections'])==5
record=dict(schema_version=1,status='FROZEN_OFFLINE_MATH_EXECUTION_PACKAGE_NOT_HARDWARE_ACCEPTED',
    created_at=datetime.now(timezone.utc).isoformat(),
    target=dict(build='83CF4AC4',source_sha256=cfg['firmware_manifest']['source_sha256'],elf_sha256=cfg['elf_sha256']),
    artifacts=artifacts,ownedtemporarySDdirectories=[cfg['directory']],
    flash_addon=dict(base=0x10180000,end=0x10182000,bytes=8192,payload_bytes=6364,
        sector_size=4096,sectors=2,page_size=256,
        binpath=str(WORK/'reference/reference-sectors.bin'),sha256=sha(WORK/'reference/reference-sectors.bin'),
        code_binpath=str(WORK/'reference/reference.bin'),code_sha256=sha(WORK/'reference/reference.bin'),
        elf_path=str(WORK/'reference/reference.elf'),elf_sha256=sha(WORK/'reference/reference.elf'),
        uf2_path=str(WORK/'reference/reference-only.uf2'),uf2_sha256=sha(WORK/'reference/reference-only.uf2'),
        layoutproof=str(WORK/'layout-proof.json'),layoutproof_sha256=sha(WORK/'layout-proof.json'),
        firmware_crc_covers_addon=False,readback_required_before_APP=True,
        firmware_bytes_modified=0,undefined_imports=[],RAM_bytes=0),
    steps=[dict(id='math_matrix',runner=str(ROOT/'.build/picocalc-apps-arm-venv/bin/python'),
        cwd=str(ROOT),argv=[str(WORK/'run-math.py'),'--execute','--port','{port}','--uid','{uid}',
            '--output','{output}/math','--verified-flash','{output}/candidate-readback.bin',
            '--stop-file','{output}/STOP-MATH','--phase','matrix'],result_relative='math/result.json',max_seconds=2400,
        expected_result=dict(status='PASS',completed_chunks=119,completed_matrix_chunks=119,
            completed_verification_chunks=0,completed_cases=23352,supplementary_cases=0,
            temporary_directory_removed=True,calculator_data_preserved=True)),
        dict(id='changed_negative_factor_public_pow_canary',runner=str(ROOT/'.build/picocalc-apps-arm-venv/bin/python'),
        cwd=str(ROOT),argv=[str(WORK/'run-math.py'),'--execute','--port','{port}','--uid','{uid}',
            '--output','{output}/math-canary','--verified-flash','{output}/candidate-readback.bin',
            '--stop-file','{output}/STOP-MATH','--phase','canary'],result_relative='math-canary/result.json',max_seconds=120,
        expected_result=dict(status='PASS',completed_chunks=1,completed_matrix_chunks=0,
            completed_verification_chunks=1,completed_cases=0,supplementary_cases=30,
            temporary_directory_removed=True,calculator_data_preserved=True))],
    prerequisites=['Human consent and reviewer acceptance of the full transaction, including this separate diagnostic write span.',
        'Transaction owner captured fresh calculator/SD/RTC/IP trajectory and double fresh full Flash before any write.',
        'Raw cold/reset/crash/watchdog/BOOTSEL observations captured before this stage and before health/reset/retry/clear.',
        'Install exact V138 plus the explicitly separate reference sectors, preserving all outside affected erase sectors.',
        'Fresh full post-install 2MiB readback at {output}/candidate-readback.bin; base prefix and addon independently verified.',
        'USB ownership held by the transaction owner; same UID awake125MHz, command mode, idle, valid firmware CRC.'],
    expected=dict(matrix_groups=117,matrix_chunks=119,matrix_cases=23352,supplementary_chunks=1,
        supplementary_cases=30,total_APP_launches=120,rounds_per_APP=12,opposite_order_pairs=6,
        measure_batches_per_APP=48,total_measure_batches=5760,warmup_us_per_APP=1000000,
        raw_round_values_per_side=1440,performance_group_rows=117),
    duration=dict(estimated_seconds=[720,1200],step_timeout_seconds=2400,
        basis='Historical87 completed timing chunks took530 seconds wall time,111.9 seconds inside APP warmup/measurement;120 launches scale to about731 seconds before current USB/SD/IRQ variability. Allow12–20 minutes; this is an estimate, not V138 physical evidence.'),
    helper_closure=dict(path=str(WORK/'frozen_helpers.py'),sha256=sha(WORK/'frozen_helpers.py'),
        verified_before_import=True,project_imports=[],CWD_independent=True,
        proof=str(WORK/'helper-proof.json'),proof_sha256=sha(WORK/'helper-proof.json')),
    filesystem_guards=dict(structured_listing=True,complete_entry_count_required=True,
        casefold_file_and_directory_collisions_rejected=True,root_dot_dotdot_mutation_paths_rejected=True,
        parent_must_apply_same_collision_guard=True,proof=str(WORK/'runner-self-test/result.json')),
    canary_execution=dict(step_id='changed_negative_factor_public_pow_canary',
        executable_input=str(WORK/'inputs/119.bin'),oracle=str(WORK/'canary-oracle.json'),
        offline_coverage=str(WORK/'path-coverage.json'),all_required_paths_observed=True,
        factor64_multiply_offline_calls=coverage['paths']['factor64_multiply'],
        physical_receipt_required='{output}/math-canary/119.bin and result.json',
        physical_execution_done=False),
    cancellation=dict(stop_file='{output}/STOP-MATH',safe_point='between completed APP chunks',
        partial_exit_code=2,failure_exit_code=1,success_exit_code=0,
        checkpoint='math/checkpoint.json and math-canary/checkpoint.json',progress='math/progress.json and math-canary/progress.json',raw='Each stage: NNN.bin and NNN.guard.bin; decoded12 raw/calibration/cache rounds in NNN.json',
        resume='Explicit --resume requires same package SHA/UID and verified saved raw files; a new live SD directory is required. Parent must supply a new verified post-install full readback.',
        failure='Save raw transcript/status/crash/identity before recovery. No retry/reset/keys/BOOTSEL/flash from the math runner. Parent owns exact fresh restore in finally.',
        cleanup='Own SD directory only, on successful or cooperative-stop path; do not delete/recover on device failure.'),
    physical_cycle_scope=cfg['cycle_reporting'],interrupts='enabled; paired calibration and both-core XIP counters retained',
    acceptance_scope='Finite public API correctness and paired physical timing. A successful execution status does not assert faster/equal cycles, all-input correctness or general-pow totality.',
    general_pow_trap_still_open=True,goal_complete=False,hardware_accessed=False)
(WORK/'execution-manifest.json').write_text(json.dumps(record,indent=2)+'\n')
(WORK/'execution-manifest.sha256').write_text(sha(WORK/'execution-manifest.json')+'  execution-manifest.json\n')
print('FROZEN:',len(artifacts),'artifacts; manifestSHA',sha(WORK/'execution-manifest.json'))
