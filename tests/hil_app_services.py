#!/usr/bin/env python3
"""Test public services from preinstalled ordinary C APPs on a Classic V3.

Build portable_app_services_hil.c as SHARED.APP with --shared-runtime and as
LOCAL.APP without it. Both create, read and delete /APITEST.txt; this test
refuses to run if that name already exists. The caller preserves device state
and installs the APPs. No firmware flashing or fixture upload is done here.
"""
import argparse
import json
from pathlib import Path
import re

from hil_portable_apps import ScreenPort
from hil_portable_system_apps import png
from hil_usb_disk_transaction import listing_entries


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', required=True)
    parser.add_argument('--public-id', required=True)
    parser.add_argument('--directory', default='/APISVC')
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--cycles', type=int, default=5)
    parser.add_argument('--minimum-stack-remaining', type=int, default=12288)
    args = parser.parse_args()
    assert 1 <= args.cycles <= 100 and '"' not in args.directory
    assert args.minimum_stack_remaining >= 0
    args.output_dir.mkdir(parents=True, exist_ok=True)
    expected = b'API\0' + bytes(((i * 29 + i // 7) ^ 0x61) & 255
                                 for i in range(4, 1536))
    foreground = False
    with ScreenPort(args.port) as port:
        identity = port.command('identity')
        assert f'public={args.public_id.upper()}' in identity, identity
        (args.output_dir/'identity.txt').write_text(identity)
        root = listing_entries(port.command('ls /'))
        assert not any(line.split('\t')[-1].casefold().split('.')[0] == 'apitest'
                       for line in root), 'reserved probe file /APITEST already exists'
        try:
            port.attach()
            for cycle in range(args.cycles):
                for name in ('SHARED', 'LOCAL'):
                    start = len(port.frames)
                    foreground = True
                    port.open(f'{args.directory}/{name}.APP')
                    port.expect_frame(expected, start)
                    png(expected, args.output_dir/f'{name.lower()}-{cycle}.png')
                    port.close_app(); foreground = False
                    memory = port.command('mem')
                    (args.output_dir/f'{name.lower()}-{cycle}-mem.txt').write_text(memory)
                    assert 'MEM invariant=ok' in memory, memory
                    for arena in ('workspace', 'scratch'):
                        line = next(x for x in memory.splitlines()
                                    if x.startswith('MEM '+arena+' '))
                        assert ' active=none ' in line and ' depth=0 ' in line, line
                    assert listing_entries(port.command('ls /')) == root, 'C5 file leaked'
                print(f'Cycle {cycle+1}: shared/local C service probes, pixels, memory and C5 PASS',
                      flush=True)
            for command in ('crash show', 'mpu status', 'df'):
                report = port.command(command, timeout=15)
                (args.output_dir/(command.replace(' ', '-')+'.txt')).write_text(report)
                if command == 'crash show': assert 'CRASH none' in report, report
                if command == 'mpu status':
                    assert 'enabled=1 layout=ok' in report and 'watermark=1' in report, report
                    remaining = int(re.search(r' observed_remaining=(\d+)', report)[1])
                    assert remaining >= args.minimum_stack_remaining, report
                if command == 'df': assert 'FIRMWARE CRC state=valid' in report, report
            (args.output_dir/'result.json').write_text(json.dumps({
                'result': 'PASS', 'launches': args.cycles * 2,
                'variants': ['shared-runtime', 'local-runtime'],
                'checks': ['lookup', 'double', 'uint64 division/remainder', 'math',
                           'format', 'workspace/scratch', 'C5 write/read/remove', 'editor callback'],
                'minimum_stack_remaining': remaining,
                'frames_verified_transport': len(port.frames)
            }, indent=2)+'\n')
        finally:
            (args.output_dir/'terminal.txt').write_bytes(port.text)
            if port.frames: png(port.frames[-1], args.output_dir/'last-frame.png')
            if foreground and port.attached: port.key(39)
            if port.attached: port.send(0x13); port.pump(.2)


if __name__ == '__main__':
    main()
