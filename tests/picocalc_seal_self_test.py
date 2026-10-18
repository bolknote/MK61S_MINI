#!/usr/bin/env python3
import sys,struct,unittest,zlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from seal_picocalc import FOOTER,BASE,PROFILE,LIMIT,seal,verify

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

if __name__=='__main__':unittest.main()
