#!/usr/bin/env python3
"""DWT A/B/A at actual Flash/ROM addresses, preserving calculator and files."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tests'))
from hil_c5_stack import read_file,write_file
from hil_multi_device_identity import parse_identity
from hil_packbits_firmware import fingerprint
from hil_portable_apps import ScreenPort
from hil_rtc_alarm import canonical_state_reply

REMOTE=('/ROMBEN.APP','/ROMBEN.bin','/ROMBASE.bin')

def decode(raw):
    h=struct.unpack_from('<12I',raw)
    magic,version,count,samples,rounds,resident,rom,crc,checks,base,size,acr=h
    assert (magic,crc)==(0x31424D52,0x9F8F7DED) and version in (1,2,3,4)
    if version==1: assert rom==0x1FFF3BD5
    else: assert 0x20000000 <= rom < 0x20020000 and rom&1
    assert len(raw)==48+count*20
    rows=[]
    for i in range(count):
        n,align,value,control,before,after,repeat=struct.unpack_from('<HBB4I',raw,48+20*i)
        b,c,r=[(x-control)/samples for x in (before,after,repeat)]
        rows.append({'bytes':n,'alignment':align,'value':value,
            'raw_batch_cycles':{'control':control,'before':before,'rom':after,'repeat':repeat},
            'cycles_per_call':{'before':b,'rom':c,'repeat':r},
            'rom_over_resident':c/((b+r)/2),
            'control_drift_cycles':abs(b-r)})
    return {'resident_pointer':f'{resident:08X}','rom_pointer':f'{rom:08X}',
            'candidate_kind':{1:'factory ROM with ISO C adapter',2:'local bulk, ROM-style',3:'local bulk, overlapping edge words',4:'local bulk, edge words and unpredicated loop'}[version],
            'candidate_pointer':f'{rom:08X}',
            'baseline_kind':'bulk helper only' if resident==0x08008935 else 'public memset',
            'rom_crc32':f'{crc:08X}','snapshot_address':f'{base:08X}','snapshot_size':size,
            'flash_acr':f'{acr:08X}','samples_per_round':samples,'rounds':rounds,
            'correctness_checks':checks,'rows':rows}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--port',required=True);p.add_argument('--public-id',required=True)
    p.add_argument('--app',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    report={'status':'RUNNING','method':'DWT CYCCNT; unchanged resident memset in actual internal Flash versus actual factory ROM through an ISO-C argument adapter; SRAM harness; 9-round medians of 128 calls minus common empty-call overhead; interrupts enabled; A/B/A per size/alignment'}
    report['test_app_sha256']=hashlib.sha256(a.app.read_bytes()).hexdigest()
    def save(): (a.output/'benchmark.json').write_text(json.dumps(report,indent=2)+'\n')
    with ScreenPort(a.port) as port:
        identity=parse_identity(port.command('identity',10))
        assert identity.public==a.public_id.upper() and identity.build=='3AB3DD45',identity
        report['identity']=identity.__dict__
        original=fingerprint(port)
        state={c:canonical_state_reply(port.command(c,15)) for c in ('reg','stk','dump','pwd')}
        assert not any(p.casefold() in {x.casefold() for x in REMOTE} for p in original['files'])
        report['files_before']=original;save()
        try:
            write_file(port,REMOTE[0],a.app.read_bytes())
            report['launch']=port.command('open "'+REMOTE[0]+'"',timeout=90)
            raw=read_file(port,REMOTE[1]);code=read_file(port,REMOTE[2])
            (a.output/'benchmark.bin').write_bytes(raw);(a.output/'resident-code.bin').write_bytes(code)
            report['measurements']=decode(raw)
            if report['measurements']['candidate_kind']!='factory ROM with ISO C adapter':
                report['method']='DWT CYCCNT; actual resident bulk helper in internal Flash versus local assembly candidate in SRAM; 9-round medians of 128 calls minus common empty-call overhead; interrupts enabled; A/B/A per size/alignment. Legacy row keys rom and rom_over_resident refer to the local candidate.'
            report['code_sha256']=hashlib.sha256(code).hexdigest()
            report['status']='PASS';save()
            print('DWT data captured; resident',report['measurements']['resident_pointer'],flush=True)
        except BaseException as error:
            report['status']='FAIL';report['error']=str(error);raise
        finally:
            port.command('fsput cancel')
            current=fingerprint(port)
            for path in REMOTE:
                actual=next((p for p in current['files'] if p.casefold()==path.casefold()),None)
                if actual: assert 'Removed 1 entry.' in port.command('rm "'+actual+'"',30)
            report['files_unchanged']=fingerprint(port)==original
            report['state_unchanged']={c:canonical_state_reply(port.command(c,15)) for c in state}==state
            report['identity_unchanged']=parse_identity(port.command('identity'))==identity
            report['health_after']={c:port.command(c,15) for c in ('df','crash show','mpu status')}
            (a.output/'terminal.txt').write_bytes(port.text);save()
            assert report['files_unchanged'] and report['state_unchanged'] and report['identity_unchanged']
            assert 'FIRMWARE CRC state=valid' in report['health_after']['df']
            assert 'CRASH none' in report['health_after']['crash show']
            assert 'enabled=1 layout=ok' in report['health_after']['mpu status']
    print('DWT benchmark and preservation PASS',flush=True)

if __name__=='__main__': main()
