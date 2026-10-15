#!/usr/bin/env python3
"""Actual C++ raw24/mixed24/raw32 over a device-qualified module-order window.

Checks every returned image against the original complete owned image and
workspace-tail canaries. This is a host correctness/counter replay, not time.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from measure_vm_cache_storage import load_images
from qualify_vm_cache_trace import fingerprint

ROOT = Path(__file__).resolve().parents[1]


def validate_qualification(trace, images, qualification):
    """Recheck the saved proof against these exact inputs, before compiling."""
    modules = {(m['language'], m['source_crc']): m for m in trace['modules']}
    if len(modules) != len(trace['modules']) or len({k[1] for k in modules}) != len(modules):
        raise ValueError('duplicate/cross-language CRC alias')
    order = trace['run_order']
    if Counter(order) != Counter({k[1]: m['runs'] for k, m in modules.items()}):
        raise ValueError('incomplete host trace')
    start, end = qualification['start'], qualification['end']
    if (qualification['status'] != 'PASS' or qualification['host_requests'] != len(order) or
            not 0 <= start < end <= len(order) or qualification['requests'] != end - start):
        raise ValueError('trace/qualification window mismatch')
    rows = qualification['modules']
    by_image = {r['image']: r for r in rows}
    if len(by_image) != len(rows) or len({r['id'] for r in rows}) != len(rows):
        raise ValueError('duplicate qualified module')
    by_crc = {}
    for key in modules:
        image = images[key]
        row = by_image.get(image['name'])
        if row is not None:
            if image['raw'] != row['bytes'] or row['hits'] < 0 or row['misses'] < 0:
                raise ValueError('qualified image size/count mismatch')
            by_crc[key[1]] = (row['id'], image['raw'], key[0])
    try:
        window = [by_crc[c] for c in order[start:end]]
    except KeyError as error:
        raise ValueError('unqualified image in replay window') from error
    ids = [r[0] for r in window]
    if (window != [tuple(r) for r in qualification['window_requests']] or
            Counter(ids) != Counter({r['id']: r['hits'] + r['misses'] for r in rows}) or
            fingerprint(ids) != qualification['fnv64']):
        raise ValueError('trace/qualification order, size or counts changed')


def replay(trace, images, qualification, repeats=3, sanitizers=False):
    validate_qualification(trace, images, qualification)
    modules = {(m['language'], m['source_crc']): m for m in trace['modules']}
    by_crc = {k[1]: (i, images[k]) for i, k in enumerate(sorted(modules), 1)}
    descriptors = {i: dict(image, id=i, runs=modules[k]['runs']) for k in modules for i, image in [by_crc[k[1]]]}
    order = [by_crc[c][0] for c in trace['run_order']]
    start, end = qualification['start'], qualification['end']
    with tempfile.TemporaryDirectory(prefix='mk61-native-mixed-') as tmp:
        binary = Path(tmp) / 'replay'
        flags = ['-O1', '-g', '-fsanitize=address,undefined', '-fno-omit-frame-pointer'] if sanitizers else ['-O2']
        subprocess.run([shutil.which('clang++') or 'c++', '-std=c++17', '-Wall', '-Wextra', '-Werror', *flags,
                        '-I' + str(ROOT / 'code'), str(ROOT / 'tools/language_vm_mixed_cache_replay.cpp'),
                        str(ROOT / 'code/language_bytecode.cpp'), str(ROOT / 'code/language_vm.cpp'),
                        '-o', str(binary)], check=True)
        data = f'{repeats} {start} {end} {len(descriptors)} {len(order)}\n'
        data += ''.join(f'{i} {d["language"]} {json.dumps(d["file"])}\n' for i, d in sorted(descriptors.items()))
        data += '\n'.join(map(str, order)) + '\n'
        result = json.loads(subprocess.check_output([str(binary)], input=data, text=True))
    assert [(v['budget'], v['mixed']) for v in result['variants']] == [(24576, False), (24576, True), (32768, False)]
    for v in result['variants']:
        assert (v['object_bytes'], v['metadata'], v['payload']) == (v['budget'], 688, v['budget'] - 688)
        for p in v['passes']:
            assert p['hits'] + p['misses'] == end - start and not p['fallback']
            assert sum(p['miss_modules'].values()) == p['misses']
    if repeats > 1:
        expected = {r['image']: r['misses'] for r in qualification['modules']}
        observed = {d['name']: result['variants'][0]['passes'][1]['miss_modules'].get(str(i), 0)
                    for i, d in descriptors.items() if d['name'] in expected}
        assert observed == expected, ('native raw baseline differs from device', observed, expected)
    return dict(result, requests=end - start, host_requests=len(order), modules=list(descriptors.values()),
                sanitizers=sanitizers,
                qualification='Actual C++ cache, bounded one-pass codec, CRC and byte/tail guards. No device cycles, cold FS invalidations, INPUT execution or firmware rollout.')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--trace', type=Path, required=True)
    ap.add_argument('--images-dir', type=Path, required=True)
    ap.add_argument('--qualification', type=Path, required=True)
    ap.add_argument('--repeats', type=int, default=3)
    ap.add_argument('--sanitizers', action='store_true')
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    q = json.loads(args.qualification.read_text())
    if q['status'] != 'PASS' or len(q['profiles']) != 1:
        raise ValueError('exactly one qualified warm profile required')
    result = replay(json.loads(args.trace.read_text()), load_images(args.images_dir),
                    next(iter(q['profiles'].values())), args.repeats, args.sanitizers)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result['variants'], indent=2))


if __name__ == '__main__':
    main()
