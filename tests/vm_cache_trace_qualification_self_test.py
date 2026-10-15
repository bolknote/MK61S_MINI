#!/usr/bin/env python3
"""Fail closed on partial, aliased, mismatched and reordered host/device traces."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from qualify_vm_cache_trace import fingerprint, parse_profile, qualify
from replay_vm_mixed_cache import validate_qualification
from copy import deepcopy

assert fingerprint([]) == 14695981039346656037
assert fingerprint([42, 42]) == 10178788028133461333
assert fingerprint([1, 2]) != fingerprint([2, 1])
images = {(1, 11): dict(name='game-a-owned.bvm', raw=64),
          (1, 22): dict(name='game-b-owned.bvm', raw=128)}
trace = dict(modules=[dict(language=1, source_crc=11, runs=3), dict(language=1, source_crc=22, runs=2)],
             run_order=[11, 11, 22, 11, 22])
text = f'''VMCACHE dropped=0
VMCACHE_ORDER count=4 fnv64={fingerprint([3, 4, 3, 4])}
VMCACHE id=3 bytes=64 hits=1 misses=1 name=a
VMCACHE id=4 bytes=128 hits=1 misses=1 name=b
'''
result = qualify(trace, images, parse_profile(text), 'game-')
assert result['start'] == 1 and result['end'] == 5 and result['requests'] == 4
assert result['window_requests'] == [(3, 64, 1), (4, 128, 1), (3, 64, 1), (4, 128, 1)]
validate_qualification(trace, images, result)


def invalid_saved(qualified=result, replay_trace=trace, replay_images=images):
    try:
        validate_qualification(replay_trace, replay_images, qualified)
    except (ValueError, KeyError):
        return
    raise AssertionError('saved qualification accepted different replay inputs')


invalid_saved(replay_trace={**trace, 'run_order': [11, 22, 11, 11, 22]})  # Same counts, reordered window.
invalid_saved(replay_images={**images, (1, 11): dict(name='game-a-owned.bvm', raw=72)})
invalid_saved({**result, 'end': 4})
invalid_saved({**result, 'fnv64': result['fnv64'] ^ 1})
invalid_saved({**result, 'window_requests': list(reversed(result['window_requests']))})
invalid_saved({**result, 'modules': result['modules'] + result['modules'][:1]})
changed = deepcopy(result)
changed['modules'][0]['hits'] += 1
invalid_saved(changed)


def invalid(text=text, trace=trace, images=images):
    try:
        qualify(trace, images, parse_profile(text), 'game-')
    except (ValueError, KeyError):
        return
    raise AssertionError('invalid qualification accepted')


invalid(text.replace('dropped=0', 'dropped=1'))
invalid(text.replace('count=4', 'count=4294967295'))
invalid(text + text)
invalid(text.replace('hits=1 misses=1 name=a', 'hits=0 misses=1 name=a'))
invalid(text.replace('bytes=64', 'bytes=72'))
invalid(text.replace('name=b', 'name=a'))
invalid(text.replace(str(fingerprint([3, 4, 3, 4])), str(fingerprint([4, 3, 3, 4]))))
invalid(trace={**trace, 'run_order': [22, 22, 11, 11, 11]})  # Same counts, wrong order.
invalid(trace={**trace, 'run_order': trace['run_order'][:-1]})
invalid(trace={**trace, 'modules': trace['modules'] + [dict(language=2, source_crc=11, runs=1)]})
invalid(trace=dict(modules=[dict(language=1, source_crc=11, runs=4), dict(language=1, source_crc=22, runs=4)],
                   run_order=[11, 22, 11, 22] * 2))  # Multiple identical windows.
print('VM cache trace qualification: exact order/count/size, partial/saturated/alias/ambiguity rejection PASS')
