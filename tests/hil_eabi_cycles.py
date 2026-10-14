#!/usr/bin/env python3
"""Measure 48 resident soft EABI calls using DWT; verify results and preserve device data."""
import argparse
import json
from pathlib import Path
import struct
from hil_portable_apps import ScreenPort
from hil_multi_device_identity import parse_identity
from hil_packbits_firmware import fingerprint
from hil_c5_stack import read_file,write_file
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--port',required=True)
p.add_argument('--public-id',required=True)
p.add_argument('--expected-build',required=True)
p.add_argument('--keyboard-layout',type=int,choices=(0,1),default=1)
p.add_argument('--app',type=Path,required=True)
p.add_argument('--output-dir',type=Path,required=True)
a=p.parse_args();a.output_dir.mkdir(parents=True,exist_ok=True)
remote=('/ALUBENCH.APP','/ALUOUT.bin');names=('add','sub','mul','div')
real=lambda x:struct.unpack('<d',struct.pack('<Q',x))[0]
bits=lambda x:struct.unpack('<Q',struct.pack('<d',x))[0]
with ScreenPort(a.port,keyboard_layout=a.keyboard_layout) as port:
    identity=parse_identity(port.command('identity',15))
    assert identity.public==a.public_id.upper() and identity.build==a.expected_build.upper(),identity
    port.command('prof',20)
    before=fingerprint(port);state={c:port.command(c,20) for c in ('reg','stk','dump','pwd')}
    assert not {x.casefold() for x in remote}.intersection(x.casefold() for x in before['files'])
    report={'identity':identity.__dict__,'samples':1024,'rounds':9,
            'method':'median DWT batches minus identical soft-call identity loop; resident code in Flash, caller in SRAM'}
    try:
        write_file(port,remote[0],a.app.read_bytes())
        launch=port.command('open "'+remote[0]+'"',90);assert 'Open failed!' not in launch,launch
        raw=read_file(port,remote[1]);assert len(raw)==1936
        assert struct.unpack_from('<4I',raw)==(0x554C4142,12,1024,9)
        report['rows']=[]
        for i in range(48):
            op,_,x,y,result,duration,control=struct.unpack_from('<IIQQQII',raw,16+40*i)
            vx,vy=real(x),real(y)
            expected=(lambda:vx+vy,lambda:vx-vy,lambda:vx*vy,lambda:vx/vy)[op]()
            assert result==bits(expected),(names[op],hex(x),hex(y),hex(result),hex(bits(expected)))
            report['rows'].append(dict(operation=names[op],a=f'{x:016X}',b=f'{y:016X}',result=f'{result:016X}',net_cycles=(duration-control)/1024,raw_cycles=duration/1024,control_cycles=control/1024))
        (a.output_dir/'raw.bin').write_bytes(raw)
    finally:
        port.command('fsput cancel')
        current=fingerprint(port)
        for name in remote:
            actual=next((x for x in current['files'] if x.casefold()==name.casefold()),None)
            if actual:assert 'Removed 1 entry.' in port.command('rm "'+actual+'"',30)
        assert fingerprint(port)==before
        assert {c:port.command(c,20) for c in state}==state
        report['preservation']='original files, program, registers, stack and pwd exact'
        report['health']={c:port.command(c,20) for c in ('df','crash show')}
        assert 'FIRMWARE CRC state=valid' in report['health']['df'] and 'actual=0x'+a.expected_build.upper() in report['health']['df']
        assert 'CRASH none' in report['health']['crash show']
        (a.output_dir/'result.json').write_text(json.dumps(report,indent=2)+'\n')
print('48 numerical EABI cases, DWT timing and data preservation PASS')
