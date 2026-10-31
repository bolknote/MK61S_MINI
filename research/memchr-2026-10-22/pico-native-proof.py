#!/usr/bin/env python3
"""Verify the exact sealed Pico BIN/ELF, optional provider and heap budget.

Preparation only: this program reads local artifacts and never opens USB.
The full-device candidate must additionally preserve the freshly read Flash
tail/settings and prove an unused payload span in the hardware transaction.
"""
import argparse
import json
from pathlib import Path
import struct
import sys

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT/'tests'));sys.path.insert(0,str(ROOT/'tools'))
from check_stm32_vectors import ElfImage
from seal_picocalc import verify as verify_footer
from session import Hold,sha
from proof import body
from pico_payload import verify as verify_payload

BASE=0x10000000


def verify(elf_path,bin_path,layout_path,min_heap=0):
    payload_folder=Path(layout_path).parent
    payload_proof=verify_payload(payload_folder/'payload.bin',payload_folder/'kernels.elf',layout_path)
    elf=ElfImage(elf_path);image=Path(bin_path).read_bytes()
    reconstructed=bytearray(len(image));spans=[]
    for kind,offset,vaddr,paddr,size,_mem,flags,_align in elf.segments:
        if kind!=1 or not size:continue
        at=paddr-BASE
        if not 0<=at<=len(image)-size:raise Hold('Pico ELF initializer outside sealed BIN')
        if any(at<hi and lo<at+size for lo,hi in spans):raise Hold('Overlapping Pico Flash initializers')
        spans.append((at,at+size));reconstructed[at:at+size]=elf.data[offset:offset+size]
    if reconstructed!=image:raise Hold('Pico ELF does not reproduce every sealed BIN byte')
    footer=elf.symbols['mk61_picocalc_firmware_footer']-BASE
    integrity=verify_footer(image,footer)
    def read_at(address,size):
        for kind,offset,vaddr,paddr,count,_mem,_flags,_align in elf.segments:
            if kind==1 and vaddr<=address and address+size<=vaddr+count:
                physical=paddr+address-vaddr-BASE
                raw=image[physical:physical+size]
                if raw!=elf.data[offset+address-vaddr:offset+address-vaddr+size]:raise Hold('Pico runtime initializer disagrees with BIN')
                return raw
        raise Hold('Pico runtime data has no initialized ELF/BIN mapping')
    services=elf.symbols['_ZN8picocalc10NativeHost6commonE']
    magic,version,size,*fields=struct.unpack('<IHH6I',read_at(services,32))
    table,count=fields[-2:]
    if (magic,version,size,count)!=(0x31535953,2,32,27) or table!=elf.symbols['_ZN8picocalc14native_runtimeE']:raise Hold('Pico optional runtime provider differs')
    entries=struct.unpack('<27I',read_at(table,108));target=elf.symbols['__wrap_memchr']|1;length=elf.sizes['__wrap_memchr']
    if any(not entry&1 for entry in entries) or entries[26]!=target:raise Hold('Pico native memchr slot is absent or redirected')
    actual=read_at(target&~1,length)
    if actual!=body(elf,'__wrap_memchr',length):raise Hold('Pico memchr initializer differs from executable ELF')
    layout=json.loads(Path(layout_path).read_text());expected=layout['functions']['balanced64']
    if layout['cpu']!='m0' or length!=expected['bytes'] or sha(actual)!=expected['sha256']:raise Hold('Pico native memchr differs from tested A8 body')
    static_end=elf.symbols['__end__'];limit=elf.symbols['__HeapLimit'];stack_limit=elf.symbols['__StackLimit']
    if not 0x20000000<static_end<limit==stack_limit==0x20038000 or elf.symbols['__StackTop']!=0x20041000:raise Hold('Pico heap/stack layout differs')
    free=limit-static_end
    if free<min_heap:raise Hold('Pico heap below the caller-requested minimum: '+str(free)+' < '+str(min_heap))
    placement='SRAM' if 0x20000000<=(target&~1)<static_end else 'Flash' if BASE<=target<BASE+len(image) else None
    if placement is None:raise Hold('Pico native memchr target outside initialized code')
    # Pico's public BUILD is the source/runtime digest, not its sealed CRC.
    # Check the builder manifest and the actual status/fault ELF literals.
    manifest_path=Path(bin_path).parent/'manifest.json'
    manifest_raw=manifest_path.read_bytes();manifest=json.loads(manifest_raw)
    build=manifest['build_id'].upper()
    derived=sha((manifest['source_sha256']+'\0'+manifest['arithmetic_runtime']).encode())[:8].upper()
    if (build!=derived or manifest['arithmetic_runtime']!='owned-m0' or
        manifest['bin_sha256']!=sha(image) or
        manifest['firmware_integrity']['crc32'].upper()!=integrity['crc32'].upper()):
        raise Hold('Pico builder manifest/build/CRC differs')
    literal=struct.pack('<I',int(build,16))
    for name in ('_ZN8picocalc11diagnostics13status_reportEPcj',
                 '_ZN8picocalc11diagnostics13capture_faultEPKmS2_mmmmm'):
        if literal not in body(elf,name,elf.sizes[name]):
            raise Hold('Pico public BUILD is absent from its actual ELF diagnostics')
    return dict(status='PASS',scope='Offline exact sealed Pico provider/body/resources, not hardware acceptance',
        build=build,firmware_crc32=integrity['crc32'].upper(),manifest_sha256=sha(manifest_raw),
        source_sha256=manifest['source_sha256'],prefix_bytes=len(image),prefix_sha256=sha(image),elf_sha256=sha(elf.data),
        footer=integrity,static_end=static_end,heap_limit=limit,heap_reserve=free,
        requested_minimum_heap=min_heap,services_address=services,provider=dict(table=table,target=target,bytes=length,sha256=sha(actual)),
        native_placement=placement,runtime_entries=list(entries),runtime_count=27,services_size=32,
        installed_payload_reference=payload_proof)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--elf',type=Path,required=True);p.add_argument('--bin',type=Path,required=True)
    p.add_argument('--payload-layout',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--min-heap',type=int,default=0,help='Optional caller-requested minimum; validate actual APP allocations separately')
    a=p.parse_args();result=verify(a.elf,a.bin,a.payload_layout,a.min_heap);a.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('status','build','prefix_bytes','heap_reserve','native_placement','provider')}))
