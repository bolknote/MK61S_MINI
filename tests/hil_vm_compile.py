#!/usr/bin/env python3
"""Full sizing/EMIT A/B through ordinary APPs; byte-verify native images."""
import argparse
from dataclasses import asdict
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import re
import statistics
import struct
import time
import zlib

from hil_c6_system_bootstrap import read_file,write_file
from hil_multi_device_identity import parse_identity
from hil_packbits_firmware import fingerprint,stable_pixels
from hil_vm_scan import connect
from hil_rtc_alarm import warm_reset

REMOTE='/VMCOMP.APP'
VARIANTS=('scalar','line_word','line_dsp')


def payload(frame): return frame[:176]+frame[192:368]+frame[384:]


def await_frame(port,magic,start,predicate=lambda p:True):
    deadline=time.monotonic()+40
    while time.monotonic()<deadline:
        port.pump(.05)
        for frame in port.frames[start:]:
            p=payload(frame)
            if p.startswith(magic) and predicate(p): return frame,p
    raise TimeoutError(f'APP frame {magic!r} absent: {port.text[-1000:]!r}')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',required=True)
    parser.add_argument('--public-id',required=True)
    parser.add_argument('--manifest',type=Path,required=True)
    parser.add_argument('--language',choices=('basic','focal'),required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--runs',type=int,default=3)
    parser.add_argument('--reset-before',action='store_true',
                        help='release previous test caches, only if the calculator is empty')
    parser.add_argument('--reset-after-each',action='store_true',
                        help='release retained APP caches before deleting each temporary image')
    args=parser.parse_args()
    out=args.output_dir.resolve();out.mkdir(parents=True,exist_ok=True)
    manifest=json.loads(args.manifest.read_text())
    apps=[a for a in manifest['apps'] if a['language']==args.language]
    assert [a['variant'] for a in apps]==list(VARIANTS)
    results=[]
    installed=None
    foreground=False
    with ExitStack() as contexts:
        port=contexts.enter_context(connect(args.port,30))
        identity=parse_identity(port.command('identity'))
        assert identity.public==args.public_id.upper()
        before={c:port.command(c,timeout=15) for c in ('df','crash show','mpu status','reg','stk','dump','pwd')}
        if args.reset_before or args.reset_after_each:
            numbers=re.findall(r'=\s*([+\-]?\d+\.\d+)\s+([+\-]?\d+)',before['reg']+before['stk'])
            assert len(numbers)==20 and all(float(n)==0 for n,e in numbers)
            codes=re.findall(r'\b[0-9A-F]{2}\b',before['dump'].split('\r\n',1)[1])
            assert len(codes)==105 and set(codes)=={'00'} and '\r\n/\r\n' in before['pwd']
        if args.reset_before:
            new,path,elapsed=warm_reset(port,port.path,identity.public)
            new.close();port=contexts.enter_context(connect(path,0))
            assert parse_identity(port.command('identity'))==identity
            for c in ('reg','stk','dump','pwd'): assert port.command(c,timeout=15)==before[c]
        assert 'CRASH none' in before['crash show'] and 'FIRMWARE CRC state=valid' in before['df']
        free=int(re.search(r'Nodes: \d+ used, (\d+) free',before['df']).group(1))
        for a in apps:
            assert (Path(a['app']).stat().st_size+2047)//2048<=free, 'APP exceeds free C6 nodes'
        files_before=fingerprint(port)
        assert REMOTE.casefold() not in {p.casefold() for p in files_before['files']}
        try:
            for variant,app in enumerate(apps):
                data=Path(app['app']).read_bytes()
                write_file(port,REMOTE,data);installed=data
                read_file(port,REMOTE,data)
                port.attach();port.pump(.2)
                calculator=stable_pixels(port.frames[-1])
                samples=[]
                for run in range(args.runs):
                    start=len(port.frames);foreground=True;port.open(REMOTE)
                    frame,p=await_frame(port,b'VCC1',start)
                    _,version,actual_variant,count,failures,focal,address,sink,r0,r1=struct.unpack_from('<4s9I',p)
                    assert version==1 and actual_variant==variant and count==len(app['cases']) and not failures
                    assert focal==int(args.language=='focal') and 0x20000000<=address<0x20020000 and not r0 and not r1
                    metrics=[]
                    for dataset,case in enumerate(app['cases']):
                        size,crc,iterations,minimum,median,maximum=struct.unpack_from('<6I',p,40+dataset*24)
                        assert size==case['image_bytes'] and crc==case['image_crc']
                        assert iterations and minimum<=median<=maximum
                        metrics.append({'source':case['source'],'image_bytes':size,'image_crc':crc,
                            'iterations':iterations,'min_cycles':minimum/iterations,
                            'median_cycles':median/iterations,'max_cycles':maximum/iterations})
                    (out/f'{app["variant"]}-{run}-stats.bin').write_bytes(frame)
                    # Receive complete native bytecode, not just a CRC oracle.
                    for dataset,case in enumerate(app['cases']):
                        image=bytearray()
                        while len(image)<case['image_bytes']:
                            start=len(port.frames);port.key(9)
                            _,p=await_frame(port,b'VCI1',start,lambda p:
                                struct.unpack_from('<I',p,8)[0]==dataset and
                                struct.unpack_from('<I',p,16)[0]==len(image))
                            _,version,index,size,offset,count,crc,failures,r0,r1=struct.unpack_from('<4s9I',p)
                            assert version==1 and index==dataset and offset==len(image)
                            assert size==case['image_bytes'] and crc==case['image_crc'] and not failures and not r0 and not r1
                            assert 0<count<=1464
                            image.extend(p[40:40+count])
                        assert len(image)==case['image_bytes'] and zlib.crc32(image)&0xffffffff==case['image_crc']
                        assert hashlib.sha256(image).hexdigest()==case['image_sha256']
                        (out/f'{app["variant"]}-{run}-{dataset}.bvm').write_bytes(image)
                    port.close_app();foreground=False
                    port.send(0x16);port.pump(.15)
                    assert stable_pixels(port.frames[-1])==calculator
                    samples.append(metrics)
                    print(app['variant'],run+1,'full compiler DWT and native bytecode equality PASS',flush=True)
                results.append({'variant':app['variant'],'samples':samples})
                (out/'results.json').write_text(json.dumps(results,indent=2)+'\n')
                port.send(0x13);port.pump(.2)
                if args.reset_after_each:
                    for c in ('reg','stk','dump','pwd'): assert port.command(c,timeout=15)==before[c]
                    new,path,elapsed=warm_reset(port,port.path,identity.public)
                    new.close();port=contexts.enter_context(connect(path,0))
                    assert parse_identity(port.command('identity'))==identity
                read_file(port,REMOTE,data)
                removed=port.command(f'rm "{REMOTE}"',timeout=15)
                assert 'Removed 1 entry.' in removed,removed
                installed=None
        finally:
            try:
                if foreground and port.attached: port.close_app()
            finally:
                if port.attached: port.send(0x13);port.pump(.2)
                if installed is not None:
                    read_file(port,REMOTE,installed)
                    removed=port.command(f'rm "{REMOTE}"',timeout=15)
                    assert 'Removed 1 entry.' in removed,removed
                assert parse_identity(port.command('identity'))==identity
                after={c:port.command(c,timeout=15) for c in ('df','crash show','mpu status','reg','stk','dump','pwd')}
                for c in ('reg','stk','dump','pwd'): assert before[c]==after[c]
                assert 'CRASH none' in after['crash show'] and 'FIRMWARE CRC state=valid' in after['df']
                files_after=fingerprint(port)
                assert files_before==files_after
                (out/'terminal.txt').write_bytes(port.text)
                (out/'report.json').write_text(json.dumps({'status':'PASS' if len(results)==3 else 'INCOMPLETE',
                    'identity':asdict(identity),'language':args.language,'results':results,
                    'before':before,'after':after,'file_hashes_preserved':len(files_before['files']),
                    'scope':manifest['scope'],'manifest':manifest},indent=2)+'\n')
                print('All original C6 files, firmware and calculator state restored',flush=True)


if __name__=='__main__': main()
