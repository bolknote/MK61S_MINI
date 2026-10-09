#!/usr/bin/env python3
"""Research-only replay: detached resources and pressure-triggered RAM packing.

Capacity model, NOT a firmware implementation or a chess timing benchmark.
Packing accounts for simultaneous source/output bytes, but assumes usable
contiguous free space; real pinned-object fragmentation can be worse.
"""
import argparse
from collections import OrderedDict, Counter
from fractions import Fraction
import json
from pathlib import Path
import struct
import subprocess
import zlib

from replay_vm_cache import simulate, shipping_replay


def aligned(size):
    return (size + 7) & ~7


def load_images(directory):
    images = {}
    for path in sorted(directory.glob('*-owned.bvm')):
        data = path.read_bytes()
        if len(data) < 32 or data[:4] != b'LBV1' or data[4] not in (4,5,6,7) or data[5] not in (1,2):
            raise ValueError(f'unsupported image: {path}')
        if struct.unpack_from('<H', data, 8)[0] != len(data) or zlib.crc32(data[32:]) != struct.unpack_from('<I', data, 20)[0]:
            raise ValueError(f'image size/CRC: {path}')
        end = struct.unpack_from('<H', data, 30)[0] or len(data)
        if not 32 <= end <= len(data) or ((end < len(data)) != bool(data[7] & 4)) or (data[7] & 4 and not data[7] & 8):
            raise ValueError(f'non-owned/invalid resources: {path}')
        count, at = 0, end
        while at < len(data):
            if at + 2 > len(data): raise ValueError(f'resource header: {path}')
            at += 2 + struct.unpack_from('<H', data, at)[0]
            if at > len(data): raise ValueError(f'resource body: {path}')
            count += 1
        source = path.with_name(path.name.removesuffix('-owned.bvm') + '-source.bvm')
        recipe_bytes = None
        if source.exists():
            recipe = source.read_bytes()
            if recipe[:6] != data[:6] or recipe[16:20] != data[16:20] or struct.unpack_from('<H', recipe, 30)[0] != (end if end < len(data) else 0):
                raise ValueError(f'paired recipe mismatch: {path}')
            recipe_bytes = len(recipe) - end
        crc = struct.unpack_from('<I', data, 16)[0]
        key = data[5], crc
        if key in images: raise ValueError(f'ambiguous source/language: {path}')
        images[key] = {'file': str(path), 'name': path.name, 'raw': len(data),
                       'code': end, 'pool': len(data)-end, 'recipes': recipe_bytes,
                       'resources': count, 'version': data[4], 'language': data[5], 'crc': crc}
    return images


def packing_replay(requests, payload, slots, repeats, packed_sizes, staging_bytes=0,
                   minimum_saving=8, policy='density'):
    """Lazy packing; raw image required to run, current thaw source protected.

    staging_bytes=0: every pack/thaw output coexists inside the cache.
    >0: bounded EXISTING borrowed staging may hold a blob. Never interpreted
    as zero-RAM-cost firmware: availability and lifetime require verification.
    Hash dictionary is 256 bytes of temporary scratch, separately disclosed.
    """
    if policy not in ('density','lru') or payload <= 0 or slots <= 0 or not 1 <= repeats <= 10 or staging_bytes < 0:
        raise ValueError('invalid replay configuration')
    entries = OrderedDict()
    passes, peak = [], 0
    current = None
    def used(): return sum(e['stored'] for e in entries.values())
    def colder(key):
        e = entries[key]
        return Fraction(e['reuse'], e['raw']) if policy == 'density' else 0
    def candidates(protected=None):
        return sorted((k for k in entries if k != protected), key=colder)
    def age():
        if policy == 'density':
            for e in entries.values(): e['reuse'] //= 2
    def evict(protected=None):
        choices = candidates(protected)
        if not choices: return False
        victim = choices[0]
        del entries[victim]; age(); current['evictions'] += 1
        current['evicted_modules'][str(victim[0])] += 1
        return True
    def compress(key, staged=0):
        nonlocal peak
        e = entries[key]
        if e['packed'] or e['raw']-e['compressed'] < minimum_saving: return False
        temporary = e['compressed']
        if staged + temporary <= staging_bytes:
            current['peak_borrowed_staging'] = max(current['peak_borrowed_staging'], staged+temporary)
        elif used() + temporary <= payload:
            peak = max(peak, used()+temporary)
        else:
            current['pack_blocked_no_temporary_space'] += 1
            return False
        current['packs'] += 1; current['packed_input_bytes'] += e['raw']
        current['packed_modules'][str(key[0])] += 1
        e['stored'] = temporary; e['packed'] = True; age()
        return True
    def ensure(wanted, protected=None, need_slot=False, staged=0):
        if wanted > payload: return False
        while need_slot and len(entries) >= slots:
            if not evict(protected): return False
        while used() + wanted > payload:
            if any(compress(k,staged) for k in candidates(protected)): continue
            if not evict(protected): return False
        return True
    for _ in range(repeats):
        current = {'hits':0,'misses':0,'evictions':0,'fallback':0,'used':0,
                   'packs':0,'thaws':0,'packed_input_bytes':0,'thawed_output_bytes':0,
                   'peak_borrowed_staging':0,'pack_blocked_no_temporary_space':0,
                   'miss_modules':Counter(),'packed_modules':Counter(),'thawed_modules':Counter(),'evicted_modules':Counter()}
        for identifier, raw, language in requests:
            key = identifier, language
            if key in entries:
                current['hits'] += 1
                e = entries[key]
                if e['packed']:
                    original = e['stored']; staged = 0
                    if original <= staging_bytes:
                        # Blob copied out before reclaiming its cache span.
                        staged=original; e['stored']=0
                        current['peak_borrowed_staging']=max(current['peak_borrowed_staging'],staged)
                    if not ensure(e['raw'],protected=key,staged=staged):
                        e['stored']=original; current['fallback'] += 1; continue
                    peak=max(peak,used()+e['raw'])
                    e['stored']=e['raw'];e['packed']=False
                    current['thaws'] += 1;current['thawed_output_bytes'] += e['raw']
                    current['thawed_modules'][str(identifier)] += 1
                e['reuse']=min(255,e['reuse']+1);entries.move_to_end(key)
            else:
                current['misses'] += 1; current['miss_modules'][str(identifier)] += 1
                wanted=aligned(raw)
                if not ensure(wanted,need_slot=True): current['fallback'] += 1;continue
                packed=packed_sizes.get(identifier,raw)
                entries[key]={'raw':wanted,'compressed':aligned(packed),'stored':wanted,'packed':False,'reuse':0}
                peak=max(peak,used())
            assert used() <= payload and len(entries) <= slots
        current['used']=used();current['peak_cache_payload']=peak
        current['resident_packed']=sum(e['packed'] for e in entries.values())
        current['resident_modules']=len(entries)
        current['peak_cache_plus_borrowed_upper_bound']=peak+current['peak_borrowed_staging']
        passes.append(current)
    return passes


def analyze(trace, images, measurements, repeats=3, staging_sizes=(0,1600,4176)):
    modules = {(m['language'],m['source_crc']):m for m in trace['modules']}
    if len({k[1] for k in modules}) != len(modules): raise ValueError('cross-language CRC alias in old trace format')
    identifiers = {key:i+1 for i,key in enumerate(sorted(modules))}
    by_crc = {key[1]:identifiers[key] for key in modules}
    descriptions = []
    for key,identifier in identifiers.items():
        image=images[key]
        descriptions.append({'id':identifier,**image,'runs':modules[key]['runs']})
    by_id={d['id']:d for d in descriptions}
    order=[by_crc[crc] for crc in trace['run_order']]
    if len(order)!=sum(m['runs'] for m in modules.values()): raise ValueError('trace run count')
    requests=[(i,by_id[i]['raw'],by_id[i]['language']) for i in order]
    native=shipping_replay(requests,repeats,1)
    expected=simulate(requests,native['payload'],native['slots'],repeats,'density')
    if native['passes']!=expected: raise AssertionError('shipping C++/Python density mismatch')
    # A separate compact resource entry: 8-byte key + age/generation8 +
    # offset/size4 + pins/state2 + reuse2. Eight slots plus stats32 =224B.
    extra_metadata=8*24+32
    resource_bounds={}
    for label,recipe,payload in (('free_strings_no_extra_metadata',False,native['payload']),
                                ('free_strings_with_extra_metadata',False,native['payload']-extra_metadata),
                                ('source_recipes_with_extra_metadata',True,native['payload']-extra_metadata)):
        if recipe and any(d['recipes'] is None for d in descriptions): continue
        sizes=[(i,by_id[i]['code']+(by_id[i]['recipes'] if recipe else 0),by_id[i]['language']) for i in order]
        resource_bounds[label]={'payload_bytes':payload,'passes':simulate(sizes,payload,16,repeats,'density')}
    packing={}
    packed={i:measurements[by_id[i]['name']]['lzss']['bytes'] for i in by_id}
    for staging in staging_sizes:
        packing[str(staging)]={'borrowed_staging_limit':staging,
            'passes':packing_replay(requests,native['payload'],native['slots'],repeats,packed,staging)}
    hot=[d for d in descriptions if d['runs']>=40]
    return {'requests_per_pass':len(order),'modules':descriptions,'cache':{k:native[k] for k in ('budget','payload','metadata','slots')},
            'shipping_cpp_density':native['passes'],'resource_split_bounds':resource_bounds,
            'packing_lzss':packing,'frequent_set':{'selection':'modules with >=40 runs, descriptive only',
                'names':[d['name'] for d in hot],'owned_aligned_bytes':sum(aligned(d['raw']) for d in hot),
                'code_only_aligned_bytes':sum(aligned(d['code']) for d in hot)},
            'notes':['Resource-only models are optimistic bounds: strings cost no payload and no reload CPU/IO.',
                     'Recipe case retains current SOURCE recipe bytes; a runnable split-format linker may require additional indexing.',
                     'Packing is lazy, whole-image and does not increase the 24576-byte cache directory/payload budget.',
                     'Temporary source/output coexistence is charged; contiguous-hole fragmentation and concurrent pins are not modeled.',
                     'Borrowed staging is NOT new static allocation; availability during compiler/INPUT/VM phases is not yet established.',
                     'Only the unpinned inactive entries may be packed. No file writes, no device times, no firmware implementation.']}


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--trace',type=Path,action='append',required=True)
    ap.add_argument('--images-dir',type=Path,required=True)
    ap.add_argument('--codec-probe',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--repeats',type=int,default=3)
    args=ap.parse_args()
    if not 1<=args.repeats<=10:ap.error('repeats must be 1..10')
    images=load_images(args.images_dir)
    traces=[(p,json.loads(p.read_text())) for p in args.trace]
    needed={key for _,t in traces for key in ((m['language'],m['source_crc']) for m in t['modules'])}
    measurements={}
    for key in sorted(needed):
        image=images[key]
        measured=json.loads(subprocess.check_output([str(args.codec_probe.resolve()),image['file']],text=True))
        if measured['raw_bytes']!=image['raw'] or not measured['lzss']['roundtrip']:raise AssertionError(image['file'])
        measurements[image['name']]=measured
    reports={str(p):analyze(t,images,measurements,args.repeats) for p,t in traces}
    report={'status':'PASS','measurements':measurements,'traces':reports,
            'qualification':'Model and host codec roundtrip only. Not ARM/HIL speedup or production memory-layout validation.'}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    sample=min(1,args.repeats-1)
    for name,r in reports.items():
        print(name,'requests',r['requests_per_pass'],'repeat' if sample else 'cold','misses',r['shipping_cpp_density'][sample]['misses'])
        print('split bounds',{k:v['passes'][sample]['misses'] for k,v in r['resource_split_bounds'].items()})
        print('lazy LZSS',{k:{x:v['passes'][sample][x] for x in ('misses','packs','thaws','fallback','peak_cache_payload','peak_borrowed_staging')}
                           for k,v in r['packing_lzss'].items()})


if __name__=='__main__':main()
