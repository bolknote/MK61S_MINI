#!/usr/bin/env python3
"""Check memchr report decoding and input generation without opening hardware."""
import importlib.util
from pathlib import Path
import struct
from types import SimpleNamespace
import unittest

spec=importlib.util.spec_from_file_location('memchr_runner',Path(__file__).with_name('run.py'))
runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)

class ReportTest(unittest.TestCase):
    def fixture(self,cpu):
        functions=runner.names(cpu)
        inputs=[(64,3,0xffffffff,100,0,4)]
        h=[0]*64;h[:5]=[0x4D435250,3,len(functions),1,7]
        h[5]=2*len(functions);h[14]=200000 if cpu=='m0' else 19200000
        h[15]=125000000 if cpu=='m0' else 96000000
        h[24]=0x0a428502 if cpu=='m0' else 0x9f8f7ded;h[26]=1
        h[16:16+len(functions)]=[0x20001001+32*i for i in range(len(functions))];h[13]=h[21]
        control=[200,100,100,100,100,100,100]
        samples=[]
        for f in range(len(functions)):samples.extend([150]+[200+100*f]*6)
        return inputs,bytearray(struct.pack('<64I',*h)+struct.pack('<'+str(13+7*len(functions))+'I',*inputs[0],*control,*samples))

    def test_paired_units_and_negative_outliers(self):
        for cpu in ('m0','m4'):
            inputs,raw=self.fixture(cpu);result=runner.decode(raw,inputs,cpu)
            scale=125 if cpu=='m0' else 1
            self.assertEqual(result['rows'][0]['timings']['baseline']['median_cycles'],scale)
            self.assertEqual(result['rows'][0]['timings']['baseline']['paired_cycles'][0],-.5*scale)
            self.assertEqual(result['rows'][0]['value'],0xffffffff)
            self.assertIn('not public runtime',result['indirect_table'])

    def test_reject_missing_checks_bad_clock_and_failure(self):
        inputs,raw=self.fixture('m4')
        for index,value in ((1,2),(5,0),(6,1),(13,0),(15,125000000),(24,0),(26,0)):
            broken=bytearray(raw);struct.pack_into('<I',broken,4*index,value)
            with self.assertRaises(AssertionError):runner.decode(broken,inputs,'m4')
        for broken in (raw[:-1],raw+b'\0'):
            with self.assertRaises(AssertionError):runner.decode(broken,inputs,'m4')

    def test_input_prefix_changes_batch_length(self):
        args=SimpleNamespace(cpu='m0',sources=[0],sizes=[0,64,4096],modes=[0,1,4],alignments=[0,3],values=[-1,256])
        result=runner.cases(args)
        self.assertEqual(len(result),28)
        first=next(r for r in result if r[:3]==(4096,0,0xffffffff) and r[5]==1)
        absent=next(r for r in result if r[:3]==(4096,0,0xffffffff) and r[5]==0)
        self.assertGreater(first[3],absent[3])
        self.assertTrue(all(r[5]==0 for r in result if not r[0]))

    def test_flash_values_determine_prefix_without_duplicate_modes(self):
        args=SimpleNamespace(cpu='m4',sources=[1],sizes=[4096],modes=[0,1,4],alignments=[0,3],values=[0,0x10,0x1c])
        result=runner.cases(args)
        self.assertEqual(len(result),6)
        self.assertEqual(runner.prefix(4096,0,0x10,1,0),1)
        self.assertEqual(runner.prefix(4096,3,0x10,1,0),4096)
        self.assertEqual(runner.prefix(4096,3,0x1c,1,0),4093)

if __name__=='__main__':unittest.main()
