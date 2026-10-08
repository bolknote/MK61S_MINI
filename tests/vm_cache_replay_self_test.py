#!/usr/bin/env python3
"""Both research/production C++ caches agree with bounded replay models."""
import random
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from replay_vm_cache import simulate, shipping_replay


def check(requests):
    for mode, policy in ((0, 'lru'), (1, 'density')):
        actual = shipping_replay(requests, 3, mode)
        modeled = simulate(requests, actual['payload'], actual['slots'], 3, policy)
        assert modeled == actual['passes'], (policy, modeled, actual)
        assert actual['payload'] == 23888 and actual['metadata'] == 688
    return actual


check([(1, 128, 1)] * 300)
check([])
check([(i, 64 + 31 * i, 1 + i % 2) for i in range(40)] * 8)
check([(1, 30000, 1), (2, 96, 2), (2, 96, 1)] * 40)  # fallback and language key
rng = random.Random(0x61CA)
sizes = {i: rng.randint(32, 9728) for i in range(48)}
for _ in range(3):
    requests = []
    for _ in range(1800):
        identifier = rng.randrange(48)
        requests.append((identifier, sizes[identifier], rng.randint(1, 2)))
    check(requests)

# Aging must let a completely different working set become hot.
old = [(i, 1024, 1) for i in range(8)] * 40
scan = [(i, 4096, 1) for i in range(20, 44)]
new = [(i, 1024, 2) for i in range(60, 68)] * 40
result = check(old + scan + new)
assert result['passes'][1]['misses'] <= 40
print('VM cache replay: LRU/density exact C++ match, sizes, languages, fallback, fuzz and phase aging PASS')
