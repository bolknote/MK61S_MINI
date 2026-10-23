"""Offline proof of V138 allocation/write ranges and the separate reference span."""
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import sys
ROOT=Path.cwd();WORK=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'tests'))
from check_stm32_vectors import ElfImage
cfg=json.loads((WORK/'benchmark.json').read_text());elf=ElfImage(Path(cfg['firmware_elf']))
source=Path(cfg['firmware_elf']).parents[1]/'source'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
lo=0x10180000;hi=0x10182000;ranges=[]
for kind,offset,vaddr,paddr,filesz,memsz,flags,align in elf.segments:
    if kind==1 and filesz and 0x10000000<=paddr<0x10200000:
        assert paddr+filesz<=lo or paddr>=hi,(paddr,filesz)
        ranges.append(dict(base=paddr,end=paddr+filesz,bytes=filesz))
assert max(r['end'] for r in ranges)==0x101773F0
assert (0x101773F0+4095)&~4095==0x10178000<lo
assert hi<=0x101FE000
calls=[]
for directory in ('ports/picocalc','code'):
    for p in (source/directory).rglob('*'):
        if p.is_file() and p.suffix in ('.c','.cpp','.h','.hpp','.inc','.S'):
            for number,line in enumerate(p.read_text().splitlines(),1):
                if re.search(r'\b(?:flash_range_program|flash_range_erase|flash_do_cmd)\s*\(',line):
                    calls.append(dict(path=str(p.relative_to(source)),line=number,text=line.strip()))
assert len(calls)==2 and {c['path'] for c in calls}=={'ports/picocalc/device_settings.cpp'}
settings=source/'ports/picocalc/device_settings.cpp';text=settings.read_text()
for statement in ['constexpr u32 START = 2 * 1024 * 1024 - 2 * FLASH_SECTOR_SIZE;',
                  'constexpr unsigned PAGES = 2 * FLASH_SECTOR_SIZE / FLASH_PAGE_SIZE;',
                  'const u32 offset = START + operation.index * FLASH_PAGE_SIZE;',
                  'operation.index %= PAGES;']:
    assert statement in text,statement
sdk=ROOT/'.build/picocalc-deps/pico-sdk/src/rp2_common/hardware_flash/include/hardware/flash.h'
sdk_text=sdk.read_text()
assert '#define FLASH_PAGE_SIZE (1u << 8)' in sdk_text and '#define FLASH_SECTOR_SIZE (1u << 12)' in sdk_text
tc=Path('/Users/bolk/Library/Arduino15/packages/STMicroelectronics/tools/xpack-arm-none-eabi-gcc/14.2.1-1.1/bin')
disassembly=subprocess.check_output([str(tc/'arm-none-eabi-objdump'),'-d',cfg['firmware_elf']],text=True)
function='';linked=[]
for line in disassembly.splitlines():
    match=re.match(r'^[0-9a-f]+ <([^>]+)>:',line)
    if match:function=match[1]
    if re.search(r'\bbl\s+.*<(?:__)?(?:flash_range_program|flash_range_erase)(?:_veneer)?>',line):
        linked.append(dict(caller=function,instruction=line.strip()))
assert len(linked)==2 and all('write' in row['caller'] for row in linked)
raw=(WORK/'reference/reference-only.uf2').read_bytes();payload=(WORK/'reference/reference-sectors.bin').read_bytes()
assert len(payload)==8192 and len(raw)==16384
for i in range(32):
    block=raw[i*512:(i+1)*512]
    assert struct.unpack_from('<8I',block)==(0x0A324655,0x9E5D5157,0x2000,lo+i*256,256,i,32,0xE48BFF56)
    assert block[32:288]==payload[i*256:(i+1)*256]
    assert struct.unpack_from('<I',block,508)[0]==0x0AB16F30
record=dict(status='PASS_ACTUAL_V138_FLASH_ALLOCATION_AND_SEMANTIC_WRITE_SCOPE',
    elf_sha256=sha(Path(cfg['firmware_elf'])),source_sha256=cfg['firmware_manifest']['source_sha256'],
    original_flash_load_ranges=ranges,firmware_extent=[0x10000000,0x101773F0],
    firmware_sector_erase_extent=[0x10000000,0x10178000],reference_range=[lo,lo+6364],
    addon_erase_range=[lo,hi],sector_size=4096,page_size=256,addon_sectors=2,
    persistent_settings_range=[0x101FE000,0x10200000],application_persistence='SD files; the only explicit Pico firmware flash writers are settings append/rollover.',
    explicit_flash_api_call_sites=calls,linked_flash_api_call_sites=linked,
    device_settings_source=dict(path=str(settings),sha256=sha(settings)),
    sdk_flash_header=dict(path=str(sdk),sha256=sha(sdk)),
    addon_sha256=sha(WORK/'reference/reference-sectors.bin'),uf2_sha256=sha(WORK/'reference/reference-only.uf2'),
    undefined_reference_imports=[],reference_ram_bytes=0,candidate_modified=False,
    limitation='Semantically unallocated by this firmware does not mean erased in the live device. The transaction must preserve a fresh full-Flash backup, verify addon separately (outside firmware CRC), preserve all other sectors and finally restore the exact fresh full Flash.')
(WORK/'layout-proof.json').write_text(json.dumps(record,indent=2)+'\n')
print('PASS: exactV138 LOAD/erase/settings spans disjoint from two-sector reference; only settings firmware writers.')
