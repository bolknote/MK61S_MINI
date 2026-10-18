"""Post-link sealing of the shared 40-byte firmware footer for Pico H.

The canonical CRC32 zeroes the checksum and checksum-derived build ID words,
as STM32 does. It includes boot2, vectors, code, read-only and initialized data.
The separate source build ID remains in the Pico manifest and crash reports.
"""
import struct
import zlib

MAGIC=b'MK61FWC\0'
BASE=0x10000000
LIMIT=2*1024*1024-8192
PROFILE=0x50434831
FOOTER=struct.Struct('<8sHH7I')


def canonical_crc(image,offset):
    crc=zlib.crc32(image[:offset+20])
    crc=zlib.crc32(bytes(8),crc)
    return zlib.crc32(image[offset+28:],crc)


def metadata(image,offset):
    if not 256<len(image)<=LIMIT or offset<256 or offset+FOOTER.size>len(image) or offset%4:
        raise ValueError('firmware/footer outside Pico H application flash')
    values=FOOTER.unpack_from(image,offset)
    magic,version,size,start,length,crc,build,profile,flags,reserved=values
    if (magic,version,size,start,profile,flags,reserved)!=(MAGIC,1,40,BASE,PROFILE,1,0):
        raise ValueError('invalid required Pico H firmware footer')
    return length,crc,build


def verify(image,offset):
    length,crc,build=metadata(image,offset)
    if length!=len(image) or not crc or crc!=build or canonical_crc(image,offset)!=crc:
        raise ValueError('Pico H firmware CRC mismatch')
    return {'required':True,'format_version':1,'image_start':BASE,'image_size':length,
            'footer_offset':offset,'profile_id':f'{PROFILE:08x}','crc32':f'{crc:08x}'}


def seal(image,offset):
    length,crc,build=metadata(image,offset)
    if (length,crc,build)!=(0,0,0):
        raise ValueError('expected an unsealed link output')
    out=bytearray(image)
    struct.pack_into('<I',out,offset+16,len(out))
    checksum=canonical_crc(out,offset)
    if not checksum:raise ValueError('zero firmware CRC cannot identify a sealed image')
    struct.pack_into('<II',out,offset+20,checksum,checksum)
    result=bytes(out)
    verify(result,offset)
    return result
