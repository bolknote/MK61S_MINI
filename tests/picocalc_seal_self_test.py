#!/usr/bin/env python3
import sys,struct,unittest,zlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from seal_picocalc import FOOTER,BASE,PROFILE,LIMIT,seal,verify,patch_elf_footer

class FirmwareTests(unittest.TestCase):
    def image(self):
        out=bytearray((i*7)%256 for i in range(4096))
        FOOTER.pack_into(out,2048,b'MK61FWC\0',1,40,BASE,0,0,0,PROFILE,1,0)
        return out
    def test_full_image_and_metadata_corruption(self):
        original=self.image();sealed=seal(original,2048)
        result=verify(sealed,2048)
        independent=bytearray(sealed);independent[2068:2076]=bytes(8)
        self.assertEqual(result['crc32'],f'{zlib.crc32(independent):08x}')
        self.assertEqual(sealed[:2048],original[:2048])
        self.assertEqual(sealed[2088:],original[2088:])
        for offset in (0,255,256,4095,2048,2056,2058,2060,2064,2068,2072,2076,2080,2084):
            corrupt=bytearray(sealed);corrupt[offset]^=1
            with self.subTest(offset=offset),self.assertRaises(ValueError):verify(corrupt,2048)
        with self.assertRaises(ValueError):seal(sealed,2048)
    def test_bounds_and_cpu_profile(self):
        for offset in (0,2049,4092,5000):
            with self.subTest(offset=offset),self.assertRaises(ValueError):seal(self.image(),offset)
        for field,value in ((12,0x08000000),(28,0xF411),(32,0)):
            image=self.image();struct.pack_into('<I',image,2048+field,value)
            with self.assertRaises(ValueError):seal(image,2048)
        with self.assertRaises(ValueError):seal(bytes(LIMIT+1),2048)
    def test_elf_scratch_initializer_survives_noload_heap(self):
        # A scratch LOAD shares its physical base with a NOLOAD heap. Moving
        # either program header would break the startup copy address.
        elf=bytearray(0x500);ident=b'\x7fELF\x01\x01\x01'+bytes(9)
        struct.pack_into('<16sHHIIIIIHHHHHH',elf,0,ident,2,40,1,BASE+1,52,0x400,0x5000200,52,32,3,40,5,1)
        struct.pack_into('<8I',elf,52,1,0x100,BASE+0x100,BASE+0x100,40,40,5,4)
        struct.pack_into('<8I',elf,84,1,0x200,0x20038000,BASE+0x1000,16,16,7,4)
        struct.pack_into('<8I',elf,116,1,0x210,0x20001000,BASE+0x1000,0,0x1000,6,4)
        names=b'\0.shstrtab\0.mk61_fw_footer\0.heap\0.scratch_y\0';elf[0x300:0x300+len(names)]=names
        struct.pack_into('<10I',elf,0x428,names.index(b'.shstrtab'),3,0,0,0x300,len(names),0,0,1,0)
        struct.pack_into('<10I',elf,0x450,names.index(b'.mk61_fw_footer'),1,2,BASE+0x100,0x100,40,0,0,4,0)
        struct.pack_into('<10I',elf,0x478,names.index(b'.heap'),8,3,0x20001000,0x210,0x1000,0,0,4,0)
        struct.pack_into('<10I',elf,0x4a0,names.index(b'.scratch_y'),1,6,0x20038000,0x200,16,0,0,4,0)
        FOOTER.pack_into(elf,0x100,b'MK61FWC\0',1,40,BASE,0,0,0,PROFILE,1,0)
        elf[0x200:0x210]=bytes(range(160,176))
        def load(data):
            image=bytearray(0x1010)
            for offset in (52,84,116):
                _kind,file,_vma,lma,size,_memory,_flags,_align=struct.unpack_from('<8I',data,offset)
                image[lma-BASE:lma-BASE+size]=data[file:file+size]
            return bytes(image)
        sealed=seal(load(elf),0x100);patched=patch_elf_footer(elf,sealed[0x100:0x128])
        self.assertEqual(load(patched),sealed)
        self.assertEqual(patched[52:148],elf[52:148])
        self.assertEqual(patched[0x200:0x210],bytes(range(160,176)))
        verify(load(patched),0x100)

if __name__=='__main__':unittest.main()
