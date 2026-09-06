#!/usr/bin/env python3
"""Measure cumulative stack use across C5 writes, replacements and readback.

The caller supplies an existing temporary directory. Two test files are
created only if their names are unused, then removed even after a failure.
No firmware flashing, formatting or calculator register changes are performed.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

from hil_portable_apps import ScreenPort
from hil_usb_disk_transaction import listing_entries, posix_cksum, require_file_contents


def read_file(port, path):
    report = port.command(f'fsget "{path}"', timeout=15)
    data = bytearray()
    for offset, block in re.findall(r'(?m)^@MKC:DATA (\d+) ([0-9A-Fa-f]+)\r?$', report):
        assert int(offset) == len(data), report
        data.extend(bytes.fromhex(block))
    require_file_contents(report, bytes(data))
    return bytes(data)


def write_file(port, path, data):
    checksum = posix_cksum(data)
    report = port.command(f'fsput begin "{path}" {len(data)} {checksum}')
    assert f'@MKC:READY {len(data)}' in report, report
    for offset in range(0, len(data), 96):
        report = port.command(f'fsput data {offset} {data[offset:offset+96].hex()}')
        assert f'@MKC:ACK {min(offset+96, len(data))}' in report, report
    report = port.command('fsput end', timeout=30)
    assert f'@MKC:DONE {len(data)} {checksum}' in report, report
    assert read_file(port, path) == data, path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', required=True)
    parser.add_argument('--public-id', required=True)
    parser.add_argument('--directory', required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--minimum-stack-remaining', type=int, default=0)
    args = parser.parse_args()
    if not args.directory.startswith('/') or '"' in args.directory or args.minimum_stack_remaining < 0:
        parser.error('use an absolute directory without quotes and a nonnegative stack limit')
    args.output_dir.mkdir(parents=True, exist_ok=True)
    names = ('STACKIO.txt', 'STACKIO.ch8')
    paths = [args.directory.rstrip('/') + '/' + name for name in names]
    touched = []
    samples = []
    with ScreenPort(args.port) as port:
        identity = port.command('identity')
        assert f'public={args.public_id.upper()}' in identity, identity
        (args.output_dir/'identity.txt').write_text(identity)
        before = listing_entries(port.command(f'ls "{args.directory}"'))
        assert not any(line.split('\t')[-1].casefold() in {name.casefold() for name in names}
                       for line in before), 'test filenames already exist'
        try:
            for index, size in enumerate((1, 511, 512, 513, 1023, 1536, 1536, 1023, 513, 512, 511, 1)):
                data = ((b'Stack test data 1234567890\n' * 70) if index % 2 else
                        b''.join(hashlib.sha256(str(j).encode()).digest() for j in range(60)))[:size]
                if paths[0] not in touched:
                    touched.append(paths[0])
                # The second write must preserve identical content through the
                # compressed-file equality check, without publishing a new inode.
                for repeat in range(2):
                    write_file(port, paths[0], data)
                    report = port.command('mpu status')
                    remaining = int(re.search(r' observed_remaining=(\d+)', report)[1])
                    samples.append({'bytes': size, 'repeat': repeat, 'remaining': remaining})
                print(samples[-1], flush=True)
            data = b''.join(hashlib.sha256(str(j+70).encode()).digest() for j in range(112))
            assert len(data) == 3584
            touched.append(paths[1])
            for _ in range(2):
                write_file(port, paths[1], data)
        finally:
            port.command('fsput cancel')
            for path in touched:
                port.command(f'rm "{path}"')
            after = listing_entries(port.command(f'ls "{args.directory}"'))
            assert sorted(after) == sorted(before), 'temporary files were not removed cleanly'
            (args.output_dir/'terminal.txt').write_bytes(port.text)
        for command in ('mem', 'mpu status', 'crash show', 'df'):
            report = port.command(command, timeout=15)
            (args.output_dir/(command.replace(' ', '-')+'.txt')).write_text(report)
            if command == 'mem': assert 'MEM invariant=ok' in report, report
            if command == 'crash show': assert 'CRASH none' in report, report
            if command == 'df': assert 'FIRMWARE CRC state=valid' in report, report
            if command == 'mpu status':
                assert 'enabled=1 layout=ok' in report and 'watermark=1' in report, report
                remaining = int(re.search(r' observed_remaining=(\d+)', report)[1])
                assert remaining >= args.minimum_stack_remaining, (remaining, args.minimum_stack_remaining)
        result = {'result': 'PASS', 'writes': 26, 'readback_equal': True,
                  'temporary_files_removed': True, 'minimum_stack_remaining': remaining, 'cases': samples}
        (args.output_dir/'result.json').write_text(json.dumps(result, indent=2)+'\n')
        print(f'C5 writes/readback/cleanup PASS; stack remaining={remaining}', flush=True)


if __name__ == '__main__':
    main()
