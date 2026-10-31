#!/usr/bin/env python3
"""Focused negative tests for the APP-only lease, namespace and recovery."""
import copy
import importlib.util
import json
from pathlib import Path
import shlex
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import session
spec=importlib.util.spec_from_file_location('memchr_run_app',HERE/'run-app.py')
app=importlib.util.module_from_spec(spec);spec.loader.exec_module(app)
HOUT='\r\n'.join('hin '+f'{at:04d}'+' '+bytes(min(24,105-at)).hex().upper() for at in range(0,105,24))

class Disk:
    def __init__(self):
        self.files={'/USER.bin':b'original user bytes'};self.dirs=set();self.commands=[];self.writes=[];self.mkdir_mode='ok'
    def scan(self):return session.Files(dict(self.files),set(self.dirs))
    def command(self,text):
        self.commands.append(text);parts=shlex.split(text);op=parts[0]
        if op=='mkdir':
            if self.mkdir_mode=='error':return 'mkdir: entry exists\r\n/> '
            self.dirs.add(parts[1])
            if self.mkdir_mode=='lost':raise TimeoutError('mkdir ACK lost')
            if self.mkdir_mode=='lost-unknown':
                self.files[parts[1]+'/KEEP.bin']=b'unknown';raise TimeoutError('mkdir ACK lost')
        elif op=='rm':del self.files[parts[1]]
        elif op=='rmdir':
            assert not any(p.startswith(parts[1]+'/') for p in [*self.files,*self.dirs])
            self.dirs.remove(parts[1])
        elif text!='fsput cancel':raise AssertionError(text)
        return text+'\r\n/> '
    def write(self,path,data):self.writes.append((path,data));self.files[path]=data
    def owned(self):
        saved=[]
        owned=session.OwnedSession('/MCHR-M01',self.scan,self.files.__getitem__,self.write,self.command,lambda row:saved.append(copy.deepcopy(row)))
        return owned,saved

class NamespaceTest(unittest.TestCase):
    def test_case_variant_file_and_directory_block_before_write(self):
        for kind in ('file','directory'):
            disk=Disk()
            if kind=='file':disk.files['/mchr-m01']=b'do not touch'
            else:disk.dirs.add('/mchr-m01')
            owned,_=disk.owned()
            with self.assertRaises(session.Hold):owned.capture()
            self.assertEqual(disk.commands,[]);self.assertEqual(disk.writes,[])
    def test_mkdir_error_never_claims_ownership(self):
        disk=Disk();owned,_=disk.owned();owned.capture();disk.mkdir_mode='error'
        with self.assertRaises(session.Hold):owned.create()
        self.assertFalse(owned.created);self.assertEqual(disk.writes,[])
    def test_mkdir_lost_ack_requires_exact_empty_namespace_proof(self):
        disk=Disk();owned,saved=disk.owned();owned.capture();disk.mkdir_mode='lost';owned.create()
        self.assertTrue(owned.created);self.assertIn('ACK lost',saved[-1]['mkdir_ack_lost'])
        owned.cleanup();self.assertEqual(disk.files,{'/USER.bin':b'original user bytes'});self.assertFalse(disk.dirs)
    def test_mkdir_lost_ack_unknown_child_is_preserved(self):
        disk=Disk();owned,_=disk.owned();owned.capture();disk.mkdir_mode='lost-unknown'
        with self.assertRaises(session.Hold):owned.create()
        count=len(disk.commands)
        with self.assertRaises(session.Hold):owned.cleanup()
        self.assertEqual(len(disk.commands),count);self.assertEqual(disk.files['/MCHR-M01/KEEP.bin'],b'unknown')
    def test_unknown_file_child_directory_and_content_block_all_cleanup_mutations(self):
        for kind in ('file','directory','changed-owned','root-file'):
            disk=Disk();owned,_=disk.owned();owned.capture();owned.create();owned.put('CHRBEN.APP',b'approved')
            if kind=='file':disk.files['/MCHR-M01/UNKNOWN.bin']=b'unknown'
            elif kind=='directory':disk.dirs.add('/MCHR-M01/CHILD')
            elif kind=='root-file':disk.files['/NEW.bin']=b'unknown'
            else:disk.files['/MCHR-M01/CHRBEN.APP']=b'other APP'
            before=disk.scan();count=len(disk.commands);writes=len(disk.writes);state=Mock()
            with self.assertRaises(session.Hold):owned.cleanup(state,state)
            self.assertEqual(disk.scan(),before);self.assertEqual(len(disk.commands),count);self.assertEqual(len(disk.writes),writes);state.assert_not_called()
    def test_point_cleanup_keeps_input_versions_and_admits_valid_result(self):
        disk=Disk();owned,saved=disk.owned();before=owned.capture();owned.create()
        owned.put('CHRBEN.APP',b'approved');owned.put('INPUT.bin',b'one');owned.put('INPUT.bin',b'two')
        owned.expect_result(lambda b:b==b'recognized result',dict(input_sha='two'))
        disk.files['/MCHR-M01/RESULT.bin']=b'recognized result'
        result=owned.cleanup()
        self.assertEqual(result['status'],'PASS');self.assertEqual(disk.scan(),before)
        self.assertFalse(any('rm -r' in c for c in disk.commands));self.assertEqual(saved[-1]['cleanup_status'],'PASS')
    def test_known_original_file_and_directory_are_restored(self):
        disk=Disk();disk.dirs.add('/USER');disk.files['/USER/SAVE.bin']=b'preserved'
        owned,_=disk.owned();before=owned.capture();owned.create();owned.put('CHRBEN.APP',b'approved')
        disk.files['/USER.bin']=b'changed';del disk.files['/USER/SAVE.bin'];disk.dirs.remove('/USER')
        result=owned.cleanup()
        self.assertTrue(result['files_restored']);self.assertFalse(result['files_preserved']);self.assertEqual(disk.scan(),before)
    def test_state_failure_is_never_recorded_as_restored(self):
        disk=Disk();owned,saved=disk.owned();owned.capture();owned.create();owned.put('CHRBEN.APP',b'approved')
        with self.assertRaisesRegex(RuntimeError,'state recovery failed'):
            owned.cleanup(lambda:'changed',Mock(side_effect=RuntimeError('state recovery failed')))
        self.assertNotEqual(saved[-1].get('cleanup_status'),'PASS')
    def test_ambiguous_casefold_namespace_rejected(self):
        with self.assertRaises(session.Hold):session.Files({'/A.bin':b'a','/a.bin':b'b'},set()).validate()
    def test_c9_canonical_app_extension_requires_exact_owned_bytes(self):
        for changed in (False,True):
            disk=Disk();owned,_=disk.owned();before=owned.capture();owned.create();owned.put('CHRBEN.APP',b'approved')
            disk.files['/MCHR-M01/CHRBEN.app']=disk.files.pop('/MCHR-M01/CHRBEN.APP')
            if changed:
                disk.files['/MCHR-M01/CHRBEN.app']=b'unknown';count=len(disk.commands)
                with self.assertRaises(session.Hold):owned.cleanup()
                self.assertEqual(len(disk.commands),count)
            else:
                owned.cleanup();self.assertEqual(disk.scan(),before)
                self.assertIn('rm "/MCHR-M01/CHRBEN.app"',disk.commands)

class StateTest(unittest.TestCase):
    def fixture(self):
        port=Mock();state=session.ClassicState(port,lambda s:s,lambda s:None)
        original=dict(reg='IP: 0',stk='all zero',dump='00'*105,hout=HOUT,pwd='/',
            rtc=dict(calendar='2026-10-23 08:00:00.000',unset=False,wall_utc=1000))
        state.before=copy.deepcopy(original)
        return state,port,original
    def test_changed_state_is_actually_recovered_and_verified(self):
        state,port,original=self.fixture();changed=copy.deepcopy(original);changed['reg']='IP: 7'
        state.read=Mock(return_value=original);port.command.return_value='/> '
        result=state.recover(changed)
        self.assertTrue(result['restored']);self.assertFalse(result['preserved']);self.assertGreater(port.command.call_count,20)
        for c in result['actions']:self.assertFalse(c.startswith(('rst','dfu','clear','format')))
    def test_ignored_state_restoration_raises(self):
        state,port,original=self.fixture();changed=copy.deepcopy(original);changed['reg']='IP: 7'
        state.read=Mock(return_value=changed);port.command.return_value='/> '
        with self.assertRaisesRegex(session.Hold,'did not verify'):state.recover(changed)
    def test_unset_rtc_changed_stops_before_restoration_mutations(self):
        state,port,original=self.fixture();state.before['rtc'].update(calendar=None,unset=True)
        state.read=Mock(return_value=original)
        with self.assertRaisesRegex(session.Hold,'unset flag'):state.preflight_recovery()
        port.command.assert_not_called()
    def test_actual_unset_2001_calendar_advances_without_date_write(self):
        state,port,original=self.fixture()
        original['rtc']=dict(calendar='2001-01-01 00:05:10.000',unset=True,wall_utc=1000)
        state.before=copy.deepcopy(original);after=copy.deepcopy(original)
        after['rtc'].update(calendar='2001-01-01 00:05:40.000',wall_utc=1030)
        self.assertTrue(state.trajectory(after['rtc']))
        state.read=Mock(return_value=after)
        self.assertEqual(state.preflight_recovery(),after)
        result=state.recover(after)
        self.assertTrue(result['preserved']);self.assertFalse(result['restored']);port.command.assert_not_called()
    def test_unset_calendar_corruption_never_sets_date(self):
        state,port,original=self.fixture();original['rtc'].update(calendar='2001-01-01 00:05:10.000',unset=True)
        state.before=copy.deepcopy(original);after=copy.deepcopy(original)
        after['rtc'].update(calendar='2001-01-02 00:05:10.000',wall_utc=1001)
        state.read=Mock(return_value=after)
        with self.assertRaises(session.Hold):state.preflight_recovery()
        with self.assertRaises(session.Hold):state.recover(after)
        port.command.assert_not_called()
    def test_unset_flag_change_with_valid_calendar_never_sets_date(self):
        state,port,original=self.fixture();original['rtc'].update(calendar='2001-01-01 00:05:10.000',unset=True)
        state.before=copy.deepcopy(original);after=copy.deepcopy(original);after['rtc']['unset']=False
        state.read=Mock(return_value=after)
        with self.assertRaises(session.Hold):state.recover(after)
        port.command.assert_not_called()
    def test_explicit_hout_captures_complete_classic_program(self):
        state,port,original=self.fixture()
        port.command.side_effect=lambda command,**_: ('hout 0 105\r\n'+HOUT+'\r\n/> ' if command=='hout 0 105' else
            '2001-01-01 00:00:00.000\r\nSet the date.\r\n/> ' if command=='date ms' else
            'RTC ALARM A off\r\nRTC ALARM B off\r\n/> ' if command=='alarm' else original[command])
        result=state.capture()
        self.assertEqual(len(state.replay(result['hout'])),5)
        port.command.assert_any_call('hout 0 105',timeout=15)
        self.assertNotIn('hout',[c.args[0] for c in port.command.call_args_list])
    def test_legacy_empty_hout_and_gapped_replay_fail_without_writes(self):
        for text in ('hout\r\n/> ',HOUT.replace('hin 0024','hin 0025'),HOUT.replace('hin 0000 00','hin 0000 FF'),HOUT.rsplit('\r\n',1)[0]):
            with self.assertRaises(session.Hold):session.ClassicState.replay(text)
    def test_failed_capture_saves_raw_state_before_validation_error(self):
        state,port,original=self.fixture();original['hout']='hout\r\n/> '
        state.read=Mock(return_value=original);save=Mock()
        with self.assertRaises(session.Hold):state.capture(save)
        save.assert_called_once_with(original);port.command.assert_not_called()

class LeaseTest(unittest.TestCase):
    def test_exact_lease_and_all_tampered_pins_before_serial(self):
        root=app.ROOT;frozen=root/'.build/memchr-20261022/m4-app-v1'
        if not frozen.exists():self.skipTest('Prepared APP is required')
        with tempfile.TemporaryDirectory() as directory:
            plan_path=Path(directory)/'plan.json';lease_path=Path(directory)/'lease.json'
            plan=dict(cpu='m4',uid=app.UID,usb_serial=app.SERIAL,build=app.BUILD,directory=app.DIRECTORY,
                app_sha256=app.APP_SHA,scope='APP-only',port='/unused',dependencies=app.dependencies(),
                app=str(frozen/'app/CHRBEN.APP'),elf=str(frozen/'app/CHRBEN.elf'),
                elf_sha256=session.sha((frozen/'app/CHRBEN.elf').read_bytes()),manifest=str(frozen/'benchmark.json'))
            plan_path.write_text(json.dumps(plan));digest=session.sha(plan_path.read_bytes())
            grant=dict(plan_sha256=digest,runner_sha256=session.sha((HERE/'run-app.py').read_bytes()),app_sha256=app.APP_SHA,
                cpu='m4',uid=app.UID,usb_serial=app.SERIAL,build=app.BUILD,directory=app.DIRECTORY,scope='APP-only')
            lease=dict(owner='memchr',owner_thread=app.THREAD,state='reserved_app_only',build=app.BUILD,memchr_approval=grant)
            lease_path.write_text(json.dumps(lease));app.validate(plan_path,digest,'/unused',lease_path)
            for key in grant:
                broken=copy.deepcopy(lease);broken['memchr_approval'][key]='wrong';lease_path.write_text(json.dumps(broken))
                with self.assertRaises(session.Hold):app.validate(plan_path,digest,'/unused',lease_path)
            lease_path.write_text(json.dumps(lease))
            with self.assertRaises(session.Hold):app.validate(plan_path,'0'*64,'/unused',lease_path)
            with self.assertRaises(session.Hold):app.validate(plan_path,digest,'/other',lease_path)
            lease['owner']='other';lease_path.write_text(json.dumps(lease))
            with self.assertRaises(session.Hold):app.validate(plan_path,digest,'/unused',lease_path)

class EarlyFailureTest(unittest.TestCase):
    def test_main_preserves_raw_state_and_transcript_on_readonly_preflight_failure(self):
        initial_path=app.ROOT/'.build/memchr-20261023/m4-app-only-hil-v3/result.json'
        if not initial_path.exists():self.skipTest('Actual read-only baseline fixture is required')
        initial=json.loads(initial_path.read_text())['initial_health']
        original={c:initial[c] for c in ('reg','stk','dump','pwd')}
        original.update(hout='hout\r\n/> ',rtc=dict(calendar='2001-01-01 00:00:00.000',unset=True,wall_utc=1000))
        class Port:
            fd=17;text=b'identity\r\nactual preflight hout reply\r\n/> '
            def __enter__(self):return self
            def __exit__(self,*_):self.fd=-1
            def command(self,text,**_):assert text=='identity';return 'identity reply'
        port=Port();identity=SimpleNamespace(public=app.UID,usb=app.SERIAL,profile='classic-v3-uc1609',build=app.BUILD)
        with tempfile.TemporaryDirectory(dir=app.ROOT/'.build',prefix='memchr-preflight-test-') as directory:
            base=Path(directory);lease=base/'lease';lease.write_bytes(b'lease');output=base/'result'
            argv=['run-app.py','--plan',str(base/'plan'),'--plan-sha256','unused','--port','/unused','--output',str(output)]
            with patch.object(sys,'argv',argv),patch.object(app,'validate',return_value=({},b'app',lease,session.sha(b'lease'))), \
                 patch.object(app,'connect',return_value=port),patch.object(app,'correlate'),patch.object(app,'parse_identity',return_value=identity), \
                 patch.object(app,'health',return_value=initial),patch.object(app.ClassicState,'read',return_value=original), \
                 patch.object(app,'OwnedSession') as filesystem,patch.object(app,'write_file') as write:
                with self.assertRaises(session.Hold):app.main()
                filesystem.assert_not_called();write.assert_not_called()
            result=json.loads((output/'result.json').read_text())
            self.assertEqual(result['status'],'HOLD');self.assertTrue(result['serial_closed'])
            self.assertFalse(result['filesystem_mutation_attempted']);self.assertFalse(result['cleanup_pending'])
            self.assertEqual((output/'transcript.bin').read_bytes(),port.text)
            self.assertEqual(json.loads((output/'calculator-before.json').read_text())['hout'],original['hout'])

if __name__=='__main__':unittest.main()
