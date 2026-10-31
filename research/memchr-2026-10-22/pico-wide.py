"""Offline oracle for Pico's allocated SRAM APP and mixed Flash/runtime calls.

The allocator chooses a fresh 8-byte-aligned base for every APP invocation.
Only the SDK entry locates that base; all other entries must match independent
ELF offsets and the pinned native provider. This module never opens a device.
"""
import json
from pathlib import Path
import statistics
import struct
import zlib
from check_stm32_vectors import ElfImage
from session import Hold,sha
from proof import body
import run as bench

SYMBOLS=['baseline','libc_search','byte_search','own4','own16','own64',
         'pair16','balanced16','pair64','balanced64','fast16','fast64',
         'memchr','@resident_memchr','indirect_search']
NAMES=['baseline','libc','byte','own4','own16','own64','pair16','balanced16',
       'pair64','balanced64','fast16','fast64','sdk','public_body','public_veneer']
FUNCTIONS=15
ROW_WORDS=118


def prepare(row,payload_elf,payload_layout,static_end,heap_limit,provider):
    """Verify container/code identity before accepting a reported allocation."""
    raw=Path(row['app']).read_bytes();elf=ElfImage(row['elf']);image=Path(row['raw_image']).read_bytes()
    manifest=json.loads(Path(row['manifest']).read_text());layout=json.loads(Path(payload_layout).read_text())
    kernels=ElfImage(payload_elf)
    if sha(raw)!=row['app_sha256'] or manifest['app_sha256']!=row['app_sha256']:raise Hold('Pico APP identity differs')
    if (manifest['cpu'],manifest['directory'],manifest['shared'],manifest['placement'])!=('m0',row['directory'],row['shared'],row['placement']):raise Hold('Pico APP manifest differs')
    if manifest['symbols']!=SYMBOLS or manifest['expected_runtime_count']!=27 or manifest['expected_services_size']!=32:raise Hold('Pico optional runtime contract differs')
    if manifest['report_version']!=4 or manifest['rows_per_chunk']!=7 or manifest['fp_base']!=36:raise Hold('Pico report layout differs')
    if raw[:8]!=b'MK61APP\0' or struct.unpack_from('<3H',raw,8)!=(1,64,6) or zlib.crc32(raw[:60])!=struct.unpack_from('<I',raw,60)[0]:raise Hold('Pico APP header differs')
    flags,base,stored,image_size,memory_size=struct.unpack_from('<5I',raw,16)
    section=elf.named_sections['.module_image']
    if not flags&4 or base!=0x20000000 or len(raw)!=64+stored or section[3]!=base or elf.bytes_at(section)!=image or len(image)!=image_size:raise Hold('Pico ELF/raw/container image differs')
    if zlib.crc32(image)!=struct.unpack_from('<I',raw,52)[0] or elf.symbols['__module_memory_end']-base!=memory_size:raise Hold('Pico image CRC/memory span differs')
    if layout['cpu']!='m0' or layout['elf_sha256']!=sha(kernels.data):raise Hold('Pico payload reference differs')
    if not 0x20000000<=static_end<heap_limit<=0x20041000 or memory_size>heap_limit-static_end:raise Hold('Pico APP does not fit the pinned heap')
    offsets=[];bodies={}
    for name in SYMBOLS:
        if name=='@resident_memchr':offsets.append(None);continue
        start=elf.symbols[name]&~1
        size=elf.sizes[name] if name!='libc_search' else layout['functions'][name]['bytes']
        reference_name=name
        if name=='memchr' and not row['shared']:reference_name='balanced64'
        if not size or not base<=start<start+size<=base+image_size:raise Hold('Pico function outside APP image')
        actual=image[start-base:start-base+size]
        if reference_name in layout['functions']:
            reference=layout['functions'][reference_name]
            if size!=reference['bytes'] or actual!=body(kernels,reference_name,size):raise Hold('Pico APP/payload function differs: '+name)
        offsets.append(start-base);bodies[name]=dict(bytes=size,sha256=sha(actual))
    fallback='mk61_memchr_fallback' if row['shared'] else 'memchr'
    size=elf.sizes[fallback]
    if body(elf,fallback,size)!=body(kernels,'balanced64',size):raise Hold('Pico local SDK fallback differs')
    # Provider comes from a separately checked sealed native ELF/full image;
    # an address supplied only by the report cannot establish this identity.
    if set(provider)!={'table','target','bytes','sha256'} or provider['bytes']!=size or provider['sha256']!=sha(body(kernels,'balanced64',size)):raise Hold('Pico native provider body differs')
    if not provider['target']&1 or not provider['table']%4==0:raise Hold('Pico native provider alignment differs')
    return dict(offsets=offsets,image_bytes=image_size,memory_bytes=memory_size,
        static_end=static_end,heap_limit=heap_limit,placement=row['placement'],shared=row['shared'],
        flash_pointers=[layout['functions'][n]['address'] for n in SYMBOLS[:12]],
        payload_crc32=int(layout['crc32'],16),provider=provider,
        fallback_offset=(elf.symbols[fallback]&~1)-base,bodies=bodies)


def bind(raw,proof):
    if len(raw)<256:raise Hold('Truncated Pico report')
    h=struct.unpack_from('<64I',raw)
    sdk=h[48]
    base=(sdk&~1)-proof['offsets'][12]
    if not sdk&1 or base%8 or base<proof['static_end'] or base+proof['memory_bytes']>proof['heap_limit']:raise Hold('Pico APP allocation outside pinned heap')
    pointers=[(base+offset)|1 if offset is not None else proof['provider']['target'] for offset in proof['offsets']]
    if proof['placement']=='flash':pointers[:12]=proof['flash_pointers']
    cached=proof['provider']['target'] if proof['shared'] else (base+proof['fallback_offset'])|1
    if h[36:51]!=tuple(pointers) or h[51]!=0 or h[13]!=proof['provider']['target'] or h[33]!=cached or h[35]!=proof['provider']['table']:raise Hold('Pico reported code/provider pointer differs')
    return dict(base=base,image_end=base+proof['image_bytes'],memory_end=base+proof['memory_bytes'],pointers=pointers,sdk_cached_target=cached)


def decode(raw,inputs,proof,full):
    if len(raw)!=256+ROW_WORDS*4*len(inputs):raise Hold('Pico report length differs')
    h=struct.unpack_from('<64I',raw)
    if h[:5]!=(0x4d435250,4,15,len(inputs),7) or h[15]!=125000000:raise Hold('Pico report header/clock differs')
    if h[11]!=3 or h[24]!=0x0a428502 or h[25]!=proof['payload_crc32'] or h[26:28]!=(4,27) or h[34]!=32:raise Hold('Pico ROM/payload/provider contract differs')
    bound=bind(raw,proof)
    if h[6] or h[54]!=6 or h[5]!=15*(len(inputs)+1)+(181500 if full else 0) or h[14]<200000:raise Hold('Pico correctness/warmup did not pass')
    rows=[]
    for i,expected in enumerate(inputs):
        words=struct.unpack_from('<118I',raw,256+i*472)
        if words[:6]!=tuple(expected):raise Hold('Pico row input differs')
        control=words[6:13];timings={}
        for f,name in enumerate(NAMES):
            samples=words[13+f*7:20+f*7]
            cycles=[125*(sample-empty)/expected[3] for sample,empty in zip(samples,control)]
            timings[name]=dict(raw_us=list(samples),paired_cycles=cycles,median_cycles=statistics.median(cycles))
        rows.append(dict(size=expected[0],offset=expected[1],value=expected[2],loops=expected[3],source=expected[4],mode=expected[5],
            prefix_bytes=bench.prefix(expected[0],expected[1],expected[2],expected[4],expected[5]),control_us=list(control),timings=timings))
    return dict(checks=h[5],clock=h[15],rows=rows,allocation=bound,public_runtime_present=True,
        sdk_first_call_raw_us=h[32],runtime_count=27,services_size=32,
        public_body='Native function pointer hoisted outside the timed loop',public_veneer='Actual public table load and dispatch on every call')


def validator(inputs,proof,full):
    """Recognize success or exact owned diagnostics for safe point cleanup."""
    def recognized(raw):
        try:
            decode(raw,inputs,proof,full)
            return True
        except Hold:
            if len(raw)!=256+ROW_WORDS*4*len(inputs):return False
            h=struct.unpack_from('<64I',raw)
            if h[:5]!=(0x4d435250,4,15,len(inputs),7) or h[15]!=125000000 or h[11]!=3 or h[24]!=0x0a428502:return False
            if h[6]!=1 or h[14] or any(raw[256:]):return False
            if h[54]==1 and h[25]!=proof['payload_crc32']:
                return h[5]==0 and not any(h[7:11]) and not h[13] and not any(h[26:28]) and not any(h[32:52])
            if h[54] not in (3,4) or h[25]!=proof['payload_crc32'] or h[26:28]!=(4,27) or h[34]!=32:return False
            try:bind(raw,proof)
            except Hold:return False
            return h[7]<15 and h[8]<=4096 and h[9]<=7
    return recognized
