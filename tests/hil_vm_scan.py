#!/usr/bin/env python3
"""Measure compiler scan candidates in an ordinary APP on a pinned F411.

One reserved temporary APP is installed and removed; no firmware/System
updates. Optional reset-after releases retained test caches, only with a
verified empty calculator. USB packets and full pixel frames are CRC-verified.
"""
import argparse
from dataclasses import asdict
from contextlib import ExitStack
import errno
import fcntl
import hashlib
import json
from pathlib import Path
import re
import statistics
import struct
import termios
import time

from hil_c6_system_bootstrap import read_file, write_file
from hil_multi_device_identity import parse_identity
from hil_packbits_firmware import fingerprint, stable_pixels
from hil_portable_apps import ScreenPort
from hil_rtc_alarm import warm_reset
from hil_usb_disk_transaction import listing_entries

REMOTE='/VMSCAN.APP'
FAMILIES=('line_end','space_prefix','keyword_scan','resource_equality')
VARIANTS=('scalar','word','dsp')


class ExclusiveScreenPort(ScreenPort):
    def __init__(self,path):
        super().__init__(path)
        try: fcntl.ioctl(self.fd,termios.TIOCEXCL)
        except BaseException:
            super().close()
            raise
    def close(self):
        if self.fd>=0:
            try: fcntl.ioctl(self.fd,termios.TIOCNXCL)
            finally: super().close()


def connect(path,timeout):
    deadline=time.monotonic()+timeout
    announced=False
    while True:
        try: return ExclusiveScreenPort(path)
        except OSError as error:
            if error.errno not in (errno.EBUSY,errno.ENOENT) or time.monotonic()>=deadline: raise
            if not announced:
                print('Waiting for the serial port to be released by the other hardware test',flush=True)
                announced=True
            time.sleep(1)


def parse_report(frame, dataset, fixture):
    payload=frame[:176]+frame[192:368]+frame[384:]
    magic,version,source,count,failures,address,checksum,blob_bytes,records,reserved=struct.unpack_from('<4s9I',payload)
    assert magic==b'VSC1' and version==1 and source==dataset and not failures
    assert blob_bytes==fixture['blob_bytes'] and records==fixture['records'] and not reserved
    assert 0x20000000<=address<0x20020000
    expected=sum(bool(g['calls']) for g in fixture['cases'][dataset]['groups'])*12
    assert count==expected and count<=48
    rows=[]
    for i in range(count):
        kernel,alignment,reserved_a,reserved_b,iterations,minimum,median,maximum=struct.unpack_from('<4B4I',payload,40+i*20)
        assert kernel<12 and alignment<4 and not reserved_a and not reserved_b
        assert iterations and minimum<=median<=maximum
        family=kernel//3
        calls=fixture['cases'][dataset]['groups'][family]['calls']
        rows.append({'family':FAMILIES[family],'variant':VARIANTS[kernel%3],
            'alignment':alignment,'calls_per_replay':calls,'iterations':iterations,
            'min_cycles_per_replay':minimum/iterations,
            'median_cycles_per_replay':median/iterations,
            'max_cycles_per_replay':maximum/iterations,
            'median_cycles_per_call':median/iterations/calls})
    return {'case':dataset,'code_address':hex(address),'checksum':checksum,'rows':rows}


def summary(runs,fixture):
    results=[]
    for dataset,case in enumerate(fixture['cases']):
        for family,name in enumerate(FAMILIES):
            if not case['groups'][family]['calls']: continue
            by_alignment=[]
            for alignment in range(4):
                cycles={}
                for variant in VARIANTS:
                    values=[row['median_cycles_per_replay'] for run in runs for batch in run
                        if batch['case']==dataset for row in batch['rows']
                        if (row['family'],row['alignment'],row['variant'])==(name,alignment,variant)]
                    cycles[variant]=statistics.median(values)
                by_alignment.append({'alignment':alignment,'cycles_per_replay':cycles,
                    'word_time_change_percent':100*(cycles['word']/cycles['scalar']-1),
                    'dsp_time_change_percent':100*(cycles['dsp']/cycles['scalar']-1)})
            results.append({'source':case['source'],'family':name,
                'calls_per_replay':case['groups'][family]['calls'],
                'by_alignment':by_alignment})
    return results


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',required=True)
    parser.add_argument('--public-id',required=True)
    parser.add_argument('--app',type=Path,required=True)
    parser.add_argument('--fixture',type=Path,required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--runs',type=int,default=3)
    parser.add_argument('--wait-for-port',type=int,default=0,
                        help='wait this many seconds for another hardware test to release the port')
    parser.add_argument('--reset-after',action='store_true',
                        help='release retained APP/workspace caches by resetting an empty calculator before cleanup')
    args=parser.parse_args()
    assert 1<=args.runs<=10
    out=args.output_dir.resolve();out.mkdir(parents=True,exist_ok=True)
    fixture=json.loads(args.fixture.read_text())
    app=args.app.read_bytes()
    installed=foreground=False
    runs=[]
    with ExitStack() as contexts:
        port=contexts.enter_context(connect(args.port,args.wait_for_port))
        identity=parse_identity(port.command('identity'))
        assert identity.public==args.public_id.upper() and identity.profile=='classic-v3-uc1609'
        before={c:port.command(c,timeout=15) for c in ('df','crash show','mpu status','reg','stk','dump','pwd')}
        assert 'CRASH none' in before['crash show'] and 'FIRMWARE CRC state=valid' in before['df']
        if args.reset_after:
            numbers=re.findall(r'=\s*([+\-]?\d+\.\d+)\s+([+\-]?\d+)',before['reg']+before['stk'])
            assert len(numbers)==20 and all(float(n)==0 for n,e in numbers), 'reset-after requires an empty calculator'
            codes=re.findall(r'\b[0-9A-F]{2}\b',before['dump'].split('\r\n',1)[1])
            assert len(codes)==105 and set(codes)=={'00'}
            assert '\r\n/\r\n' in before['pwd'], 'reset-after requires root cwd'
        free=int(re.search(r'Nodes: \d+ used, (\d+) free',before['df']).group(1))
        assert (len(app)+2047)//2048<=free, 'APP needs more free C6 nodes; no files will be removed'
        content_before=fingerprint(port)
        print('Pinned device acquired; firmware and all C6 fingerprints recorded',flush=True)
        assert REMOTE.casefold() not in {p.casefold() for p in content_before['files']}
        (out/'content-before.json').write_text(json.dumps(content_before,indent=2)+'\n')
        try:
            write_file(port,REMOTE,app);installed=True
            read_file(port,REMOTE,app)
            port.attach();port.pump(.2)
            assert port.frames
            calculator=stable_pixels(port.frames[-1])
            for run in range(args.runs):
                start=len(port.frames);foreground=True;port.open(REMOTE)
                batches=[]
                for dataset in range(len(fixture['cases'])):
                    deadline=time.monotonic()+40
                    frame=None
                    while time.monotonic()<deadline:
                        port.pump(.05)
                        frame=next((x for x in port.frames[start:] if x.startswith(b'VSC1') and
                            struct.unpack_from('<I',x,8)[0]==dataset),None)
                        if frame is not None: break
                    assert frame is not None, f'APP report absent: {port.text[-1200:]!r}'
                    batches.append(parse_report(frame,dataset,fixture))
                    (out/f'frame-{run}-{dataset}.bin').write_bytes(frame)
                    print(f'Run {run+1}, {fixture["cases"][dataset]["source"]}: matched DWT replay PASS',flush=True)
                    start=len(port.frames)
                    if dataset+1<len(fixture['cases']): port.key(9) # Classic digit 1
                port.close_app();foreground=False
                port.send(0x16);port.pump(.15)
                assert stable_pixels(port.frames[-1])==calculator, 'calculator renderer/pixels changed'
                runs.append(batches)
                (out/'runs.json').write_text(json.dumps(runs,indent=2)+'\n')
        finally:
            try:
                if foreground and port.attached: port.close_app()
            finally:
                if port.attached: port.send(0x13);port.pump(.2)
                if installed:
                    if args.reset_after:
                        (out/'terminal-before-reset.txt').write_bytes(port.text)
                        new,path,elapsed=warm_reset(port,port.path,identity.public)
                        new.close()
                        port=contexts.enter_context(connect(path,0))
                    read_file(port,REMOTE,app)
                    removed=port.command(f'rm "{REMOTE}"',timeout=15)
                    assert 'Removed 1 entry.' in removed,removed
                after_identity=parse_identity(port.command('identity'))
                assert after_identity==identity
                after={c:port.command(c,timeout=15) for c in ('df','crash show','mpu status','reg','stk','dump','pwd')}
                assert 'CRASH none' in after['crash show'] and 'FIRMWARE CRC state=valid' in after['df']
                for c in ('reg','stk','dump','pwd'): assert before[c]==after[c],c
                content_after=fingerprint(port)
                assert content_before==content_after,'C6 contents changed'
                (out/'content-after.json').write_text(json.dumps(content_after,indent=2)+'\n')
                (out/'terminal.txt').write_bytes(port.text)
                report={'status':'PASS' if len(runs)==args.runs else 'INCOMPLETE',
                    'identity':asdict(identity),'app_bytes':len(app),
                    'warm_reset_after':args.reset_after,
                    'app_sha256':hashlib.sha256(app).hexdigest(),'fixture':fixture,
                    'runs':runs,'before':before,'after':after,
                    'restored':['firmware identity','DWT controls','calculator pixels/renderer',
                                'calculator registers/stack/program/cwd','all C6 file hashes'],
                    'scope':'physical DWT, actual compiler calls with branch-shape coalescing; '
                            'all candidates in one ordinary SRAM APP; not end-to-end VM time'}
                if runs: report['summary']=summary(runs,fixture)
                (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
                print(f'Restored all {len(content_before["files"])} C6 files and original calculator state',flush=True)


if __name__=='__main__': main()
