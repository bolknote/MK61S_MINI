#!/usr/bin/env python3
"""Offline mixed placement/real-runtime identities and report negative cases."""
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sys.path.insert(0,str(HERE));sys.path.insert(0,str(ROOT/'tests'))
import wide
from session import Hold

class WideTest(unittest.TestCase):
    def setUp(self):
        self.packet=ROOT/'.build/memchr-20261023/wide-fw-packet-v6'
        self.plan=json.loads((self.packet/'plan.json').read_text())
    def fixture(self,index=0):
        bounded=wide.proof(self.plan,self.plan['apps'][index]);inputs=[(16,1,0,512,1,0)]
        raw=bytearray(756);h=[0]*64;h[:5]=[0x4d435250,4,16,1,7];h[5]=32;h[13]=0x8050a75;h[14]=19200000;h[15]=96000000
        h[24]=0x9f8f7ded;h[25]=bounded['payload_crc32'];h[26:28]=[4,27];h[33]=bounded['sdk_cached_target'];h[34]=32;h[35]=bounded['runtime_table'];h[36:52]=bounded['pointers'];h[54]=6
        struct.pack_into('<64I',raw,0,*h);struct.pack_into('<6I',raw,256,*inputs[0]);return raw,bounded,inputs
    def test_three_placements_match_exact_bodies_and_public_entry(self):
        wide.verify_images(self.plan)
        for index in range(3):
            raw,bounded,inputs=self.fixture(index);self.assertTrue(wide.validator(inputs,bounded,False)(raw))
            self.assertEqual(bounded['pointers'][14],0x8050a75)
            self.assertEqual(bounded['sdk_cached_target'],0x8050a75 if index==1 else bounded['pointers'][13])
            if index==2:self.assertTrue(all(0x8062040<=p<0x8063000 for p in bounded['pointers'][:13]))
            else:self.assertTrue(all(0x20000000<=p<0x2001bf00 for p in bounded['pointers'][:13]))
    def test_provider_pointer_crc_and_stage_mismatches_are_rejected(self):
        raw,bounded,inputs=self.fixture()
        for offset,value in ((13,0),(27,26),(34,28),(35,bounded['runtime_table']+4),(36,bounded['pointers'][0]+32),(50,0),(25,0),(54,5),(5,33)):
            bad=bytearray(raw);struct.pack_into('<I',bad,offset*4,value)
            self.assertFalse(wide.validator(inputs,bounded,False)(bad),offset)
    def test_known_payload_diagnostic_cleans_safely_but_never_qualifies(self):
        raw,bounded,inputs=self.fixture();raw[:256]=bytes(256);raw[256:]=bytes(500)
        h=[0]*64;h[:5]=[0x4d435250,4,16,1,7];h[6]=1;h[15]=96000000;h[24]=0x9f8f7ded;h[25]=123;h[54]=1
        struct.pack_into('<64I',raw,0,*h)
        self.assertTrue(wide.validator(inputs,bounded,False)(raw))
        with self.assertRaisesRegex(Hold,'correctness failed'):wide.decode(raw,inputs,bounded,False)
        struct.pack_into('<I',raw,25*4,bounded['payload_crc32']);self.assertFalse(wide.validator(inputs,bounded,False)(raw))
    def test_full_corpus_and_raw_negative_pair_are_preserved(self):
        for row in self.plan['apps']:self.assertEqual(len(wide.cases(wide.SimpleNamespace(**row['corpus']))),1440)
        raw,bounded,inputs=self.fixture();struct.pack_into('<I',raw,256+6*4,512)
        decoded=wide.decode(raw,inputs,bounded,False);self.assertEqual(decoded['rows'][0]['timings']['baseline']['paired_cycles'][0],-1)
        self.assertTrue(decoded['public_runtime_present'])
    def test_runtime_json_cannot_claim_a_different_body_than_the_sealed_image(self):
        with tempfile.TemporaryDirectory() as directory:
            proof=json.loads(Path(self.plan['runtime_proof']).read_text());proof['services']['memchr']['sha256']='0'*64
            path=Path(directory)/'false-proof.json';path.write_text(json.dumps(proof));self.plan['runtime_proof']=str(path)
            with self.assertRaisesRegex(Hold,'disagrees with sealed'):wide.verify_images(self.plan)

if __name__=='__main__':unittest.main()
