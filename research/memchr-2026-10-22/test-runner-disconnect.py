#!/usr/bin/env python3
"""Keep recovery evidence if USB loss breaks both APP upload and cleanup."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
spec=importlib.util.spec_from_file_location('search_runner',HERE/'run.py')
runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)

class DisconnectedPort:
    text=b'received bytes before USB loss'
    closed=False
    def __enter__(self):return self
    def __exit__(self,*_):self.closed=True
    def status(self):
        return ('RP2040 125 MHz POWER_MODE=RUN SYS_HZ=125000000 '
            'RUN=0 BUSY=0 USB_DISK=0 RUNTIME=NONE SERVICE=CLOSED DIRTY=0 '
            'FIRMWARE_CRC=valid CRASH=NONE BUILD=4AFD4305 BOOTS=1 IP=24')
    def commands(self):pass
    def command(self,command,**_):
        if command=='identity':return 'UID=E6657CD423721C35'
        if command=='fsput cancel':raise OSError('USB gone during cleanup')
        if command in ('reg','stk','hout','dump','pwd'):return 'saved '+command
        return 'mk61> '

with tempfile.TemporaryDirectory(prefix='memchr-disconnect-') as directory:
    work=Path(directory);app=work/'frozen/app/CHRBEN.APP';app.parent.mkdir(parents=True)
    app.write_bytes(b'not executed')
    manifest=dict(app_sha256=hashlib.sha256(app.read_bytes()).hexdigest(),directory='/MCHR-TEST',target='picocalc-pico-h')
    (app.parents[1]/'benchmark.json').write_text(json.dumps(manifest))
    fake_root=work/'root';(fake_root/'.build').mkdir(parents=True)
    lease=fake_root/'.build/picocalc-device-handoff.json'
    lease.write_text(json.dumps(dict(owner='somebody-else',build='4AFD4305')))
    output=work/'result';port=DisconnectedPort()
    arguments=['run.py','--cpu','m0','--port','/unused','--uid','E6657CD423721C35','--build','4AFD4305',
        '--app',str(app),'--directory','/MCHR-TEST','--output',str(output),'--runs','1',
        '--sizes','1','--alignments','0','--modes','0']
    with patch.object(sys,'argv',arguments),patch.object(runner,'ROOT',fake_root), \
         patch.object(runner.old,'BenchPort') as constructor:
        try:runner.main()
        except AssertionError as error:assert 'handoff' in str(error)
        else:raise AssertionError('Another owner was ignored')
        constructor.assert_not_called()
        assert not output.exists()
    lease.write_text(json.dumps(dict(owner='memchr',build='4AFD4305')))
    def lose_usb(*_):
        saved=json.loads((output/'result.json').read_text())
        assert saved['before']['dump']=='saved dump' and 'IP=24' in saved['awake_status']
        raise OSError('USB gone during upload')
    with patch.object(sys,'argv',arguments),patch.object(runner,'ROOT',fake_root), \
         patch.object(runner.old,'BenchPort',return_value=port),patch.object(runner,'write_file',side_effect=lose_usb):
        try:runner.main()
        except OSError as error:assert str(error)=='USB gone during upload'
        else:raise AssertionError('Upload failure was swallowed')
    result=json.loads((output/'result.json').read_text())
    assert result['status']=='FAIL' and result['cleanup_pending']
    assert 'upload' in result['failure'] and 'cleanup' in result['cleanup_failure']
    assert set(result['before'])=={'reg','stk','hout','dump','pwd'}
    assert not result['calculator_data_preserved'] and not result['files_preserved']
    assert not result['temporary_directory_removed']
    assert (output/'transcript.bin').read_bytes()==port.text and port.closed
print('PASS: ownership checked before serial; snapshot and both failures survive USB loss')
