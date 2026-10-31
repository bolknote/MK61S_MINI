"""Bounded identity oracle for the frozen Classic SRAM APP, not timing data."""
from pathlib import Path
import struct
import zlib
from session import Hold,sha
from check_stm32_vectors import ElfImage

NAMES=('baseline','libc_search','byte_search','own4','own16','own64','indirect_search','swar16')

def geometry(app_path,elf_path,raw_image_path,kernels_path,layout_path,static_end,guard,names=NAMES):
    import json
    app=Path(app_path).read_bytes();elf=ElfImage(elf_path);image=Path(raw_image_path).read_bytes()
    if app[:8]!=b'MK61APP\0' or struct.unpack_from('<3H',app,8)!=(1,64,6):raise Hold('Unknown APP container')
    if zlib.crc32(app[:60])!=struct.unpack_from('<I',app,60)[0]:raise Hold('APP header CRC differs')
    flags,base,stored,image_size,memory_size=struct.unpack_from('<5I',app,16)
    if not flags&4 or base!=0x20000000 or len(app)!=64+stored:raise Hold('APP is not the expected relocatable image')
    section=elf.named_sections['.module_image']
    if section[3]!=base or elf.bytes_at(section)!=image or len(image)!=image_size or zlib.crc32(image)!=struct.unpack_from('<I',app,52)[0]:raise Hold('ELF/raw/container image identity differs')
    if elf.symbols['__module_memory_end']-base!=memory_size:raise Hold('APP memory span differs')
    capacity=(memory_size+31)&~31
    actual_base=guard-capacity
    if static_end>actual_base or actual_base%32 or actual_base+memory_size>guard:raise Hold('APP allocation does not fit guarded dynamic RAM')
    kernels=ElfImage(kernels_path);layout=json.loads(Path(layout_path).read_text())
    if layout['elf_sha256']!=sha(Path(kernels_path).read_bytes()):raise Hold('Kernel reference changed')
    bodies={};pointers=[]
    for name in names:
        start=elf.symbols[name]&~1
        if name in layout['functions']:
            entry=layout['functions'][name]
            size=entry['bytes'];reference_start=kernels.symbols[entry.get('reference_symbol',name)]&~1
            reference_section=next(s for s in kernels.sections if s[2]&4 and s[3]<=reference_start and reference_start+size<=s[3]+s[5])
            at=reference_section[4]+reference_start-reference_section[3];reference=kernels.data[at:at+size]
        else:size=elf.sizes[name];reference=None
        if not size or not base<=start<start+size<=base+image_size:raise Hold('Function body outside APP image')
        body=image[start-base:start-base+size]
        if reference is not None and body!=reference:raise Hold('APP/kernel body identity differs: '+name)
        actual=start+actual_base-base
        if not actual_base<=actual<actual+size<=actual_base+image_size:raise Hold('Relocated body outside image')
        pointers.append(actual|1);bodies[name]=dict(bytes=size,sha256=sha(body),linked=hex(start|1),actual=hex(actual|1))
    return dict(base=actual_base,delta=actual_base-base,image_end=actual_base+image_size,memory_end=actual_base+memory_size,
        capacity=capacity,static_end=static_end,guard=guard,pointers=pointers,bodies=bodies)

def validate_pointers(raw,proof):
    if len(raw)<256:raise Hold('Truncated report')
    h=struct.unpack_from('<64I',raw)
    if tuple(h[16:24])!=tuple(proof['pointers']) or h[13]!=proof['pointers'][5]:raise Hold('Report does not match the bounded relocated APP')
    return True
