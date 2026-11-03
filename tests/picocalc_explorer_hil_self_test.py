#!/usr/bin/env python3
"""Failure-path tests only: fake ports, no device enumeration or serial I/O."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import hil_picocalc_explorer as hil

BUILD='FAD3AEEB'
UID='0000000000000001'
DIRECTORY='/MK61S-EXPLORER-20261103-000000'


def status(keys=0,service='BROWSER',dirty=0,steps=105,memory=2):
    return f'BUILD={BUILD} FIRMWARE_CRC=valid CRASH=NONE DIRTY={dirty} M61_ACTIVE=0 USB_DISK=0 RUN=0 BUSY=0 SLEEP=0 SERVICE={service} PHYSICAL_KEYS={keys} MEMORY={memory} STEPS={steps}'


def snapshot(steps=105):
    return {
        'reg':''.join(f'R{i:X} =  1.0000000  00\r\n' for i in range(15)),
        'stk':''.join(f'S{i:X} =  1.0000000  00\r\n' for i in range(5)),
        'hout':''.join(f'hin {start:04d} '+bytes(range(start,min(start+24,steps))).hex()+'\r\n'
                       for start in range(0,steps,24)),
        'pwd':'/\r\nmk61> ',
    }


class FakePort:
    def __init__(self,statuses=None,replies=None):
        self.statuses=list(statuses or [status()]);self.replies=replies or snapshot()
        self.calls=[];self.closed=False;self.text=bytearray()
    def status(self):
        self.calls.append('status')
        result=self.statuses.pop(0) if len(self.statuses)>1 else self.statuses[0]
        if isinstance(result,Exception):raise result
        return result
    def command(self,text,**kwargs):
        self.calls.append(text);return self.replies.get(text,'OK')
    def send(self,*args):self.calls.append(('send',args))
    def pump(self,*args):self.calls.append('pump')
    def expect(self,*args):pass
    def __exit__(self,*args):self.closed=True


class GuardTests(unittest.TestCase):
    def finish(self,port,before=None,initial=None):
        report={'passed':False}
        with patch.object(hil,'calculator') as calculator,patch.object(hil,'restore') as restore:
            hil.finish(port,snapshot() if before is None else before,status() if initial is None else initial,BUILD,report,DIRECTORY,True)
        return report,calculator,restore

    def test_exception_before_next_check_with_new_physical_input(self):
        # Models an assert/timeout in the body before check() sets its flag.
        port=FakePort([status(keys=1)])
        report,calculator,restore=self.finish(port)
        self.assertEqual(port.calls,['status'])
        calculator.assert_not_called();restore.assert_not_called()
        self.assertTrue(report['unexpected_physical_input'])
        self.assertFalse(report['passed'])

    def test_body_exception_closes_and_logs_without_cleanup_mutations(self):
        class BodyFailure(FakePort):
            def command(self,text,**kwargs):
                result=super().command(text,**kwargs)
                if text.startswith('mkdir '):raise RuntimeError('body failed before check')
                return result
        for guard in (status(keys=1),TimeoutError('lost guard')):
            with self.subTest(guard=guard),tempfile.TemporaryDirectory() as temporary:
                port=BodyFailure([status(),guard]);output=Path(temporary)/'evidence'
                argv=['hil','--port','/not-a-device','--uid',UID,'--build-id',BUILD,'--output',str(output)]
                with patch.object(hil.sys,'argv',argv),patch.object(hil,'connect_checked',return_value=port),\
                     patch.object(hil,'calculator') as calculator,patch.object(hil,'restore') as restore:
                    with self.assertRaisesRegex(RuntimeError,'body failed'):
                        hil.main()
                calculator.assert_called_once();restore.assert_not_called()
                self.assertTrue(port.closed)
                self.assertEqual(port.calls[-1],'status')
                self.assertFalse(any(isinstance(call,str) and call.startswith('rm ') for call in port.calls))
                self.assertFalse(any(isinstance(call,tuple) for call in port.calls))
                report=json.loads((output/'report.json').read_text())
                self.assertFalse(report['passed'])
                self.assertIn('cleanup_skipped',report)
                self.assertTrue((output/'transcript.bin').exists())

    def test_unchanged_snapshot_can_remove_only_its_private_directory(self):
        port=FakePort();report,calculator,restore=self.finish(port)
        calculator.assert_called_once();restore.assert_not_called()
        self.assertTrue(report['data_unchanged'])
        self.assertTrue(report['temporary_directory_removed'])
        removal=port.calls.index('rm -r '+DIRECTORY)
        self.assertEqual(port.calls[removal-1],'status')

    def test_unavailable_guard_is_read_only(self):
        port=FakePort([TimeoutError('no status')])
        report,calculator,restore=self.finish(port)
        self.assertEqual(port.calls,['status'])
        calculator.assert_not_called();restore.assert_not_called()
        self.assertIn('TimeoutError',report['cleanup_skipped'])

    def test_unknown_or_dirty_foreground_is_read_only(self):
        for current in (status(service='EDITOR',dirty=1),status(service='CONSOLE'),status().replace('SLEEP=0','SLEEP=1')):
            with self.subTest(current=current):
                port=FakePort([current]);report,calculator,restore=self.finish(port)
                self.assertEqual(port.calls,['status'])
                calculator.assert_not_called();restore.assert_not_called()
                self.assertFalse(report['passed'])

    def test_guard_is_repeated_before_restore(self):
        changed=snapshot();changed['reg']=changed['reg'].replace('1.0000000','2.0000000',1)
        port=FakePort([status(),status(keys=1)],changed)
        report,calculator,restore=self.finish(port)
        calculator.assert_called_once();restore.assert_not_called()
        self.assertNotIn('rm -r '+DIRECTORY,port.calls)
        self.assertTrue(report['unexpected_physical_input'])

    def test_guard_is_repeated_before_removal(self):
        for second in (status(keys=1),TimeoutError('lost status')):
            with self.subTest(second=second):
                port=FakePort([status(),second]);report,calculator,restore=self.finish(port)
                calculator.assert_called_once();restore.assert_not_called()
                self.assertNotIn('rm -r '+DIRECTORY,port.calls)
                self.assertFalse(report['passed'])

    def test_snapshot_must_be_complete_before_any_mutation(self):
        cases=[{}]
        bad=snapshot();bad['reg']=bad['reg'].splitlines()[0];cases.append(bad)
        bad=snapshot();bad['stk']=bad['stk'].replace('S4','S3');cases.append(bad)
        for key in ('reg','stk','hout','pwd'):
            bad=snapshot();bad[key]='';cases.append(bad)
        bad=snapshot();bad['hout']='hin garbage';cases.append(bad)
        bad=snapshot();bad['hout']='hin 0024 00\r\n';cases.append(bad)
        bad=snapshot();bad['hout']='\r\n'.join(bad['hout'].splitlines()[:-1])+'\r\n';cases.append(bad)
        bad=snapshot();bad['hout']=bad['hout'][:-4]+'\r\n';cases.append(bad)
        bad=snapshot();bad['pwd']='unknown';cases.append(bad)
        for before in cases:
            with self.subTest(before=before):
                port=FakePort();report,calculator,restore=self.finish(port,before)
                self.assertEqual(port.calls,[])
                calculator.assert_not_called();restore.assert_not_called()
                self.assertFalse(report['passed'])
        self.assertFalse(hil.same_snapshot({},{},105))
        for steps in (105,112):
            hil.validate_snapshot(snapshot(steps),steps)
            self.assertTrue(hil.same_snapshot(snapshot(steps),snapshot(steps),steps))

    def test_unknown_or_inconsistent_program_mode_is_read_only(self):
        for initial in ('',status(memory=3),status(steps=48),status(memory=0,steps=112),status(memory=1,steps=105)):
            with self.subTest(initial=initial):
                port=FakePort();report,calculator,restore=self.finish(port,initial=initial)
                self.assertEqual(port.calls,[])
                calculator.assert_not_called();restore.assert_not_called()
                self.assertFalse(report['passed'])

    def test_real_active_bank_lengths_pass_cleanup(self):
        for steps in (105,112):
            with self.subTest(steps=steps):
                port=FakePort([status(steps=steps)],snapshot(steps))
                report,calculator,restore=self.finish(port,snapshot(steps),status(steps=steps))
                calculator.assert_called_once();restore.assert_not_called()
                self.assertTrue(report['data_unchanged'])
                self.assertTrue(report['temporary_directory_removed'])

    def test_truncated_initial_bank_stops_before_navigation(self):
        short=snapshot();short['hout']='\r\n'.join(short['hout'].splitlines()[:-1])+'\r\n'
        for current,replies in ((status(),short),(status(),snapshot(104)),(status(steps=112),snapshot(111)),(status(memory=7),snapshot())):
            with self.subTest(current=current,replies=replies),tempfile.TemporaryDirectory() as temporary:
                port=FakePort([current],replies);output=Path(temporary)/'evidence'
                argv=['hil','--port','/not-a-device','--uid',UID,'--build-id',BUILD,'--output',str(output)]
                with patch.object(hil.sys,'argv',argv),patch.object(hil,'connect_checked',return_value=port),\
                     patch.object(hil,'calculator') as calculator,patch.object(hil,'restore') as restore:
                    with self.assertRaises(AssertionError):hil.main()
                calculator.assert_not_called();restore.assert_not_called()
                self.assertTrue(port.closed)
                self.assertTrue(all(call in ('status','reg','stk','hout','pwd') for call in port.calls))
                self.assertFalse(json.loads((output/'report.json').read_text())['passed'])

    def test_incomplete_final_snapshot_does_not_trigger_restore(self):
        replies=snapshot();replies['reg']=''
        port=FakePort([status()],replies);report,calculator,restore=self.finish(port)
        calculator.assert_called_once();restore.assert_not_called()
        self.assertNotIn('rm -r '+DIRECTORY,port.calls)
        self.assertIn('Invalid final snapshot',report['cleanup_skipped'])


class ConnectTests(unittest.TestCase):
    def test_uid_mismatch_and_handshake_exceptions_close_port(self):
        for error in (None,ValueError('handshake failed'),TimeoutError('handshake timeout')):
            with self.subTest(error=error):
                port=FakePort()
                def enter():return port
                def commands():
                    if error:raise error
                def close(*args):port.closed=True
                port.__enter__=enter;port.commands=commands;port.__exit__=close
                port.replies['identity']='UID=0000000000000002'
                with self.assertRaises(type(error) if error else AssertionError):
                    hil.connect_checked('/not-a-device',UID,lambda *a,**k:port)
                self.assertTrue(port.closed)


if __name__=='__main__':unittest.main()
