"""Offline identity of every installed Pico Flash body and read-only input."""
import json
from pathlib import Path
import struct
import zlib
from check_stm32_vectors import ElfImage
from session import Hold,sha
from proof import body
from run import FLASH_PATTERN

NAMES=('baseline','libc_search','byte_search','own4','own16','own64',
       'pair16','balanced16','pair64','balanced64','fast16','fast64')
BASE=0x101e0000


def verify(payload_path,elf_path,layout_path):
    payload=Path(payload_path).read_bytes();elf=ElfImage(elf_path)
    layout=json.loads(Path(layout_path).read_text())
    if (layout['cpu'],layout['base'],layout['data'],layout['bytes'])!=('m0',BASE,BASE+4096,8208):
        raise Hold('Pico payload geometry differs')
    if sha(payload)!=layout['sha256'] or len(payload)!=8208 or sha(elf.data)!=layout['elf_sha256']:
        raise Hold('Pico payload/ELF identity differs')
    if f'{zlib.crc32(payload):08X}'!=layout['crc32'] or set(layout['functions'])!=set(NAMES):
        raise Hold('Pico payload CRC or candidate set differs')
    text=elf.named_sections['.text'];size=layout['code_bytes']
    if text[3]!=BASE+64 or text[5]!=size or not 0<size<=4096-64:
        raise Hold('Pico executable payload section differs')
    code=elf.bytes_at(text);data=bytes(FLASH_PATTERN)
    header=struct.pack('<8s14I',b'MCHRFL4\0',4,8208,4096,size,12,zlib.crc32(code),zlib.crc32(data),*([0]*7))
    expected=header+code+b'\xff'*(4096-64-size)+data
    if payload!=expected:raise Hold('Pico installed header/code/gap/input differs from ELF and oracle')
    spans=[];functions={}
    for name in NAMES:
        item=layout['functions'][name];start=item['address']&~1;count=item['bytes']
        if (item['address']!=(elf.symbols[name]|1) or count<=0 or
            not BASE+64<=start<start+count<=BASE+64+size):
            raise Hold('Pico Flash candidate is outside the exact executable section: '+name)
        if any(start<hi and lo<start+count for lo,hi in spans):raise Hold('Pico Flash candidates overlap')
        spans.append((start,start+count));raw=payload[start-BASE:start-BASE+count]
        if raw!=body(elf,name,count) or sha(raw)!=item['sha256']:
            raise Hold('Pico installed candidate differs from referenced body: '+name)
        functions[name]=dict(address=item['address'],bytes=count,sha256=sha(raw))
    return dict(status='PASS',scope='Offline exact installed Pico payload, not hardware acceptance',
        payload_sha256=sha(payload),elf_sha256=sha(elf.data),layout_sha256=sha(Path(layout_path).read_bytes()),
        code_bytes=size,input_bytes=len(data),functions=functions)
