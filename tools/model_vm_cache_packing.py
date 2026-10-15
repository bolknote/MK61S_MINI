#!/usr/bin/env python3
"""Research-only physical mixed-cache model. Does not configure firmware.

Fixed directory/payload; first-fit contiguous spans; shipping all-unpinned
compaction rule; no movement/packing/eviction of pinned images. Packing needs
256 dictionary bytes and a disjoint complete output, thaw a disjoint raw image.
Staging is phase-bounded EXISTING borrowed memory, never an extra allocation.
Codec latencies and a viable production metadata layout remain separate gates.
"""
import argparse
from collections import Counter, OrderedDict
from dataclasses import dataclass
from fractions import Fraction
import json
from pathlib import Path
import subprocess

from measure_vm_cache_storage import aligned, load_images
from replay_vm_cache import simulate, shipping_replay


@dataclass
class Entry:
    raw: int
    compressed: int
    offset: int
    stored: int
    packed: bool = False
    pins: int = 0
    reuse: int = 0


class PhysicalCache:
    def __init__(self, payload, slots, packed_sizes, dictionary=256, minimum_saving=8):
        if payload < 32 or payload % 8 or slots < 1 or dictionary < 0 or dictionary % 8 or minimum_saving < 8:
            raise ValueError('invalid cache configuration')
        self.payload, self.slots = payload, slots
        self.packed_sizes, self.dictionary = packed_sizes, dictionary
        self.minimum_saving = minimum_saving
        self.entries = OrderedDict()
        self.temporary = []
        self.begin_pass()

    def begin_pass(self):
        self.metrics = dict(hits=0, raw_hits=0, packed_hits=0, misses=0, fallback=0,
                            evictions=0, packs=0, thaws=0, packed_input_bytes=0,
                            thawed_output_bytes=0, codec_copy_bytes=0, compactions=0,
                            compacted_bytes=0, pack_blocked=0, fragmentation_blocked=0,
                            peak_cache_payload=self.used(), peak_borrowed_staging=0,
                            peak_cache_and_borrowed=self.used(),
                            miss_modules=Counter(), packed_modules=Counter(),
                            thawed_modules=Counter(), evicted_modules=Counter())

    def spans(self):
        return [(e.offset, aligned(e.stored)) for e in self.entries.values() if e.stored] + self.temporary

    def used(self):
        return sum(n for _, n in self.spans())

    def peak(self, borrowed=0):
        used = self.used()
        self.metrics['peak_cache_payload'] = max(self.metrics['peak_cache_payload'], used)
        self.metrics['peak_borrowed_staging'] = max(self.metrics['peak_borrowed_staging'], borrowed)
        self.metrics['peak_cache_and_borrowed'] = max(self.metrics['peak_cache_and_borrowed'], used + borrowed)
        self.check()

    def check(self):
        spans = sorted(self.spans())
        assert len(self.entries) <= self.slots and self.used() <= self.payload
        assert all(at >= 0 and at % 8 == 0 and size > 0 and size % 8 == 0 and at + size <= self.payload for at, size in spans)
        assert all(a + n <= b for (a, n), (b, _) in zip(spans, spans[1:])), spans
        # A compressed source may be temporarily pinned by the decoder; it
        # must never be exposed as an executable image by request(hold=True).
        assert all(e.pins >= 0 for e in self.entries.values())

    def hole(self, wanted):
        at = 0
        for offset, size in sorted(self.spans()):
            if offset - at >= wanted:
                return at
            at = max(at, offset + size)
        return at if self.payload - at >= wanted else None

    def compact(self):
        if self.temporary or any(e.pins for e in self.entries.values()):
            return False
        at, moved = 0, 0
        for e in sorted(self.entries.values(), key=lambda e: e.offset):
            if not e.stored:
                continue
            if e.offset != at:
                moved += e.stored
                e.offset = at
            at += aligned(e.stored)
        if moved:
            self.metrics['compactions'] += 1
            self.metrics['compacted_bytes'] += moved
        return bool(moved)

    def candidates(self, protected=None):
        # OrderedDict is recency tie-break, matching shipping density.
        return sorted((k for k, e in self.entries.items() if k != protected and not e.pins),
                      key=lambda k: Fraction(self.entries[k].reuse, aligned(self.entries[k].raw)))

    def age(self):
        for e in self.entries.values():
            e.reuse //= 2

    def evict(self, protected=None):
        choices = self.candidates(protected)
        if not choices:
            return False
        key = choices[0]
        del self.entries[key]
        self.age()
        self.metrics['evictions'] += 1
        self.metrics['evicted_modules'][str(key[0])] += 1
        return True

    def pack(self, key, staging, occupied=0):
        e = self.entries[key]
        packed = aligned(e.compressed)
        if e.pins or e.packed or aligned(e.raw) - packed < self.minimum_saving:
            return False
        # May compact BEFORE pinning source or reserving codec temporaries.
        self.compact()
        available = staging - occupied
        dictionary_external = min(self.dictionary, available)
        dictionary_cache = self.dictionary - dictionary_external
        borrowed = occupied + dictionary_external
        scratch = None
        if dictionary_cache:
            scratch = self.hole(dictionary_cache)
            if scratch is None:
                self.metrics['pack_blocked'] += 1
                return False
            self.temporary.append((scratch, dictionary_cache))
        output_external = staging - borrowed >= packed
        destination = None if output_external else self.hole(packed)
        if not output_external and destination is None:
            if self.used() + packed <= self.payload:
                self.metrics['fragmentation_blocked'] += 1
            if scratch is not None:
                self.temporary.remove((scratch, dictionary_cache))
            self.metrics['pack_blocked'] += 1
            return False
        if output_external:
            borrowed += packed
        else:
            self.temporary.append((destination, packed))
        self.peak(borrowed)
        # Source unchanged until the entire separate output exists. External
        # output is copied back into the old (now shrinkable) raw span.
        if not output_external:
            self.temporary.remove((destination, packed))
            e.offset = destination
        else:
            self.metrics['codec_copy_bytes'] += e.compressed
        if scratch is not None:
            self.temporary.remove((scratch, dictionary_cache))
        e.stored, e.packed = e.compressed, True
        self.metrics['packs'] += 1
        self.metrics['packed_input_bytes'] += e.raw
        self.metrics['packed_modules'][str(key[0])] += 1
        self.age()
        self.check()
        return True

    def ensure(self, wanted, staging=0, occupied=0, protected=None, need_slot=False):
        wanted = aligned(wanted)
        if wanted > self.payload:
            return None
        while need_slot and len(self.entries) >= self.slots:
            if not self.evict(protected):
                return None
        while True:
            at = self.hole(wanted)
            if at is not None:
                return at
            self.compact()
            at = self.hole(wanted)
            if at is not None:
                return at
            if self.used() + wanted <= self.payload:
                self.metrics['fragmentation_blocked'] += 1
            if any(self.pack(k, staging, occupied) for k in self.candidates(protected)):
                continue
            if not self.evict(protected):
                return None

    def request(self, identifier, raw, language=1, miss_staging=0, thaw_staging=0, hold=False):
        if not 0 <= identifier < 0xFFFF or raw < 32 or language not in (1, 2) or min(miss_staging, thaw_staging) < 0:
            raise ValueError('invalid request')
        # Staging tails are aligned, including a possible partial dictionary.
        if miss_staging % 8 or thaw_staging % 8:
            raise ValueError('unaligned staging')
        key = identifier, language
        e = self.entries.get(key)
        if e is not None:
            if e.raw != raw:
                raise ValueError('source changed without cache invalidation')
            self.metrics['hits'] += 1
            if e.packed:
                self.metrics['packed_hits'] += 1
                # Either retain the pinned compressed source in the cache,
                # or copy it into bounded staging before reclaiming its span.
                staged = aligned(e.stored) if aligned(e.stored) <= thaw_staging else 0
                if staged:
                    self.metrics['codec_copy_bytes'] += e.stored
                    self.peak(staged)
                    e.stored = 0
                else:
                    e.pins = 1
                at = self.ensure(raw, thaw_staging, staged, protected=key)
                if at is None:
                    e.pins = 0
                    # A staged source may have lost its old span. Dropping a
                    # cache-only copy is safe; count fallback, never a free hit.
                    if staged:
                        del self.entries[key]
                    self.metrics['fallback'] += 1
                    self.check()
                    return None
                self.temporary.append((at, aligned(raw)))
                self.peak(staged)
                self.temporary.remove((at, aligned(raw)))
                e.offset, e.stored, e.packed, e.pins = at, raw, False, 0
                self.metrics['thaws'] += 1
                self.metrics['thawed_output_bytes'] += raw
                self.metrics['thawed_modules'][str(identifier)] += 1
            else:
                self.metrics['raw_hits'] += 1
            e.reuse = min(255, e.reuse + 1)
            self.entries.move_to_end(key)
        else:
            self.metrics['misses'] += 1
            self.metrics['miss_modules'][str(identifier)] += 1
            at = self.ensure(raw, miss_staging, need_slot=True)
            if at is None:
                self.metrics['fallback'] += 1
                return None
            packed = self.packed_sizes.get(key, raw)
            if packed <= 0:
                raise ValueError('invalid compressed size')
            e = Entry(raw, packed, at, raw)
            self.entries[key] = e
        e.pins += int(hold)
        self.peak()
        return key

    def release(self, key):
        if key not in self.entries or not self.entries[key].pins:
            raise ValueError('invalid release')
        self.entries[key].pins -= 1
        self.check()

    def result(self):
        self.check()
        # Freeze nested counters too: the next cycle's UI prelude executes
        # before begin_pass(), and must not mutate an already saved window.
        frozen = {k: dict(v) if isinstance(v, Counter) else v for k, v in self.metrics.items()}
        m = dict(frozen, used=self.used(), resident_modules=len(self.entries),
                 resident_packed=sum(e.packed for e in self.entries.values()))
        # Packed hits that cannot thaw still need ordinary reload/VM fallback.
        m['loads_required'] = m['misses'] + m['packed_hits'] - m['thaws']
        return m


def replay(requests, payload, slots, packed_sizes, repeats=3, miss_staging=0, thaw_staging=0, dictionary=256, window=None):
    if not 1 <= repeats <= 10:
        raise ValueError('repeats must be 1..10')
    cache = PhysicalCache(payload, slots, packed_sizes, dictionary)
    start, end = window if window is not None else (0, len(requests))
    if not 0 <= start <= end <= len(requests):
        raise ValueError('invalid measured window')
    result = []
    for _ in range(repeats):
        for i, raw, language in requests[:start]:
            cache.request(i, raw, language, miss_staging, thaw_staging)
        cache.begin_pass()
        for i, raw, language in requests[start:end]:
            cache.request(i, raw, language, miss_staging, thaw_staging)
        result.append(cache.result())
        for i, raw, language in requests[end:]:
            cache.request(i, raw, language, miss_staging, thaw_staging)
    return result


def analyze(trace, images, measurements, repeats=3, qualification=None):
    modules = {(m['language'], m['source_crc']): m for m in trace['modules']}
    if len(modules) != len(trace['modules']) or len({k[1] for k in modules}) != len(modules):
        raise ValueError('duplicate/cross-language CRC alias')
    by_crc = {key[1]: (n, images[key]['raw'], key[0]) for n, key in enumerate(sorted(modules), 1)}
    requests = [by_crc[c] for c in trace['run_order']]
    if Counter(trace['run_order']) != Counter({k[1]: m['runs'] for k, m in modules.items()}):
        raise ValueError('incomplete trace')
    descriptions = [{**images[key], 'id': by_crc[key[1]][0], 'runs': modules[key]['runs']} for key in sorted(modules)]
    packed = {(d['id'], d['language']): measurements[d['name']]['lzss']['bytes'] for d in descriptions}
    native = shipping_replay(requests, repeats, 1)
    unchanged = replay(requests, native['payload'], native['slots'], {}, repeats)
    fields = ('hits', 'misses', 'evictions', 'fallback', 'used')
    if [{k: r[k] for k in fields} for r in unchanged] != native['passes']:
        raise AssertionError('physical uncompressed model disagrees with shipping C++')
    if simulate(requests, native['payload'], native['slots'], repeats, 'density') != native['passes']:
        raise AssertionError('capacity model disagrees with shipping C++')
    window = None
    device_match = None
    if qualification is not None:
        if repeats < 2 or qualification.get('status') != 'PASS':
            raise ValueError('warm qualification needs PASS and at least two passes')
        window = qualification['start'], qualification['end']
        actual = replay(requests, native['payload'], native['slots'], {}, repeats, window=window)
        names = {d['id']: d['name'] for d in descriptions}
        # Qualification has already joined bytecode size/name/source CRC and
        # exact request order. Here verify warm state, not just run counts.
        expected = {row['image']: row['misses'] for row in qualification['modules']}
        observed = {name: actual[1]['miss_modules'].get(str(i), 0) for i, name in names.items() if name in expected}
        if observed != expected:
            raise AssertionError(('warm module miss attribution differs from device', observed, expected))
        device_match = dict(status='PASS', warm_misses=sum(observed.values()), by_module=observed)
    cases = {}
    for extra in (0, 32):
        for label, miss, thaw in (('cache_only', 0, 0), ('warm_prefix_only', 0, 4176),
                                  ('always_prefix_optimistic_control', 4176, 4176)):
            cases[f'{label}_metadata_plus_{extra}'] = dict(
                extra_metadata=extra, payload=native['payload'] - extra,
                miss_staging=miss, thaw_staging=thaw, dictionary=256,
                feasibility='not feasible at compiler-owned cold reserve' if miss else
                            'lifetime/metadata/Flash/stack implementation still required',
                passes=replay(requests, native['payload'] - extra, native['slots'], packed, repeats, miss, thaw, window=window))
    return dict(cache={k: native[k] for k in ('budget', 'payload', 'metadata', 'slots')},
                requests=len(requests), measured_window=window, modules=descriptions,
                shipping_cpp_full_cycle=native['passes'],
                shipping_density_window=replay(requests, native['payload'], native['slots'], {}, repeats, window=window),
                warm_device_miss_match=device_match, scenarios=cases,
                qualification='Physical capacity/operation model and host roundtrip, NOT ARM cycles or device speedup.',
                notes=['The 256-byte dictionary is charged against staging and/or cache payload in every pack.',
                       'All source/output spans coexist; temporary spans and compaction copies are counted.',
                       'Packing retains raw-size density scores; compression does not create directory slots.',
                       'Only all-unpinned compaction is allowed; no pinned image can move, pack or evict.',
                       'Actual trace has sequential released images; independent pinned stress tests cover allocator safety.',
                       'Warm-prefix staging is borrowed workspace, not new RAM; compiler-owned phase gets zero staging.',
                       'Zero extra metadata assumes fields can be reused. Plus32 charges two extra bytes per slot.',
                       'Packed lengths are known offline; a firmware encoder must bound output or pay a sizing pass and failed attempts.',
                       'No firmware cache-policy change, filesystem writes, pin concurrency trace or real codec latency.'])


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--trace', type=Path, required=True)
    ap.add_argument('--images-dir', type=Path, required=True)
    ap.add_argument('--codec-probe', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--repeats', type=int, default=3)
    ap.add_argument('--qualification', type=Path, help='qualified WARM profile; also require per-module miss agreement')
    args = ap.parse_args()
    trace, images = json.loads(args.trace.read_text()), load_images(args.images_dir)
    measurements = {}
    for m in trace['modules']:
        image = images[m['language'], m['source_crc']]
        measured = json.loads(subprocess.check_output([str(args.codec_probe.resolve()), image['file']], text=True))
        if measured['raw_bytes'] != image['raw'] or not measured['lzss']['roundtrip']:
            raise AssertionError(image['file'])
        measurements[image['name']] = measured
    qualification = json.loads(args.qualification.read_text()) if args.qualification else None
    if qualification is not None and 'profiles' in qualification:
        if qualification.get('status') != 'PASS' or len(qualification['profiles']) != 1:
            raise ValueError('select exactly one qualified warm profile')
        qualification = next(iter(qualification['profiles'].values()))
    result = dict(status='PASS', measurements=measurements, report=analyze(trace, images, measurements, args.repeats, qualification))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: v['passes'][min(1, args.repeats - 1)] for k, v in result['report']['scenarios'].items()}, indent=2))


if __name__ == '__main__':
    main()
