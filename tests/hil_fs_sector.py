#!/usr/bin/env python3
"""Classic sector RAM benchmarks through a temporary ordinary APP.

Calls the actual resident runtime memcpy/memcmp, plus SRAM controls and
word/DSP candidates. No MCU or System file replacements, no MSC session.
"""
import argparse
from contextlib import ExitStack
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import re
import statistics
import struct
import sys
import time

from hil_c6_system_bootstrap import read_file,write_file
from hil_multi_device_identity import parse_identity
from hil_packbits_firmware import fingerprint,stable_pixels
from hil_vm_scan import connect
from hil_rtc_alarm import warm_reset

REMOTE='/FSCHECK.APP'
PATTERNS=('equal','different_first','different_byte4','different_middle255','different_last511')
KERNELS=('resident_memcmp','scalar_memcmp','word_memcmp','dsp_memcmp','word_equal_full','dsp_equal_full',
         'resident_memcpy','scalar_memcpy','word_memcpy','unrolled_memcpy',
         'resident_cache_update','scalar_cache_update','word_cache_update','dsp_cache_update',
         'word_full_cache_update','dsp_full_cache_update')


def parse(frame,page):
    p=frame[:176]+frame[192:368]+frame[384:]
    (magic,version,actual_page,count,failures,code,libcmp,libcpy,demcr,control,sink,
     length,kernel_count,patterns,alignments,optimization)=struct.unpack_from('<4s15I',p)
    assert magic==b'FSC1' and version==1 and actual_page==page and not failures
    assert (length,kernel_count,patterns,alignments,optimization)==(512,16,5,4,2)
    assert 0x20000000<=code<0x20020000
    assert 0x08000000<=libcmp<0x08080000 and 0x08000000<=libcpy<0x08080000
    assert count==(64 if page<4 else 48)
    rows=[]
    for i in range(count):
        kernel,pattern,sa,ta,iterations,minimum,median,maximum=struct.unpack_from('<4B4I',p,64+i*20)
        assert kernel<16 and pattern==page//4 and sa==page%4 and ta<4
        assert iterations and minimum<=median<=maximum
        rows.append({'kernel':KERNELS[kernel],'pattern':PATTERNS[pattern],
            'source_alignment':sa,'target_alignment':ta,'iterations':iterations,
            'min_cycles':minimum/iterations,'median_cycles':median/iterations,'max_cycles':maximum/iterations})
    return {'page':page,'code_address':hex(code),'resident_memcmp_address':hex(libcmp),
        'resident_memcpy_address':hex(libcpy),'demcr_before':demcr,'dwt_control_before':control,
        'checksum':sink,'rows':rows,'memcmp_code_hex':p[1376:1440].hex(),'memcpy_code_hex':p[1440:1504].hex()}


def summarize(runs):
    summary=[]
    for pattern in PATTERNS:
        data={}
        for kernel in KERNELS:
            if 'memcpy' in kernel and pattern!='equal': continue
            aligned=[];all_alignments=[]
            for run in runs:
                for batch in run:
                    for row in batch['rows']:
                        if row['pattern']==pattern and row['kernel']==kernel:
                            all_alignments.append(row['median_cycles'])
                            if (row['source_alignment'],row['target_alignment'])==(0,0):aligned.append(row['median_cycles'])
            if not aligned: continue
            data[kernel]={'aligned_median_cycles':statistics.median(aligned),
                'all_alignments_median_cycles':statistics.median(all_alignments)}
        summary.append({'pattern':pattern,'kernels':data})
    return summary


def require_empty(state):
    numbers=re.findall(r'=\s*([+\-]?\d+\.\d+)\s+([+\-]?\d+)',state['reg']+state['stk'])
    assert len(numbers)==20 and all(float(n)==0 for n,e in numbers),'reset requires empty registers/stack'
    codes=re.findall(r'\b[0-9A-F]{2}\b',state['dump'].split('\r\n',1)[1])
    assert len(codes)==105 and set(codes)=={'00'} and '\r\n/\r\n' in state['pwd']


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',required=True)
    parser.add_argument('--app',type=Path,required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--runs',type=int,default=3)
    parser.add_argument('--wait-for-port',type=int,default=30)
    parser.add_argument('--reset-before',action='store_true')
    parser.add_argument('--reset-after',action='store_true')
    args=parser.parse_args();assert 1<=args.runs<=10
    out=args.output_dir.resolve();out.mkdir(parents=True,exist_ok=True)
    app=args.app.read_bytes();runs=[]
    installed=foreground=False
    with ExitStack() as contexts:
        port=contexts.enter_context(connect(args.port,args.wait_for_port))
        identity=parse_identity(port.command('identity',timeout=15))
        assert (identity.public,identity.usb,identity.profile)==('AEB505B6E0067623','2068336B4731','classic-v3-uc1609')
        before={c:port.command(c,timeout=15) for c in ('df','crash show','mpu status','reg','stk','dump','pwd')}
        assert 'CRASH none' in before['crash show'] and 'FIRMWARE CRC state=valid' in before['df']
        if args.reset_before or args.reset_after: require_empty(before)
        if args.reset_before:
            new,path,elapsed=warm_reset(port,port.path,identity.public)
            new.close();port=contexts.enter_context(connect(path,0))
            assert parse_identity(port.command('identity'))==identity
            for c in ('reg','stk','dump','pwd'): assert port.command(c,timeout=15)==before[c]
        files_before=fingerprint(port)
        assert REMOTE.casefold() not in {p.casefold() for p in files_before['files']}
        (out/'content-before.json').write_text(json.dumps(files_before,indent=2)+'\n')
        print('Classic pinned and original file fingerprints recorded:',identity.build,flush=True)
        try:
            write_file(port,REMOTE,app);installed=True
            read_file(port,REMOTE,app)
            port.attach();port.pump(.2)
            assert port.frames
            calculator=stable_pixels(port.frames[-1])
            for run in range(args.runs):
                start=len(port.frames);foreground=True;port.open(REMOTE)
                batches=[]
                for page in range(20):
                    deadline=time.monotonic()+40;frame=None
                    while time.monotonic()<deadline:
                        port.pump(.03)
                        frame=next((x for x in port.frames[start:] if x.startswith(b'FSC1') and
                            struct.unpack_from('<I',x,8)[0]==page),None)
                        if frame is not None: break
                    assert frame is not None,f'APP report absent: {port.text[-1400:]!r}'
                    batch=parse(frame,page);batches.append(batch)
                    (out/f'frame-{run}-{page}.bin').write_bytes(frame)
                    if page%4==3:print(f'Run {run+1}: {PATTERNS[page//4]}, all 16 alignments PASS',flush=True)
                    start=len(port.frames)
                    if page+1<20:port.key(9)
                port.close_app();foreground=False
                port.send(0x16);port.pump(.15)
                assert stable_pixels(port.frames[-1])==calculator,'calculator renderer/pixels changed'
                runs.append(batches)
                (out/'runs.json').write_text(json.dumps(runs,indent=2)+'\n')
        finally:
            try:
                if foreground and port.attached:port.close_app()
            finally:
                if port.attached:port.send(0x13);port.pump(.2)
                if installed:
                    if args.reset_after:
                        (out/'terminal-before-reset.txt').write_bytes(port.text)
                        for c in ('reg','stk','dump','pwd'):assert port.command(c,timeout=15)==before[c]
                        new,path,elapsed=warm_reset(port,port.path,identity.public)
                        new.close();port=contexts.enter_context(connect(path,0))
                        assert parse_identity(port.command('identity'))==identity
                    read_file(port,REMOTE,app)
                    removed=port.command(f'rm "{REMOTE}"',timeout=15)
                    assert 'Removed 1 entry.' in removed,removed
                assert parse_identity(port.command('identity'))==identity
                after={c:port.command(c,timeout=15) for c in ('df','crash show','mpu status','reg','stk','dump','pwd')}
                for c in ('reg','stk','dump','pwd'):assert before[c]==after[c],c
                assert 'CRASH none' in after['crash show'] and 'FIRMWARE CRC state=valid' in after['df']
                files_after=fingerprint(port);assert files_before==files_after
                (out/'content-after.json').write_text(json.dumps(files_after,indent=2)+'\n')
                (out/'terminal.txt').write_bytes(port.text)
                result={'status':'PASS' if len(runs)==args.runs else 'INCOMPLETE','identity':asdict(identity),
                    'before':before,'after':after,'app_bytes':len(app),'app_sha256':hashlib.sha256(app).hexdigest(),
                    'runs':runs,'summary':summarize(runs) if runs else [],
                    'reset_before':args.reset_before,'reset_after':args.reset_after,
                    'original_file_hashes_preserved':len(files_before['files']),
                    'scope':'DWT RAM sector operations in an ordinary Oz/LTO APP; actual resident helpers run from Flash, '
                            'matched scalar/word/DSP kernels run from SRAM; no NOR/USB/import throughput measurement',
                    'semantics':'memcmp candidates retain first-difference sign; full-scan equality kernels are not general memcmp replacements'}
                (out/'report.json').write_text(json.dumps(result,indent=2)+'\n')
                print('Classic firmware, calculator state and all original file hashes preserved; FSCHECK removed',flush=True)


if __name__=='__main__':main()
