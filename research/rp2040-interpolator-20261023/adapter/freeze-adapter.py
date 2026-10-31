#!/usr/bin/env python3
"""Freeze this offline adapter for review; never construct a device port."""
import argparse
import json
from pathlib import Path
import shutil

from lifecycle import Accepted, PACKET_SHA, REFERENCE_SHA, ROOT, hardware_requirements, sha, verified_apps


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tests', type=Path, required=True)
    parser.add_argument('--passive-tests', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    source = Path(__file__).resolve().parent
    tests = args.tests.resolve()
    passive_tests = args.passive_tests.resolve()
    output = args.output.resolve()
    if output.exists():
        raise SystemExit('Use a new directory; review packets are never overwritten')

    accepted = Accepted()
    verified_apps()
    previous = ROOT / '.build/rp2040-interpolator-20261023/adapter-packet-v1/adapter-manifest.json'
    assert sha(previous.read_bytes()) == '45d9f637355b936b55e0264a1f96bb50719486bb70b2216d442776c7df3a6960'
    for name, pin in json.loads(previous.read_text())['files'].items():
        path = previous.parent / name
        assert path.stat().st_size == pin['bytes'] and sha(path.read_bytes()) == pin['sha256'], name
    report_path = tests / 'report.json'
    report = json.loads(report_path.read_text())
    assert report['status'] == 'PASS_OFFLINE'
    assert report['hardware_verified'] is False and report['hardware_constructor_called'] is False
    assert report['candidate_manifest_sha256'] == PACKET_SHA
    assert report['transport_reference_sha256'] == REFERENCE_SHA
    assert report['accepted_python_pins_sha256'] == accepted.reference['pins_sha256']
    for name, digest in report['source_sha256'].items():
        assert Path(name).name == name and sha((source / name).read_bytes()) == digest, name
    bindings = json.loads((source / 'bindings.template.json').read_text())
    held = hardware_requirements(bindings)
    assert held['status'] == 'HELD' and len(held['missing']) == 5 and not held['port_opened']
    contracts = json.loads((source / 'provider-contracts.json').read_text())
    assert contracts['hardware_enabled'] is False
    cases = {row['case']: row for row in report['cases']}
    assert len(cases) == 27 and all(row['serial_closed'] and row['original_user_bytes_preserved'] for row in cases.values())
    assert cases['normal']['status'] == 'PASS'
    assert all(row['status'] == 'HOLD' for name, row in cases.items() if name != 'normal')
    for name in ('app_active_timeout', 'app_active_stale_prompt', 'app_output_fake_prompt'):
        assert cases[name]['manual_recovery_required'] and not cases[name]['command_channel_available']
        assert not cases[name]['full_restore_attempted']
    assert cases['app_late_return']['full_restore_attempted']
    passive = json.loads((passive_tests / 'report.json').read_text())
    assert passive['status'] == 'PASS_OFFLINE' and not passive['hardware_accessed']
    assert not passive['hardware_constructor_called'] and len(passive['cases']) == 3
    for name, digest in passive['source_sha256'].items():
        assert sha((source / name).read_bytes()) == digest, name
    for row in passive['cases']:
        assert row['valid_CAPS_decoded'] and not row['post_open_tx'] and row['closed_descriptors'] == [101, 102]
        if row['case'] != 'late_caps_fresh_return':
            assert row['manual_recovery_required'] and not row['command_channel_available']
    upstream = ROOT / '.build/interp-independent-review-20261023/carrier-late-attach.json'
    assert sha(upstream.read_bytes()) == 'ab94f5840ba7ec6cc43ffb0fe85827a55cd9fb41f08a760df0ea6b9bbb623d48'

    output.mkdir(parents=True)

    def copy(original, relative):
        destination = output / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(original, destination)

    for name in ('lifecycle.py', 'test_lifecycle.py', 'test_passive.py', 'bindings.template.json',
                 'provider-contracts.json', 'README.md', 'freeze-adapter.py'):
        copy(source / name, 'source/' + name)
    copy(report_path, 'evidence/report.json')
    copy(passive_tests / 'report.json', 'evidence/passive-report.json')
    copy(upstream, 'evidence/independent-v1-late-attach.json')
    for name in ('late_caps_no_return', 'already_attached_no_return'):
        for filename in ('receipt.json', 'calculator-before.bin', 'passive-wire.bin'):
            copy(passive_tests / name / filename, 'evidence/' + name + '/' + filename)
    for name in cases:
        copy(tests / name / 'receipt.json', 'evidence/' + name + '/receipt.json')
    for name in ('bad_first_good_later', 'truncated_first'):
        for filename in ('initial-received.bin', 'initial-first-status.txt'):
            copy(tests / name / filename, 'evidence/' + name + '/' + filename)
    for name in ('app_active_timeout', 'app_active_stale_prompt', 'app_output_fake_prompt', 'app_late_return'):
        for filename in ('calculator-before.bin', 'received-before-finally.bin'):
            copy(tests / name / filename, 'evidence/' + name + '/' + filename)
    summary = dict(
        status='OFFLINE_PASS_REVIEW_PENDING_HARDWARE_HELD', hardware_enabled=False,
        hardware_verified=False, cases=len(cases), actual_transport_passive_cases=3, candidate_manifest_sha256=PACKET_SHA,
        reference_adapter_v1_manifest_sha256='45d9f637355b936b55e0264a1f96bb50719486bb70b2216d442776c7df3a6960',
        delta='Always receive-only pump and disabled screen packet send; actual late CAPS regression closes the adapter-v1 keepalive counterexample',
        candidate_scope='Historical V2 context only; mathematical V3 separate, no combined V3 hardware binding',
        transport_reference_sha256=REFERENCE_SHA, missing_bindings=held['missing'],
        test_output=str(tests), test_report_sha256=sha(report_path.read_bytes()),
        source_scope='Separate lifecycle and provider contracts only; immutable arithmetic packet unchanged',
        review_scope='Real accepted framing/ACK/CRC plus lifecycle/ownership/finally; physical CDC, APP execution and preservation providers are test doubles',
        limitation='No real complete arbitrary-state provider, lease, accepted post-fix base, physical timing or independent adapter review exists',
    )
    (output / 'review-summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    files = {str(path.relative_to(output)): dict(bytes=path.stat().st_size, sha256=sha(path.read_bytes()))
             for path in sorted(output.rglob('*')) if path.is_file()}
    manifest = output / 'adapter-manifest.json'
    manifest.write_text(json.dumps(dict(schema=2, status=summary['status'], files=files), indent=2) + '\n')
    print(json.dumps(dict(status=summary['status'], files=len(files), bytes=sum(row['bytes'] for row in files.values()),
                         manifest=str(manifest), manifest_sha256=sha(manifest.read_bytes())), indent=2))


if __name__ == '__main__':
    main()
