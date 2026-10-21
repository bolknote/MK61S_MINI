#!/usr/bin/env python3
"""Capture F411 ROM twice via a temporary RAM APP; restore the file set."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys
import zlib

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tests'))
from hil_c5_stack import read_file, write_file
from hil_multi_device_identity import parse_identity
from hil_packbits_firmware import fingerprint
from hil_portable_apps import ScreenPort
from hil_rtc_alarm import canonical_state_reply

CHUNKS = tuple('/ROMC' + str(i) + '.bin' for i in range(8))
REMOTE = ('/ROMCAP.APP', *CHUNKS, '/ROMINFO.bin')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', required=True)
    parser.add_argument('--public-id', required=True)
    parser.add_argument('--app', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    report = {'status': 'RUNNING', 'method': 'Two independent ROM reads and software CRC32 in a temporary RAM APP; CDC file transfer; no reset or MCU Flash write'}
    def save():
        (args.output / 'capture.json').write_text(json.dumps(report, indent=2) + '\n')
    with ScreenPort(args.port) as port:
        identity = parse_identity(port.command('identity', 10))
        assert identity.public == args.public_id.upper(), identity
        assert identity.profile == 'classic-v3-uc1609', identity
        report['identity'] = identity.__dict__
        original = fingerprint(port)
        state = {c: canonical_state_reply(port.command(c, 15)) for c in ('reg', 'stk', 'dump', 'pwd')}
        assert not any(p.casefold() in {q.casefold() for q in REMOTE} for p in original['files'])
        report['files_before'] = original
        report['state_before'] = state
        report['health_before'] = {c: port.command(c, 15) for c in ('df', 'crash show', 'mpu status')}
        assert 'FIRMWARE CRC state=valid' in report['health_before']['df']
        save()
        try:
            write_file(port, REMOTE[0], args.app.read_bytes())
            report['reads'] = []
            for label in ('a', 'b'):
                launch = port.command('open "' + REMOTE[0] + '"', timeout=45)
                assert 'Open failed!' not in launch, launch
                raw = b''.join(read_file(port, path) for path in CHUNKS)
                info = read_file(port, '/ROMINFO.bin')
                magic, address, size, crc, cpuid, idcode, flash_kib = struct.unpack('<7I', info)
                assert (magic, address, size) == (0x314D4F52, 0x1FFF0000, 0x7800)
                assert len(raw) == size and zlib.crc32(raw) == crc
                (args.output / ('rom-' + label + '.bin')).write_bytes(raw)
                row = {'label': label, 'bytes': size, 'sha256': hashlib.sha256(raw).hexdigest(),
                       'crc32': f'{crc:08X}', 'cpuid': f'{cpuid:08X}', 'idcode': f'{idcode:08X}',
                       'flash_kib': flash_kib, 'launch': launch}
                report['reads'].append(row)
                save()
                print(json.dumps(row), flush=True)
            assert (args.output / 'rom-a.bin').read_bytes() == (args.output / 'rom-b.bin').read_bytes()
            report['status'] = 'PASS'
        except BaseException as error:
            report['status'] = 'FAIL'
            report['error'] = str(error)
            raise
        finally:
            port.command('fsput cancel')
            current = fingerprint(port)
            for path in REMOTE:
                actual = next((p for p in current['files'] if p.casefold() == path.casefold()), None)
                if actual:
                    assert 'Removed 1 entry.' in port.command('rm "' + actual + '"', 30)
            report['files_unchanged'] = fingerprint(port) == original
            report['state_unchanged'] = {c: canonical_state_reply(port.command(c, 15)) for c in state} == state
            report['identity_unchanged'] = parse_identity(port.command('identity')) == identity
            report['health_after'] = {c: port.command(c, 15) for c in ('df', 'crash show', 'mpu status')}
            (args.output / 'terminal.txt').write_bytes(port.text)
            save()
            assert report['files_unchanged'] and report['state_unchanged'] and report['identity_unchanged']
            assert 'FIRMWARE CRC state=valid' in report['health_after']['df']
            assert 'CRASH none' in report['health_after']['crash show']
            assert 'enabled=1 layout=ok' in report['health_after']['mpu status']
    print('ROM capture PASS; original files, calculator state and firmware preserved.', flush=True)

if __name__ == '__main__':
    main()
