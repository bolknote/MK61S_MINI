#!/usr/bin/env python3
"""Explicit offline V3 APP/decoder + reviewed RX-only adapter binding."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True

ROOT = Path('/Users/bolk/Projects/MK61S_MINI')
BUILD = ROOT / '.build/rp2040-interpolator-20261023'
REVIEWS = ROOT / '.build/interp-independent-review-20261023'
MATH_SHA = '633ee492b2c57d746507920613b144135b01516fad8ec50d73a3ed62bb3aa979'
ADAPTER_SHA = '8a763f8c196fd8c0e262954264b9a664d73b30ee32ec75cd266722afa38fc36e'
MATH_REVIEW_SHA = '0879ae7e38636e0ce6345b0940f98adfa79b79baed9a9461d750b1453953207a'
ADAPTER_REVIEW_SHA = 'e9942c8525b47721da7aa3ababac00dfb6b6036f906f6cd8bb4cb1839eed5c8e'
V2_SHA = '849885aa360bf83cd45f21163a3079ba37b78c34fcd4dd9e822bea32197eccf0'
PROVIDERS = ('exclusive_lease', 'post_cold_anchor', 'full_calculator_provider', 'all_sd_provider', 'environment_provider')
APP_ORDER = (('alu', 'IALU'), ('rsqrt', 'IRSQ'), ('sqrt', 'ISQRT'), ('address', 'IADDR'))


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text())


def verified_manifest(folder, filename, expected):
    folder = Path(folder).resolve()
    path = folder / filename
    require(sha(path) == expected, 'Manifest pin mismatch: ' + str(path))
    manifest = read_json(path)
    for name, pin in manifest['files'].items():
        file = folder / name
        require(file.resolve().is_relative_to(folder) and not file.is_symlink(), 'Unsafe manifest path')
        require(file.stat().st_size == pin['bytes'] and sha(file) == pin['sha256'], 'Artifact changed: ' + str(file))
    if filename == 'combined-manifest.json':
        actual = {str(file.relative_to(folder)) for file in folder.rglob('*') if file.is_file()}
        require(actual == set(manifest['files']) | {filename}, 'Unsealed extra file in combined packet')
    return manifest


def verified_review(folder, expected, manifest_sha, status):
    folder = Path(folder).resolve()
    require(sha(folder / 'receipt.json') == expected, 'Review receipt pin mismatch')
    receipt = read_json(folder / 'receipt.json')
    require(receipt['status'] == status and receipt['manifest_sha256'] == manifest_sha, 'Review does not cover this input')
    require(not receipt['findings'] and not receipt['hardware_GO'] and not receipt['production_GO'], 'Unexpected review scope')
    for name, pin in receipt['artifacts'].items():
        path = folder / name
        require(path.resolve().is_relative_to(folder) and sha(path) == pin['sha256'], 'Review artifact changed: ' + name)
    return receipt


def load_module(path, role):
    path = Path(path).resolve()
    suffix = hashlib.sha256(str(path).encode()).hexdigest()[:12]
    name = '_interp_combined_' + role + '_' + suffix
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    module = sys.modules[name]
    require(Path(module.__file__).resolve() == path, 'Wrong combined module import')
    return module


class BoundSet:
    def __init__(self, packet=None, manifest_sha=None):
        self.packet = Path(packet).resolve() if packet is not None else None
        self.combined_manifest_sha = manifest_sha
        if self.packet is not None:
            require(isinstance(manifest_sha, str) and len(manifest_sha) == 64,
                    'A frozen combined packet requires the external HANDOFF manifest SHA')
            verified_manifest(self.packet, 'combined-manifest.json', manifest_sha)
        self.math = self.packet / 'math' if self.packet else BUILD / 'packet-v3'
        self.adapter_root = self.packet / 'adapter' if self.packet else BUILD / 'adapter-packet-v2'
        self.math_review_root = self.packet / 'reviews/math' if self.packet else REVIEWS / 'v3-delta'
        self.adapter_review_root = self.packet / 'reviews/adapter' if self.packet else REVIEWS / 'adapter-v2-delta'
        self.math_manifest = verified_manifest(self.math, 'packet-manifest.json', MATH_SHA)
        self.adapter_manifest = verified_manifest(self.adapter_root, 'adapter-manifest.json', ADAPTER_SHA)
        self.math_review = verified_review(self.math_review_root, MATH_REVIEW_SHA, MATH_SHA,
                                          'TECHNICAL_GO_FOCUSED_OFFLINE_INTERP_V3_DELTA')
        self.adapter_review = verified_review(self.adapter_review_root, ADAPTER_REVIEW_SHA, ADAPTER_SHA,
                                             'TECHNICAL_GO_FOCUSED_OFFLINE_RX_ONLY_ADAPTER_V2_DELTA')
        # Imports happen only after both complete sealed inputs and review
        # artifact chains have been checked. No device factory is called.
        self.adapter = load_module(self.adapter_root / 'source/lifecycle.py', 'adapter')
        self.decoder = load_module(self.math / 'source/decode.py', 'decoder')
        self.accepted = self.adapter.Accepted()
        self.port_type = self.adapter.accepted_port_type(self.accepted)
        self.apps = {}
        for variant, name in APP_ORDER:
            relative = 'apps/' + variant + '/' + name + '.APP'
            self.apps[variant] = dict(name=name, path=str(self.math / relative),
                                      sha256=self.math_manifest['files'][relative]['sha256'])
        require(self.adapter.PACKET_SHA == V2_SHA, 'Reviewed adapter globals were silently rebound')
        require(read_json(self.math / 'delta-report.json')['result_schema'] == 3, 'Require V3 result schema')
        self.reference = read_json(self.math / 'execution-plan.json')['target']
        require(self.reference['uid'] == self.adapter.UID and self.reference['build'] == self.adapter.BUILD,
                'Reference UID/build incompatible with reviewed adapter')

    def admit(self, raw, variant, expected_rounds=7, expected_samples=4096):
        require(variant in self.apps, 'Unknown bound V3 variant')
        return self.decoder.decode(raw, variant=variant, physical=False,
                                   expected_rounds=expected_rounds, expected_samples=expected_samples)

    def held(self, bindings):
        missing = [name for name in PROVIDERS if not bindings.get(name)]
        return dict(status='HELD_NO_HARDWARE_ENTRY_POINT', missing_provider_bindings=missing,
                    accepted_repaired_base_bound=False, exclusive_live_lease_verified=False,
                    hardware_enabled=False, hardware_verified=False, port_constructed=False,
                    reason='This reviewed-input binding is offline only. Labels do not implement providers or admit a new firmware base; a separately reviewed real execution binding is required.')

    def report(self):
        return dict(status='BOUND_OFFLINE_V3_ADAPTER_V2_HARDWARE_HELD', math_manifest_sha256=MATH_SHA,
                    combined_manifest_sha256=self.combined_manifest_sha,
                    adapter_manifest_sha256=ADAPTER_SHA, math_review_sha256=MATH_REVIEW_SHA,
                    adapter_review_sha256=ADAPTER_REVIEW_SHA, result_schema=3,
                    apps=self.apps, reference_base=self.reference, active_hardware_base=None,
                    adapter_legacy_manifest_sha256=self.adapter.PACKET_SHA,
                    adapter_legacy_selector_called=False, adapter_source_changed=False,
                    join='Explicit V3 descriptors passed to reviewed Lifecycle; V3 decoder is the admission callback. Legacy verified_apps(V2) is never used or modified.',
                    raw_timing='Function+loop+checksum and applicable setup/restore; no empty subtraction or kernel-only timing claim.',
                    hardware_enabled=False, hardware_verified=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--packet', type=Path)
    parser.add_argument('--manifest-sha', help='External SHA-256 from the combined HANDOFF; required with --packet')
    parser.add_argument('--bindings', type=Path)
    parser.add_argument('--hardware', action='store_true', help='Report hardware HOLD; this tool never opens a device')
    args = parser.parse_args()
    bound = BoundSet(args.packet, args.manifest_sha)
    if args.hardware:
        bindings = read_json(args.bindings) if args.bindings else {}
        print(json.dumps(bound.held(bindings), indent=2))
        raise SystemExit(2)
    print(json.dumps(bound.report(), indent=2))


if __name__ == '__main__':
    main()
