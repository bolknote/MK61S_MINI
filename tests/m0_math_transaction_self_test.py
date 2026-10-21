#!/usr/bin/env python3
"""Exercise a prepared transaction's restore function with simulated USB only."""
import argparse
import ast
from copy import deepcopy
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from hil_m0_math_compare import rtc_after_wall_elapsed


class Clock(datetime):
    @classmethod
    def now(cls,tz=None):
        value=cls(2026,10,21,14,32,tzinfo=timezone.utc)
        return value.astimezone(tz) if tz else value.replace(tzinfo=None)


class Port:
    text=b'last USB response\r\n*** PANIC ***\r\n'
    def __init__(self,fail=False):
        self.fail=fail
        self.closed=False
        self.commands=[]
        self.rtc='2026-10-21T17:02:00'
    def status(self):
        if self.fail:
            raise OSError('Lost USB after flash')
        return 'RTC='+self.rtc+' RTC_SET=1'
    def command(self,command):
        self.commands.append(command)
        if command.startswith('date '):
            self.rtc=command[5:].replace(' ','T')
        return '/' if command=='pwd' else 'ok'
    def __exit__(self,*_unused):
        self.closed=True


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--driver',type=Path,required=True)
    parser.add_argument('--json',type=Path)
    args=parser.parse_args()
    source=args.driver.read_text()
    tree=ast.parse(source)
    nodes=[node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=='install']
    assert len(nodes)==1
    module=ast.fix_missing_locations(ast.Module(body=nodes,type_ignores=[]))
    initial=dict(before={'pwd':'/'},settings_before={},
        clock_before={'configured':True,'date':'2026-10-21T17:00:00'},
        clock_sample_utc='2026-10-21T14:00:00+00:00',clock_sample_monotonic=0)
    # Thirty-two minutes of UTC elapsed, including thirty minutes asleep;
    # the old host monotonic counter would report only two minutes.
    with TemporaryDirectory(prefix='m0-transaction-') as temporary:
        output=Path(temporary)
        device=Port()
        namespace=dict(datetime=Clock,timezone=timezone,time=SimpleNamespace(monotonic=lambda:120),
            out=output,state=deepcopy(initial),tool=Path('SIMULATED-NO-USB'),uid='SIMULATED',
            re=re,enter_rom=lambda:None,connect=lambda:device,healthy=lambda *args:None,
            restore=lambda *args:None,restore_ip=lambda *args:None,save=lambda:None,
            rtc_after_wall_elapsed=rtc_after_wall_elapsed,
            subprocess=SimpleNamespace(run=lambda *args,**kwargs:SimpleNamespace(
                returncode=0,stdout='SIMULATED: no process was launched',stderr='')))
        exec(compile(module,str(args.driver),'exec'),namespace)
        with patch('hil_m0_math_compare.datetime',Clock):
            namespace['install'](output,{'build_id':'a7483ae6'},'control_restore')
        assert device.closed and device.rtc=='2026-10-21T17:32:00',device.commands
        result=namespace['state']['clock_restored']
        assert result['method']=='UTC wall elapsed including host sleep'
        assert result['error_seconds']==0,result
        assert result['sampled_at_utc']==initial['clock_sample_utc']
        assert (output/'control_restore-transcript.bin').read_bytes()==Port.text
        success=result

        device=Port(fail=True)
        namespace['state']=deepcopy(initial)
        try:
            namespace['install'](output,{'build_id':'a7483ae6'},'failed_install')
        except OSError as error:
            assert str(error)=='Lost USB after flash'
        else:
            raise AssertionError('Disconnected install was accepted')
        assert device.closed
        assert (output/'failed_install-transcript.bin').read_bytes()==Port.text

        device=Port()
        namespace['state']=deepcopy(initial)
        namespace['state']['clock_before']['configured']=False
        namespace['install'](output,{'build_id':'a7483ae6'},'control_restore')
        assert device.closed and not any(c.startswith('date ') for c in device.commands)

    report=dict(status='PASS',driver=str(args.driver),
        driver_sha256=hashlib.sha256(args.driver.read_bytes()).hexdigest(),
        clock_restored_after_host_sleep=success,failed_install_transcript_saved=True,
        original_install_exception_preserved=True,serial_closed_after_failure=True,
        unconfigured_RTC_not_set=True,hardware_opened=False,
        scope='Only the actual prepared install function is compiled from its AST. USB, flash tool, health and data restoration callbacks are simulated; this proves RTC calculation and failure evidence handling, not physical device restoration.')
    text=json.dumps(report,indent=2)+'\n'
    if args.json:
        args.json.write_text(text)
    print(text,end='')


if __name__=='__main__':
    main()
