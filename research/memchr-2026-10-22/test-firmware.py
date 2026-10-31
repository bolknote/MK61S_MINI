#!/usr/bin/env python3
"""No hardware: exact ROM transport and unconditional verified FW rollback."""
import dataclasses
import errno
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock,patch

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sys.path.insert(0,str(HERE));sys.path.insert(0,str(ROOT/'tests'))
import firmware
import hil_system_memory as system_transport
from session import Hold,Files,sha
spec=importlib.util.spec_from_file_location('wide_fw_runner',HERE/'run-wide-fw.py');runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)

class TransportTest(unittest.TestCase):
    def test_actual_post_leave_enumeration_identity_descriptor_and_original_recovery(self):
        original=(ROOT/'.build/memmove-20261021/m4-v3-flash-hil/flash-original-a.bin').read_bytes()
        candidate=(ROOT/'.build/memchr-20261023/wide-fw-packet-v4/inputs/candidate.bin').read_bytes()
        listing=json.loads((ROOT/'.build/memchr-20261023/m4-rom-read-recovery-v1/original-rom-readback.transfer.json').read_text())['listing']['stdout'].encode()
        for fault in ('delayed','uid','descriptor','enumeration-timeout','identity-timeout'):
            with self.subTest(fault=fault),tempfile.TemporaryDirectory(dir=ROOT/'.build',prefix='memchr-fw-test-') as directory:
                out=Path(directory);image=out/'candidate.bin';image.write_bytes(candidate)
                restore=out/'original.bin';restore.write_bytes(original)
                device=dict(image=original,build='3AB3DD45',rom=False,delay=0,fault_active=False,clock=0)
                commands=[];ports=[]
                def clock():
                    device['clock']+=31 if device['fault_active'] and fault in ('descriptor','enumeration-timeout','identity-timeout') else 1
                    return device['clock']
                class Port:
                    def __init__(self):self.fd=12;self.text=b'CDC raw\xff\r\n';ports.append(self)
                    def __enter__(self):return self
                    def __exit__(self,*_):self.close()
                    def close(self):self.fd=-1
                    def command(self,command,**_):
                        if command!='identity':return 'status'
                        public='0000000000000000' if device['fault_active'] and fault=='uid' else system_transport.PUBLIC
                        reply=('MK61 ID v=1 public='+public+' short='+public[-8:]+' usb='+firmware.SERIAL+
                            ' volume=00000000 build='+device['build']+' profile='+system_transport.PROFILE+'\r\n')
                        self.text+=reply.encode()
                        if device['fault_active'] and fault=='identity-timeout':raise TimeoutError('partial identity reply')
                        return reply
                    def drain(self):pass
                    def write_line(self,line):
                        self.text+=line.encode()+b'\r\n';self.asserted=line;device['rom']=True
                    def pump(self,_):raise OSError(errno.ENXIO,'Expected DFU USB disconnect')
                def construct(path):
                    self.assertEqual(path,firmware.PORT)
                    if device['rom']:raise FileNotFoundError(errno.ENOENT,'In ROM')
                    if device['fault_active'] and fault=='enumeration-timeout':raise FileNotFoundError(errno.ENOENT,'Enumeration deadline')
                    if device['delay']:
                        device['delay']-=1;raise FileNotFoundError(errno.ENOENT,'Delayed USB enumeration')
                    return Port()
                def execute(command,**_):
                    commands.append(command)
                    if '-l' in command:
                        self.assertTrue(device['rom'])
                        data=listing.replace(b'/0x08000000/',b'/0x09000000/') if device['fault_active'] and fault=='descriptor' else listing
                        return SimpleNamespace(returncode=0,stdout=data,stderr=b'')
                    if '-D' in command:
                        self.assertTrue(device['rom']);device['image']=Path(command[-1]).read_bytes()
                        device['build']='3AB3DD45' if device['image']==original else 'D4D8DB55'
                        device['rom']=not command[command.index('-s')+1].endswith(':leave')
                        if device['image']==candidate:device.update(fault_active=True,delay=2 if fault=='delayed' else 0)
                        return SimpleNamespace(returncode=0,stdout=b'Download done.\n',stderr=b'')
                    self.assertIn('-U',command);self.assertTrue(device['rom'])
                    Path(command[-1]).write_bytes(device['image']);device.update(rom=False,delay=1)
                    return SimpleNamespace(returncode=0,stdout=b'Upload done.\nSubmitting leave request\n',stderr=b'')
                flasher=firmware.ClassicFlash(lambda:None,out)
                with patch.object(system_transport,'ExclusiveScreenPort',side_effect=construct), \
                     patch.object(firmware,'health',return_value={}),patch.object(firmware,'require_empty'), \
                     patch.object(firmware.subprocess,'run',side_effect=execute), \
                     patch.object(firmware.time,'monotonic',side_effect=clock),patch.object(firmware.time,'sleep'):
                    flasher.download('3AB3DD45',image,sha(candidate),out/'download.json')
                    before=len(commands)
                    if fault=='delayed':
                        self.assertEqual(flasher.upload('D4D8DB55',out/'candidate-readback.bin',sha(candidate)),candidate)
                    else:
                        with self.assertRaises((AssertionError,Hold,OSError,TimeoutError)):
                            flasher.upload('D4D8DB55',out/'candidate-readback.bin',sha(candidate))
                        self.assertFalse(any('-U' in c or '-D' in c for c in commands[before:]))
                    receipt=json.loads((out/'candidate-readback.transfer.json').read_text())
                    if fault=='descriptor':
                        self.assertEqual(receipt['listing']['status'],'HOLD')
                        raw=Path(receipt['listing']['stdout_raw']['path']).read_bytes();self.assertIn(b'/0x09000000/',raw)
                    else:
                        self.assertTrue(receipt['cdc_attempts'])
                        for attempt in receipt['cdc_attempts']:
                            self.assertEqual(sha(Path(attempt['raw']['path']).read_bytes()),attempt['raw']['sha256'])
                        if fault in ('uid','identity-timeout'):
                            self.assertEqual(receipt['cdc_attempts'][-1]['status'],'REJECTED')
                            raw=Path(receipt['cdc_attempts'][-1]['raw']['path']).read_bytes()
                            self.assertIn(b'CDC raw\xff',raw);self.assertIn(b'MK61 ID',raw)
                        if fault=='delayed':self.assertEqual([r['status'] for r in receipt['cdc_attempts']],['RETRY','RETRY','ADMITTED','RETRY','ADMITTED'])
                    device.update(fault_active=False,delay=0)
                    # Real original-only recovery after each post-D failure;
                    # stay in ROM for the independent final full readback.
                    flasher.download(None,restore,firmware.ORIGINAL_SHA,out/'restore.json',recovery=True,already_in_dfu=device['rom'])
                    self.assertTrue(device['rom']);self.assertEqual(device['image'],original)
                    self.assertEqual(flasher.upload(None,out/'restored.bin',firmware.ORIGINAL_SHA,recovery=True,already_in_dfu=True),original)
                    self.assertEqual(json.loads((out/'restored.transfer.json').read_text())['status'],'PASS')
                self.assertTrue(all(p.fd<0 for p in ports))

    def test_real_connect_waits_for_usb_enumeration_and_still_has_a_deadline(self):
        Identity=dataclasses.make_dataclass('Identity',[('public',str),('usb',str),('profile',str),('build',str)])
        identity=Identity(system_transport.PUBLIC,system_transport.SERIAL,system_transport.PROFILE,'3AB3DD45')
        for expires in (False,True):
            with self.subTest(expires=expires),tempfile.TemporaryDirectory(dir=ROOT/'.build',prefix='memchr-fw-test-') as directory:
                out=Path(directory);attempts=[]
                class Port:
                    fd=12;text=b'identity\r\ndfu\r\n'
                    def __enter__(self):return self
                    def __exit__(self,*_):self.close()
                    def close(self):self.fd=-1
                    def command(self,*_,**__):return 'identity'
                    def drain(self):pass
                    def write_line(self,text):attempts.append(text)
                    def pump(self,_):pass
                def construct(path):
                    attempts.append(path)
                    if expires or attempts.count(path)<=2:raise FileNotFoundError(errno.ENOENT,'USB is re-enumerating')
                    return Port()
                flasher=firmware.ClassicFlash(lambda:None,out)
                with patch.object(system_transport,'ExclusiveScreenPort',side_effect=construct), \
                     patch.object(system_transport,'parse_identity',return_value=identity),patch.object(firmware,'parse_identity',return_value=identity), \
                     patch.object(firmware,'health',return_value={}),patch.object(firmware,'require_empty'), \
                     patch.object(system_transport.time,'monotonic',side_effect=[0,31] if expires else [0,1,2]),patch.object(system_transport.time,'sleep'):
                    if expires:
                        with self.assertRaises(FileNotFoundError):flasher.enter('3AB3DD45')
                    else:
                        before,_=flasher.enter('3AB3DD45');self.assertTrue(before['serial_closed']);self.assertTrue(before['dfu_request_issued'])
                self.assertEqual('dfu' in attempts,not expires)
                self.assertEqual(attempts.count(firmware.PORT),1 if expires else 3)

    def test_disconnect_after_dfu_request_requires_exact_rom_before_upload(self):
        original=(ROOT/'.build/memmove-20261021/m4-v3-flash-hil/flash-original-a.bin').read_bytes()
        observed=json.loads((ROOT/'.build/memchr-20261023/m4-rom-read-recovery-v1/original-rom-readback.transfer.json').read_text())['listing']['stdout']
        Identity=dataclasses.make_dataclass('Identity',[('build',str)])
        cases=[('pump',errno.ENXIO,True),('pump',errno.EIO,True),('pump',errno.ENODEV,True),
               ('write',errno.ENXIO,True),('pump',errno.ENXIO,False),('drain',errno.ENXIO,True),('pump',errno.EACCES,True)]
        for phase,number,matching in cases:
            with self.subTest(phase=phase,errno=number,matching=matching),tempfile.TemporaryDirectory(dir=ROOT/'.build',prefix='memchr-fw-test-') as directory:
                out=Path(directory);commands=[]
                class Port:
                    fd=12;text=b'identity\r\ndfu\r\n'
                    def __enter__(self):return self
                    def __exit__(self,*_):self.fd=-1
                    def command(self,*_,**__):return 'identity'
                    def drain(self):
                        if phase=='drain':raise OSError(number,'disconnect before request')
                    def write_line(self,text):
                        self.requested=text
                        if phase=='write':raise OSError(number,'disconnect after request attempt')
                    def pump(self,_):raise OSError(number,'disconnect after request')
                def execute(command,**_):
                    commands.append(command)
                    if '-l' in command:return SimpleNamespace(returncode=0,stdout=(observed if matching else observed.replace(firmware.SERIAL,'000000000000')).encode(),stderr=b'')
                    self.assertIn('-U',command);self.assertNotIn('-D',command);Path(command[-1]).write_bytes(original)
                    return SimpleNamespace(returncode=0,stdout=b'Upload done.\nSubmitting leave request\n',stderr=b'')
                flasher=firmware.ClassicFlash(lambda:None,out)
                good=matching and phase!='drain' and number!=errno.EACCES
                with patch.object(firmware,'connect',side_effect=lambda *_args,**_kw:Port()),patch.object(firmware,'parse_identity',return_value=Identity('3AB3DD45')), \
                     patch.object(firmware,'health',return_value={}),patch.object(firmware,'require_empty'), \
                     patch.object(firmware.subprocess,'run',side_effect=execute),patch.object(firmware.time,'monotonic',side_effect=[0,16]):
                    if good:self.assertEqual(flasher.upload('3AB3DD45',out/'read.bin',firmware.ORIGINAL_SHA),original)
                    else:
                        with self.assertRaises((Hold,OSError)):flasher.upload('3AB3DD45',out/'read.bin',firmware.ORIGINAL_SHA)
                self.assertEqual(any('-U' in command for command in commands),good)
                if good:
                    receipt=json.loads((out/'read.transfer.json').read_text());self.assertEqual(receipt['before']['dfu_usb_disconnect']['errno'],number)
                if phase=='drain' or number==errno.EACCES:self.assertFalse(commands)

    def test_bad_image_and_nonoriginal_recovery_stop_before_device_access(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'.build',prefix='memchr-fw-test-') as directory:
            out=Path(directory);image=out/'bad.bin';image.write_bytes(bytes(524288));flasher=firmware.ClassicFlash(lambda:None,out)
            with patch.object(flasher,'enter') as enter,patch.object(flasher,'ready') as ready:
                with self.assertRaises(Hold):flasher.download('3AB3DD45',image,'0'*64,out/'result.json')
                with self.assertRaises(Hold):flasher.download('3AB3DD45',image,sha(image.read_bytes()),out/'result.json',recovery=True,already_in_dfu=True)
                with self.assertRaises(Hold):flasher.download('3AB3DD45',image,sha(image.read_bytes()),out/'result.json',already_in_dfu=True)
                with self.assertRaises(Hold):flasher.upload('3AB3DD45',out/'read.bin','0'*64,recovery=True)
                with self.assertRaises(Hold):flasher.upload('3AB3DD45',out/'read.bin',firmware.ORIGINAL_SHA,already_in_dfu=True)
                enter.assert_not_called();ready.assert_not_called()
    def test_full_upload_leaves_without_any_download_and_verifies_all_bytes(self):
        raw=(ROOT/'.build/memmove-20261021/m4-v3-flash-hil/flash-original-a.bin').read_bytes()
        Identity=dataclasses.make_dataclass('Identity',[('build',str)])
        class Port:
            fd=10
            def __enter__(self):return self
            def __exit__(self,*_):self.fd=-1
            def command(self,*_,**__):return 'identity'
        commands=[]
        def execute(command,**kwargs):
            commands.append(command);Path(command[-1]).write_bytes(raw)
            return SimpleNamespace(returncode=0,stdout='Upload done.\nSubmitting leave request\n',stderr='')
        with tempfile.TemporaryDirectory(dir=ROOT/'.build',prefix='memchr-fw-test-') as directory:
            out=Path(directory);flasher=firmware.ClassicFlash(lambda:None,out)
            with patch.object(flasher,'enter',return_value=({},b'evidence')),patch.object(flasher,'ready',return_value={}),patch.object(flasher,'guard'), \
                 patch.object(firmware.subprocess,'run',side_effect=execute),patch.object(firmware,'connect',return_value=Port()), \
                 patch.object(firmware,'parse_identity',return_value=Identity('3AB3DD45')),patch.object(firmware,'health',return_value={}):
                self.assertEqual(flasher.upload('3AB3DD45',out/'read.bin',firmware.ORIGINAL_SHA),raw)
            self.assertIn('0x08000000:524288:leave',commands[0]);self.assertIn('-U',commands[0]);self.assertNotIn('-D',commands[0])
            receipt=json.loads((out/'read.transfer.json').read_text());self.assertEqual(receipt['status'],'PASS');self.assertTrue(receipt['serial_closed'])
    def test_rejected_or_timed_out_descriptor_saves_raw_evidence_without_a_transfer(self):
        for timeout in (False,True):
            with self.subTest(timeout=timeout),tempfile.TemporaryDirectory(dir=ROOT/'.build',prefix='memchr-fw-test-') as directory:
                out=Path(directory);flasher=firmware.ClassicFlash(lambda:None,out);commands=[]
                def execute(command,**_):
                    commands.append(command);self.assertIn('-l',command)
                    self.assertEqual(json.loads((out/'read.transfer.json').read_text())['phase'],'rom-ready')
                    if timeout:raise firmware.subprocess.TimeoutExpired(command,8,output=b'partial descriptor\xff',stderr=b'partial stderr\xfe')
                    return SimpleNamespace(returncode=0,stdout=b'Found DFU: [0483:df11] UNKNOWN\r\n',stderr=b'Broken LANGID\r\n')
                with patch.object(flasher,'enter',return_value=({},b'CDC before DFU')),patch.object(flasher,'guard'), \
                     patch.object(firmware.subprocess,'run',side_effect=execute),patch.object(firmware.time,'monotonic',side_effect=[0,16]):
                    with self.assertRaises((Hold,firmware.subprocess.TimeoutExpired)):flasher.upload('3AB3DD45',out/'read.bin',firmware.ORIGINAL_SHA)
                saved=json.loads((out/'read.transfer.json').read_text());self.assertEqual(saved['status'],'HOLD')
                self.assertEqual((out/'read.transfer.serial.bin').read_bytes(),b'CDC before DFU')
                if timeout:
                    self.assertEqual((out/'read.transfer.stdout.bin').read_bytes(),b'partial descriptor\xff')
                    self.assertEqual((out/'read.transfer.stderr.bin').read_bytes(),b'partial stderr\xfe')
                else:
                    self.assertEqual((out/'read.transfer.listing-000.stdout.bin').read_bytes(),b'Found DFU: [0483:df11] UNKNOWN\r\n')
                    self.assertEqual((out/'read.transfer.listing-000.stderr.bin').read_bytes(),b'Broken LANGID\r\n')
                self.assertEqual(len(commands),1)

class RollbackTest(unittest.TestCase):
    def test_real_transport_restores_after_candidate_crash_bad_crc_bad_build_or_lost_cdc(self):
        original=(ROOT/'.build/memmove-20261021/m4-v3-flash-hil/flash-original-a.bin').read_bytes()
        candidate=(ROOT/'.build/memchr-20261023/runtime-a8-v1/candidate-full.bin').read_bytes()
        Identity=dataclasses.make_dataclass('Identity',[('public',str),('usb',str),('profile',str),('build',str)])
        for fault in ('crash','crc','build','cdc','read-timeout','read-failure','write-timeout','write-failure','restore-timeout',
                      'restore-read-timeout','restore-corrupt','retained-crash','retained-crc','restore-no-cdc'):
            with self.subTest(fault=fault),tempfile.TemporaryDirectory(dir=ROOT/'.build',prefix='memchr-fw-test-') as directory:
                base=Path(directory);output=base/'output';lease=base/'lease';lease.write_bytes(b'lease')
                image=base/'candidate.bin';image.write_bytes(candidate)
                device=dict(build=runner.ORIGINAL_BUILD,image=original,in_dfu=False,candidate_seen=False);events=[]
                before={k:k for k in ('reg','stk','dump','hout','pwd')};before['rtc']={}
                class Port:
                    def __init__(self):self.build=device['build'];self.fd=12;self.text=b'trace'
                    def __enter__(self):return self
                    def __exit__(self,*_):self.fd=-1
                    def command(self,command,*_,**__):
                        if command=='crash show' and device['candidate_seen'] and fault=='retained-crash':return 'CRASH retained'
                        if command=='df' and device['candidate_seen'] and fault=='retained-crc':return 'FIRMWARE CRC invalid'
                        return self.build
                    def drain(self):pass
                    def write_line(self,_):pass
                    def pump(self,_=0):pass
                def connect(_path,build=None,**_):
                    if device['in_dfu']:raise TimeoutError('Still in ROM until full readback')
                    if fault=='cdc' and device['build']!=runner.ORIGINAL_BUILD:raise TimeoutError('candidate CDC lost')
                    if fault=='restore-no-cdc' and device['candidate_seen'] and device['build']==runner.ORIGINAL_BUILD:raise TimeoutError('restored CDC lost')
                    if build is not None and build!=device['build']:raise AssertionError('candidate build is corrupt')
                    return Port()
                def health(port,build):
                    if device['build']!=runner.ORIGINAL_BUILD:raise AssertionError('CRASH hardfault' if fault=='crash' else 'FIRMWARE CRC invalid')
                    if device['candidate_seen'] and fault in ('retained-crash','retained-crc'):raise AssertionError('CRASH retained' if fault=='retained-crash' else 'FIRMWARE CRC invalid')
                    return {'mpu status':'static_end=0x200053F8 guard=0x2001BF00+256'}
                def execute(command,**_):
                    failing=False
                    if '-D' in command:
                        data=Path(command[-1]).read_bytes();events.append(('write',sha(data)));device['image']=data
                        if data==candidate:device['candidate_seen']=True
                        else:
                            saved=json.loads((output/'result.json').read_text());self.assertIn('failure',saved)
                            self.assertTrue((output/'failure-before-rollback-transcript.bin').exists())
                            self.assertEqual(command[command.index('-s')+1],'0x08000000')
                            if fault=='restore-corrupt':device['image']=original[:-1]+bytes([original[-1]^1])
                        device['in_dfu']=not command[command.index('-s')+1].endswith(':leave')
                        device['build']=runner.ORIGINAL_BUILD if data==original else ('DEADBEEF' if fault=='build' else runner.wide.BUILD)
                        failing=(data==candidate and fault.startswith('write-')) or (data==original and fault=='restore-timeout')
                        journal=output/('restore-download.json' if data==original else 'candidate-download.json')
                    elif '-U' in command:
                        events.append(('read',sha(device['image'])));failing=fault.startswith('read-') or (Path(command[-1]).name=='restored-full.bin' and fault=='restore-read-timeout')
                        Path(command[-1]).write_bytes(device['image'][:128] if failing else device['image'])
                        device['in_dfu']=False
                        journal=Path(command[-1]).with_suffix('.transfer.json')
                    else:self.fail('Unexpected external operation')
                    self.assertEqual(json.loads(journal.read_text())['phase'],'subprocess')
                    if failing:
                        if fault.endswith('timeout'):raise firmware.subprocess.TimeoutExpired(command,180,output=b'partial\xff stdout',stderr=b'partial\xfe stderr')
                        return SimpleNamespace(returncode=1,stdout='failed stdout',stderr='failed stderr')
                    return SimpleNamespace(returncode=0,stdout='Upload done.\nSubmitting leave request\n',stderr='')
                state=MagicMock();state.capture.return_value=before;state.preflight_recovery.return_value=before
                disk=MagicMock();disk.cleanup.return_value=dict(status='PASS',files_preserved=True,state=dict(status='PASS',preserved=True))
                plan=dict(candidate=str(image),apps=[])
                argv=['run-wide-fw.py','--plan',str(base/'plan'),'--plan-sha256','unused','--port',firmware.PORT,'--output',str(output)]
                with patch.object(sys,'argv',argv),patch.object(runner,'validate',return_value=(plan,lease,sha(b'lease'))), \
                     patch.object(runner,'connect',side_effect=connect),patch.object(firmware,'connect',side_effect=connect),patch.object(runner,'correlate'), \
                     patch.object(runner,'parse_identity',side_effect=lambda b:Identity(runner.UID,runner.SERIAL,'classic-v3-uc1609',b)), \
                     patch.object(firmware,'parse_identity',side_effect=lambda b:Identity(runner.UID,runner.SERIAL,'classic-v3-uc1609',b)), \
                     patch.object(runner,'health',side_effect=health),patch.object(firmware,'health',side_effect=health),patch.object(firmware,'require_empty'), \
                     patch.object(runner,'ClassicState',return_value=state),patch.object(runner,'OwnedSession',return_value=disk), \
                     patch.object(runner,'scan_files',return_value=Files({'/USER.bin':b'original'},set())), \
                     patch.object(firmware.ClassicFlash,'ready',return_value={'pinned_rom_serial':runner.SERIAL}), \
                     patch.object(firmware.subprocess,'run',side_effect=execute):
                    with self.assertRaises((AssertionError,TimeoutError,firmware.subprocess.TimeoutExpired,Hold)) as raised:runner.main()
                if fault.startswith('read-'):self.assertFalse(any(e[0]=='write' for e in events))
                elif fault in ('restore-read-timeout','restore-corrupt'):self.assertEqual(events[-2][0],'write');self.assertEqual(events[-1][0],'read')
                else:self.assertEqual(events[-2:],[('write',firmware.ORIGINAL_SHA),('read',firmware.ORIGINAL_SHA)])
                if fault!='restore-corrupt':self.assertEqual(device['image'],original)
                result=json.loads((output/'result.json').read_text())
                if fault in ('restore-read-timeout','restore-corrupt'):
                    self.assertIsInstance(raised.exception,AssertionError);self.assertEqual(result['status'],'HOLD')
                    self.assertIn('FIRMWARE CRC invalid',result['failure'])
                    self.assertIn('TimeoutExpired' if fault=='restore-read-timeout' else 'readback differs',result['restore_failure'])
                    self.assertTrue(result['firmware_restore_pending']);self.assertNotIn('full_original_flash_verified',result)
                    continue
                if fault in ('retained-crash','retained-crc','restore-no-cdc'):
                    self.assertEqual(result['status'],'HOLD');self.assertTrue(result['full_original_flash_verified']);self.assertFalse(result['firmware_restore_pending'])
                    self.assertEqual(json.loads((output/'restored-full.transfer.json').read_text())['status'],'PASS')
                    continue
                self.assertEqual(result['status'],'FAIL_RESTORED')
                if fault=='restore-timeout':
                    self.assertIsInstance(raised.exception,AssertionError);self.assertIn('TimeoutExpired',result['restore_write_failure'])
                    self.assertEqual((output/'restore-download.stdout.bin').read_bytes(),b'partial\xff stdout')
                if not fault.startswith('read-'):self.assertTrue(result['full_original_flash_verified'])
                self.assertFalse(result['firmware_restore_pending']);self.assertTrue(result['serial_closed'])
                if fault.startswith(('read-','write-')):
                    journal=output/('original-a.transfer.json' if fault.startswith('read-') else 'candidate-download.json')
                    saved=json.loads(journal.read_text());self.assertEqual(saved['status'],'HOLD')
                    if fault.endswith('timeout'):
                        self.assertEqual(saved['failure_type'],'TimeoutExpired')
                        self.assertEqual(journal.with_suffix('.stdout.bin').read_bytes(),b'partial\xff stdout')
                        self.assertEqual(journal.with_suffix('.stderr.bin').read_bytes(),b'partial\xfe stderr')
                    else:
                        self.assertEqual(saved['returncode'],1)
                        self.assertEqual(journal.with_suffix('.stdout.bin').read_bytes(),b'failed stdout')
                        self.assertEqual(journal.with_suffix('.stderr.bin').read_bytes(),b'failed stderr')

    def test_benchmark_failure_still_restores_and_reads_back_entire_original(self):
        before={k:k for k in ('reg','stk','dump','hout','pwd')};before['rtc']={}
        identity=lambda build:SimpleNamespace(public=runner.UID,usb=runner.SERIAL,profile='classic-v3-uc1609',build=build)
        class Port:
            def __init__(self,build):self.build=build or runner.wide.BUILD;self.fd=12;self.text=b'trace'
            def __enter__(self):return self
            def __exit__(self,*_):self.fd=-1
            def command(self,*_,**__):return self.build
        state=MagicMock();state.capture.return_value=before;state.preflight_recovery.return_value=before
        disk=MagicMock();disk.cleanup.return_value=dict(status='PASS',files_preserved=True,state=dict(status='PASS',preserved=True))
        flasher=MagicMock();events=[]
        flasher.upload.side_effect=lambda build,path,digest,**kw:(events.append(('read',build,digest)),b'exact verified image')[1]
        flasher.recovery_health.return_value={}
        flasher.download.side_effect=lambda build,path,digest,receipt,**kw:events.append(('write',digest,kw.get('recovery',False)))
        with tempfile.TemporaryDirectory(dir=ROOT/'.build',prefix='memchr-fw-test-') as directory:
            base=Path(directory);lease=base/'lease';lease.write_bytes(b'lease');app=base/'APP';app.write_bytes(b'app');output=base/'output'
            corpus=dict(full_hardware_correctness_sweep=False)
            plan=dict(candidate=str(app),apps=[dict(directory='/MCHR-W01',shared=False,placement='sram',app=str(app),corpus=corpus)])
            argv=['run-wide-fw.py','--plan',str(base/'plan'),'--plan-sha256','unused','--port',firmware.PORT,'--output',str(output)]
            with patch.object(sys,'argv',argv),patch.object(runner,'validate',return_value=(plan,lease,sha(b'lease'))), \
                 patch.object(runner,'connect',side_effect=lambda _port,build=None,**kw:Port(build)),patch.object(runner,'correlate'), \
                 patch.object(runner,'parse_identity',side_effect=lambda value:identity(value)),patch.object(runner,'health',return_value={'mpu status':'static_end=0x200053F8 guard=0x2001BF00+256'}), \
                 patch.object(runner,'ClassicState',return_value=state),patch.object(runner,'OwnedSession',return_value=disk), \
                 patch.object(runner,'scan_files',return_value=Files({'/USER.bin':b'original'},set())),patch.object(runner,'ClassicFlash',return_value=flasher), \
                 patch.object(runner.wide,'proof',return_value={}),patch.object(runner.wide,'cases',return_value=[(0,0,0,1024,0,0)]), \
                 patch.object(runner,'read_file',return_value=b'failed report'),patch.object(runner.wide,'decode',side_effect=Hold('simulated correctness failure')):
                with self.assertRaisesRegex(Hold,'simulated correctness'):runner.main()
            self.assertEqual(events[-2:], [('write',firmware.ORIGINAL_SHA,True),('read','3AB3DD45',firmware.ORIGINAL_SHA)])
            result=json.loads((output/'result.json').read_text());self.assertEqual(result['status'],'FAIL_RESTORED')
            self.assertTrue(result['full_original_flash_verified']);self.assertTrue(result['serial_closed']);self.assertFalse(result['firmware_restore_pending'])

class MetadataTest(unittest.TestCase):
    def test_seal_covers_all_files_and_binding_uses_the_final_plan_and_runner(self):
        for fault in ('none','stale-binding','changed-command','unlisted-file'):
            with self.subTest(fault=fault),tempfile.TemporaryDirectory() as directory:
                packet=Path(directory);plan=dict(apps=[]);path=packet/'plan.json';path.write_text(json.dumps(plan));digest=sha(path.read_bytes())
                binding=runner.grant(plan,digest)
                if fault=='stale-binding':binding['plan_sha256']='0'*64
                (packet/'requested-lease-binding.json').write_text(json.dumps(binding));(packet/'command.json').write_text('[]')
                (packet/'sha256.json').write_text(json.dumps({p.name:sha(p.read_bytes()) for p in packet.iterdir() if p.is_file()}))
                if fault=='changed-command':(packet/'command.json').write_text('["different"]')
                if fault=='unlisted-file':(packet/'unlisted.bin').write_bytes(b'unlisted')
                if fault=='none':runner.validate_metadata(path,plan,digest)
                else:
                    with self.assertRaises(Hold):runner.validate_metadata(path,plan,digest)

if __name__=='__main__':unittest.main()
