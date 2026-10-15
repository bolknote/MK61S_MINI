#!/usr/bin/env python3
"""Capture both Graphics.tbi pages from a matched Classic USB Screen.

Firmware/System installation is separate. Reserves one unused temporary file,
then removes it and verifies all files and calculator state. A warm reset after
leaving the foreground releases the USB Screen workspace before cleanup.
"""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import time

from hil_c5_stack import read_file
from hil_c6_system_bootstrap import write_file
from hil_language_vm import health, require_foreground
from hil_multi_device_identity import parse_identity
from hil_packbits_firmware import fingerprint
from hil_portable_apps import PROMPT, ScreenPort
from hil_portable_system_apps import png

ROOT = Path(__file__).resolve().parents[1]
REMOTE = '/GFXDEMO.tbi'


def pixel(frame, x, y):
    return bool(frame[y//8*192+x] & (1 << (y%8)))


def wait_page(port, first_frame, predicate, timeout=20):
    deadline = time.monotonic()+timeout
    while time.monotonic() < deadline:
        port.pump(.1)
        for frame in reversed(port.frames[first_frame:]):
            if predicate(frame):
                require_foreground(port)
                return frame
        require_foreground(port)
    raise TimeoutError('expected graphics page did not arrive')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', required=True)
    parser.add_argument('--public-id', required=True)
    parser.add_argument('--build-id', required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    result = {'status': 'RUNNING', 'pages': []}
    source = (ROOT/'programs/examples/Graphics.tbi').read_bytes()
    port = None
    written = screen_started = False
    before = saved = None

    def connect():
        p = ScreenPort(args.port)
        try:
            p.pump(.2)
            p.write_line('')
            p.pump(.2)
            identity = parse_identity(p.command('identity'))
            assert identity.public == args.public_id.upper(), identity
            assert identity.build == args.build_id.upper(), identity
            assert identity.profile == 'classic-v3-uc1609', identity
            return p, identity
        except BaseException:
            p.close()
            raise

    try:
        port, identity = connect()
        result['identity'] = asdict(identity)
        result['before'] = health(port)
        before = fingerprint(port)
        assert REMOTE.casefold() not in {n.casefold() for n in before['files']}, REMOTE
        saved = {c: port.command(c) for c in ('reg', 'stk', 'dump', 'pwd')}
        result['alarms'] = [line for line in port.command('alarm').splitlines()
                            if line.startswith('RTC ALARM ')]
        write_file(port, REMOTE, source)
        written = True
        assert read_file(port, REMOTE) == source
        port.attach()
        screen_started = True
        first = len(port.frames)
        port.open(REMOTE)
        frame = wait_page(port, first, lambda f:
            pixel(f, 0, 30) and pixel(f, 69, 21) and not pixel(f, 90, 30)
            and pixel(f, 160, 27) and pixel(f, 50, 12))
        png(frame, args.output_dir/'primitives.png')
        (args.output_dir/'primitives.bin').write_bytes(frame)
        result['pages'].append({'name': 'primitives', 'sha256': hashlib.sha256(frame).hexdigest()})
        first = len(port.frames)
        port.key(37)
        frame = wait_page(port, first, lambda f:
            pixel(f, 48, 42) and pixel(f, 144, 42) and pixel(f, 96, 20)
            and pixel(f, 30, 53))
        png(frame, args.output_dir/'graph.png')
        (args.output_dir/'graph.bin').write_bytes(frame)
        result['pages'].append({'name': 'graph', 'sha256': hashlib.sha256(frame).hexdigest()})
        port.key(37)
        deadline = time.monotonic()+5
        while not PROMPT.search(port.text[port.open_text_start:]) and time.monotonic() < deadline:
            port.pump(.1)
        assert PROMPT.search(port.text[port.open_text_start:]), 'example did not exit after its second PAUSE'
        result['crc_checked_frames'] = len(port.frames)
        result['status'] = 'PASS'
    except BaseException as error:
        result['status'] = 'FAIL'
        result['error'] = str(error)
        raise
    finally:
        try:
            if port is not None:
                if screen_started:
                    if not PROMPT.search(port.text[getattr(port, 'open_text_start', 0):]):
                        port.key(39)
                        port.key(39)
                    port.send(0x13)
                    port.attached = False
                    port.pump(.2)
                    port.write_line('rst now')
                    try:
                        port.pump(.5)
                    except OSError:
                        pass
                    (args.output_dir/'terminal.txt').write_bytes(port.text)
                    port.close()
                    port = None
                    deadline = time.monotonic()+25
                    while port is None:
                        try:
                            port, _ = connect()
                        except (OSError, TimeoutError):
                            if time.monotonic() >= deadline:
                                raise
                            time.sleep(.2)
                if written:
                    assert read_file(port, REMOTE) == source
                    assert 'Removed 1 entry.' in port.command('rm "'+REMOTE+'"')
                if saved is not None:
                    cwd = saved['pwd'].splitlines()[1].strip()
                    port.command('cd "'+cwd+'"')
                    assert {c: port.command(c) for c in saved} == saved, 'calculator state changed'
                    assert [line for line in port.command('alarm').splitlines()
                            if line.startswith('RTC ALARM ')] == result['alarms']
                    result['calculator_state_preserved'] = True
                if before is not None:
                    assert fingerprint(port) == before, 'file fingerprints changed'
                    result['files_preserved'] = len(before['files'])
                result['after'] = health(port)
        except BaseException as error:
            result['status'] = 'FAIL'
            result['cleanup_error'] = str(error)
            raise
        finally:
            if port is not None:
                port.close()
            (args.output_dir/'result.json').write_text(json.dumps(result, indent=2)+'\n')
    print('BASIC graphics USB Screen: two pages, frame CRCs, files/state preserved PASS')


if __name__ == '__main__':
    main()
