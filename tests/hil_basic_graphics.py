#!/usr/bin/env python3
"""Capture the BASIC or FOCAL Graphics example on a matched Classic USB Screen.

Firmware/System installation is separate. Reserves one unused temporary file,
then removes it and verifies all files and calculator state. Requires an empty
calculator because its cleanup performs a warm reset. A warm reset after
leaving the foreground releases the USB Screen workspace before cleanup.
When installed, VMCache/VMSTORE.APP must match the language APPs. Legacy and paged
VM caches are byte-snapshotted and restored; unknown paths stop cleanup.
"""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import re
import time

from hil_c5_stack import read_file
from hil_c6_system_bootstrap import write_file
from hil_language_vm import health, require_foreground
from hil_multi_device_identity import parse_identity
from hil_system_memory import require_empty
from hil_vm_cache_snapshot import CacheSnapshot, require_empty_calculator
from hil_packbits_firmware import fingerprint
from hil_portable_apps import PROMPT, ScreenPort
from hil_portable_system_apps import png
from hil_rtc_alarm import canonical_state_reply

ROOT = Path(__file__).resolve().parents[1]


def restore_cache(port, saved, current):
    return saved.restore(current, lambda path: read_file(port, path),
                         lambda path, data: write_file(port, path, data),
                         lambda command: port.command(command, timeout=30))


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
    parser.add_argument('--language', choices=('basic', 'focal'), default='basic')
    parser.add_argument('--port', required=True)
    parser.add_argument('--public-id', required=True)
    parser.add_argument('--build-id', required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--reopen', action='store_true',
                        help='run a second uncached source without detaching USB after the first END')
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True)  # Preserve every earlier PASS/FAIL report.
    result = {'status': 'RUNNING', 'pages': []}
    extension = 'foc' if args.language == 'focal' else 'tbi'
    remote = '/GFXDEMO.' + extension
    remotes = [remote] + (['/GFXNEXT.' + extension] if args.reopen else [])
    result['language'] = args.language
    source = (ROOT/('programs/examples/Graphics.'+extension)).read_bytes()
    port = None
    written = []
    screen_started = False
    before = saved = None
    cache_saved = None

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
        assert not {p.casefold() for p in remotes} & {n.casefold() for n in before['files']}, remotes
        result['file_snapshot_before'] = before
        result['alarms'] = [line for line in port.command('alarm').splitlines()
                            if line.startswith('RTC ALARM ')]
        saved = {c: port.command(c) for c in ('reg', 'stk', 'dump', 'pwd')}
        require_empty(saved)
        require_empty_calculator(saved)
        cache_saved = CacheSnapshot(before, lambda path: read_file(port, path))
        result['reserved_source_paths'] = remotes
        for path in remotes:
            written.append(path)  # Own absent path before upload/lost-ACK failure.
            write_file(port, path, source)
            assert read_file(port, path) == source
        port.attach()
        screen_started = True
        for index, path in enumerate(remotes):
            prefix = 'reopen-' if index else ''
            first = len(port.frames)
            port.open(path)
            frame = wait_page(port, first, lambda f:
                pixel(f, 0, 30) and pixel(f, 69, 21) and not pixel(f, 90, 30)
                and pixel(f, 160, 27) and pixel(f, 50, 12))
            png(frame, args.output_dir/(prefix+'primitives.png'))
            (args.output_dir/(prefix+'primitives.bin')).write_bytes(frame)
            result['pages'].append({'name': prefix+'primitives', 'sha256': hashlib.sha256(frame).hexdigest()})
            first = len(port.frames)
            port.pump(.2)  # Let SHOW return and PAUSE/ASK enter its key wait.
            port.key(37)
            frame = wait_page(port, first, lambda f:
                pixel(f, 48, 42) and pixel(f, 144, 42) and pixel(f, 96, 20)
                and pixel(f, 30, 53))
            png(frame, args.output_dir/(prefix+'graph.png'))
            (args.output_dir/(prefix+'graph.bin')).write_bytes(frame)
            result['pages'].append({'name': prefix+'graph', 'sha256': hashlib.sha256(frame).hexdigest()})
            port.pump(.2)
            port.key(37)
            deadline = time.monotonic()+5
            while not PROMPT.search(port.text[port.open_text_start:]) and time.monotonic() < deadline:
                port.pump(.1)
            assert PROMPT.search(port.text[port.open_text_start:]), 'example did not exit after its second wait'
            assert b'Open failed!' not in port.text[port.open_text_start:]
        result['uncached_reopen_same_usb_session'] = args.reopen
        result['crc_checked_frames'] = len(port.frames)
        result['foreground_health'] = health(port)  # Capture stack watermark before cleanup resets it.
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
                source_files = fingerprint(port)['files'] if written and 'error' in result else None
                for path in written:
                    if source_files is not None and path not in source_files:
                        continue  # Failed atomic upload created no logical file.
                    assert read_file(port, path) == source
                    assert 'Removed 1 entry.' in port.command('rm "'+path+'"')
                if cache_saved is not None:
                    current = fingerprint(port)
                    result['file_snapshot_before_cache_restore'] = current
                    try:
                        result['vm_cache_cleanup'] = restore_cache(port, cache_saved, current)
                    finally:
                        result['vm_cache_delta'] = cache_saved.delta
                if saved is not None:
                    cwd = saved['pwd'].splitlines()[1].strip()
                    port.command('cd "'+cwd+'"')
                    assert {c: canonical_state_reply(port.command(c)) for c in saved} == {
                        c: canonical_state_reply(reply) for c, reply in saved.items()}, 'calculator state changed'
                    assert [line for line in port.command('alarm').splitlines()
                            if line.startswith('RTC ALARM ')] == result['alarms']
                    result['calculator_state_preserved'] = True
                if before is not None:
                    result['file_snapshot_after'] = fingerprint(port)
                    assert result['file_snapshot_after'] == before, 'file fingerprints changed'
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
    print(args.language.upper(), 'graphics USB Screen:', len(result['pages']),
          'pages, frame CRCs, files/state preserved PASS')


if __name__ == '__main__':
    main()
