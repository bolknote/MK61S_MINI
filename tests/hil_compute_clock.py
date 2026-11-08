#!/usr/bin/env python3
"""Finite Classicselected-frequency comparison, leaving the requested final profile.

Firmware is installed separately. Uses the production SETUP service, finite
APPs, nonce-checked PONG and a private temporary directory. Never opens Pico.
"""
import argparse
import hashlib
import json
import re
import time
from pathlib import Path
from hil_classic_cdc_guard import current_binding, require_no_holders
from hil_multi_device_identity import parse_identity
from hil_c6_system_bootstrap import write_file, read_file
from hil_chip8_fps import receive_file, fields as chip_fields
from hil_vm_cache_latency import PingPort
from hil_portable_system_apps import png
from hil_rtc_alarm import PROMPT, Port
from compute_clock_fixture import oracle

DIRECTORY = '/ClockBench1108'


def identify(port, build):
    value = parse_identity(port.command('identity'))
    assert (value.public, value.usb, value.profile, value.build) == (
        'AEB505B6E0067623', '2068336B4731', 'classic-v3-uc1609', build), value


def connect(path, build):
    end = time.monotonic() + 35
    while True:
        port = None
        try:
            require_no_holders(current_binding(path))
            port = PingPort(path)
            identify(port, build)
            return port
        except (OSError, TimeoutError):
            if port is not None:
                port.close()
            if time.monotonic() >= end:
                raise
            time.sleep(.2)
        except AssertionError as error:
            if port is not None:
                port.close()
            # A warm reset temporarily removes the IOKit/CDC node. Retry
            # only that exact absence; ambiguous bindings/identity fail.
            if error.args != (('ambiguous/missing OS CDC binding', 0),) or time.monotonic() >= end:
                raise
            time.sleep(.2)
        except BaseException:
            if port is not None:
                port.close()
            raise


def launch(port, name, timeout):
    port.open(DIRECTORY + '/' + name)
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        port.pump(.01)
        if PROMPT.search(port.text[port.open_text_start:]):
            reply = bytes(port.text[port.open_text_start:])
            assert b'Open failed' not in reply and b'error' not in reply.lower(), reply
            return
    raise TimeoutError(('finite APP did not return', name, bytes(port.text[port.open_text_start:])))


def set_profile(args, profile):
    with connect(args.port, args.build) as port:
        write_file(port, DIRECTORY + '/profile.txt', str(profile).encode())
        read_file(port, DIRECTORY + '/profile.txt', str(profile).encode())
        launch(port, 'CLKSET.APP', 7)
        report = receive_file(port, DIRECTORY + '/select.txt')
        assert b'STEP=4 ' in report, report
        port.command('rm "' + DIRECTORY + '/select.txt"')
        port.write_line('rst now')
        time.sleep(.15)
    with connect(args.port, args.build) as port:
        print('Rebooted persisted profile', profile, flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', default='/dev/cu.usbmodem2068336B47311')
    parser.add_argument('--build', required=True)
    parser.add_argument('--artifacts', type=Path, required=True)
    parser.add_argument('--selector', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--final-profile', type=int, default=1, choices=range(3))
    parser.add_argument('--repeat', type=int, default=3, choices=(1, 2, 3))
    parser.add_argument('--profiles', type=int, nargs='+', default=[0, 1, 0], choices=range(3))
    args = parser.parse_args()
    args.output.mkdir(exist_ok=False, parents=True)
    samples = []
    expected_hash = oracle(4096 * 1024)
    with connect(args.port, args.build) as port:
        before = port.command('ls')
        assert DIRECTORY[1:] not in before, 'do not overwrite an existing directory'
        (args.output / 'before-ls.txt').write_text(before)
        port.command('mkdir "' + DIRECTORY + '"')
        for name, path in (('CLKTEST.APP', args.artifacts / 'CLKTEST.APP'),
                           ('C8FPS.APP', args.artifacts / 'C8FPS.APP'),
                           ('active.ch8', args.artifacts / 'stress.ch8'),
                           ('CLKSET.APP', args.selector)):
            data = path.read_bytes()
            write_file(port, DIRECTORY + '/' + name, data)
            read_file(port, DIRECTORY + '/' + name, data)
    try:
        for stage_index, profile in enumerate(args.profiles):
            stage = f'{stage_index}-{(96,108,120)[profile]}MHz'
            set_profile(args, profile)
            out = args.output / stage
            out.mkdir()
            with connect(args.port, args.build) as port:
                (out / 'df.txt').write_text(port.command('df', timeout=15))
                port.attach()
                for workload in ('CLKTEST.APP', 'C8FPS.APP'):
                    for repeat in range(args.repeat):
                        frame_start = len(port.frames)
                        port.begin_measurement()
                        launch(port, workload, 18)
                        port.end_measurement()
                        report_name = 'clock.txt' if workload == 'CLKTEST.APP' else 'result.txt'
                        payload = receive_file(port, DIRECTORY + '/' + report_name)
                        row = {k: int(v) for k, v in re.findall(r'(\w+)=(\d+)', payload.decode())}
                        if workload == 'CLKTEST.APP':
                            assert row['N'] == 4096 * 1024 and row['HASH'] == expected_hash, row
                            assert row['END'] == row['DUP'] == row['MATCH'] == 1, row
                            assert [row['HZ' + str(i)] for i in range(3)] == (
                                [(96,108,120)[profile]*500000, (96,108,120)[profile]*1000000, (96,108,120)[profile]*500000] if profile else [96000000] * 3), row
                        else:
                            row.update(chip_fields(payload))
                        row.update(stage=stage, profile=profile, workload=workload, repeat=repeat,
                            pongs=len(port.pings), pong_max_s=max(port.pings),
                            host_poll_max_s=port.maximum_host_poll_gap,
                            usb_frames=len(port.frames) - frame_start)
                        samples.append(row)
                        (out / f'{workload}-{repeat}.txt').write_bytes(payload)
                        if len(port.frames) > frame_start:
                            png(port.frames[-1], out / f'{workload}-{repeat}.png')
                        port.command('rm "' + DIRECTORY + '/' + report_name + '"')
                        (args.output / 'samples.json').write_text(json.dumps(samples, indent=2) + '\n')
                        print(stage, workload, repeat, json.dumps(row), flush=True)
                port.send(0x13)
                port.pump(.2)
                (out / 'terminal.bin').write_bytes(port.text)
                (out / 'crash.txt').write_text(port.command('crash show'))
        set_profile(args, args.final_profile)
        with connect(args.port, args.build) as port:
            launch(port, 'CLKTEST.APP', 18)
            final = receive_file(port, DIRECTORY + '/clock.txt')
            assert ('HZ1=' + str((96,108,120,144)[args.final_profile]*1000000)).encode() in final
            (args.output / 'final-clock.txt').write_bytes(final)
    finally:
        with connect(args.port, args.build) as port:
            for name in ('clock.txt', 'result.txt', 'select.txt', 'profile.txt', 'active.ch8',
                         'CLKSET.APP', 'CLKTEST.APP', 'C8FPS.APP'):
                port.command('rm "' + DIRECTORY + '/' + name + '"')
            port.command('rmdir "' + DIRECTORY + '"')
            health = {name: port.command(name, timeout=15)
                      for name in ('identity', 'df', 'crash show', 'mpu status', 'ls')}
            assert 'CRASH none' in health['crash show'], health
            assert 'FIRMWARE CRC state=valid' in health['df'], health
            assert 'layout=ok' in health['mpu status'], health
            (args.output / 'final-health.json').write_text(json.dumps(health, indent=2) + '\n')
    print('selected-frequency comparison complete; new firmware retained, selected profile', args.final_profile, flush=True)


if __name__ == '__main__':
    main()
