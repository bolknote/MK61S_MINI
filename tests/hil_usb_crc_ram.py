#!/usr/bin/env python3
"""Same-ELF driver/clock matrix; boost results stay in RAM, no boost FS writes."""
import argparse
import json
import time
from pathlib import Path
import hil_compute_clock as clock
from hil_usb_crc_transport import CapturePort
from hil_c6_system_bootstrap import write_file, read_file
from hil_vm_cache_latency import fast_control


def exchange(port, index, tag):
    port.next_measured_ping = float('inf')
    deadline = time.monotonic()+1
    while port.automatic_pending:
        assert time.monotonic() < deadline
        port.pump(.005)
    start = len(port.responses)
    port.send(0x14, bytes((index, tag)))
    while time.monotonic() < deadline:
        port.pump(.003)
        if len(port.responses) > start:
            value = port.responses[-1]
            assert value[:2] == (0x55435231, index), value
            return value
    raise TimeoutError(('diagnostic response', index, tag))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--port', default='/dev/cu.usbmodem2068336B47311')
    ap.add_argument('--build', required=True)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--artifacts', type=Path, required=True)
    ap.add_argument('--app', type=Path, required=True)
    ap.add_argument('--profiles', type=int, nargs='+', default=[0, 2, 3, 0], choices=range(4))
    ap.add_argument('--modes', type=int, nargs='+', default=[0, 32, 16, 1, 33, 2, 3, 35, 4, 5, 6, 7, 8],
                    help='Diagnostic mode bits; explicit mode9 violates FIFO ordering and may require USB reset')
    ap.add_argument('--repeat', type=int, default=1)
    ap.add_argument('--no-screen', action='store_true')
    args = ap.parse_args()
    assert 1 <= args.repeat <= 10
    assert all(0 <= m <= 255 and (m & 15) <= 9 and (m & 0x30) != 0x30 for m in args.modes)
    assert all(bool(m & 0xC0) == args.no_screen for m in args.modes), 'quiet flags and --no-screen must agree'
    args.output.mkdir(parents=True, exist_ok=False)
    clock.PingPort = CapturePort
    l = args.artifacts
    files = {'CLKSET.APP': l/'fixed-ui/CLKSET.APP',
             'CRCWORK.APP': args.app}
    rows = []
    attached = False
    with clock.connect(args.port, args.build) as port:
        fast_control(port)
        assert clock.DIRECTORY[1:] not in port.command('ls')
        port.command('mkdir '+clock.DIRECTORY)
        for name, path in files.items():
            data = path.read_bytes()
            write_file(port, clock.DIRECTORY+'/'+name, data)
            read_file(port, clock.DIRECTORY+'/'+name, data)
    try:
        for stage, profile in enumerate(args.profiles):
            clock.set_profile(args, profile)
            with clock.connect(args.port, args.build) as port:
                port.attach()
                attached = True
                for mode in args.modes:
                    for repeat in range(args.repeat):
                        bad_start = len(port.bad_packets)
                        row = dict(stage=stage, profile=profile, mode=mode, repeat=repeat)
                        try:
                            exchange(port, mode, 0xD3)
                            if args.no_screen:
                                assert mode&0xC0, 'quiet mode required for isolated no-screen run'
                                port.send(0x13)
                                port.pump(.1)
                                port.attached = False
                                attached = False
                            else:port.begin_measurement()
                            start = time.monotonic()
                            clock.launch(port, 'CRCWORK.APP', 30)
                            if args.no_screen:
                                port.attach()
                                attached = True
                            else:port.end_measurement()
                            row.update(seconds=time.monotonic()-start,
                                       pongs=len(port.pings), pong_max_s=max(port.pings,default=None),
                                       host_poll_max_s=port.maximum_host_poll_gap)
                        except (AssertionError, TimeoutError) as error:
                            row['error'] = repr(error)
                            # A diagnostic negative control can corrupt its
                            # own ACK. Record it, return to safe low/default TX.
                            port.measuring = False
                            port.outstanding = None
                        exchange(port, 0, 0xD3)
                        values = [exchange(port, i, 0xD4)[2] for i in range(70)]
                        row['results'] = values
                        row['errors'] = port.bad_packets[bad_start:]
                        high = (96,108,120,144)[profile]*1000000
                        low = high//2 if profile else high
                        expected = [high]*3 if mode & 32 else [low]*3 if mode & 16 else [low,high,low]
                        row['hashes_pass'] = all(values[20*i] == 3289793925 for i in range(3))
                        row['clocks_pass'] = [values[20*i+1] for i in range(3)] == expected
                        row['ram_copy_errors'] = values[60]
                        row['format_errors'] = values[62]
                        row['critical_format_errors'] = values[64:70]
                        row['critical_cycles'] = [exchange(port, i, 0xD4)[2] for i in (100,101)]
                        if values[62] not in (0, 0xFFFFFFFF):
                            row['format_failure'] = [exchange(port, i, 0xD4)[2] for i in range(112,116)]
                        row['gap_limit_pass'] = all(values[20*p+4+i] <= 30000 for p in range(3) for i in range(8))
                        row['pass'] = not row.get('error') and not row['errors'] and row['hashes_pass'] and row['clocks_pass'] and values[60] == values[62] == 0 and values[63] == 0x31415926 and values[61] == mode and row['gap_limit_pass'] and all(v==0 for v in values[64:70])
                        rows.append(row)
                        (args.output/'rows.json').write_text(json.dumps(rows, indent=2)+'\n')
                        print('profile', profile, 'mode', mode, 'repeat', repeat,
                              'badCRC', len(row['errors']), 'copyErrors', values[60], 'formatErrors', values[62],
                              'HZ', [values[20*i+1] for i in range(3)], 'PASS', row['pass'], flush=True)
                port.send(0x13)
                port.pump(.2)
                attached = False
                (args.output/f'{stage}-{profile}-terminal.bin').write_bytes(port.text)
        clock.set_profile(args, 0)
    finally:
        if attached:
            from hil_portable_apps import ScreenPort
            with ScreenPort(args.port) as port:
                port.send(0x13)
                time.sleep(.15)
                port.drain()
        with clock.connect(args.port, args.build) as port:
            for name in (*files, 'profile.txt', 'select.txt'):
                port.command('rm "'+clock.DIRECTORY+'/'+name+'"')
            port.command('rmdir '+clock.DIRECTORY)
            health = {n: port.command(n, timeout=15) for n in ('identity', 'df', 'crash show', 'mpu status')}
            (args.output/'health.json').write_text(json.dumps(health, indent=2)+'\n')
            assert 'CRASH none' in health['crash show'] and 'layout=ok' in health['mpu status']

    print('Recorded rows:',len(rows),'failed rows:',sum(not r['pass'] for r in rows),flush=True)


if __name__ == '__main__':
    main()
