#!/usr/bin/env python3
"""Exact matrix identities, provider prefix and failed correctness admission."""
import importlib.util
import json
from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock,patch

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sys.path.insert(0,str(HERE));sys.path.insert(0,str(ROOT/'tests'))
import matrix
from session import Hold,Files,sha
spec=importlib.util.spec_from_file_location('matrix_runner',HERE/'run-matrix.py')
runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)

class MatrixTest(unittest.TestCase):
    def fixture(self):
        p=ROOT/'.build/memchr-20261023/m4-matrix-shared-v2'
        bounded=json.loads((p/'bounded-relocation-proof.json').read_text());inputs=[(16,0,0,512,0,0)]
        raw=bytearray(256+276);h=[0]*64
        h[:5]=[0x4d435250,3,8,1,7];h[5]=16;h[14]=19200000;h[15]=96000000;h[16:24]=bounded['pointers']
        h[24]=0x9f8f7ded;h[26]=3;h[27]=26;h[33]=bounded['sdk_cached_target'];h[34]=28
        struct.pack_into('<64I',raw,0,*h);struct.pack_into('<6I',raw,256,*inputs[0])
        return raw,bounded,inputs
    def test_valid_report_and_raw_negative_samples_survive(self):
        raw,bounded,inputs=self.fixture()
        struct.pack_into('<I',raw,256+6*4,512);struct.pack_into('<I',raw,256+13*4,0)
        self.assertTrue(matrix.validator(inputs,bounded,False)(raw))
        decoded=matrix.decode(raw,inputs,bounded,False,True)
        self.assertEqual(decoded['rows'][0]['timings']['baseline']['paired_cycles'][0],-1)
        self.assertFalse(decoded['public_runtime_present']);self.assertEqual(decoded['runtime_count'],26)
    def test_changed_provider_layout_counter_and_pointers_are_rejected(self):
        raw,bounded,inputs=self.fixture()
        for index,value in ((13,1),(27,27),(34,32),(5,17),(14,19199999),(16,bounded['pointers'][0]+32),(33,bounded['sdk_cached_target']+32)):
            changed=bytearray(raw);struct.pack_into('<I',changed,index*4,value)
            self.assertFalse(matrix.validator(inputs,bounded,False)(changed),index)
        self.assertFalse(matrix.validator(inputs,bounded,False)(raw+b'bad'))
    def test_recognized_correctness_failure_is_never_a_pass(self):
        raw,bounded,inputs=self.fixture();raw[256:]=bytes(276)
        struct.pack_into('<I',raw,6*4,1);struct.pack_into('<I',raw,14*4,0)
        self.assertTrue(matrix.validator(inputs,bounded,False)(raw))
        with self.assertRaisesRegex(Hold,'correctness failed'):matrix.decode(raw,inputs,bounded,False,True)
    def test_all_matrix_bodies_and_cached_fallback_are_bounded(self):
        for shared in (False,True):
            p=ROOT/('.build/memchr-20261023/m4-matrix'+('-shared' if shared else '')+'-v2');ref=ROOT/'.build/memchr-20261023/m4-matrix-v2/reference'
            row=dict(app=str(p/'app/CHRBEN.APP'),elf=str(p/'app/CHRBEN.elf'),raw_image=str(p/'app/CHRBEN.bin'),
                manifest=str(p/'benchmark.json'),kernels=str(ref/'kernels.elf'),kernel_layout=str(ref/('shared-kernels.json' if shared else 'kernels.json')),shared=shared)
            bounded=matrix.proof(row)
            self.assertLessEqual(bounded['memory_end'],0x2001bf00);self.assertEqual(len(bounded['pointers']),8)
            target=next(iter(bounded['sdk_cached_body'].values()));self.assertEqual(target['bytes'],512)
    def test_repaired_original_fails_entire_matrix_and_closes_port(self):
        class Port:
            fd=20;text=b'transaction'
            def __enter__(self):return self
            def __exit__(self,*_):self.fd=-1
            def command(self,*_,**__):return 'reply'
        port=Port();identity=SimpleNamespace(public=matrix.UID,usb=matrix.SERIAL,profile='classic-v3-uc1609',build=matrix.BUILD)
        disk=MagicMock();disk.capture.return_value=Files({'/original.bin':b'original'},set())
        disk.cleanup.return_value=dict(status='PASS',files_preserved=False,files_restored=True,state=dict(status='PASS',preserved=True))
        with tempfile.TemporaryDirectory(dir=ROOT/'.build',prefix='memchr-matrix-test-') as folder:
            base=Path(folder);lease=base/'lease';lease.write_bytes(b'lease');app=base/'APP';app.write_bytes(b'app');output=base/'output'
            plan=dict(apps=[dict(directory='/MCHR-M03',shared=False,app=str(app),corpus=dict(sizes=[0],alignments=[0],values=[0],sources=[0],modes=[0],runs=1,full_hardware_correctness_sweep=False))])
            argv=['run-matrix.py','--plan',str(base/'plan'),'--plan-sha256','unused','--port','/unused','--output',str(output)]
            with patch.object(sys,'argv',argv),patch.object(matrix,'validate',return_value=(plan,lease,sha(b'lease'))), \
                 patch.object(runner,'connect',return_value=port),patch.object(runner,'correlate'),patch.object(runner,'parse_identity',return_value=identity), \
                 patch.object(runner,'health',return_value={'mpu status':'static_end=0x20005438 guard=0x2001BF00+256'}), \
                 patch.object(runner,'ClassicState'),patch.object(runner,'OwnedSession',return_value=disk),patch.object(matrix,'proof',return_value={'pointers':list(range(8)),'sdk_cached_target':1}), \
                 patch.object(runner,'read_file',return_value=b'report'),patch.object(matrix,'decode',return_value={'checks':16}):
                with self.assertRaisesRegex(Hold,'qualification failed'):runner.main()
            result=json.loads((output/'result.json').read_text())
            self.assertEqual(result['status'],'FAIL');self.assertEqual(result['apps'][0]['status'],'FAIL_RESTORED')
            self.assertTrue(result['serial_closed']);self.assertFalse(result['cleanup_pending'])

if __name__=='__main__':unittest.main()
