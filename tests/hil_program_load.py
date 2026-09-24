#!/usr/bin/env python3
"""Test addressed binary load on a pinned device; replaces RAM and temporary files."""
import argparse
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from program_pack import program_binary
from hil_c6_system_bootstrap import read_file, write_file
from hil_elite_performance import TimedScreenPort
from hil_multi_device_identity import parse_identity
from hil_usb_disk_transaction import listing_entries


def memory(port, address, count):
    result = bytearray()
    while count:
        size = min(count, 112)
        report = port.command(f'hout {address:04d} {size}')
        block = b''.join(bytes.fromhex(h) for h in re.findall(r'(?m)^hin \d{4} ([0-9A-F]+)\r?$', report))
        assert len(block) == size, report
        result.extend(block)
        address += size
        count -= size
    return bytes(result)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--port', required=True)
    ap.add_argument('--public-id', required=True)
    ap.add_argument('--build-id', required=True)
    ap.add_argument('--confirm-ram-overwrite', action='store_true')
    args = ap.parse_args()
    if not args.confirm_ram_overwrite:
        ap.error('pass --confirm-ram-overwrite')
    source = bytes(range(256)) + bytes(73) + bytes(range(100))
    small = program_binary(bytes([0x50]))
    bad = bytes([small[0] ^ 1]) + small[1:]
    temporary = '/_bin-load-test'
    files = {
        'data.bin': program_binary(source),
        'one.bin': small,
        'two.bin': program_binary(bytes(2)),
        'full.bin': program_binary(bytes(32 * 112)),
        'bad.bin': bad,
        'short.bin': small[:-1],
        'extra.bin': small + b'\x00',
        'raw.bin': bytes(range(256)) * 16,
        '2026 demo.m61': b'hin 0000 50\n',
        'nested.m61': b'load 0224 one.bin\n',
        'autoexec.m61': b'reinit\nload 0100 data.bin\nopen nested.m61\nload 9999 one.bin\n',
    }
    with TimedScreenPort(args.port) as port:
        identity = parse_identity(port.command('identity'))
        assert identity.public == args.public_id.upper() and identity.build == args.build_id.upper(), identity
        before = listing_entries(port.command('ls /'))
        assert not any(e.split('\t')[-1].rstrip('/').casefold() == temporary[1:] for e in before)
        port.command('reinit')
        port.command('mkdir ' + temporary)
        try:
            for name, data in files.items():
                write_file(port, temporary + '/' + name, data)
                read_file(port, temporary + '/' + name, data)
            print('PASS: binary C6/CDC roundtrip, all byte values and 4096-byte file', flush=True)
            port.command('cd ' + temporary)
            report = port.command('load 0100 data.bin')
            assert memory(port, 100, len(source)) == source, report
            report = port.command('load 9999 one.bin')
            assert memory(port, 9999, 1) == b'\x50', report
            assert memory(port, 100, len(source)) == source
            print('PASS: crossed banks, separate ranges, address 9999 and no implicit clearing', flush=True)

            port.command('load 2026 demo.m61')
            assert memory(port, 0, 1) == b'\x50'
            port.command('open ' + temporary + '/autoexec.m61')
            expected = bytearray(source)
            expected[224 - 100] = 0x50
            assert memory(port, 100, len(source)) == expected
            assert memory(port, 9999, 1) == b'\x50'
            print('PASS: numeric M61 filename, relative binary paths and nested M61 without clearing', flush=True)

            for filename, error in [('bad.bin', 'CRC32 mismatch'),
                                    ('short.bin', 'Incomplete ZX0'),
                                    ('extra.bin', 'after ZX0')]:
                port.command('reinit')
                report = port.command('load 0000 ' + filename)
                assert error in report, report
                for command in ('run', 'cmd 50', 'hin 0000 50'):
                    report = port.command(command)
                    assert error in report, report
                for tail in ('', 'ret\n', 'run\n'):
                    payload = ('load 0000 ' + filename + '\n' + tail).encode('ascii')
                    write_file(port, temporary + '/failure.m61', payload)
                    report = port.command('open ' + temporary + '/failure.m61')
                    assert error in report, report
                    assert error in port.command('run')
            print('PASS: malformed/CRC/EOF failures stop M61 and block execution', flush=True)

            for command in ('load 9999 two.bin', 'load 0112 full.bin'):
                port.command('reinit')
                report = port.command(command)
                assert 'program memory full' in report, report
                assert 'program memory full' in port.command('run')
            port.command('reinit')
            report = port.command('load 0000 missing.bin')
            assert 'Cannot open binary program' in report, report
            assert 'Cannot' not in port.command('hin 0000 50')
            assert memory(port, 0, 1) == b'\x50'
            print('PASS: address overflow, bank-slot exhaustion, missing-file recovery', flush=True)
            assert 'CRASH none' in port.command('crash show')
        finally:
            port.command('reinit')
            port.command('cd /')
            port.command('rm -r ' + temporary, timeout=30)
            assert listing_entries(port.command('ls /')) == before
        print('PASS: temporary files removed; original root listing restored', flush=True)


if __name__ == '__main__':
    main()
