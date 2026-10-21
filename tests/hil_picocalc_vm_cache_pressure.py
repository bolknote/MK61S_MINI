#!/usr/bin/env python3
"""Exercise packed PicoCalc RAM images on one UID, preserving calculator data."""
import argparse
from contextlib import ExitStack
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import zlib
from hil_c5_stack import read_file,write_file
from hil_picocalc_software import connect,restore
from hil_picocalc_turochamp import healthy
from hil_picocalc_vm_cache import counters

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',required=True);parser.add_argument('--uid',required=True)
    parser.add_argument('--firmware-directory',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--programs',type=int,default=16,choices=range(16,49))
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    build=json.loads((args.firmware_directory/'manifest.json').read_text())
    directory='/MK61S-PACK-'+datetime.now().strftime('%Y%m%d-%H%M%S')
    paths=[directory+f'/part{i:02d}.bas' for i in range(args.programs)]
    report=dict(passed=False,uid=args.uid,build=build['build_id'].upper(),uf2_sha256=build['uf2_sha256'],
        driver_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    before=None;created=False
    with ExitStack() as stack:
        p=connect(args.port,args.uid);stack.callback(p.__exit__,None,None,None)
        try:
            initial=p.status();healthy(initial,report['build'])
            for marker in ('SERVICE=CLOSED','DIRTY=0','M61_ACTIVE=0','USB_SCREEN=OFF'):assert marker in initial,initial
            before={c:p.command(c) for c in ('reg','stk','hout','pwd')}
            (args.output/'snapshot.json').write_text(json.dumps(before,indent=2)+'\n')
            assert directory[1:] not in p.command('ls /')
            assert 'ERROR' not in p.command('mkdir '+directory);created=True
            # All writes precede execution: later sources must not invalidate
            # earlier images. The long owned PRINT resource is skipped at run.
            for i,path in enumerate(paths):
                text='PICO PACKED RESOURCE '*(83+(i%16)*5)
                data=(f'10 GOTO 30\n20 PRINT "{text}"\n30 .R0={101+i}\n40 END\n').encode()
                write_file(p,path,data);assert read_file(p,path)==data
                print(f"Uploaded and checked {i+1}/{len(paths)} cache-pressure sources",flush=True)
            start=counters(p.status())
            for path in paths:
                assert 'VM_RESULT=OK' in p.command('open "'+path+'"',timeout=30)
            cold=p.status();c=counters(cold)
            assert c['COMPILES']==start['COMPILES']+len(paths),cold
            assert c['BYTES']==32768 and c['USED']<=32768 and c['PACKS']>start['PACKS'],cold
            for path in reversed(paths):
                assert 'VM_RESULT=OK' in p.command('open "'+path+'"',timeout=30)
            warm=p.status();w=counters(warm)
            assert w['COMPILES']==c['COMPILES'] and w['THAWS']>c['THAWS'],warm
            if args.programs>32:
                ext=lambda text:re.search(r'(?m)^EXT_CACHE=[^\r\n]*',text)[0]
                hits=lambda text:int(re.search(r'\bVM_HIT=(\d+)',ext(text))[1])
                assert hits(warm)>hits(cold),(cold,warm)
            assert re.search(r'(?m)^R0 =  1\.0100000  02\r?$',p.command('reg'))
            report.update(passed=True,programs=len(paths),cold=cold,warm=warm)
        finally:
            if before:
                p.calculator()
                if created:
                    assert 'ERROR' not in p.command('rm -r '+directory,timeout=30)
                    listing=p.command('ls /System/VMCache/Pico')
                    for path in paths:
                        for rf in (0,1):
                            name=f'/System/VMCache/Pico/{zlib.crc32(path.encode()):08X}-1-{rf}.cache'
                            if name.rsplit('/',1)[1] not in listing:continue
                            data=read_file(p,name);n=int.from_bytes(data[4:6],'little') if len(data)>=12 else 0
                            if data[:4]==b'PCC1' and data[12:12+n]==path.encode():
                                assert 'ERROR' not in p.command('rm "'+name+'"')
                pwd=re.search(r'(?m)^(/[^\r\n]*)',before['pwd'])[1]
                assert 'ERROR' not in p.command('cd "'+pwd+'"');restore(p,before)
                report.update(calculator_state_restored=True,temporary_files_removed=created,final=p.status())
                healthy(report['final'],report['build'])
            (args.output/'terminal.bin').write_bytes(p.text)
            (args.output/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    assert report['passed'] and report['calculator_state_restored']
    print(json.dumps(dict(passed=True,build=report['build'],programs=report['programs'],
        cold=counters(report['cold']),warm=counters(report['warm'])),indent=2),flush=True)

if __name__=='__main__':main()
