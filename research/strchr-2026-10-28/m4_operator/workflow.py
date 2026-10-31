#!/usr/bin/env python3
"""Generate a finite HOST workflow and reject incomplete physical bindings.

There is deliberately no device execution command before the actual release
and supplier acceptance. No serial, USB, flash or RTC helper is imported here.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import time

from build import load_template
from prepare import pin

COORDINATOR = '01a164b7-9caa-7011-90d1-807e9630921c'
THIS_CHAT = '01a17a32-c316-7880-86b9-969da392543c'
ROLES = ['capture', 'flash_readback', 'app_files', 'app_once_readback', 'cleanup', 'return']


def canonical_sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def checked(condition, reason):
    if not condition:
        raise ValueError(reason)


def verify_pin(ref):
    checked(isinstance(ref, dict) and set(ref) == {'path', 'bytes', 'sha256'}, 'exact file pin required')
    checked(Path(ref['path']).is_absolute() and pin(Path(ref['path'])) == ref, 'file pin changed')


def make_workflow(build_path):
    build = json.loads(build_path.read_text())
    verify_pin(build['template'])
    template = load_template(Path(build['template']['path']))
    for app in build['apps']:
        verify_pin(app['APP']); verify_pin(app['ELF'])
    jobs = []

    def add(phase, role, seconds, **fields):
        jobs.append(dict(sequence=len(jobs), phase=phase, role=role, attempts=1,
                         timeout_seconds=seconds, **fields))

    add('capture_original', 'capture', 240, requires=['actual identity and profile', 'fresh full512KiB readback',
        'files including owned-name absence', 'cache/typed context explicitly restorable', 'RTC/elapsed baseline',
        'source-backed permission for any required reset'], reset_allowed=False)
    add('install_carrier_and_full_readback', 'flash_readback', 240,
        transform='overlay_snapshot: exact sealed prefix + erased destination only',
        fixture=template['fixture'], fixture_base=template['fixture_base'],
        readback='full512KiB equals derived overlay; unchanged resident/footer/runtime18',
        reset_requires='accepted capture receipt and exact reset/RTC return supplier')
    add('install_owned_apps', 'app_files', 180, namespace=template['root_namespace'],
        apps=[dict(mode=x['mode'], APP=x['APP']) for x in build['apps']],
        write_readback_before_open=True, replace_foreign=False)
    for app in build['apps']:
        add('qualify_timer', 'app_once_readback', 30, mode=app['mode'], APP=app['APP'],
            request=dict(mode=0, batch=0), raw_report_bytes=3584,
            may_run_APP=1, readback_must_not_run_APP=True,
            accept='wire.parse_report + identical bound clock/power/IRQ/cache context; DWT vs wall timer')
    for app in build['apps']:
        for batch in range(template['timed_APP_runs_per_mode']):
            first = batch * template['rows_per_APP_run']
            add('measure_once', 'app_once_readback', 30, mode=app['mode'], APP=app['APP'],
                request=dict(mode=1, batch=batch, first=first, count=min(10, 1152-first)),
                context='exact accepted qualification, frozen before first timing',
                raw_report_bytes=3584, may_run_APP=1, readback_must_not_run_APP=True,
                on_fault='save entire raw report and first error; stop remaining jobs; no replay/resizing')
    add('cleanup_owned', 'cleanup', 180, namespace=template['root_namespace'],
        remove_only_if_byte_and_inode_match=True, cache_release='source-backed accepted supplier only',
        original_files_byte_exact=True)
    add('return_original', 'return', 300, full_firmware='fresh accepted full512KiB original',
        compare=['physical full image', 'files', 'cache', 'typed context', 'RTC/elapsed', 'clock/power',
                 'known terminal exit', 'supplier process EXIT/reap/group/FD/lock'],
        status='RETURN_VERIFIED_AWAIT_INDEPENDENT_CLOSED')
    return dict(schema=1, status='HOST_WORKFLOW_NO_DEVICE_GO', build=pin(build_path), template=build['template'],
        jobs=jobs, ordinary_timed_APP_runs=sum(x['phase']=='measure_once' for x in jobs),
        qualification_APP_runs=4, cases_per_mode=1152, functions=11, rounds=7,
        raw_intervals=1152*4*11*7, report_bytes=3584, maximum_APP_load_bytes=max(x['report']['memory_bytes'] for x in build['apps']),
        process_primitive='supervisor.run_once; explicit argv, shell=False, own session, one attempt, saved EXIT/reap/FD/lock',
        argv_template=['{pinned_python}', '{accepted_role_adapter}', '--binding', '{accepted_binding_json}', '--job', '{immutable_job_json}'],
        stop_policy='Any first fault -> HOLD. No later measurement. Only separately preaccepted finite return, or coordinator recovery Go.',
        independent_close='Root must verify actual return/proofs and issue CLOSED; executor cannot self-certify',
        physical_unbound=['predecessor release', 'actual image/profile/context', 'role adapters and dependencies',
            'RTC/nonexportable-context preservation', 'exact argv', 'finite lease', 'fresh coordinator Go'],
        physical_IO=0, hardware_GO=None, winner=None)


def validate_binding(binding, workflow_path, now=None):
    """Pure HOST guard, called before lock access/process creation/physical I/O.

    This establishes consistency, not authority by itself. The referenced Go
    must also be the actual message/receipt independently accepted by Root.
    It cannot convert this HOST template or a locally fabricated JSON into Go.
    """
    now = time.time() if now is None else now
    checked(binding.get('status') == 'ROOT_ACCEPTED_STRCHR_M4_BINDING', 'fresh accepted physical binding required')
    checked(binding.get('hardware_GO') is True and binding.get('executor') == THIS_CHAT, 'wrong/no hardware Go or executor')
    verify_pin(binding.get('workflow'))
    checked(binding['workflow'] == pin(workflow_path), 'Go is for a different workflow')
    for label in ['actual_full_snapshot', 'profile', 'source_manifest', 'reset_context_receipt', 'lease', 'authority']:
        verify_pin(binding.get(label))
    checked(binding['actual_full_snapshot']['bytes'] == 512*1024, 'full original512KiB required')
    checked(re.fullmatch(r'[A-F0-9]{16}', binding.get('public_id', '')), 'actual device identity missing')
    checked(binding.get('sys_hz') == 96000000 and all(binding.get(x) for x in ['power_mode', 'IRQ_context', 'cache_context']),
            'actual clock/power/IRQ/cache must be bound')
    ctx = binding.get('context')
    checked(isinstance(ctx, list) and len(ctx) == 6 and any(ctx) and all(type(x) is int and 0 <= x <= 0xffffffff for x in ctx),
            'six actual clock/cache/FPU words required')
    closed = binding.get('predecessors')
    checked(isinstance(closed, list) and len(closed) == 2, 'both predecessor CLOSED receipts required')
    for item, expected_scope in zip(closed, ['Bytecode', 'MK85 Runner']):
        verify_pin(item)
        receipt = json.loads(Path(item['path']).read_text())
        checked(receipt.get('status') == 'CLOSED' and receipt.get('accepted_by') == COORDINATOR and
                receipt.get('scope') == expected_scope, 'predecessor not independently CLOSED; HOLD cannot be waived')
    reset = json.loads(Path(binding['reset_context_receipt']['path']).read_text())
    checked(reset.get('status') == 'CAPTURED_AND_RESTORABLE' and reset.get('accepted_by') == COORDINATOR and
            all(reset.get(x) for x in ['files', 'cache', 'typed_state', 'RTC', 'reset_authority']),
            'reset/nonexportable context return is unbound')
    lease = json.loads(Path(binding['lease']['path']).read_text())
    checked(lease.get('owner') == THIS_CHAT and lease.get('scope') == 'strchr-M4' and
            lease.get('window_id') == binding.get('window_id') and lease.get('token') == binding.get('lease_token'), 'wrong lease')
    checked(lease.get('starts_unix', now+1) <= now < lease.get('expires_unix', 0)-binding.get('return_reserve_seconds', 0),
            'lease not active or insufficient return reserve')
    checked(300 <= binding.get('return_reserve_seconds', 0) <= 1800, 'explicit bounded return reserve required')
    adapters = binding.get('adapters', {})
    checked(set(adapters) == set(ROLES), 'all exact physical/RTC/readback/return suppliers required')
    for role in ROLES:
        spec = adapters[role]
        argv = spec.get('argv_template')
        checked(isinstance(argv, list) and len(argv) >= 2 and Path(argv[0]).is_absolute() and
                argv[-4:] == ['--binding', '{binding}', '--job', '{job}'] and
                all(type(x) is str and '\0' not in x and ('{' not in x or x in ('{binding}', '{job}')) for x in argv),
                'exact argv template required')
        checked(bool(spec.get('pins')), 'supplier dependencies missing')
        for ref in spec['pins']:
            verify_pin(ref)
        checked(argv[0] in [x['path'] for x in spec['pins']], 'executable not pinned')
    authority = json.loads(Path(binding['authority']['path']).read_text())
    payload = {k: v for k, v in binding.items() if k != 'authority'}
    checked(authority.get('status') == 'ACCEPTED_EXACT_GO' and authority.get('coordinator') == COORDINATOR and
            authority.get('window_id') == binding.get('window_id') and
            authority.get('binding_payload_sha256') == canonical_sha(payload), 'authority does not cover exact binding/argv')
    return dict(status='CONSISTENT_BINDING_REQUIRES_ACTUAL_ROOT_AUTHORITY', physical_IO=0)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--build', type=Path, required=True)
    p.add_argument('--output-dir', type=Path, required=True)
    a = p.parse_args()
    result = make_workflow(a.build)
    a.output_dir.mkdir(parents=True, exist_ok=False)
    output = a.output_dir / 'WORKFLOW.json'
    output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(dict(workflow=pin(output), jobs=len(result['jobs']), physical_IO=0)))


if __name__ == '__main__':
    main()
