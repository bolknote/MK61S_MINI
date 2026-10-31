#!/usr/bin/env python3
"""Seal the explicit offline join of independently reviewed V3 and adapter V2."""
import argparse
import json
from pathlib import Path
import shutil

import bind as B


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tests', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    require = B.require
    require(not output.exists(), 'Use a new directory; sealed packets are never overwritten')
    source = Path(__file__).resolve().parent
    tests = args.tests.resolve()
    report = B.read_json(tests / 'report.json')
    require(report['status'] == 'PASS_FOCUSED_OFFLINE_BINDING', 'Focused binding tests did not pass')
    require(not report['hardware_verified'] and report['hardware_constructor_calls'] == 0, 'Unexpected hardware scope')
    require(not report['mathematical_matrix_repeated'] and not report['adapter_legacy_selector_called'], 'Unexpected join scope')
    require(len(report['decoder_negative_cases']) == 8 and len(report['lifecycle_cases']) == 4 and
            len(report['cli_hold_cases']) == 2 and len(report['pin_rejection_cases']) == 3, 'Incomplete join checks')
    for name, digest in report['source_sha256'].items():
        require(B.sha(source / name) == digest, 'Tested binding source changed: ' + name)
    bound = B.BoundSet()
    require(report['math_manifest_sha256'] == B.MATH_SHA and report['adapter_manifest_sha256'] == B.ADAPTER_SHA,
            'Wrong tested inputs')
    template = B.read_json(source / 'bindings.template.json')
    require(all(template[name] is None for name in B.PROVIDERS) and template['accepted_repaired_base'] is None,
            'Do not enable hardware in this offline packet')
    output.mkdir(parents=True)

    def copy(original, relative):
        destination = output / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(original, destination)

    for folder, manifest, filename, destination in (
        (bound.math, bound.math_manifest, 'packet-manifest.json', 'math'),
        (bound.adapter_root, bound.adapter_manifest, 'adapter-manifest.json', 'adapter'),
    ):
        for name in (*manifest['files'], filename):
            copy(folder / name, destination + '/' + name)
    for folder, receipt, destination in ((bound.math_review_root, bound.math_review, 'reviews/math'),
                                          (bound.adapter_review_root, bound.adapter_review, 'reviews/adapter')):
        for name in ('receipt.json', *receipt['artifacts']):
            copy(folder / name, destination + '/' + name)
    for name in ('bind.py', 'test_binding.py', 'freeze.py', 'bindings.template.json', 'README.md'):
        copy(source / name, 'source/' + name)
    copy(tests / 'report.json', 'join-evidence/report.json')
    for case in ('normal', 'old_schema', 'wrong_variant', 'no_return'):
        copy(tests / case / 'receipt.json', 'join-evidence/' + case + '/receipt.json')
    for variant in bound.apps:
        copy(tests / 'normal' / (variant + '-decoded.json'), 'join-evidence/normal/' + variant + '-decoded.json')
    reference = bound.accepted.reference
    copy(B.ROOT / '.build/finish-picocalc-v138-20261023/PICO-APP-TRANSPORT-REUSE-REFERENCE.json', 'transport/reference.json')
    rows = {'alu': 18, 'rsqrt': 12, 'sqrt': 12, 'address': 18}
    checks = {'alu': 288, 'rsqrt': 96, 'sqrt': 96, 'address': 288}
    delta = B.read_json(bound.math / 'delta-report.json')
    firmware_reference = B.read_json(bound.math / 'firmware-proof/report.json')
    apps = []
    for variant, name in B.APP_ORDER:
        info = delta['apps'][variant]
        apps.append(dict(variant=variant, source='math/apps/' + variant + '/' + name + '.APP',
                         sha256=info['app_sha256'], app_bytes=info['app_bytes'], memory_bytes=info['memory_bytes'],
                         requested_remote_path='/INTRP01/' + name + '.APP', resolve_actual_canonical_case=True,
                         result_path='/INTRP01/RESULT.bin', result_schema=3,
                         result_rows=rows[variant], result_checks=checks[variant],
                         expected_result_bytes=256+rows[variant]*(48+40*7)))
    plan = dict(
        schema=1, status='PREPARED_OFFLINE_FOR_COMBINED_REVIEW_HARDWARE_HELD',
        hardware_entry_point_enabled=False, firmware_actions=[],
        immutable_inputs=dict(math_manifest_sha256=B.MATH_SHA, adapter_manifest_sha256=B.ADAPTER_SHA,
                              math_review_sha256=B.MATH_REVIEW_SHA, adapter_review_sha256=B.ADAPTER_REVIEW_SHA),
        reference_base=bound.reference, accepted_repaired_base=None,
        reference_source_sha256=firmware_reference['source_sha256'],
        reference_elf_sha256=firmware_reference['firmware_elf_sha256'],
        base_rule='A748 is an offline source/ELF/ABI/loader reference only. Review the future accepted fixed source, ELF, ABI, allocator, clock and peripheral ownership before binding execution.',
        shared_transport=dict(reference='transport/reference.json', reference_sha256=bound.adapter.REFERENCE_SHA,
                              original_library_root=reference['library_root'], external_host_dependencies=True,
                              rule='Reviewed adapter retains its original local absolute shared-library pins; it verifies every named and transitive Python dependency before import. This is a same-host packet, not a relocated shared-library fork.'),
        provider_bindings={name: None for name in B.PROVIDERS},
        preflight=[
            'Coordinator grants a new exclusive scoped lease after preceding hardware queue steps; no current lease is inferred.',
            'Record the observed UID/build/source/ELF/first full status/boot counter/health and fresh current state before any mode change or APP.',
            'Bind complete calculator capture/restore through loader pre-entry, bootstrap, live-call-stack and postlude; persist original snapshot and SHA before mutation.',
            'Bind fresh complete ALL-SD bytes/tree/hidden/large/FAT metadata and full calibrated RTC trajectory/RTC_SET/settings/alarms/CWD preservation.',
            'Verify live largest allocator block for at least20411bytes plus actual loader/live allocations; static30760B headroom is not sufficient evidence.',
            'Verify core0 privileged Thread, PRIMASK0, idle divider and exclusive core0 INTERP/IRQ context on the accepted base.',
            'Verify /INTRP01 absent including casefold aliases; journal exact owned bytes/canonical paths. Never use recursive cleanup.',
        ],
        app_order=apps, namespace='/INTRP01', marker=dict(name='MARKER.bin', bytes_hex='00'),
        timing=dict(rows=60, rounds=7, calls_per_batch=4096, physical_order='rotating ABBA/BAAB',
                    units='raw TIMERAWL microseconds', reference_clock_hz=125000000, reference_crystal_hz=12000000,
                    interrupts='enabled', empty_references='retained without subtraction',
                    measured_cost='function+loop+V3checksum+applicable save/setup/restore; never kernel-only'),
        normal_flow=[
            'Keep original first received frame and raw exchange; reject observed faults before further work.',
            'Capture and persist all reviewed real preservation anchors, then create only the owned namespace.',
            'For each APP: upload with accepted32-byteACK+CRC/readback, run once, await an actual fresh return prompt.',
            'Fetch and retain that APP raw RESULT.bin before health/admission; decode exact variant/schema3/4096/7 and retain all raw observations.',
            'Point-remove each verified result between APPs. Keep immutable source and raw failure evidence.',
            'Verify every owned object before deletion; remove only exact recorded paths/bytes, then audit every original SD byte/metadata.',
            'Independently restore/readback environment and full calculator state; final environment/health proof must not invalidate state restoration. Save transcript and close serial+lock.',
        ],
        failure_flow=[
            'Original failure remains HOLD after any later recovery.',
            'Before APP return: receive-only pump, disabled screen send, no query/ESC/ACK/keepalive or filesystem command.',
            'If no fresh prompt arrives, preserve original snapshot, raw binary RX and owned files; record pending restoration/operator recovery and close both descriptors.',
            'After confirmed return, execute independent finalizers even if evidence/journal/cleanup or another restore stage fails; preserve unknown/changed objects.',
        ],
        not_yet_established=['Combined join independent review', 'Accepted repaired base mapping', 'All five real bindings',
                             'Fresh scoped hardware lease', 'Any physical speed or real preservation result'],
    )
    (output / 'operator-plan.json').write_text(json.dumps(plan, indent=2) + '\n')
    summary = bound.report()
    summary['apps'] = {variant: dict(app, path=str(output / 'math/apps' / variant / (app['name'] + '.APP')))
                       for variant, app in summary['apps'].items()}
    summary.update(status=plan['status'], join_test_report_sha256=B.sha(output / 'join-evidence/report.json'),
                   joined_source_or_numerical_algorithms_changed=False, independent_combined_review='PENDING',
                   real_provider_bindings=plan['provider_bindings'], accepted_repaired_base=None)
    (output / 'combined-summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    files = {str(path.relative_to(output)): dict(bytes=path.stat().st_size, sha256=B.sha(path))
             for path in sorted(output.rglob('*')) if path.is_file()}
    manifest = output / 'combined-manifest.json'
    manifest.write_text(json.dumps(dict(schema=1, status=plan['status'], hardware_enabled=False, files=files), indent=2) + '\n')
    digest = B.sha(manifest)
    handoff = dict(status=plan['status'], packet=str(output), manifest=str(manifest), manifest_sha256=digest,
                   files=len(files), content_bytes=sum(pin['bytes'] for pin in files.values()),
                   math_manifest_sha256=B.MATH_SHA, adapter_manifest_sha256=B.ADAPTER_SHA,
                   math_review_sha256=B.MATH_REVIEW_SHA, adapter_review_sha256=B.ADAPTER_REVIEW_SHA,
                   inspect_command=['python3', str(output / 'source/bind.py'), '--packet', str(output), '--manifest-sha', digest],
                   hardware_enabled=False, next='Coordinator relays the new join for focused independent review; actual base/providers/lease remain required before hardware')
    (source.parent / 'COMBINED-HANDOFF.json').write_text(json.dumps(handoff, indent=2) + '\n')
    print(json.dumps(handoff, indent=2))


if __name__ == '__main__':
    main()
