#!/usr/bin/env python3
"""A repaired original is a failed benchmark even if timings passed."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock,patch

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('memchr_sram_runner',HERE/'run-app-sram.py')
app=importlib.util.module_from_spec(spec);spec.loader.exec_module(app)

class QualificationTest(unittest.TestCase):
    def test_benchmark_pass_with_repaired_original_fails_after_successful_recovery(self):
        for repaired in ('file','calculator'):
            class Port:
                fd=19;text=b'simulated transaction'
                def __enter__(self):return self
                def __exit__(self,*_):self.fd=-1
                def command(self,*_,**__):return 'reply'
            port=Port();identity=SimpleNamespace(public=app.UID,usb=app.SERIAL,profile='classic-v3-uc1609',build=app.BUILD)
            disk=MagicMock();disk.capture.return_value=app.Files({'/original.bin':b'original'},set())
            disk.cleanup.return_value=dict(status='PASS',files_preserved=repaired!='file',files_restored=repaired=='file',
                state=dict(status='PASS',preserved=repaired!='calculator',restored=repaired=='calculator'))
            state=MagicMock();state.capture.return_value={'saved':'state'}
            plan=dict(elf=str(app.ROOT/'.build/memchr-20261022/m4-app-v1/app/CHRBEN.elf'),app='unused',raw_image='unused',kernels='unused',kernel_layout='unused',
                corpus=dict(sizes=[0],alignments=[0],values=[0],sources=[0],modes=[0],runs=1,full_hardware_correctness_sweep=False))
            with tempfile.TemporaryDirectory(dir=app.ROOT/'.build',prefix='memchr-qualification-test-') as directory:
                base=Path(directory);lease=base/'lease';lease.write_bytes(b'lease');output=base/'output'
                argv=['run-app-sram.py','--plan',str(base/'plan'),'--plan-sha256','unused','--port','/unused','--output',str(output)]
                with patch.object(sys,'argv',argv),patch.object(app,'validate',return_value=(plan,b'app',lease,app.sha(b'lease'))), \
                     patch.object(app,'connect',return_value=port),patch.object(app,'correlate'),patch.object(app,'parse_identity',return_value=identity), \
                     patch.object(app,'health',return_value={'mpu status':'static_end=0x20005438 guard=0x2001BF00+256'}), \
                     patch.object(app,'geometry',return_value={'pointers':list(range(8))}),patch.object(app,'ClassicState',return_value=state), \
                     patch.object(app,'OwnedSession',return_value=disk),patch.object(app,'read_file',return_value=b'report'), \
                     patch.object(app.bench,'decode',return_value={'checks':16}):
                    with self.assertRaisesRegex(app.Hold,'did not pass'):app.main()
                result=json.loads((output/'result.json').read_text())
                self.assertEqual(result['benchmark_status'],'PASS');self.assertEqual(result['status'],'FAIL_RESTORED')
                self.assertFalse(result['cleanup_pending']);self.assertTrue(result['serial_closed'])

if __name__=='__main__':unittest.main()
