#!/usr/bin/env python3
"""Check disconnected-session evidence and RTC restoration across host sleep."""
from datetime import datetime,timezone
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from hil_m0_math_compare import cleanup_session,rtc_after_wall_elapsed


class Port:
    fd=9876
    text=b'last acknowledgement\r\n*** PANIC ***\r\n'

    def __init__(self,disconnect=False,changed=False,entries=('TIMING.APP','INPUT.bin','RESULT.bin')):
        self.disconnect=disconnect
        self.changed=changed
        self.commands=[]
        self.entries=list(entries)
        self.present=True

    def command(self,command,timeout=5):
        self.commands.append(command)
        if self.disconnect:
            raise OSError('USB disappeared during cleanup')
        if command=='ls /MK61S-M0-TIMING-TEST':
            count=len(self.entries)
            return ''.join(f'f\t17\t{name}\r\n' for name in self.entries)+(
                f'{count} {"entry" if count==1 else "entries"}.\r\n')
        if command.startswith('rm "'):
            self.entries.remove(command.rsplit('/',1)[-1][:-1])
        if command=='rmdir /MK61S-M0-TIMING-TEST':
            assert not self.entries
            self.present=False
        if command=='ls /':return 'MK61S-M0-TIMING-TEST/' if self.present else '0 entries.'
        return 'changed' if self.changed and command=='reg' else 'ok'

    def pump(self,seconds):pass
    def status(self):return 'healthy'


def main():
    before={'reg':'ok','stk':'ok','hout':'ok','pwd':'ok'}
    with TemporaryDirectory(prefix='m0-cleanup-') as temporary:
        output=Path(temporary)
        with patch('hil_m0_math_compare.os.write',return_value=4):
            result=cleanup_session(Port(),output,before,'/MK61S-M0-TIMING-TEST',True,'UID','initial',None)
        assert result['status']=='PASS' and result['calculator_data_preserved']
        assert result['temporary_directory_removed'] and result['cleanup_failure'] is None
        assert (output/'transcript.bin').read_bytes()==Port.text
        with patch('hil_m0_math_compare.os.write',return_value=4):
            partial=Port(entries=('TIMING.APP',))
            result=cleanup_session(partial,output,before,'/MK61S-M0-TIMING-TEST',True,'UID','initial','upload failed')
            assert result['status']=='FAIL' and result['temporary_directory_removed']
            foreign=Port(entries=('TIMING.APP','OTHER.bin'))
            result=cleanup_session(foreign,output,before,'/MK61S-M0-TIMING-TEST',True,'UID','initial','upload failed')
            assert not result['temporary_directory_removed'] and result['cleanup_failure']
            assert not any(cmd.startswith(('rm ','rmdir ')) for cmd in foreign.commands)
        primary=OSError('USB disappeared during input upload')
        try:
            try:
                raise primary
            except OSError as error:
                failure=repr(error)
                raise
            finally:
                cleanup_session(Port(disconnect=True),output,before,'/MK61S-M0-TIMING-TEST',True,'UID','initial',failure)
        except OSError as error:
            assert error is primary,'Cleanup replaced the original failure'
        else:
            raise AssertionError('Original disconnect was swallowed')
        result=json.loads((output/'session.json').read_text())
        assert result['status']=='FAIL' and result['failure']==repr(primary)
        assert 'during cleanup' in result['cleanup_failure']
        assert not result['calculator_data_preserved'] and not result['temporary_directory_removed']
        assert (output/'transcript.bin').read_bytes()==Port.text
        try:
            cleanup_session(Port(disconnect=True),output,before,'/MK61S-M0-TIMING-TEST',True,'UID','initial',None)
        except OSError:pass
        else:raise AssertionError('A cleanup-only failure was swallowed')
        result=json.loads((output/'session.json').read_text())
        assert result['failure'] is None and result['cleanup_failure']
        with patch('hil_m0_math_compare.os.write',return_value=4):
            try:
                cleanup_session(Port(changed=True),output,before,'/MK61S-M0-TIMING-TEST',True,'UID','initial',None)
            except AssertionError:pass
            else:raise AssertionError('Changed calculator data was accepted')
        assert not json.loads((output/'session.json').read_text())['calculator_data_preserved']
    # The elapsed UTC interval includes a thirty-minute host sleep even
    # when a monotonic uptime counter would advance by only two minutes.
    got=rtc_after_wall_elapsed('2026-10-21T17:00:00','2026-10-21T14:00:00+00:00',
                              datetime(2026,10,21,14,32,tzinfo=timezone.utc))
    assert got==datetime(2026,10,21,17,32)
    got=rtc_after_wall_elapsed('2026-10-21T23:59:50','2026-10-21T20:59:50+00:00',
                              datetime(2026,10,21,21,0,10,tzinfo=timezone.utc))
    assert got==datetime(2026,10,22,0,0,10)
    for sample,now in [('2026-10-21T14:00:00',datetime(2026,10,21,14,1,tzinfo=timezone.utc)),
                       ('2026-10-21T14:00:00+00:00',datetime(2026,10,21,13,59,tzinfo=timezone.utc))]:
        try:rtc_after_wall_elapsed('2026-10-21T17:00:00',sample,now)
        except ValueError:pass
        else:raise AssertionError('Invalid wall-clock sample was accepted')
    print('PASS: cleanup evidence, primary exception, state checks and RTC across host sleep/midnight')


if __name__=='__main__':main()
