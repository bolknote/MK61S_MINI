#!/usr/bin/env python3
"""Reject uniform but unbounded pointers and image/body mismatches."""
from pathlib import Path
import struct
import sys
import tempfile
import unittest

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT/'tests'));sys.path.insert(0,str(HERE))
from relocation import geometry,validate_pointers
from session import Hold

class RelocationTest(unittest.TestCase):
    def setUp(self):
        self.app=ROOT/'.build/memchr-20261022/m4-app-v1/app';self.kernel=ROOT/'.build/memchr-20261022/m4-v1'
        if not self.app.exists():self.skipTest('Frozen APP required')
    def proof(self,image=None,static_end=0x20005438):
        return geometry(self.app/'CHRBEN.APP',self.app/'CHRBEN.elf',image or self.app/'CHRBEN.bin',
            self.kernel/'kernels.elf',self.kernel/'kernels.json',static_end,0x2001bf00)
    def test_actual_raw_matches_bounded_loader_allocation_and_reference_bodies(self):
        proof=self.proof();self.assertEqual(proof['base'],0x20019180);self.assertEqual(proof['memory_end'],0x2001bef4)
        self.assertEqual(proof['bodies']['libc_search']['bytes'],160)
        self.assertTrue(validate_pointers((ROOT/'.build/memchr-20261023/m4-app-only-hil-v4/00-00.bin').read_bytes(),proof))
    def test_uniform_wrong_delta_and_non_thumb_and_different_indirect_are_rejected(self):
        proof=self.proof();original=bytearray((ROOT/'.build/memchr-20261023/m4-app-only-hil-v4/00-00.bin').read_bytes())
        for mode in ('uniform','nonthumb','indirect'):
            raw=bytearray(original)
            if mode=='uniform':
                for index in [13,*range(16,24)]:struct.pack_into('<I',raw,index*4,struct.unpack_from('<I',raw,index*4)[0]+32)
            elif mode=='nonthumb':struct.pack_into('<I',raw,16*4,proof['pointers'][0]&~1)
            else:struct.pack_into('<I',raw,13*4,proof['pointers'][4])
            with self.assertRaises(Hold):validate_pointers(raw,proof)
    def test_raw_image_mismatch_and_overlapping_static_ram_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'bad.bin';bad=bytearray((self.app/'CHRBEN.bin').read_bytes());bad[123]^=1;path.write_bytes(bad)
            with self.assertRaises(Hold):self.proof(path)
        with self.assertRaises(Hold):self.proof(static_end=0x20019200)

if __name__=='__main__':unittest.main()
