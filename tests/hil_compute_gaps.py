#!/usr/bin/env python3
"""Finite actual keyboard-row/USB gaps on the diagnostic Classic source copy."""
import argparse
import json
import re
from pathlib import Path
from hil_compute_clock import connect, launch, set_profile, DIRECTORY
from hil_c6_system_bootstrap import write_file, read_file
from hil_chip8_fps import receive_file, fields as chip_fields


def gap_fields(payload):
    row = {key: int(value) for key, value in re.findall(r'(\w+)=(\d+)', payload.decode())}
    assert payload.startswith(b'GAPS V=1 ') and all(row[f'N{i}'] > 0 for i in range(8)), row
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', default='/dev/cu.usbmodem2068336B47311')
    parser.add_argument('--build', required=True)
    parser.add_argument('--selector', type=Path, required=True)
    parser.add_argument('--gap-app', type=Path, required=True)
    parser.add_argument('--chip8', type=Path, required=True)
    parser.add_argument('--rom', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--profiles', type=int, nargs='+', default=[0, 1, 0], choices=range(3))
    parser.add_argument('--final-profile', type=int, default=0, choices=range(3))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    rows = []
    with connect(args.port, args.build) as port:
        assert DIRECTORY[1:] not in port.command('ls')
        port.command('mkdir "' + DIRECTORY + '"')
        for name, path in (('CLKSET.APP', args.selector), ('GAPTEST.APP', args.gap_app),
                           ('C8FPS.APP', args.chip8), ('active.ch8', args.rom)):
            write_file(port, DIRECTORY + '/' + name, path.read_bytes())
            read_file(port, DIRECTORY + '/' + name, path.read_bytes())
    try:
        for stage_index, profile in enumerate(args.profiles):
            stage = f'{stage_index}-{(96,108,120)[profile]}MHz'
            set_profile(args, profile)
            with connect(args.port, args.build) as port:
                port.attach()
                for app in ('GAPTEST.APP', 'C8FPS.APP'):
                    port.begin_measurement()
                    launch(port, app, 18)
                    port.end_measurement()
                    files = ('low0', 'high', 'low1') if app == 'GAPTEST.APP' else ('chipgap',)
                    for name in files:
                        payload = receive_file(port, DIRECTORY + '/' + name + '.txt')
                        row = gap_fields(payload)
                        row.update(stage=stage, profile=profile, workload=app, section=name,
                            pongs=len(port.pings), pong_max_s=max(port.pings),
                            host_poll_max_s=port.maximum_host_poll_gap)
                        rows.append(row)
                        (args.output / (stage + '-' + name + '.txt')).write_bytes(payload)
                        (args.output / 'samples.json').write_text(json.dumps(rows, indent=2) + '\n')
                        print(stage, app, name, 'row max us', max(row[f'M{i}'] for i in range(2, 7)),
                              'USB max us', row['M7'], 'PONG max ms', row['pong_max_s'] * 1000, flush=True)
                        port.command('rm "' + DIRECTORY + '/' + name + '.txt"')
                    if app == 'C8FPS.APP':
                        result = chip_fields(receive_file(port, DIRECTORY + '/result.txt'))
                        (args.output / (stage + '-chip8.json')).write_text(json.dumps(result, indent=2) + '\n')
                        port.command('rm "' + DIRECTORY + '/result.txt"')
                port.send(0x13)
                port.pump(.2)
        set_profile(args, args.final_profile)
    finally:
        with connect(args.port, args.build) as port:
            for name in ('low0.txt', 'low1.txt', 'high.txt', 'chipgap.txt', 'result.txt', 'select.txt',
                         'profile.txt', 'CLKSET.APP', 'GAPTEST.APP', 'C8FPS.APP', 'active.ch8'):
                port.command('rm "' + DIRECTORY + '/' + name + '"')
            port.command('rmdir "' + DIRECTORY + '"')
            health = {name: port.command(name) for name in ('identity', 'crash show', 'df')}
            (args.output / 'final-health.json').write_text(json.dumps(health, indent=2) + '\n')
    assert len(rows) == 4 * len(args.profiles) and all(row[f'M{i}'] <= 30000 for row in rows for i in range(8)), rows
    print('Actual keyboard poll/sample/five rows and USB: all gaps <=30ms, strict PONG <1s PASS', flush=True)


if __name__ == '__main__':
    main()
