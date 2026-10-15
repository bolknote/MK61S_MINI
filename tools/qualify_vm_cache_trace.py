#!/usr/bin/env python3
"""Qualify a host module-order window against a diagnostic device profile.

The signature is a non-cryptographic order check, not an identity/security
boundary. It is checked together with complete per-module counts and sizes.
No device access or firmware changes. Game/board correctness is a HIL duty.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import re

from measure_vm_cache_storage import load_images

FNV_OFFSET = 14695981039346656037
FNV_PRIME = 1099511628211


def fingerprint(ids):
    result = FNV_OFFSET
    for identifier in ids:
        if not 0 <= identifier < 0xFFFF:
            raise ValueError('invalid source inode')
        for shift in (0, 8):
            result = ((result ^ ((identifier >> shift) & 255)) * FNV_PRIME) & ((1 << 64) - 1)
    return result


def parse_profile(text):
    signatures = re.findall(r'^VMCACHE_ORDER count=(\d+) fnv64=(\d+)\s*$', text, re.M)
    dropped = re.findall(r'^VMCACHE dropped=(\d+)\s*$', text, re.M)
    if len(signatures) != 1 or dropped != ['0']:
        raise ValueError('one complete, undropped cache profile required')
    count, fnv64 = map(int, signatures[0])
    if not 0 < count < 0xFFFFFFFF or not 0 <= fnv64 < 1 << 64:
        raise ValueError('empty, saturated or invalid signature')
    rows = {}
    names = set()
    for match in re.finditer(r'^VMCACHE id=(\d+) bytes=(\d+) hits=(\d+) misses=(\d+) name=([^\r\n]+)', text, re.M):
        identifier, size, hits, misses = map(int, match.group(1, 2, 3, 4))
        name = match[5]
        if identifier in rows or name.casefold() in names or not 0 <= identifier < 0xFFFF or size < 32 or not hits + misses:
            raise ValueError('duplicate/invalid cache row')
        names.add(name.casefold())
        rows[identifier] = dict(id=identifier, bytes=size, hits=hits, misses=misses, name=name)
    if sum(r['hits'] + r['misses'] for r in rows.values()) != count:
        raise ValueError('cache rows/signature count mismatch')
    return dict(count=count, fnv64=fnv64, rows=rows)


def qualify(trace, images, profile, image_prefix):
    modules = {(m['language'], m['source_crc']): m for m in trace['modules']}
    if len(modules) != len(trace['modules']) or len({k[1] for k in modules}) != len(modules):
        raise ValueError('duplicate/cross-language CRC alias in legacy trace')
    order = trace['run_order']
    if Counter(order) != Counter({k[1]: m['runs'] for k, m in modules.items()}):
        raise ValueError('incomplete host trace')
    by_crc = {}
    image_names = {}
    row_names = {r['name'].casefold(): r for r in profile['rows'].values()}
    for key, module in modules.items():
        image = images[key]
        name = Path(image['name']).name
        if not name.startswith(image_prefix) or not name.endswith('-owned.bvm'):
            raise ValueError('ambiguous image naming: ' + name)
        name = name[len(image_prefix):-len('-owned.bvm')]
        row = row_names.get(name.casefold())
        if row is not None and image['raw'] != row['bytes']:
            raise ValueError('host/device image size mismatch: ' + name)
        if row is not None:
            image_names[row['id']] = image['name']
        by_crc[key[1]] = (row['id'] if row else None, image['raw'], key[0], name)
    expected = Counter({i: r['hits'] + r['misses'] for i, r in profile['rows'].items()})
    count = profile['count']
    matches = []
    # Profiles normally trim a few UI calls. An exact contiguous window is
    # required; never reorder requests to make aggregate counts agree.
    for start in range(len(order) - count + 1):
        window = [by_crc[c][0] for c in order[start:start + count]]
        if Counter(window) == expected and fingerprint(window) == profile['fnv64']:
            matches.append(start)
    if len(matches) != 1:
        raise ValueError(f'expected one host/device order match, got {matches}')
    start = matches[0]
    return dict(status='PASS', start=start, end=start + count, requests=count,
                host_requests=len(order), fnv64=profile['fnv64'],
                modules=[dict(r, image=image_names[i]) for i, r in profile['rows'].items()],
                window_requests=[by_crc[c][:3] for c in order[start:start + count]],
                note='Order/count/size qualification only; initial cache state and HIL board checked separately.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--trace', type=Path, required=True)
    parser.add_argument('--images-dir', type=Path, required=True)
    parser.add_argument('--profile', type=Path, action='append', required=True)
    parser.add_argument('--image-prefix', required=True, help='e.g. turochamp-')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    trace = json.loads(args.trace.read_text())
    images = load_images(args.images_dir)
    reports = {str(p): qualify(trace, images, parse_profile(p.read_text()), args.image_prefix) for p in args.profile}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(dict(status='PASS', profiles=reports), indent=2) + '\n')
    print(json.dumps({p: {k: r[k] for k in ('status', 'start', 'end', 'requests', 'host_requests', 'fnv64')}
                      for p, r in reports.items()}, indent=2))


if __name__ == '__main__':
    main()
