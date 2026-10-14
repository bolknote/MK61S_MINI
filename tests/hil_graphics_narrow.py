#!/usr/bin/env python3
"""Qualify the same complete framebuffer before/after a graphics change.

Uses portable_app_hil_check.c as GFXCHECK.APP. Verifies 100 complete CRC frames,
SPI ownership/errors, original files and calculator state. Never flashes.
"""
import argparse
import hashlib
import json
import re
import time
from pathlib import Path

from hil_c5_stack import read_file, write_file
from hil_multi_device_identity import parse_identity
from hil_packbits_firmware import fingerprint
from hil_portable_apps import ScreenPort
from hil_uc1609_spi1 import key_values, require_zero


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', required=True)
    parser.add_argument('--public-id', required=True)
    parser.add_argument('--expected-build', required=True)
    parser.add_argument('--keyboard-layout', type=int, choices=(0, 1), required=True)
    parser.add_argument('--app', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--restart-after', action='store_true',
                        help='work around known stock USB-screen/cache cleanup bug; requires a zero/empty calculator')
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    expected = bytes(((i * 17 + i // 16) ^ 0xA5) & 255 for i in range(1536))
    remote = '/GFXCHECK.APP'
    report = {}
    with ScreenPort(args.port, keyboard_layout=args.keyboard_layout) as port:
        identity = parse_identity(port.command('identity', 15))
        assert identity.public == args.public_id.upper() and identity.build == args.expected_build.upper()
        report['identity'] = identity.__dict__
        files = fingerprint(port)
        logical = {command: port.command(command, 20) for command in ('reg', 'stk', 'dump', 'pwd')}
        assert remote.casefold() not in {p.casefold() for p in files['files']}
        if args.restart_after:
            registers = re.findall(r'(?m)^(?:R[0-9A-E]|X1|[TZYX])\s+=\s+(-?\d\.\d+)\s+(-?\d+)\r?$', logical['reg'] + logical['stk'])
            assert len(registers) == 20 and all(float(value) == 0 and not value.startswith('-') and int(exponent) == 0 for value, exponent in registers), 'restart requires zero registers/stack'
            assert 'IP: 0' in logical['reg'] and 'IP =  0' in logical['stk']
            assert not re.search(r'(?m)^\d{4} ', port.command('hout', 20)), 'restart requires an empty program'
        foreground = False
        try:
            write_file(port, remote, args.app.read_bytes())
            port.command('prof reset')
            port.attach()
            port.frames.clear()
            port.open(remote)
            foreground = True
            port.expect_frame(expected, 0, timeout=8)
            for _ in range(100):
                begin = len(port.frames)
                port.send(0x16)
                deadline = time.monotonic() + 4
                while len(port.frames) == begin and time.monotonic() < deadline:
                    port.pump(.03)
                assert len(port.frames) > begin, 'incomplete framebuffer'
                assert port.frames[-1] == expected, 'framebuffer differs from independent pixel formula'
            report['frames'] = len(port.frames)
            report['frame_sha256'] = hashlib.sha256(expected).hexdigest()
            port.close_app()
            foreground = False
            port.send(0x13)
            port.attached = False
            port.pump(.2)
            profile = port.command('prof', 20)
            bus = key_values(profile, 'SPI1 backend=')
            require_zero(bus, ('failures', 'contentions', 'double', 'inactive', 'wrong', 'invalid', 'latched', 'recoveries'))
            assert bus['state'] == 'idle' and bus['owner'] == 'none'
            assert bus['acquisitions'] == bus['releases']
            report['profile'] = profile
            report['workload_mpu'] = port.command('mpu status', 20)
            remaining = re.search(r'watermark_remaining=(\d+)', report['workload_mpu'])
            assert remaining and int(remaining[1]) >= 12288, report['workload_mpu']
        finally:
            if foreground:
                port.close_app()
            if port.attached:
                port.send(0x13)
                port.attached = False
                port.pump(.2)
            def cleanup(port):
                port.command('fsput cancel')
                current = fingerprint(port)
                path = next((p for p in current['files'] if p.casefold() == remote.casefold()), None)
                if path:
                    assert 'Removed 1 entry.' in port.command(f'rm "{path}"', 30)
                assert fingerprint(port) == files, 'graphics test changed original files'
                assert {command: port.command(command, 20) for command in logical} == logical, 'graphics test changed calculator state'
                report['health'] = {command: port.command(command, 20) for command in ('df', 'crash show', 'mpu status')}
                assert 'FIRMWARE CRC state=valid' in report['health']['df'] and 'actual=0x' + args.expected_build.upper() in report['health']['df']
                assert 'CRASH none' in report['health']['crash show']
                report['preservation'] = 'Original files/program/registers/stack/pwd exact'
                (args.output_dir / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
            if args.restart_after:
                port.write_line('rst now')
                port.close()  # Release the exclusive CDC lock before reconnecting.
                time.sleep(1)
                deadline = time.monotonic() + 20
                while True:
                    restored = None
                    try:
                        restored = ScreenPort(args.port, keyboard_layout=args.keyboard_layout)
                        identity = parse_identity(restored.command('identity', 15))
                        assert identity.public == args.public_id.upper() and identity.build == args.expected_build.upper()
                        break
                    except (OSError, TimeoutError):
                        if restored is not None:
                            restored.close()
                        if time.monotonic() >= deadline:
                            raise
                        time.sleep(.2)
                with restored:
                    cleanup(restored)
                report['restart_after_graphics'] = True
                (args.output_dir / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
            else:
                cleanup(port)
    print(args.public_id, '100 complete frames match reference; state and SPI ownership PASS', flush=True)


if __name__ == '__main__':
    main()
