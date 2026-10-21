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


def patch_elf_footer(elf,sealed_footer):
    """Replace footer bytes without relaying out LOAD/NOLOAD RAM segments.

    objcopy --update-section can move the LMA of a scratch RAM initializer
    past a preceding NOLOAD heap. Startup still uses the link-time address.
    The footer has fixed size, so no ELF header or segment needs to change.
    """
    header=struct.Struct('<16sHHIIIIIHHHHHH')
    section=struct.Struct('<10I')
    if len(elf)<header.size or len(sealed_footer)!=FOOTER.size:
        raise ValueError('truncated ARM ELF/footer')
    h=header.unpack_from(elf)
    if h[0][:7]!=b'\x7fELF\x01\x01\x01' or h[1:4]!=(2,40,1) or h[11]!=section.size:
        raise ValueError('expected linked little-endian ARM ELF32')
    if not h[12] or h[13]>=h[12] or h[6]+h[12]*section.size>len(elf):
        raise ValueError('invalid ARM ELF section table')
    sections=[section.unpack_from(elf,h[6]+i*section.size) for i in range(h[12])]
    names_section=sections[h[13]]
    if names_section[1]!=3 or names_section[4]+names_section[5]>len(elf):
        raise ValueError('invalid ARM ELF section names')
    names=elf[names_section[4]:names_section[4]+names_section[5]]
    matches=[]
    for s in sections:
        if s[0]>=len(names):raise ValueError('invalid ARM ELF section name')
        end=names.find(b'\0',s[0])
        if end<0:raise ValueError('unterminated ARM ELF section name')
        if names[s[0]:end]==b'.mk61_fw_footer':matches.append(s)
    if len(matches)!=1:raise ValueError('required ARM ELF footer is missing or duplicated')
    s=matches[0];at=s[4]
    if s[1]!=1 or not s[2]&2 or s[5]!=FOOTER.size or at+s[5]>len(elf):
        raise ValueError('invalid ARM ELF footer section')
    previous=elf[at:at+FOOTER.size]
    if (previous[:16]!=sealed_footer[:16] or previous[28:]!=sealed_footer[28:] or
            previous[16:28]!=bytes(12)):
        raise ValueError('expected matching unsealed ARM ELF footer')
    result=bytearray(elf);result[at:at+FOOTER.size]=sealed_footer
    return bytes(result)
