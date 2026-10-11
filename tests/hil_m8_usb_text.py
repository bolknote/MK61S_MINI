#!/usr/bin/env python3
"""Measure ordinary UTF-8 file I/O on a pinned MK61 board; own subtree only."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import random
import statistics
import time

from hil_rtc_alarm import Port
from hil_multi_device_identity import Target, parse_identity
from hil_c6_system_bootstrap import write_file, read_file
from hil_usb_disk_transaction import (decode_m8, encode_m8, enter_usb_disk,
    ensure_mounted, find_cdc_location, listing_entries, reconnect, run_text,
    usb_tree, wait_for_msc_disk, whole_disks)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', required=True)
    parser.add_argument('--public-id', required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    p = Port(args.port)
    identity = parse_identity(p.command('identity', 8))
    assert identity.public == args.public_id.upper(), identity
    target = Target(args.port, identity)
    root = '/M8USB-' + identity.short
    original = listing_entries(p.command('ls /', 15))
    assert all(row.split('\t')[-1].rstrip('/').casefold() != root[1:].casefold() for row in original)
    rng = random.Random(0x4D38)
    data = {
        'ascii': bytes(rng.randrange(32,127) for _ in range(3584)),
        'russian': bytes(0xC0 + rng.randrange(64) for _ in range(3584)),
        'alternating': bytes((0xC0+rng.randrange(64)) if i%2 else rng.randrange(32,127) for i in range(3584)),
        'program': (encode_m8('10 PRINT "Привет → мир"\r\n20 GOTO 10\r\n')*120)[:3584],
    }
    report = {'build': identity.build, 'profile': identity.profile, 'public': identity.public,
              'samples': {}, 'status': 'RUNNING'}
    disk = ''
    try:
        assert 'mkdir:' not in p.command('mkdir '+root, 30)
        for index,(name,payload) in enumerate(data.items()):
            write_file(p,f'{root}/BASE{index}.tbi',payload)
            read_file(p,f'{root}/BASE{index}.tbi',payload)
        location = find_cdc_location(usb_tree(),identity)
        baseline = whole_disks();p.close();enter_usb_disk(target)
        disk,info = wait_for_msc_disk(location,identity.usb,baseline,60)
        folder = ensure_mounted(disk,info)/root[1:]
        for index,(name,payload) in enumerate(data.items()):
            expected = decode_m8(payload).encode('utf-8')
            times = []
            for repeat in range(5):
                fd = os.open(folder/f'BASE{index}.tbi',os.O_RDONLY)
                try:
                    fcntl.fcntl(fd,48,1) # Darwin F_NOCACHE, SDK sys/fcntl.h.
                    start = time.monotonic_ns();chunks=[]
                    while True:
                        block=os.read(fd,512)
                        if not block:break
                        chunks.append(block)
                    times.append((time.monotonic_ns()-start)/1e6)
                    assert b''.join(chunks)==expected
                finally:os.close(fd)
            start=time.monotonic_ns()
            with (folder/f'COPY{index}.tbi').open('xb') as output:
                output.write(expected);output.flush();os.fsync(output.fileno())
            report['samples'][name]={'m8_bytes':len(payload),'utf8_bytes':len(expected),
                'read_ms':times,'read_median_ms':statistics.median(times),
                'write_fsync_ms':(time.monotonic_ns()-start)/1e6}
            print(name,report['samples'][name],flush=True)
        start=time.monotonic();run_text(['diskutil','eject',disk],timeout=60);disk='';reconnect(target,60)
        report['eject_ms']=(time.monotonic()-start)*1000
        p=Port(target.path)
        for index,payload in enumerate(data.values()):
            read_file(p,f'{root}/COPY{index}.tbi',payload)
            read_file(p,f'{root}/BASE{index}.tbi',payload)
        response=p.command('rm -r '+root,60);assert 'rm:' not in response,response
        assert listing_entries(p.command('ls /',20))==original
        for c in ['vlog','crash','wdog']:
            response=p.command(c,20);report[c]=response
            assert ('VFAT v=1 code=0 ' in response) if c=='vlog' else ('CRASH none' in response) if c=='crash' else (' reset=0 ' in response)
        report['status']='PASS';report['cleanup']=True
    except BaseException as e:
        report['status']='FAIL';report['error']=str(e);raise
    finally:
        if disk:
            try:run_text(['diskutil','eject',disk],timeout=60)
            except Exception:pass
        p.close();args.report.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print('M8 USB text PASS',flush=True)

if __name__=='__main__':main()
