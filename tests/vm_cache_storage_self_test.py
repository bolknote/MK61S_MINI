#!/usr/bin/env python3
"""Research replay bounds, source/output coexistence and image corruption."""
from pathlib import Path
import random
import struct
import sys
import tempfile
import zlib
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from measure_vm_cache_storage import aligned, load_images, packing_replay
from replay_vm_cache import simulate

def fields(row):
    return {k:row[k] for k in ('hits','misses','evictions','fallback','used')}

def unchanged(requests):
    for policy in ('density','lru'):
        old=simulate(requests,23888,16,3,policy)
        actual=packing_replay(requests,23888,16,3,{},policy=policy)
        assert old==[fields(x) for x in actual],(policy,old,actual)
        assert not any(x['packs'] or x['thaws'] for x in actual)

unchanged([])
unchanged([(1,128,1)]*300)
unchanged([(1,30000,1),(2,96,1),(2,96,2)]*40)
rng=random.Random(0xCA61)
sizes={i:rng.randint(32,9728) for i in range(40)}
unchanged([(i,sizes[i],rng.randint(1,2)) for i in (rng.randrange(40) for _ in range(1800))])

# Capacity alone must not allow a packed source to disappear during thaw.
# Two 192-byte raw images fit only after packing. Packing uses a separate
# 64-byte temporary span, then thaw requires 192 bytes plus its source64.
req=[(1,192,1),(2,192,1)]*20
strict=packing_replay(req,320,8,2,{1:64,2:64})
assert strict[1]['misses']==0 and strict[1]['thaws']>0,strict
assert max(x['peak_cache_payload'] for x in strict)==320
assert all(x['peak_borrowed_staging']==0 and x['fallback']==0 for x in strict)

# Full cache + no temporary output is not an in-place compressor.
# A claimed 32-byte packing result cannot be produced into a 24-byte gap.
no_room=packing_replay([(1,200,1),(2,200,1)],224,8,1,{1:32,2:32})
assert no_room[0]['packs']==0 and no_room[0]['evictions']==1
assert no_room[0]['pack_blocked_no_temporary_space']>0
borrowed=packing_replay([(1,200,1),(2,200,1)],224,8,1,{1:32,2:32},staging_bytes=32)
assert borrowed[0]['packs']>0 and borrowed[0]['peak_borrowed_staging']<=32

# Compression does not create directory entries or let an oversized image run.
slots=packing_replay([(i,64,1) for i in range(8)]*3,1024,4,2,{i:32 for i in range(8)},64)
assert all(x['resident_modules']<=4 for x in slots)
oversized=packing_replay([(1,2000,1)]*3,1024,4,2,{1:64},64)
assert all(x['fallback']==3 and x['used']==0 for x in oversized)

for staging in (0,32,256,1600):
    req=[(i,sizes[i],1+i%2) for i in (rng.randrange(40) for _ in range(1800))]
    packed={i:max(32, sizes[i]//2) for i in sizes}
    result=packing_replay(req,23888,16,3,packed,staging)
    assert all(x['peak_cache_payload']<=23888 and x['peak_borrowed_staging']<=staging and x['fallback']==0 for x in result)

def image(pool=b'',version=7):
    data=bytearray(38)+pool;data[:4]=b'LBV1';data[4:8]=bytes((version,1,1,12 if pool else 0))
    struct.pack_into('<HHHH',data,8,len(data),36,1,5)
    struct.pack_into('<I',data,16,0x12345678)
    struct.pack_into('<H',data,30,38 if pool else 0)
    data[32:38]=bytes((10,0,36,0,64,0))
    struct.pack_into('<I',data,20,zlib.crc32(data[32:]))
    return data

with tempfile.TemporaryDirectory(prefix='mk61-vm-storage-test-') as temp:
    path=Path(temp)/'test-owned.bvm'
    path.write_bytes(image(b'\x03\0ABC'))
    loaded=load_images(Path(temp))[(1,0x12345678)]
    assert (loaded['code'],loaded['pool'],loaded['resources'])==(38,5,1)
    for data in (image(version=8), image(b'\xFF\xFFABC')):
        path.write_bytes(data)
        try: load_images(Path(temp))
        except ValueError: pass
        else:raise AssertionError('invalid image accepted')
    data=image();data[-1]^=1;path.write_bytes(data)
    try:load_images(Path(temp))
    except ValueError:pass
    else:raise AssertionError('bad CRC accepted')

print('VM cache storage models: unchanged LRU/density, staging, simultaneous thaw, slots, fallback, fuzz and image CRC PASS')
