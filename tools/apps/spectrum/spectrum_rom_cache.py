#!/usr/bin/env python3
"""Build a non-executable RP2040 XIP cache of the Spectrum ROM assets."""
import hashlib
import json
from pathlib import Path
import struct
import zlib

FLASH_OFFSET=0x1C0000
CAPACITY=128*1024
NAMES=('48.rom','128-0.rom','128-1.rom','trdos.rom','esxmmc.rom')

def validate_uf2(transport: bytes, firmware_bytes: int = 0) -> bytes:
    """Reject an overlapping firmware or UF2 addresses outside the cache slot."""
    if not 0 <= firmware_bytes <= FLASH_OFFSET:
        raise ValueError('firmware overlaps the Spectrum ROM cache at 0x101C0000')
    if not transport or len(transport) % 512:
        raise ValueError('invalid Spectrum ROM cache UF2 size')
    blocks = len(transport) // 512
    if blocks * 256 > CAPACITY:
        raise ValueError('Spectrum ROM cache exceeds its reserved Flash slot')
    payload = bytearray()
    for index in range(blocks):
        block = transport[index * 512:(index + 1) * 512]
        expected = (0x0A324655, 0x9E5D5157, 0x2000,
                    0x10000000 + FLASH_OFFSET + index * 256,
                    256, index, blocks, 0xE48BFF56)
        if struct.unpack_from('<8I', block) != expected or struct.unpack_from('<I', block, 508)[0] != 0x0AB16F30:
            raise ValueError('Spectrum ROM cache UF2 block/address mismatch')
        payload += block[32:288]
    return bytes(payload)


def prepare(folder: Path):
    # All five assets are required for this fast path. An ordinary SD build
    # without device ROMs still works through the original memory backend.
    if not all((folder/name).is_file() for name in NAMES):
        return None
    image=bytearray(256);image[:8]=b'MK61ROM1'
    records=[]
    for i,name in enumerate(NAMES):
        data=(folder/name).read_bytes();expected=8192 if i==4 else 16384
        if len(data)!=expected:raise ValueError(f'{name}: ROM size must be {expected}')
        offset=len(image);crc=zlib.crc32(data)
        struct.pack_into('<4I16s',image,32+i*32,i,offset,len(data),crc,name.encode())
        image+=data
        records.append({'name':name,'bytes':len(data),'crc32':f'{crc:08x}','sha256':hashlib.sha256(data).hexdigest()})
    struct.pack_into('<4I',image,8,1,len(image),len(NAMES),zlib.crc32(image[256:]))
    struct.pack_into('<I',image,24,zlib.crc32(image[:256]))
    assert len(image)<=CAPACITY
    payload=image+bytes([255])*((-len(image))%4096)
    blocks=len(payload)//256;uf2=bytearray()
    for i in range(blocks):
        uf2+=struct.pack('<8I',0x0A324655,0x9E5D5157,0x2000,0x10000000+FLASH_OFFSET+i*256,256,i,blocks,0xE48BFF56)
        uf2+=payload[i*256:(i+1)*256]+bytes(220)+struct.pack('<I',0x0AB16F30)
    assert validate_uf2(uf2) == payload
    (folder/'ROMCACHE.uf2').write_bytes(uf2)
    record={'flash_offset':FLASH_OFFSET,'address':0x10000000+FLASH_OFFSET,'reserved_bytes':CAPACITY,
            'payload_bytes':len(image),'written_bytes':len(payload),'uf2_sha256':hashlib.sha256(uf2).hexdigest(),'roms':records}
    (folder/'rom-cache.json').write_text(json.dumps(record,indent=2)+'\n')
    return record

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('folder',type=Path)
    args=parser.parse_args()
    if prepare(args.folder) is None:parser.error('all five ROM files must be present in the folder')
