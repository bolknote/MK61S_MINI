#!/usr/bin/env python3
"""No hardware: full Pico ROM readback, delayed USB and original-only recovery."""
from contextlib import contextmanager
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
spec=importlib.util.spec_from_file_location('pico_transport',HERE/'pico-transport.py')
transport=importlib.util.module_from_spec(spec);spec.loader.exec_module(transport)
ROM=('Device Information\n type:              RP2040\n flash size:        2048K\n flash id:          0x'+transport.UID+'\n').encode()
ABSENT=('No accessible RP-series devices in BOOTSEL mode were found found with serial\nnumber '+transport.UID+'.\n').encode()


class TransportTest(unittest.TestCase):
    @contextmanager
    def fixture(self):
        with tempfile.TemporaryDirectory(prefix='memchr-pico-transport-') as directory:
            out=Path(directory);tool=out/'picotool';tool.write_bytes(b'pinned test executable')
            original=b'A'*transport.FLASH_BYTES;candidate=b'B'*transport.FLASH_BYTES
            (out/'original.bin').write_bytes(original);(out/'candidate.bin').write_bytes(candidate)
            calls=[];device=dict(image=original,delay=0,read_short=False,wrong=False,clock=0,reboots=0)
            def clock():device['clock']+=1;return device['clock']
            def execute(command,**_):
                self.assertEqual(command[-2:],['--ser',transport.UID]);calls.append(command)
                args=command[1:-2]
                if args==['info','-d']:
                    if device['delay']:
                        device['delay']-=1;return SimpleNamespace(returncode=253,stdout=b'',stderr=ABSENT)
                    return SimpleNamespace(returncode=0,stdout=ROM.replace(transport.UID.encode(),b'0000000000000000') if device['wrong'] else ROM,stderr=b'')
                if args[0]=='save':
                    self.assertEqual(args[:3],['save','-a','-v']);self.assertEqual(args[-2:],['-t','bin'])
                    Path(args[3]).write_bytes(device['image'][:-1] if device['read_short'] else device['image'])
                elif args[0]=='load':
                    self.assertEqual(args[:3],['load','-u','-v']);self.assertEqual(args[-4:],['-t','bin','-o','0x10000000'])
                    self.assertNotIn('-x',args);device['image']=Path(args[3]).read_bytes()
                elif args==['reboot']:device['reboots']+=1
                else:raise AssertionError(args)
                return SimpleNamespace(returncode=0,stdout=b'complete\n',stderr=b'')
            flasher=transport.PicoRomFlash(out,tool,transport.sha(tool.read_bytes()),transport.sha(original),lambda:None)
            with patch.object(transport.subprocess,'run',side_effect=execute),patch.object(transport.time,'monotonic',side_effect=clock),patch.object(transport.time,'sleep'):
                yield flasher,out,device,calls,original,candidate

    def test_exact_device_parser_rejects_wrong_size_uid_type_duplicates_and_warnings(self):
        self.assertTrue(transport.exact_rom(ROM,b'',0))
        for bad in (ROM.replace(b'2048K',b'4096K'),ROM.replace(b'RP2040',b'RP2350'),
                    ROM.replace(transport.UID.encode(),b'0000000000000000'),ROM+ROM,
                    ROM+b' type:              RP2040\n',ROM+b'\xff'):
            self.assertFalse(transport.exact_rom(bad,b'',0))
        self.assertFalse(transport.exact_rom(ROM,b'permission warning',0))
        self.assertFalse(transport.exact_rom(ROM,b'',1))

    def test_delayed_enumeration_complete_write_readback_and_original_recovery(self):
        with self.fixture() as (flasher,out,device,calls,original,candidate):
            device['delay']=2
            self.assertEqual(flasher.read_full('backup',out/'backup.bin',transport.sha(original)),original)
            self.assertEqual(len(json.loads((out/'backup-rom.json').read_text())['attempts']),3)
            flasher.write_full('candidate-write',out/'candidate.bin',transport.sha(candidate))
            self.assertEqual(device['reboots'],0)
            with self.assertRaises(transport.Hold):flasher.reboot_verified('too-early',transport.sha(candidate))
            flasher.read_full('candidate-read',out/'candidate-read.bin',transport.sha(candidate))
            flasher.reboot_verified('candidate-boot',transport.sha(candidate))
            # Recovery is ROM-only and does not consult a candidate CRC/build.
            flasher.write_full('restore',out/'original.bin',transport.sha(original),recovery=True)
            flasher.read_full('restore-read',out/'restore-read.bin',transport.sha(original),recovery=True)
            flasher.reboot_verified('restore-boot',transport.sha(original))
            self.assertEqual(device['image'],original);self.assertEqual(device['reboots'],2)
            self.assertEqual(sum(c[1]=='load' for c in calls),2)

    def test_wrong_identity_or_nonoriginal_recovery_never_transfers(self):
        with self.fixture() as (flasher,out,device,calls,original,candidate):
            for operation in ('write','read'):
                with self.assertRaises(transport.Hold):
                    if operation=='write':flasher.write_full('bad-restore',out/'candidate.bin',transport.sha(candidate),recovery=True)
                    else:flasher.read_full('bad-read',out/'bad.bin',transport.sha(candidate),recovery=True)
            self.assertEqual(calls,[])
            device['wrong']=True
            with self.assertRaises(transport.Hold):flasher.write_full('wrong-device',out/'candidate.bin',transport.sha(candidate))
            self.assertEqual([c[1] for c in calls],['info'])

    def test_partial_readback_preserved_and_cannot_qualify_reboot(self):
        with self.fixture() as (flasher,out,device,calls,original,candidate):
            device['read_short']=True
            with self.assertRaises(transport.Hold):flasher.read_full('short',out/'short.bin',transport.sha(original))
            receipt=json.loads((out/'short.json').read_text())
            self.assertEqual(receipt['status'],'HOLD');self.assertEqual(receipt['bytes'],len(original)-1)
            self.assertEqual((out/'short.stdout.bin').read_bytes(),b'complete\n')
            with self.assertRaises(transport.Hold):flasher.reboot_verified('bad-boot',transport.sha(original))
            self.assertEqual(device['reboots'],0)

    def test_lease_is_rechecked_between_rom_identity_and_write(self):
        with self.fixture() as (flasher,out,device,calls,original,candidate):
            count=0
            def lease():
                nonlocal count
                count+=1
                if count==2:raise transport.Hold('Lease changed before write')
            flasher.lease_guard=lease
            with self.assertRaises(transport.Hold):flasher.write_full('lease-change',out/'candidate.bin',transport.sha(candidate))
            self.assertEqual([c[1] for c in calls],['info']);self.assertEqual(device['image'],original)

    def test_subprocess_timeout_keeps_partial_output_and_unchanged_original(self):
        with self.fixture() as (flasher,out,device,calls,original,candidate):
            failure=subprocess.TimeoutExpired('picotool info',10,output=b'partial ROM\xff',stderr=b'USB timeout')
            with patch.object(transport.subprocess,'run',side_effect=failure):
                with self.assertRaises(subprocess.TimeoutExpired):flasher.write_full('timeout',out/'candidate.bin',transport.sha(candidate))
            self.assertEqual((out/'timeout-rom-attempt-000.stdout.bin').read_bytes(),b'partial ROM\xff')
            self.assertEqual(json.loads((out/'timeout-rom.json').read_text())['status'],'HOLD')
            self.assertEqual(device['image'],original);self.assertEqual(device['reboots'],0)


if __name__=='__main__':unittest.main()
