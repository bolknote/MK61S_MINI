#!/usr/bin/env python3
"""Measure a verified unused RP2040 Flash extension; restore the complete snapshot.

This is a separate, explicitly reserved Flash window, never the APP-only scout.
The plan contains hashed APPs and bounded runner arguments. Firmware, calculator
data, current address, settings and RTC trajectory are restored in finally.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
from hil_m0_math_compare import MathPort, rtc_after_wall_elapsed
from hil_picocalc_software import restore, calculator
from hil_usb_disk_transaction import listing_entries

UID = 'E6657CD423721C35'
FLASH_BASE = 0x10000000
FLASH_BYTES = 2 * 1024 * 1024
SETTINGS_OFFSET = FLASH_BYTES - 8192


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_payload_receipts(payload):
    expected = sha(payload / 'payload.elf')
    for name in ('validation.json', 'copy-validation.json', 'move-validation.json'):
        report = json.loads((payload / name).read_text())
        reports = report if isinstance(report, list) else [report]
        assert reports, ('Empty validation receipt', name)
        for validation in reports:
            assert validation['elf_sha256'] == expected
            assert validation['results']
            assert all(item['status'] == 'PASS' for item in validation['results'])


def make_candidate(backup, payload, layout, firmware, manifest):
    """Reject occupied spans and preserve every byte outside the payload."""
    assert layout['cpu'] == 'm0'
    assert len(backup) == FLASH_BYTES
    assert len(firmware) == manifest['flash_bytes']
    assert hashlib.sha256(firmware).hexdigest() == manifest['bin_sha256']
    assert backup[:len(firmware)] == firmware
    assert len(payload) == layout['bytes'] <= 8192
    assert hashlib.sha256(payload).hexdigest() == layout['sha256']
    offset = layout['base'] - FLASH_BASE
    assert offset % 4096 == 0 and len(firmware) <= offset
    assert offset + len(payload) <= min(SETTINGS_OFFSET, manifest['settings_flash_offset'])
    assert backup[offset:offset + len(payload)] == b'\xff' * len(payload)
    candidate = bytearray(backup)
    candidate[offset:offset + len(payload)] = payload
    assert candidate[:offset] == backup[:offset]
    assert candidate[offset + len(payload):] == backup[offset + len(payload):]
    return bytes(candidate)


def main():
    if not __debug__:
        raise RuntimeError('Run without -O: preservation checks are mandatory')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--payload', type=Path, required=True)
    parser.add_argument('--restore-package', type=Path, required=True)
    parser.add_argument('--restore-sha256', required=True)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--picotool', type=Path, default=ROOT / '.build/picocalc-picotool/picotool')
    parser.add_argument('--handoff', type=Path, default=ROOT / '.build/picocalc-device-handoff.json')
    args = parser.parse_args()
    assert sha(args.restore_package / 'RESTORE.json') == args.restore_sha256
    receipt = json.loads((args.restore_package / 'RESTORE.json').read_text())
    manifest = json.loads((args.restore_package / 'manifest.json').read_text())
    assert receipt['uid'] == UID and receipt['hardware_verified']
    assert sha(args.restore_package / 'manifest.json') == receipt['manifest_sha256']
    assert receipt['build_id'].lower() == manifest['build_id'].lower()
    assert sha(args.restore_package / receipt['uf2']) == receipt['uf2_sha256'] == manifest['uf2_sha256']
    firmware = (args.restore_package / 'mk61s-picocalc-pico-h.bin').read_bytes()
    layout = json.loads((args.payload / 'layout.json').read_text())
    payload = (args.payload / 'payload.bin').read_bytes()
    verify_payload_receipts(args.payload)
    plan = json.loads(args.plan.read_text())
    assert plan['payload_sha256'] == layout['sha256']
    assert 0 < len(plan['sessions']) <= 8
    directories = []
    for session in plan['sessions']:
        assert session['operation'] in ('memcmp', 'memcpy', 'memmove')
        assert re.fullmatch(r'[a-z0-9-]+', session['name'])
        prefix = {'memcmp': 'MCMP', 'memcpy': 'MCPY', 'memmove': 'MOVE'}[session['operation']]
        assert re.fullmatch('/' + prefix + r'[A-Za-z0-9-]*', session['directory'])
        assert sha(Path(session['app'])) == session['app_sha256']
        assert 1 <= session['runs'] <= 3
        directories.append(session['directory'])
    shared = json.loads(args.handoff.read_text())
    assert shared['owner'] == 'memcmp' and shared['state'] == 'reserved_flash'
    assert shared['uid'] == UID and not shared['serial_port_open']
    assert shared['calculator_state_restored'] and shared['firmware_crc_verified']
    assert shared['build'].lower() == manifest['build_id'].lower()
    port_name = shared['port']
    assert re.fullmatch(r'/dev/cu\.usbmodem[0-9]+', port_name)
    args.output.mkdir(parents=True, exist_ok=False)
    state = dict(status='PREPARING', uid=UID, build=manifest['build_id'],
                 restore_sha256=args.restore_sha256, payload=layout,
                 started_at=datetime.now(timezone.utc).isoformat(), sessions=[])
    backup = None
    entered_rom = False

    def save():
        path = args.output / 'transaction.json'
        temporary = path.with_suffix('.new')
        temporary.write_text(json.dumps(state, indent=2) + '\n')
        temporary.replace(path)

    def healthy(status):
        for token in ('BUILD=' + manifest['build_id'].upper(), 'FIRMWARE_CRC=valid',
                      'CRASH=NONE', 'KBD=OK', 'SD=OK', 'PANEL_INIT=1',
                      'PSRAM=OK BYTES=8388608', 'USB_DISK=0', 'MATH_TEST=OK'):
            assert token in status, (token, status)
        assert 'FIRMWARE_LAST_FAILURE' not in status, status

    @contextmanager
    def connect(label):
        deadline = time.monotonic() + 40
        error = None
        while time.monotonic() < deadline:
            port = None
            try:
                port = MathPort(port_name, keyboard_layout=0)
                port.__enter__()
                port.commands()
                assert 'UID=' + UID in port.command('identity')
                while time.monotonic() < deadline:
                    status = port.status()
                    if all(token in status for token in ('KBD=OK', 'SD=OK', 'PANEL_INIT=1')):
                        break
                    port.pump(.25)
                healthy(status)
                break
            except (OSError, TimeoutError) as failure:
                error = failure
                if port is not None:
                    port.__exit__(None, None, None)
                time.sleep(.25)
            except BaseException:
                if port is not None:
                    port.__exit__(None, None, None)
                raise
        else:
            raise TimeoutError(('Pinned Pico did not reconnect', error))
        try:
            yield port
        finally:
            try:
                (args.output / (label + '-transcript.bin')).write_bytes(port.text)
            finally:
                port.__exit__(None, None, None)

    def tool(label, *arguments):
        result = subprocess.run([str(args.picotool), *map(str, arguments), '--ser', UID],
                                capture_output=True, text=True, timeout=120)
        (args.output / (label + '.log')).write_text(result.stdout + result.stderr)
        assert result.returncode == 0, (label, result.stdout, result.stderr)
        return result

    def enter_rom(label):
        nonlocal entered_rom
        result = subprocess.run([str(args.picotool), 'info', '-a', '--ser', UID],
                                capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            assert UID.lower() in result.stdout.lower()
            entered_rom = True
            return
        with connect(label) as port:
            # Set this first: a lost USB response must still trigger recovery.
            entered_rom = True
            port.write_line('dfu')
            try:
                port.pump(.3)
            except OSError:
                pass
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            result = subprocess.run([str(args.picotool), 'info', '-a', '--ser', UID],
                                    capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                assert UID.lower() in result.stdout.lower()
                return
            time.sleep(.25)
        raise TimeoutError('Pinned Pico did not enter ROM loader')

    def restore_data(port, label):
        before = state['before']
        directory = re.search(r'(?m)^(/[^\r\n]*)', before['pwd'])[1]
        assert 'ERROR' not in port.command('cd "' + directory + '"')
        restore(port, before)
        calculator(port)
        os.write(port.fd, b'\x1e' + ('g%02d' % state['ip_before']).encode('ascii'))
        port.pump(.4)
        port.expect('IP=%02d' % state['ip_before'], 'RUN=0 BUSY=0')
        port.commands()
        assert {command: port.command(command) for command in before} == before
        clock = state['clock_before']
        if clock['configured']:
            wanted = rtc_after_wall_elapsed(clock['date'], state['clock_sample_utc'])
            assert 'ERROR' not in port.command('date ' + wanted.strftime('%Y-%m-%d %H:%M:%S'))
            status = port.status()
            actual = datetime.fromisoformat(re.search(r'RTC=([0-9T:-]+)', status)[1])
            expected = rtc_after_wall_elapsed(clock['date'], state['clock_sample_utc'])
            assert abs((actual - expected).total_seconds()) <= 2
            state[label + '_rtc'] = dict(actual=actual.isoformat(), expected=expected.isoformat(),
                                         method='UTC wall elapsed, including host sleep')
        status = port.status()
        healthy(status)
        for key, value in state['settings_before'].items():
            assert re.search(r'\b' + key + '=' + re.escape(value) + r'\b', status)
        state[label + '_status'] = status
        save()

    with connect('before') as port:
        start = datetime.now(timezone.utc)
        initial = port.status()
        end = datetime.now(timezone.utc)
        assert 0 <= (end - start).total_seconds() <= 10
        for token in ('RUN=0 BUSY=0', 'SERVICE=CLOSED', 'DIRTY=0', 'RUNTIME=NONE'):
            assert token in initial, (token, initial)
        clock = re.search(r'RTC=([0-9T:-]+) RTC_SET=([01])', initial)
        assert clock, initial
        root_before = listing_entries(port.command('ls /'))
        root_names = port.command('ls /')
        for directory in directories:
            assert directory[1:].casefold() not in root_names.casefold(), directory
        state.update(initial_status=initial,
                     before={command: port.command(command) for command in ('reg', 'stk', 'hout', 'dump', 'pwd')},
                     ip_before=int(re.search(r'\bIP=(\d+)', initial)[1]),
                     clock_before=dict(date=clock[1], configured=bool(int(clock[2]))),
                     clock_sample_utc=(start + (end - start) / 2).isoformat(),
                     settings_before=dict(re.findall(r'\b(UI_FONT_FAMILY|UI_FONT_SIZE|UI_FONT_KEY|KBD_LAYOUT)=([^\s]+)', initial)))
        assert state['ip_before'] <= 99
        state['status'] = 'BACKED_UP'
        save()
    try:
        enter_rom('enter')
        reads = []
        for suffix in ('a', 'b'):
            path = args.output / ('flash-original-' + suffix + '.bin')
            tool('save-' + suffix, 'save', '-a', '-v', path, '-t', 'bin')
            reads.append(path.read_bytes())
        assert reads[0] == reads[1]
        candidate = make_candidate(reads[0], payload, layout, firmware, manifest)
        backup = reads[0]
        state['backup_sha256'] = hashlib.sha256(backup).hexdigest()
        candidate_path = args.output / 'flash-test.bin'
        candidate_path.write_bytes(candidate)
        state['status'] = 'INSTALLING'
        save()
        tool('install', 'load', '-u', '-v', candidate_path, '-t', 'bin', '-o', hex(FLASH_BASE))
        tool('boot-candidate', 'reboot')
        with connect('candidate') as port:
            restore_data(port, 'candidate')
        for session in plan['sessions']:
            operation = session['operation']
            command = [sys.executable, str(HERE / ('run.py' if operation == 'memcmp' else 'run-placement.py'))]
            if operation != 'memcmp':
                command.append(operation)
            destination = args.output / session['name']
            command += ['--cpu', 'm0', '--port', port_name, '--uid', UID, '--app', session['app'],
                        '--directory', session['directory'], '--output', str(destination), '--runs', str(session['runs'])]
            for key in ('sizes', 'alignments', 'sources', 'modes', 'gaps'):
                if key in session:
                    command += ['--' + key, *map(str, session[key])]
            for key in ('selected_runtime', 'extra_flash', 'quick', 'placement'):
                if session.get(key):
                    command.append('--' + key.replace('_', '-'))
            subprocess.run(command, check=True)
            report = json.loads((destination / 'result.json').read_text())
            assert report['status'] == 'PASS' and report['files_preserved'] and report['calculator_data_preserved']
            state['sessions'].append(dict(name=session['name'], status='PASS', app_sha256=report['app_sha256']))
            save()
    except BaseException as error:
        state['failure'] = repr(error)
        save()
        raise
    finally:
        if entered_rom:
            state['status'] = 'RESTORING'
            save()
            enter_rom('restore-enter')
            if backup is not None:
                tool('restore', 'load', '-u', '-v', args.output / 'flash-original-a.bin', '-t', 'bin', '-o', hex(FLASH_BASE))
                verified = args.output / 'flash-restored.bin'
                tool('restore-readback', 'save', '-a', '-v', verified, '-t', 'bin')
                assert verified.read_bytes() == backup, 'Complete Flash readback differs'
                state['full_flash_restored'] = True
            tool('boot-original', 'reboot')
            with connect('restored') as port:
                # Each directory was proven absent before the experiment.
                for directory in set(directories):
                    if directory[1:].casefold() in port.command('ls /').casefold():
                        assert 'ERROR' not in port.command('rm -r ' + directory, timeout=30)
                restore_data(port, 'restored')
                assert sorted(listing_entries(port.command('ls /'))) == sorted(root_before)
                state.update(files_preserved=True, calculator_data_preserved=True, ip_preserved=True)
            state['serial_closed'] = True
            state['status'] = 'PASS_RESTORED' if len(state['sessions']) == len(plan['sessions']) and not state.get('failure') else 'FAIL_RESTORED'
            save()


if __name__ == '__main__':
    main()
