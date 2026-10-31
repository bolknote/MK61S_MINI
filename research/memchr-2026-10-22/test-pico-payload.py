#!/usr/bin/env python3
"""No hardware: actual A8 payload bytes, header, pattern and every code body."""
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
import zlib

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sys.path[:0]=[str(HERE),str(ROOT/'tests')]
import pico_payload

SOURCE=ROOT/'.build/memchr-20261023/m0-a8-flash-v1'


class PayloadTest(unittest.TestCase):
    def verify(self,folder):return pico_payload.verify(folder/'payload.bin',folder/'kernels.elf',folder/'layout.json')

    def test_actual_prepared_A8_payload_has_exact_ELF_bodies_and_oracle_data(self):
        result=self.verify(SOURCE)
        self.assertEqual(result['status'],'PASS');self.assertEqual(len(result['functions']),12)
        self.assertEqual(result['functions']['balanced64']['sha256'],'b279c07b519dc6ad8369bc8ed803c68dfee0855165186110c73e3cce19aa4e80')

    def test_resealed_corrupt_header_code_gap_and_input_still_rejected(self):
        for offset in (0,12,64,3500,4096,8207):
            with self.subTest(offset=offset),tempfile.TemporaryDirectory(prefix='memchr-payload-') as d:
                folder=Path(d)
                for name in ('payload.bin','kernels.elf','layout.json'):shutil.copyfile(SOURCE/name,folder/name)
                raw=bytearray((folder/'payload.bin').read_bytes());raw[offset]^=1;(folder/'payload.bin').write_bytes(raw)
                layout=json.loads((folder/'layout.json').read_text());layout.update(sha256=pico_payload.sha(raw),crc32=f'{zlib.crc32(raw):08X}')
                (folder/'layout.json').write_text(json.dumps(layout))
                with self.assertRaises(pico_payload.Hold):self.verify(folder)

    def test_redirected_body_size_or_digest_rejected_even_with_unchanged_payload(self):
        for field,value in (('address',0x101e0041),('bytes',400),('sha256','0'*64)):
            with self.subTest(field=field),tempfile.TemporaryDirectory(prefix='memchr-payload-') as d:
                folder=Path(d)
                for name in ('payload.bin','kernels.elf','layout.json'):shutil.copyfile(SOURCE/name,folder/name)
                layout=json.loads((folder/'layout.json').read_text());layout['functions']['balanced64'][field]=value
                (folder/'layout.json').write_text(json.dumps(layout))
                with self.assertRaises(pico_payload.Hold):self.verify(folder)


if __name__=='__main__':unittest.main()
