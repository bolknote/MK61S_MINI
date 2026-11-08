#!/usr/bin/env python3
"""Time the unchanged library 8 Queens calculator program on Classic at 144 MHz."""
import argparse
import hashlib
import json
import re
import time
from pathlib import Path
from hil_compute_clock import connect, set_profile, DIRECTORY
from hil_c6_system_bootstrap import write_file, read_file
from hil_vm_cache_latency import fast_control
from hil_turochamp_performance import ROOT


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--port', default='/dev/cu.usbmodem2068336B47311')
    ap.add_argument('--screen', action='store_true', help='Also attach USB Screen and check nonce PONG')
    ap.add_argument('--build', required=True)
    ap.add_argument('--selector', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    source = (ROOT / 'programs/library/8 Queens.m61').read_bytes()
    assert source.endswith(b'run\n')
    # Keep every calculator opcode intact; stack markers bracket only RUN.
    wrapper = source[:-4] + b'stk\nrun\nstk\n'
    with connect(args.port, args.build) as port:
        fast_control(port)
        assert DIRECTORY[1:] not in port.command('ls')
        port.command('mkdir "' + DIRECTORY + '"')
        for name, data in [('CLKSET.APP', args.selector.read_bytes()), ('queens.m61', wrapper)]:
            write_file(port, DIRECTORY + '/' + name, data)
            read_file(port, DIRECTORY + '/' + name, data)
    try:
        set_profile(args, 3)
        with connect(args.port, args.build) as port:
            if args.screen:
                port.attach()
                port.begin_measurement()
            started = time.monotonic()
            port.open(DIRECTORY + '/queens.m61')
            notice = started
            run_started = None
            while True:
                port.pump(.01)
                reply = bytes(port.text[port.open_text_start:])
                if run_started is None and re.search(rb'(?m)^IP =  +0\r?\n', reply):
                    run_started = time.monotonic()
                if len(re.findall(rb'(?m)^IP =  +\d+\r?\n', reply)) >= 2:
                    break
                assert time.monotonic() - started < 1200, '8 Queens timeout (20 min)'
                if time.monotonic() - notice >= 30:
                    (args.output / 'terminal-progress.bin').write_bytes(reply)
                    print('8 Queens 144 MHz running', round(time.monotonic()-started, 1), 's', flush=True)
                    notice = time.monotonic()
            elapsed = time.monotonic() - started
            finished = time.monotonic()
            if args.screen:
                port.end_measurement()
            (args.output / 'terminal.bin').write_bytes(reply)
            assert b'Open failed' not in reply and b'error' not in reply.lower(), reply
            assert run_started is not None, reply
            assert re.findall(rb'(?m)^IP =  +(\d+)\r?\n', reply) == [b'0', b'90'], reply
            run_seconds = finished - run_started
            result = dict(profile=3, mhz=144, source_sha256=hashlib.sha256(source).hexdigest(),
                          run_seconds=run_seconds, launch_seconds=elapsed, timing='host first stack marker to second stack marker', screen=args.screen,
                          pongs=len(port.pings), pong_max_s=max(port.pings, default=None),
                          host_poll_max_s=port.maximum_host_poll_gap if args.screen else None,
                          terminal=reply.decode('cp1251', 'replace'))
            (args.output / 'result.json').write_text(json.dumps(result, indent=2)+'\n')
            print(json.dumps(result), flush=True)
            if args.screen:
                port.send(0x13)
                port.pump(.2)
        set_profile(args, 0)
    finally:
        with connect(args.port, args.build) as port:
            for name in ('select.txt', 'profile.txt', 'CLKSET.APP', 'queens.m61'):
                port.command('rm "' + DIRECTORY + '/' + name + '"')
            port.command('rmdir "' + DIRECTORY + '"')
            health = {name: port.command(name, timeout=15) for name in ('identity', 'df', 'crash show', 'mpu status')}
            (args.output / 'health.json').write_text(json.dumps(health, indent=2)+'\n')
            assert 'CRASH none' in health['crash show'] and 'layout=ok' in health['mpu status']


if __name__ == '__main__':
    main()
