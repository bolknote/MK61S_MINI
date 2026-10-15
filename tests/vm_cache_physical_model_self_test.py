#!/usr/bin/env python3
"""Physical mixed-cache research: dictionary, spans, pins, overlap, failures."""
from pathlib import Path
import random
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from model_vm_cache_packing import Entry, PhysicalCache, replay
from replay_vm_cache import simulate


def unchanged(requests):
    fields = ('hits', 'misses', 'evictions', 'fallback', 'used')
    actual = replay(requests, 23888, 16, {}, 3)
    assert [{k: r[k] for k in fields} for r in actual] == simulate(requests, 23888, 16, 3, 'density')
    assert not any(r['packs'] or r['thaws'] for r in actual)


unchanged([])
unchanged([(1, 128, 1)] * 300)
unchanged([(1, 30000, 1), (2, 96, 1), (2, 96, 2)] * 40)
rng = random.Random(0xCA617)
sizes = {i: rng.randrange(32, 9729) for i in range(40)}
requests = [(i, sizes[i], 1 + i % 2) for i in (rng.randrange(40) for _ in range(1800))]
unchanged(requests)

# UI prelude mutates/warm-starts the cache but is not charged to the measured
# search window. Repetition must preserve those state transitions.
windowed = replay([(1, 128, 1), (1, 128, 1), (2, 128, 1)], 256, 4, {}, 2, window=(1, 3))
assert (windowed[0]['hits'], windowed[0]['misses']) == (1, 1)
assert (windowed[1]['hits'], windowed[1]['misses']) == (2, 0)
assert windowed[0]['miss_modules'] == {'2': 1} and windowed[1]['miss_modules'] == {}
prelude = replay([(1, 128, 1), (2, 128, 1)], 128, 4, {}, 3, window=(1, 2))
assert all(r['miss_modules'] == {'2': 1} and r['misses'] == 1 for r in prelude)

# The old aggregate model ignored the codec's 256-byte dictionary. Output64
# alone is insufficient: the raw source192 + dictionary + output must coexist.
small = [(1, 192, 1), (2, 192, 1)] * 12
packed = {(1, 1): 64, (2, 1): 64}
for staging in (0, 64):
    rows = replay(small, 320, 8, packed, 2, staging, staging)
    assert all(r['packs'] == 0 for r in rows), (staging, rows)
rows = replay(small, 320, 8, packed, 2, 256, 256)
assert rows[1]['misses'] == 0 and rows[1]['thaws'] > 0 and rows[1]['loads_required'] == 0, rows
assert all(r['peak_borrowed_staging'] <= 256 and r['peak_cache_payload'] <= 320 for r in rows)

# No new directory entries, no execution of an image larger than payload.
rows = replay([(i, 64, 1) for i in range(8)] * 3, 1024, 4, {(i, 1): 32 for i in range(8)}, 2, 320, 320)
assert all(r['resident_modules'] <= 4 for r in rows)
rows = replay([(1, 2000, 1)] * 3, 1024, 4, packed, 2, 4096, 4096)
assert all(r['fallback'] == r['misses'] == r['loads_required'] == 3 and r['used'] == 0 for r in rows)

# Fixture with two separated 128-byte holes. A live pointer blocks global
# compaction, even when aggregate free bytes would suffice for request192.
cache = PhysicalCache(512, 8, {})
for i in range(1, 5):
    cache.request(i, 128, hold=i == 2)
del cache.entries[(1, 1)], cache.entries[(3, 1)]
offset = cache.entries[(2, 1)].offset
cache.begin_pass()
cache.request(5, 192)
assert cache.metrics['fragmentation_blocked'] and cache.metrics['evictions'] == 1
assert cache.entries[(2, 1)].offset == offset and cache.entries[(2, 1)].pins == 1
cache.release((2, 1))
cache.compact()
assert cache.metrics['compacted_bytes'] > 0
cache.check()

# Every live pointer survives an impossible allocation without packing,
# eviction or compaction; releasing it lets the same request succeed.
cache = PhysicalCache(256, 4, {(1, 1): 32})
key = cache.request(1, 256, hold=True)
offset = cache.entries[key].offset
assert cache.request(2, 128, miss_staging=320) is None
assert cache.entries[key].offset == offset and cache.metrics['packs'] == cache.metrics['evictions'] == 0
cache.release(key)
assert cache.request(2, 128, miss_staging=320) is not None

# A packed hit that cannot thaw is a reload, not an execution/free speedup.
# Staged-source failure may discard only that cache copy; the pinned peer is
# immutable. Test both retained-source and staged-source paths.
for staging in (0, 64):
    cache = PhysicalCache(256, 4, packed)
    cache.entries[(1, 1)] = Entry(192, 64, 0, 64, packed=True)
    cache.entries[(2, 1)] = Entry(192, 64, 64, 192, pins=1)
    cache.begin_pass()
    assert cache.request(1, 192, thaw_staging=staging) is None
    result = cache.result()
    assert result['packed_hits'] == result['fallback'] == result['loads_required'] == 1
    assert result['thaws'] == 0 and cache.entries[(2, 1)].offset == 64
    assert ((1, 1) not in cache.entries) == bool(staging)

# Languages remain distinct; source revision changes cannot silently reuse
# an old image. Packing while a peer is pinned must leave its offset stable.
cache = PhysicalCache(512, 4, {(1, 1): 40, (1, 2): 40})
a = cache.request(1, 192, 1, hold=True)
b = cache.request(1, 192, 2)
assert a != b and cache.pack(b, 320)
assert cache.entries[a].offset == 0 and not cache.entries[a].packed
try:
    cache.request(1, 200, 1)
except ValueError:
    pass
else:
    raise AssertionError('source changed without revision invalidation')

for miss, thaw in ((0, 0), (0, 4176), (1600, 1600), (4176, 4176)):
    packed = {(i, 1 + i % 2): max(16, sizes[i] // 2) for i in sizes}
    rows = replay(requests, 23888, 16, packed, 3, miss, thaw)
    assert all(r['peak_cache_payload'] <= 23888 and r['peak_borrowed_staging'] <= max(miss, thaw) for r in rows)
    assert all(r['hits'] == r['raw_hits'] + r['packed_hits'] and r['fallback'] == 0 for r in rows)
    assert all(r['hits'] + r['misses'] == len(requests) for r in rows)
    assert all(sum(r['miss_modules'].values()) == r['misses'] and
               sum(r['packed_modules'].values()) == r['packs'] and
               sum(r['thawed_modules'].values()) == r['thaws'] for r in rows)

print('VM physical cache model: shipping density match, dictionary charge, disjoint spans, pins/fragmentation, thaw failure, slots, fuzz PASS')
