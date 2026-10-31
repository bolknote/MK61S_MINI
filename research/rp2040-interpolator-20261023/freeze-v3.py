#!/usr/bin/env python3
"""Freeze the narrow V3 checksum delta. No device, carrier or production edits."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BUILD = ROOT / '.build/rp2040-interpolator-20261023'
V2 = BUILD / 'packet-v2'
V2_SHA = '849885aa360bf83cd45f21163a3079ba37b78c34fcd4dd9e822bea32197eccf0'
sys.path.insert(0, str(ROOT / 'tests'))
from check_stm32_vectors import ElfImage


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path):
    return json.loads(Path(path).read_text())


def frame(path):
    elf = ElfImage(path)
    address = elf.symbols['time_batch'] & ~1
    section = elf.named_sections['.module_image']
    prologue = elf.bytes_at(section)[address-section[3]:address-section[3]+4]
    # Exact observed Thumb push {r4-r7,lr}; sub sp,#92 in both generations.
    assert prologue == bytes.fromhex('f0b597b0'), (str(path), prologue.hex())
    return dict(prologue=prologue.hex(), own_stack_bytes=5*4+92, code_bytes=elf.sizes['time_batch'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    assert not output.exists(), 'Use a new directory; immutable packets are never overwritten'
    assert sha(V2 / 'packet-manifest.json') == V2_SHA
    for name, pin in load(V2 / 'packet-manifest.json')['files'].items():
        path = V2 / name
        assert path.stat().st_size == pin['bytes'] and sha(path) == pin['sha256'], name
    old_plan = load(V2 / 'execution-plan.json')
    for name, pin in old_plan['external_dependency_sha256'].items():
        assert sha(ROOT / name) == pin, 'External build/reference dependency changed: ' + name
    mathematical = ('kernels.cpp', 'divide.S', 'root_seed.S', 'tables.inc', 'baseline_sqrt_table.inc',
                    'seed-certificate.json', 'generate.py', 'verify.py')
    for name in mathematical:
        assert (HERE / name).read_bytes() == (V2 / 'source' / name).read_bytes(), name
    # Only the checksum body/comments changed in the shared declaration header.
    def declarations(text):
        start = text.index('static inline uint32_t interp_checksum_step')
        end = text.index('\nvoid interp_blend_setup', start)
        return text[:start] + text[end:]
    assert declarations((HERE / 'kernels.h').read_text()) == declarations((V2 / 'source/kernels.h').read_text())
    checksum = load(BUILD / 'checksum-v3/report.json')
    assert checksum['status'] == 'PASS_OFFLINE' and checksum['negative_cases'] == 2048
    assert checksum['samples'] == 4096 and not checksum['hardware_verified']
    for name, pin in checksum['source_sha256'].items():
        assert sha(HERE / name) == pin, name
    assert sha(BUILD / 'checksum-v3/checksum.elf') == checksum['elf_sha256']
    assert checksum['baseline'] != checksum['msb_j7']['checksum']
    upstream = ROOT / '.build/interp-independent-review-20261023/checksum-bit-boundary.json'
    assert sha(upstream) == 'e39c4bebe730a21fa3e9c707737b2f91b024d21508057a986c5d3863acb431bf'
    firmware = load(BUILD / 'firmware-proof-v3/report.json')
    assert firmware['status'] == 'PASS_OFFLINE' and not firmware['hardware_verified']
    apps = load(BUILD / 'app-v3/app-manifest.json')['apps']
    evidence = {}
    calls = 0
    for variant, app in apps.items():
        parent = Path(app['app']).parent
        validation = load(parent / 'arm-validation.json')
        previous = load(V2 / 'apps' / variant / 'arm-validation.json')
        protocol = load(BUILD / ('protocol-v3b-' + variant) / 'report.json')
        assert validation['status'] == protocol['status'] == 'PASS'
        assert validation['elf_sha256'] == sha(app['elf']) and app['app_sha256'] == sha(app['app'])
        assert validation['digest'] == previous['digest'] and validation['checked'] == previous['checked']
        assert protocol['benchmark_sha256'] == sha(HERE / 'benchmark.c')
        assert len(protocol['cases']) == 4 and protocol['decoder_negative_cases'] == 6
        assert all(row['peripheral_state_restored'] for row in protocol['cases'])
        old_name = Path(app['app']).name
        old_memory = load(V2 / 'apps' / variant / (app['name'] + '.json'))['memory_bytes']
        assert app['memory_bytes'] == old_memory + 8
        before = frame(V2 / 'apps' / variant / (app['name'] + '.elf'))
        after = frame(app['elf'])
        assert before['own_stack_bytes'] == after['own_stack_bytes'] and after['code_bytes'] == before['code_bytes'] + 8
        evidence[variant] = dict(app_sha256=app['app_sha256'], elf_sha256=validation['elf_sha256'],
            app_bytes=app['app_bytes'], memory_bytes=app['memory_bytes'], loaded_delta_bytes=8,
            old_time_batch=before, new_time_batch=after,
            protocol_stack_bytes=max(row['stack_bytes_observed'] for row in protocol['cases']),
            actual_arm_calls=validation['actual_arm_calls'], identical_numerical_output_digest=validation['digest'])
        calls += validation['actual_arm_calls']
    output.mkdir(parents=True)

    def copy(original, relative):
        destination = output / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(original, destination)

    for name in (*mathematical, 'kernels.h', 'benchmark.c', 'build-app.py', 'app-self-test.py', 'decode.py',
                 'decode-proof.cpp', 'firmware-proof.py', 'checksum-probe.cpp', 'checksum-self-test.py', 'freeze-v3.py', 'README.md'):
        copy(HERE / name, 'source/' + name)
    for variant, app in apps.items():
        parent = Path(app['app']).parent
        for suffix in ('.APP', '.elf', '.map', '.json'):
            copy(parent / (app['name'] + suffix), 'apps/' + variant + '/' + app['name'] + suffix)
        copy(parent / 'arm-validation.json', 'apps/' + variant + '/arm-validation.json')
        for name in ('report.json', 'fixture.elf', 'synthetic-result.bin'):
            copy(BUILD / ('protocol-v3b-' + variant) / name, 'protocol/' + variant + '/' + name)
    for name in ('report.json', 'frozen.bin', 'current.bin'):
        copy(BUILD / 'firmware-proof-v3' / name, 'firmware-proof/' + name)
    for name in ('report.json', 'checksum.elf'):
        copy(BUILD / 'checksum-v3' / name, 'checksum/' + name)
    copy(upstream, 'checksum/independent-v2-counterexample.json')
    delta = dict(
        status='OFFLINE_DELTA_PASS_INDEPENDENT_REVIEW_PENDING_HARDWARE_HELD',
        hardware_verified=False, physical_timing=False, reference_v2_manifest_sha256=V2_SHA,
        v2_status='HISTORICAL_TIMED_INTEGRITY_HOLD; previous regression covered low-word bit0 at position7 only',
        result_schema=3, mathematical_source_unchanged={name: sha(HERE / name) for name in mathematical},
        current_external_dependencies=old_plan['external_dependency_sha256'],
        actual_arm_kernel_calls=calls, actual_arm_checksum_stream_calls=2049,
        checksum_negative_cases=2048, protocol_cases=16, decoder_negative_cases=24,
        checksum_counterexample_closed=True, checksum_report_sha256=sha(output / 'checksum/report.json'),
        checksum_overhead=checksum['step_profiles'], apps=evidence,
        stack_scope='time_batch own frame112B unchanged in exact shipping ELFs; observed short-loop fixture stacks304-388B exclude firmware loader, IRQs and real service implementations',
        timing_scope='Raw loop+function+checksum plus applicable setup/restore. Empty references retained without subtraction. No kernel-only speed or physical cycle claim.',
        integrity_limit=checksum['limitation'],
        carrier='Separate adapter-packet-v1 is immutable V2 context and pins V2; no V3 carrier binding exists. All five lease/base/fullstate/ALL-SD/environment bindings remain absent.',
        next='Independent review of this V3 delta; new accepted firmware source/ELF/ABI/ownership/loader and real preservation bindings before any hardware lease',
    )
    (output / 'delta-report.json').write_text(json.dumps(delta, indent=2) + '\n')
    plan = dict(old_plan)
    plan.update(status=delta['status'], result_schema=3, checksum='Sequential word mixes with multiply and right-shift; see checksum/report.json',
                reference_base_only=True, carrier_binding=None, transport_binding=None, lease_binding=None,
                required_provider_bindings=['lease', 'accepted post-Cold base', 'full calculator', 'ALL-SD', 'environment'],
                future_base='A748 reference is not admission for the future cold-RAM/USB/memory-fixed firmware')
    plan['preflight'] = [value.replace('20396', '20404') for value in plan['preflight']]
    (output / 'execution-plan.json').write_text(json.dumps(plan, indent=2) + '\n')
    files = {str(path.relative_to(output)): dict(bytes=path.stat().st_size, sha256=sha(path))
             for path in sorted(output.rglob('*')) if path.is_file()}
    manifest = output / 'packet-manifest.json'
    manifest.write_text(json.dumps(dict(schema=3, status=delta['status'], hardware_verified=False, files=files), indent=2) + '\n')
    handoff = dict(status=delta['status'], hardware_verified=False, packet=str(output), manifest=str(manifest),
                   manifest_sha256=sha(manifest), reference_v2_manifest_sha256=V2_SHA,
                   actual_arm_kernel_calls=calls, checksum_negative_cases=2048, apps=evidence,
                   next=delta['next'])
    (HERE / 'HANDOFF.json').write_text(json.dumps(handoff, indent=2) + '\n')
    (HERE / 'offline-result.json').write_text(json.dumps(delta, indent=2) + '\n')
    print(json.dumps(dict(status=delta['status'], manifest=str(manifest), manifest_sha256=sha(manifest),
                         files=len(files), content_bytes=sum(row['bytes'] for row in files.values())), indent=2))


if __name__ == '__main__':
    main()
