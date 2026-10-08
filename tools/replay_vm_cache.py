#!/usr/bin/env python3
"""Replay real module order against the shipping cache and research policies.

Requires a LANGUAGE_VM_TRACE report and qualified owned bytecode images.
This models cache requests, not CPU speed, source I/O, APP loads or real timing.
Research policies never change firmware defaults. No device access.
"""
import argparse
from collections import OrderedDict
from fractions import Fraction
import json
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def simulate(requests, payload, slots, repeats, policy):
    entries = OrderedDict()
    passes = []
    for _ in range(repeats):
        result = {'hits': 0, 'misses': 0, 'evictions': 0, 'fallback': 0, 'used': 0}
        for identifier, size, _language in requests:
            key = (identifier, _language)
            if key in entries:
                size, reuse = entries.pop(key)
                entries[key] = (size, min(255, reuse + 1))
                result['hits'] += 1
                continue
            result['misses'] += 1
            wanted = (size + 7) & ~7
            if wanted > payload:
                result['fallback'] += 1
                continue
            while len(entries) >= slots or sum(v[0] for v in entries.values()) + wanted > payload:
                if policy == 'lru':
                    victim = next(iter(entries))
                elif policy == 'probation':
                    victim = next((key for key, value in entries.items() if not value[1]), next(iter(entries)))
                elif policy == 'density':
                    # Research only: decaying reuse/bytes, recency tie-break.
                    victim = min(entries, key=lambda key: Fraction(entries[key][1], entries[key][0]))
                    entries = OrderedDict((key, (value[0], value[1] // 2)) for key, value in entries.items())
                else:
                    raise ValueError(policy)
                del entries[victim]
                result['evictions'] += 1
            entries[key] = (wanted, 0)
        result['used'] = sum(v[0] for v in entries.values())
        passes.append(result)
    return passes


def shipping_replay(requests, repeats, policy=0):
    # Use the actual C++ ImageCache, not just a Python model of its LRU.
    with tempfile.TemporaryDirectory(prefix='mk61-vm-cache-replay-') as scratch:
        binary = Path(scratch) / 'replay'
        subprocess.run([shutil.which('clang++') or 'c++', '-std=c++17', '-O2',
                        '-Wall', '-Wextra', '-Werror', '-I' + str(ROOT / 'code'),
                        str(ROOT / 'tools/language_vm_cache_replay.cpp'), '-o', str(binary)], check=True)
        data = f'{repeats} {len(requests)} {policy}\n' + ''.join(f'{i} {s} {l}\n' for i, s, l in requests)
        return json.loads(subprocess.check_output([str(binary)], input=data, text=True))


def replay(trace, images, repeats=3):
    modules = {(m['language'], m['source_crc']): m for m in trace['modules']}
    available = {}
    for path in sorted(images.glob('*-owned.bvm')):
        data = path.read_bytes()
        assert len(data) >= 32 and (not data[7] & 4 or data[7] & 8), path
        assert data[:4] == b'LBV1' and data[4] == 4, path
        key = (data[5], struct.unpack_from('<I', data, 16)[0])
        if key in available:
            assert available[key][1] == data, ('ambiguous source CRC/language', path)
        available[key] = (path.name, data)
    descriptions = []
    ids = {}
    for identifier, (key, module) in enumerate(sorted(modules.items()), 1):
        name, image = available[key]
        ids[key[1]] = (identifier, len(image), key[0])
        descriptions.append({'id': identifier, 'source_crc': key[1], 'language': key[0],
                             'image': name, 'bytes': len(image), 'runs': module['runs']})
    # Trace currently identifies modules by CRC; reject cross-language aliases.
    assert len(ids) == len(modules)
    requests = [ids[crc] for crc in trace['run_order']]
    assert len(requests) == sum(m['runs'] for m in trace['modules'])
    shipping = shipping_replay(requests, repeats)
    modeled = simulate(requests, shipping['payload'], shipping['slots'], repeats, 'lru')
    assert modeled == shipping['passes'], ('shipping/model disagreement', modeled, shipping)
    policies = {'shipping_lru': shipping['passes']}
    for policy in ('probation', 'density'):
        policies[policy] = simulate(requests, shipping['payload'], shipping['slots'], repeats, policy)
    native_density = shipping_replay(requests, repeats, 1)
    assert native_density['passes'] == policies['density'], ('density/model disagreement', native_density, policies['density'])
    return {'status': 'PASS', 'requests_per_pass': len(requests), 'repeats': repeats,
            'unique_modules': len(modules), 'unique_aligned_bytes': sum((m['bytes'] + 7) & ~7 for m in descriptions),
            'cache': {key: shipping[key] for key in ('budget', 'payload', 'metadata', 'slots')},
            'modules': descriptions, 'policies': policies,
            'note': 'Request-order replay, not hardware time. No filesystem revisions, concurrent pins or native APP/arena evictions modeled.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--trace', type=Path, required=True)
    parser.add_argument('--images-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--repeats', type=int, default=3)
    args = parser.parse_args()
    assert 1 <= args.repeats <= 10
    result = replay(json.loads(args.trace.read_text()), args.images_dir, args.repeats)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({key: result[key] for key in ('status', 'requests_per_pass', 'unique_modules',
                                                'unique_aligned_bytes', 'cache', 'policies')}, indent=2))


if __name__ == '__main__':
    main()
