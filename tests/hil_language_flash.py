#!/usr/bin/env python3
"""Identity-pinned Classic HIL for Flash-backed BASIC/FOCAL programs.

Writes only /FLHIL fixtures, generated /System/VMCache/Pages and RA/RB.
A matching firmware/System bundle must already be installed.
"""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import struct
import re
import time
from hil_language_sources import SourcePort, read_file
from hil_c6_system_bootstrap import write_file
from hil_c5_stack import read_file as read_bytes
from hil_language_vm import health
from hil_multi_device_identity import parse_identity
from hil_portable_system_apps import registers

ROOT='/FLHIL'
CACHE='/System/VMCache/Pages'
def fixture(language,reverse=False,wide=False):
    basic=language=='basic'
    lines=['1 GOTO 30000'] if basic else ['1.0 G 9.0']
    for i in range(550 if wide else 600):
        statement=('A=A+A+A+A+A+A+A' if basic else 'S A=A+A+A+A+A+A+A') if wide else ('A=1' if basic else 'S A=1')
        body=';'.join([statement]*5) if wide else statement
        lines.append(f'{i+2} {body}' if basic else f'{2+i//100}.{i%100} {body}')
    lines+=([
        '30000 B=2;C=3;D=4;E=5;S=B+C+D+E;FOR I=1 TO 3;GOSUB 31000;NEXT I',
        '30010 IF S<>20 GOTO 32767', '30020 .RA=S;END', '31000 S=S+I;RETURN'] if basic else [
        '9.0 S B=2;S C=3;S D=4;S E=5;S S=B+C+D+E;F I=1,1,3;D 10,I',
        '9.1 S .RB=S;E', '10.0 S S=S+ARG(1);R'])
    if reverse:lines.reverse()
    return ('\n'.join(lines)+'\n').encode(),len(lines)

def manifests(port):
    result=[]
    listing=port.command(f'ls "{CACHE}"')
    for line in listing.splitlines():
        if not line.startswith('d\t'):continue
        name=line.split('\t')[-1].strip('\r/')
        if len(name)!=4 or any(c not in '0123456789ABCDEF' for c in name):continue
        directory=f'{CACHE}/{name}'
        if "Manifest.bin" not in port.command(f'ls "{directory}"'):
            continue
        path=f'{directory}/Manifest.bin'
        data=read_bytes(port,path)
        if len(data)==64 and data[:4]==b'LFP1':
            header=data[16:48]
            result.append(dict(path=path,language=header[5],lines=struct.unpack_from('<H',header,18)[0],
                bytecode_bytes=struct.unpack_from('<I',header,8)[0],bank=data[4]))
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--port',required=True);p.add_argument('--public-id',required=True)
    p.add_argument('--build-id',required=True);p.add_argument('--output-dir',type=Path,required=True)
    p.add_argument('--wide',action='store_true',help='exercise the 64-KiB bytecode address boundary')
    p.add_argument('--minimum-stack-remaining',type=int,default=0)
    p.add_argument('--language',choices=('basic','focal','all'),default='all')
    args=p.parse_args();args.output_dir.mkdir(parents=True,exist_ok=True)
    report=dict(status='RUNNING',wide=args.wide,cases=[])
    def save(): (args.output_dir/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    with SourcePort(args.port,keyboard_layout=1) as port:
        identity=parse_identity(port.command('identity'))
        assert identity.public==args.public_id.upper() and identity.build==args.build_id.upper() and identity.profile=='classic-v3-uc1609',identity
        report['identity']=asdict(identity);report['before']=health(port)
        try:
            port.attach();port.command('mkdir '+ROOT,timeout=20)
            for reverse in ((False,) if args.wide else (False,True)):
                for language,extension,register in [('basic','tbi','RA'),('focal','foc','RB')]:
                    if args.language!='all' and args.language!=language:continue
                    if args.wide:
                        other='foc' if language=='basic' else 'tbi'
                        port.command(f'rm \"{ROOT}/case.{other}\"',timeout=20)
                    if port.attached:
                        port.send(0x13);port.attached=False;port.pump(.2)
                    text,count=fixture(language,reverse,args.wide);path=f'{ROOT}/case.{extension}'
                    write_file(port,path,text);read_file(port,path,text)
                    loader=f'open "{path}"\nret\n'.encode();write_file(port,ROOT+'/run.m61',loader)
                    port.attach()
                    times=[]
                    for repeat in range(2):
                        port.command(register+'= 0');start=time.monotonic()
                        port.run_source(ROOT+'/run.m61',language=='focal',timeout=300 if args.wide else 120)
                        times.append(time.monotonic()-start)
                        values,raw=registers(port);assert values[register]==20,raw
                    metadata=[m for m in manifests(port) if m['language']==(1 if language=='basic' else 2) and m['lines']==count]
                    assert metadata and all(m['bytecode_bytes']>(65536 if args.wide else 6144) for m in metadata),metadata
                    case=dict(language=language,reverse=reverse,lines=count,source_bytes=len(text),run_seconds=times,manifests=metadata)
                    report['cases'].append(case);save();print(language,'reverse' if reverse else 'sorted',case,flush=True)
            report['after']=health(port)
            remaining=int(re.search(r'observed_remaining=(\d+)',report['after']['mpu status'])[1])
            assert remaining>=args.minimum_stack_remaining,(remaining,args.minimum_stack_remaining)
            report['minimum_stack_remaining']=remaining;report['status']='PASS'
        except BaseException as error:
            report['status']='FAIL';report['error']=repr(error)
            try:report['after_failure']=health(port)
            except BaseException as diagnostic:report['diagnostic_error']=repr(diagnostic)
            raise
        finally:
            if port.attached:
                try:port.send(0x13);port.attached=False;port.pump(.2)
                except (OSError,TimeoutError):pass
            (args.output_dir/'terminal.txt').write_bytes(port.text);save()
    print('Physical Flash language HIL PASS',flush=True)
if __name__=='__main__':main()
