#!/usr/bin/env python3
"""Test ztart/zin on a pinned device; replaces calculator RAM and temporary M61 files."""
import argparse
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from program_pack import program_lines
from hil_c6_system_bootstrap import read_file, write_file
from hil_elite_performance import TimedScreenPort
from hil_multi_device_identity import parse_identity


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
    lines = program_lines(source, 100)
    small = program_lines(bytes([0x50]))
    # Files are removed before attaching USB Screen, which leases the C6 overlay.
    temporary = '/_zin-test.m61'
    with TimedScreenPort(args.port) as port:
        identity = parse_identity(port.command('identity'))
        assert identity.public == args.public_id and identity.build == args.build_id, identity
        assert '_zin-test.m61' not in port.command('ls /')
        port.command('reinit')
        for line in lines:
            report = port.command(line.rstrip('\n'))
            assert not re.search(r'Invalid|incomplete|mismatch|full|Stop calculator', report), report
        assert memory(port, 100, len(source)) == source
        assert 'Incomplete' not in port.command('hin 0100 00')
        print('PASS: generic image, all byte values, crossed banks, CRC and raw Base91 punctuation', flush=True)

        port.command('reinit')
        # A legal stream with a wrong checksum must not unlock execution.
        bad = small[0].rstrip('\n')
        bad = bad[:-1] + ('0' if bad[-1] != '0' else '1')
        port.command(bad)
        assert 'CRC32 mismatch' in port.command(small[1].strip())
        assert 'CRC32 mismatch' in port.command('run')
        assert 'CRC32 mismatch' in port.command('cmd 50')
        port.command('reinit')
        port.command(small[0].strip())
        assert 'Invalid Base91' in port.command('zin A-')
        assert 'Invalid Base91' in port.command('run')
        print('PASS: bad CRC/Base91 block run and direct commands', flush=True)

        port.command('reinit')
        overflow = program_lines(bytes(2))
        port.command(overflow[0].replace('0000', '9999', 1).strip())
        assert 'program memory full' in port.command(overflow[1].strip())
        assert 'program memory full' in port.command('run')
        port.command('reinit')
        exhausted = program_lines(bytes(32 * 112), 112)
        report = ''
        for line in exhausted:
            report += port.command(line.strip())
        assert 'program memory full' in report, report
        assert 'program memory full' in port.command('run')
        print('PASS: address limit and exhaustion of 32 bank slots', flush=True)

        for tail in ('', 'ret\n', 'run\n'):
            port.command('reinit')
            payload = (small[0] + tail).encode('ascii')
            write_file(port, temporary, payload)
            read_file(port, temporary, payload)
            report = port.command('open ' + temporary)
            port.pump(.2)
            assert 'Incomplete ZX0 program' in report, report
            assert 'Incomplete ZX0 program' in port.command('run')
        port.command('reinit')
        assert 'Removed 1 entry.' in port.command('rm ' + temporary)
        assert '_zin-test.m61' not in port.command('ls /')
        assert 'CRASH none' in port.command('crash show')
        print('PASS: truncated M61 blocks EOF, ret and run; temporary file removed', flush=True)


if __name__ == '__main__':
    main()
