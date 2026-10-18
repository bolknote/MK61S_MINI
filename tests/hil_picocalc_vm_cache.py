#!/usr/bin/env python3
"""Qualify the PicoCalc VM cache on one exact UID/build, restoring calculator data.

Uses a new SD directory. Only its sources and positively identified derived
cache entries are removed. One normal MCU reset checks persistence on SD.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
import time
from zoneinfo import ZoneInfo
import zlib

from hil_c5_stack import read_file, write_file
from hil_picocalc_software import connect, restore
from hil_picocalc_turochamp import healthy

def counters(status):
    row=re.search(r'(?m)^VM_CACHE=([^\r\n]*)',status)
    assert row,status
    return {key:int(value) for key,value in re.findall(r'([A-Z_]+)=(\d+)',row[1])}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',required=True)
    parser.add_argument('--uid',required=True)
    parser.add_argument('--firmware-directory',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    assert re.fullmatch(r'[0-9A-F]{16}',args.uid)
    args.output.mkdir(parents=True,exist_ok=False)
    build=json.loads((args.firmware_directory/'manifest.json').read_text())
    directory='/MK61S-CACHE-'+datetime.now().strftime('%Y%m%d-%H%M%S')
    path=directory+'/part.bas'
    sources={path:b'10 .R0=23\n20 END\n'}
    report=dict(passed=False,recorded_at_utc=datetime.now(timezone.utc).isoformat(),
        uid=args.uid,uf2_sha256=build['uf2_sha256'],build=build['build_id'].upper(),cases=[])
    p=None;before=None;created=False;transcripts=[]
    def check():
        status=p.status();healthy(status,report['build']);return status
    def run():
        output=p.command('open "'+path+'"',timeout=30)
        assert 'VM_RESULT=OK' in output,output
        return check()
    try:
        p=connect(args.port,args.uid)
        initial=check()
        for token in ('SERVICE=CLOSED','DIRTY=0','M61_ACTIVE=0','RUN=0 BUSY=0','USB_SCREEN=OFF'):
            assert token in initial,initial
        report['initial']=initial
        before={cmd:p.command(cmd) for cmd in ('reg','stk','hout','pwd')}
        (args.output/'snapshot.json').write_text(json.dumps(before,indent=2)+'\n')
        assert directory[1:] not in p.command('ls /')
        assert 'ERROR' not in p.command('mkdir '+directory);created=True
        for name,data in sources.items():
            write_file(p,name,data);assert read_file(p,name)==data
        first=counters(check());cold=run();after_cold=counters(cold)
        assert after_cold['COMPILES']==first['COMPILES']+1
        assert after_cold['STORES']==first['STORES']+1
        warm=run();after_warm=counters(warm)
        assert after_warm['COMPILES']==after_cold['COMPILES']
        assert after_warm['RAM_HIT']==after_cold['RAM_HIT']+1
        assert 'X_RAW=' in warm
        report['cases'].append('Second execution uses the immutable RAM image without compilation')
        report.update(cold=cold,warm=warm)
        p.write_line('rst now')
        try:p.pump(.3)
        except OSError:pass
        transcripts.append(bytes(p.text));p.__exit__(None,None,None);p=None
        p=connect(args.port,args.uid)
        restarted=check();assert counters(restarted)['BYTES']==0,restarted
        saved=run();after_saved=counters(saved)
        assert after_saved['COMPILES']==0 and after_saved['SD_HIT']==1 and after_saved['STORES']==0,saved
        report['cases'].append('After a normal MCU reset the verified SD image runs with zero compiles and zero cache writes')
        report.update(restarted=restarted,persistent=saved)
        write_file(p,path,b'10 .R0=24\n20 END\n')
        edited=run();after_edit=counters(edited)
        assert after_edit['COMPILES']==1 and after_edit['REJECTED']>=1,edited
        register=p.command('reg')
        assert re.search(r'(?m)^R0 =  2\.4000000  01\r?$',register),register
        report['cases'].append('A same-length source edit invalidates RAM and SD bytecode and executes the new result')
        report['edited']=edited
        report['passed']=True
    finally:
        if before and p is not None:
            p.calculator()
            if created:
                assert 'ERROR' not in p.command('rm -r '+directory,timeout=30)
                for name in sources:
                    for rf in (0,1):
                        derived=f'/System/VMCache/Pico/{zlib.crc32(name.encode()):08X}-1-{rf}.cache'
                        listing=p.command('ls /System/VMCache/Pico')
                        if derived.rsplit('/',1)[1] not in listing:continue
                        data=read_file(p,derived)
                        n=int.from_bytes(data[4:6],'little') if len(data)>=12 else 0
                        if data[:4]==b'PCC1' and data[12:12+n]==name.encode():
                            assert 'ERROR' not in p.command('rm "'+derived+'"')
                report['temporary_sources_and_cache_removed']=True
            pwd=re.search(r'(?m)^(/[^\r\n]*)',before['pwd'])[1]
            assert 'ERROR' not in p.command('cd "'+pwd+'"')
            restore(p,before)
            now=datetime.now(ZoneInfo('Europe/Moscow'))
            assert 'ERROR' not in p.command('date '+now.strftime('%Y-%m-%d %H:%M:%S'))
            p.command('uscreen off')
            report.update(calculator_state_restored=True,final=check())
        if p is not None:
            transcripts.append(bytes(p.text));p.__exit__(None,None,None)
        (args.output/'terminal.bin').write_bytes(b''.join(transcripts))
        (args.output/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    assert report['passed'] and report['calculator_state_restored']
    print(json.dumps(dict(passed=True,build=report['build'],cases=report['cases']),ensure_ascii=False,indent=2))

if __name__=='__main__':main()
