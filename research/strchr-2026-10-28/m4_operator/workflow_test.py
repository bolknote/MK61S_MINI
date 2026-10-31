#!/usr/bin/env python3
"""HOST-only binding negatives and real subprocess/lock lifecycle checks.

All synthetic Go/lease receipts are created inside this test output directory.
They are labelled HOST fixtures and confer no authority for physical I/O.
"""
import argparse
import copy
import json
import os
from pathlib import Path
import sys

from prepare import pin
from supervisor import ExistingLease, fd_numbers, run_once
from workflow import (COORDINATOR, THIS_CHAT, ROLES, canonical_sha, make_workflow,
                      validate_binding)


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')
    return pin(path)


def reject(fn):
    try:
        fn()
    except (ValueError, BlockingIOError, FileNotFoundError):
        return 1
    raise AssertionError('negative guard unexpectedly accepted')


def binding_checks(output, workflow_path):
    """Exercise semantic guards after re-signing only a HOST test receipt."""
    fixture = output / 'HOST_FIXTURES_NOT_A_GRANT'
    fixture.mkdir(mode=0o700)
    dummy = fixture / 'dummy.txt'; dummy.write_text('HOST fixture only\n')
    full = fixture / 'fake_full512KiB.bin'; full.write_bytes(bytes(512*1024))
    closed = [write_json(fixture / ('predecessor%d.json' % i),
                        dict(status='CLOSED', accepted_by=COORDINATOR, scope=scope, HOST_ONLY=True))
              for i, scope in enumerate(['Bytecode', 'MK85 Runner'])]
    context = dict(status='CAPTURED_AND_RESTORABLE', accepted_by=COORDINATOR, files=True,
                   cache=True, typed_state=True, RTC=True, reset_authority=True, HOST_ONLY=True)
    reset = write_json(fixture / 'reset.json', context)
    lease = dict(owner=THIS_CHAT, scope='strchr-M4', window_id='HOST-ONLY', token='HOST-ONLY',
                 starts_unix=100, expires_unix=1000, HOST_ONLY=True)
    lease_ref = write_json(fixture / 'lease.json', lease)
    python = pin(Path(sys.executable).resolve())
    adapters = {role: dict(argv_template=[python['path'], '--binding', '{binding}', '--job', '{job}'],
                           pins=[python]) for role in ROLES}
    binding = dict(status='ROOT_ACCEPTED_STRCHR_M4_BINDING', hardware_GO=True, executor=THIS_CHAT,
        workflow=pin(workflow_path), actual_full_snapshot=pin(full), profile=pin(dummy), source_manifest=pin(dummy),
        reset_context_receipt=reset, lease=lease_ref, window_id='HOST-ONLY', lease_token='HOST-ONLY',
        public_id='0011223344556677', sys_hz=96000000, power_mode='HOST', IRQ_context='HOST', cache_context='HOST',
        context=[1,2,3,4,5,6], predecessors=closed, return_reserve_seconds=300, adapters=adapters)

    def sign(value):
        value = copy.deepcopy(value)
        value.pop('authority', None)
        value['authority'] = write_json(fixture / 'HOST_authority_fixture.json',
            dict(status='ACCEPTED_EXACT_GO', coordinator=COORDINATOR, window_id=value.get('window_id'),
                 binding_payload_sha256=canonical_sha(value), HOST_ONLY=True))
        return value

    assert validate_binding(sign(binding), workflow_path, now=200)['physical_IO'] == 0
    negative = 0
    for key, value in [('status', 'HOST_WORKFLOW_NO_DEVICE_GO'), ('hardware_GO', False), ('executor', 'wrong'),
                       ('actual_full_snapshot', pin(dummy)), ('public_id', 'unknown'), ('sys_hz', 48000000),
                       ('power_mode', None), ('IRQ_context', ''), ('cache_context', ''), ('context', []),
                       ('predecessors', closed[:1]), ('lease_token', 'wrong'), ('window_id', 'wrong'),
                       ('return_reserve_seconds', 0), ('adapters', {}), ('profile', None)]:
        changed = copy.deepcopy(binding); changed[key] = value
        negative += reject(lambda changed=changed: validate_binding(sign(changed), workflow_path, now=200))
    negative += reject(lambda: validate_binding(sign(binding), workflow_path, now=99))
    negative += reject(lambda: validate_binding(sign(binding), workflow_path, now=701))
    for ref, obj, key, value in [
            (closed[0], dict(status='CLOSED', accepted_by=COORDINATOR, scope='Bytecode'), 'status', 'CLOSED_HOLD'),
            (reset, context, 'typed_state', False), (reset, context, 'reset_authority', False),
            (lease_ref, lease, 'owner', 'another chat')]:
        changed = copy.deepcopy(binding)
        bad = dict(obj); bad[key] = value
        bad_ref = write_json(fixture / 'bad-receipt.json', bad)
        if ref == closed[0]: changed['predecessors'][0] = bad_ref
        elif ref == reset: changed['reset_context_receipt'] = bad_ref
        else: changed['lease'] = bad_ref
        negative += reject(lambda: validate_binding(sign(changed), workflow_path, now=200))
    changed = copy.deepcopy(binding)
    changed['adapters']['return']['argv_template'][-1] = '{unknown}'
    negative += reject(lambda: validate_binding(sign(changed), workflow_path, now=200))
    changed = sign(binding)
    changed['public_id'] = '8899AABBCCDDEEFF'
    negative += reject(lambda: validate_binding(changed, workflow_path, now=200))
    return dict(semantic_negative_guards=negative, physical_IO=0,
                HOST_receipts_never_used_for_execution=True)


def processes(output):
    env = dict(PATH='/usr/bin:/bin', LANG='C', PYTHONDONTWRITEBYTECODE='1')
    python = str(Path(sys.executable).resolve())
    programs = [
        ('normal', 'import json,os,time; print(json.dumps(dict(pid=os.getpid(),pgid=os.getpgid(0),sid=os.getsid(0)))); time.sleep(.05)', 2, 1048576),
        ('exit7', 'import sys,time; print("first fault",file=sys.stderr); time.sleep(.05); sys.exit(7)', 2, 1048576),
        ('timeout', 'import time; time.sleep(20)', .15, 1048576),
        ('log-limit', 'import sys,time; sys.stdout.write("x"*4096); sys.stdout.flush(); time.sleep(.1)', 2, 1024),
        ('stray-child', 'import subprocess,sys,time; p=subprocess.Popen([sys.executable,"-c","import time;time.sleep(20)"]); print(p.pid,flush=True); time.sleep(.05)', 2, 1048576)]
    records = []
    initial_fds = fd_numbers()
    for name, code, seconds, limit in programs:
        record = run_once([python, '-B', '-c', code], output / name,
                          cwd=output, env=env, timeout_seconds=seconds, max_log_bytes=limit)
        assert record['attempts'] == 1 and record['reaped'] and record['group_gone'], record
        assert record['parent_fds_before'] == record['parent_fds_after'] == initial_fds
        assert (record['status'] == 'PASS_PROCESS_EXIT') == (name == 'normal'), record
        if name == 'normal':
            child = json.loads((output / name / 'stdout.bin').read_text())
            assert child == dict(pid=record['pid'], pgid=record['process_group'], sid=record['session_id'])
            assert record['EXIT'] == 0
        if name == 'exit7': assert record['EXIT'] == 7
        records.append(pin(output / name / 'PROCESS.json'))
        print(name, record['status'], 'EXIT', record['EXIT'], 'reaped/group gone', flush=True)
    lease = output / 'HOST-test-existing-lease.json'
    lease.write_text('{"HOST_ONLY":true}\n')
    ref = pin(lease)
    with ExistingLease(lease, ref) as held:
        assert held.evidence['acquired']
        assert reject(lambda: ExistingLease(lease, ref).__enter__()) == 1
    assert held.evidence['released'] and held.evidence['fd_closed'] and held.evidence['same_inode']
    assert pin(lease) == ref and fd_numbers() == initial_fds
    (output / 'LEASE.json').write_text(json.dumps(held.evidence, indent=2) + '\n')
    assert reject(lambda: ExistingLease(output / 'does-not-exist', ref).__enter__()) == 1
    return dict(real_process_cases=len(records), records=records, existing_lease=pin(output / 'LEASE.json'),
                first_fault_no_retry=True, parent_fds_preserved=True, all_children_reaped=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--build', type=Path, required=True)
    p.add_argument('--output-dir', type=Path, required=True)
    args = p.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=False)
    workflow = make_workflow(args.build)
    path = args.output_dir / 'WORKFLOW.json'
    write_json(path, workflow)
    assert len(workflow['jobs']) == 473 and workflow['ordinary_timed_APP_runs'] == 464
    timed = [x for x in workflow['jobs'] if x['phase'] == 'measure_once']
    for mode in ['standalone-sram','standalone-flash','shared-sram','shared-flash']:
        cases = [i for x in timed if x['mode'] == mode for i in range(x['request']['first'], x['request']['first'] + x['request']['count'])]
        assert cases == list(range(1152))
    result = dict(status='PASS_HOST_WORKFLOW_GUARDS_AND_PROCESS_LIFECYCLE', physical_IO=0,
                  binding=binding_checks(args.output_dir, path), processes=processes(args.output_dir),
                  workflow=pin(path), hardware_GO=None, physical_speed_claim=False,
                  sources=[pin(Path(__file__)), pin(Path(__file__).with_name('workflow.py')), pin(Path(__file__).with_name('supervisor.py'))])
    result_path = args.output_dir / 'RESULTS.json'
    write_json(result_path, result)
    print(json.dumps(pin(result_path)))


if __name__ == '__main__':
    main()
