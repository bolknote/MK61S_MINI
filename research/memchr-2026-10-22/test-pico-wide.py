#!/usr/bin/env python3
"""No hardware: allocated APP bounds, mixed pointers and Pico report rejection."""
import importlib.util
import json
from pathlib import Path
import struct
import sys
import unittest

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sys.path.insert(0,str(HERE));sys.path.insert(0,str(ROOT/'tests'))
spec=importlib.util.spec_from_file_location('pico_wide',HERE/'pico-wide.py')
pico=importlib.util.module_from_spec(spec);spec.loader.exec_module(pico)


class PicoWideTest(unittest.TestCase):
    def proof(self,index):
        base=ROOT/'.build/memchr-20261023'
        folder=('m0-a8-native-standalone-v1','m0-a8-native-shared-v1','m0-a8-native-flash-v1')[index]
        path=base/folder;manifest=json.loads((path/'benchmark.json').read_text())
        row=dict(directory=manifest['directory'],shared=manifest['shared'],placement=manifest['placement'],
            app_sha256=manifest['app_sha256'],app=str(path/'app/CHRBEN.APP'),elf=str(path/'app/CHRBEN.elf'),
            raw_image=str(path/'app/CHRBEN.bin'),manifest=str(path/'benchmark.json'))
        layout=base/'m0-a8-flash-v1/layout.json';body=json.loads(layout.read_text())['functions']['balanced64']
        provider=dict(table=0x10060000,target=0x20000101,bytes=body['bytes'],sha256=body['sha256'])
        return pico.prepare(row,base/'m0-a8-flash-v1/kernels.elf',layout,0x200307d8,0x20038000,provider)

    def fixture(self,index,base=0x20033000):
        proof=self.proof(index);inputs=[(16,4,0,1024,0,0)];h=[0]*64
        h[:5]=[0x4d435250,4,15,1,7];h[5]=30;h[11]=3;h[13]=proof['provider']['target'];h[14]=200000
        h[15]=125000000;h[24]=0x0a428502;h[25]=proof['payload_crc32'];h[26:28]=[4,27]
        h[33]=proof['provider']['target'] if proof['shared'] else (base+proof['fallback_offset'])|1
        h[34]=32;h[35]=proof['provider']['table'];h[54]=6
        h[36:51]=[(base+offset)|1 if offset is not None else proof['provider']['target'] for offset in proof['offsets']]
        if proof['placement']=='flash':h[36:48]=proof['flash_pointers']
        raw=bytearray(728);struct.pack_into('<64I',raw,0,*h);struct.pack_into('<6I',raw,256,*inputs[0])
        return raw,proof,inputs

    def test_allocated_base_can_change_without_assuming_the_classic_guard(self):
        for index in range(3):
            for base in (0x20031000,0x20033000,0x20034000):
                with self.subTest(index=index,base=hex(base)):
                    raw,proof,inputs=self.fixture(index,base)
                    report=pico.decode(raw,inputs,proof,False)
                    self.assertEqual(report['allocation']['base'],base)
                    self.assertTrue(pico.validator(inputs,proof,False)(raw))

    def test_corrupt_allocation_runtime_payload_or_row_never_qualifies(self):
        raw,proof,inputs=self.fixture(1)
        faults=((48,0x20000001),(48,0x20050001),(48,struct.unpack_from('<I',raw,48*4)[0]+2),
            (36,struct.unpack_from('<I',raw,36*4)[0]+8),(49,0),(51,1),(35,proof['provider']['table']+4),
            (33,0),(34,28),(27,26),(11,2),(24,0),(25,0),(54,5),(5,29),(15,120000000))
        for at,value in faults:
            bad=bytearray(raw);struct.pack_into('<I',bad,at*4,value)
            with self.subTest(word=at),self.assertRaises(pico.Hold):pico.decode(bad,inputs,proof,False)
            self.assertFalse(pico.validator(inputs,proof,False)(bad),at)
        bad=bytearray(raw);struct.pack_into('<I',bad,256+4,3)
        self.assertFalse(pico.validator(inputs,proof,False)(bad))

    def test_known_failed_report_can_be_cleaned_but_not_counted_as_a_measurement(self):
        raw,proof,inputs=self.fixture(0);h=[0]*64
        h[:5]=[0x4d435250,4,15,1,7];h[6]=1;h[11]=3;h[15]=125000000;h[24]=0x0a428502;h[25]=123;h[54]=1
        raw[:]=bytes(len(raw));struct.pack_into('<64I',raw,0,*h)
        self.assertTrue(pico.validator(inputs,proof,False)(raw))
        with self.assertRaises(pico.Hold):pico.decode(raw,inputs,proof,False)
        struct.pack_into('<I',raw,25*4,proof['payload_crc32'])
        self.assertFalse(pico.validator(inputs,proof,False)(raw))

    def test_subtracted_timer_samples_keep_negative_outliers_and_convert_us(self):
        raw,proof,inputs=self.fixture(0)
        struct.pack_into('<7I',raw,256+6*4,*([10]*7))
        struct.pack_into('<7I',raw,256+13*4,*([9]*7))
        report=pico.decode(raw,inputs,proof,False)
        self.assertEqual(report['rows'][0]['timings']['baseline']['median_cycles'],-125/1024)


if __name__=='__main__':unittest.main()
