#!/usr/bin/env python3
"""Test installed RACE with real USB keys and the host ROM as an oracle.

Resets the volatile game. No C6 or firmware writes. Two loop-back jumps are
temporarily redirected to a STOP in unused program RAM so each complete frame
can be compared, including collisions and the finish without a 45-minute race.
The ordinary loader is reopened on exit; all temporary RAM code is discarded.
"""
import argparse
from decimal import Decimal
import json
from pathlib import Path
import re
import subprocess
import sys
import time

from hil_c6_system_bootstrap import read_file
from hil_multi_device_identity import parse_identity
from hil_portable_apps import ScreenPort
from hil_portable_system_apps import png

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/race'))
from game import create_game

FIELDS = dict(lateral=4, phase=5, completed=6, lives=7, recovery=8, bend=9, rival=10)


def registers(port):
    report = port.command('reg', timeout=8)
    values = {int(index, 16): int(Decimal(value).scaleb(int(exponent)))
              for index, value, exponent in re.findall(
                  r'(?m)^R([0-9A-E]) =\s*([+-]?[0-9.]+)\s+([+-]?[0-9]{2})\r?$', report)}
    assert len(values) == 15, report
    return [values[i] for i in range(15)]


def command(port, text):
    reply = port.command(text, timeout=12)
    assert not any(error in reply for error in
                   ('failed!', 'Unknown command', 'BAD address!', 'Usage:')), reply
    return reply


def expect(port, expected, timeout=12):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last = registers(port)
        if last == expected:
            port.pump(.25)
            if registers(port) == expected:
                return
        port.pump(.1)
    raise AssertionError(f'registers differ: expected={expected}; actual={last}')


def oracle(runner, mode, fixture):
    inputs = ['angle ' + mode, 'start']
    inputs += [f'set {FIELDS[name]} {value}' for name, value in fixture.items()]
    inputs += ['angle ' + mode, 'next']
    result = subprocess.run([str(runner), str(ROOT / 'programs/games/RACE')],
                            input='\n'.join(inputs) + '\n', text=True,
                            capture_output=True, check=True, timeout=30)
    states = [json.loads(line) for line in result.stdout.splitlines()]
    assert len(states) == 3 and not any(s['error'] for s in states), result.stdout
    return states


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', required=True)
    parser.add_argument('--public-id', required=True)
    parser.add_argument('--build-id', required=True)
    parser.add_argument('--directory', default='/RACE')
    parser.add_argument('--runner', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--confirm-game-reset', action='store_true')
    args = parser.parse_args()
    if not args.confirm_game_reset:
        parser.error('pass --confirm-game-reset to replace the volatile game')
    args.output_dir.mkdir(parents=True, exist_ok=True)
    base = dict(lateral=0, phase=0, completed=0, lives=3, recovery=0, bend=0, rival=0)
    cases = [
        ('neutral', 'GRD', {}), ('left', 'P', {}), ('right', 'G', {}),
        ('wall', 'G', dict(lateral=12)),
        ('rival', 'GRD', dict(phase=32)),
        ('cooldown', 'G', dict(lateral=12, recovery=8)),
        ('finish', 'GRD', dict(lateral=9, phase=35, completed=19)),
        ('fatal-finish', 'G', dict(lateral=12, phase=35, completed=19, lives=1)),
    ]
    expected = {name: oracle(args.runner, mode, base | fixture)
                for name, mode, fixture in cases}
    banks, info = create_game().link()
    tick = info['labels']['tick']
    assert tick < 112
    # Only replace actual loop-back branches in executable modules, leaving
    # input, arithmetic, rendering, collision checks and result code intact.
    original_jump = bytes.fromhex('1f51') + bytes.fromhex(f'{tick:04d}')
    loop_backs = []
    for bank in (0, 19):
        for offset in range(len(banks[bank]) - 3):
            if banks[bank][offset:offset + 4] == original_jump:
                loop_backs.append(bank * 112 + offset)
    assert len(loop_backs) == 2, loop_backs
    sentinel = 31 * 112
    assert 31 not in banks
    stop_jump = '1F51' + f'{sentinel:04d}'
    measurements = []
    with ScreenPort(args.port, keyboard_layout=0) as port:
        identity = parse_identity(command(port, 'identity'))
        assert identity.public == args.public_id.upper(), identity
        assert identity.build == args.build_id.upper(), identity
        if identity.profile.startswith('classic-'):
            port.keyboard_layout = 1
        else:
            assert identity.profile.startswith('mini-'), identity
        keys = {'GRD': 9, 'P': 14, 'G': 4} if port.keyboard_layout == 0 else {
            'GRD': 31, 'P': 32, 'G': 30}
        for name in ('autoexec.m61', 'race.bin'):
            read_file(port, args.directory + '/' + name,
                      (ROOT / 'programs/games/RACE' / name).read_bytes())
        try:
            port.attach()
            for name, mode, fixture in cases:
                command(port, 'reinit')
                command(port, f'load 0000 "{args.directory}/race.bin"')
                command(port, 'run 0')
                expect(port, expected[name][0]['regs'][:15])
                command(port, f'hin {sentinel:04d} 50')
                for address in loop_backs:
                    command(port, f'hin {address:04d} {stop_jump}')
                # Initialization falls through into tick. Stop before that
                # first instruction, then restore it before fixture execution.
                command(port, f'hin {tick:04d} 50')
                command(port, f'run {info["labels"]["new_game"]}')
                expect(port, expected[name][1]['regs'][:15])
                command(port, f'hin {tick:04d} {banks[0][tick:tick + 4].hex()}')
                for field, value in (base | fixture).items():
                    command(port, f'R{FIELDS[field]:X}= {value}')
                port.key(keys[mode])
                started = time.monotonic()
                command(port, f'run {tick}')
                expect(port, expected[name][2]['regs'][:15])
                elapsed = time.monotonic() - started
                png(port.frames[-1], args.output_dir / (name + '.png'))
                row = dict(case=name, seconds_to_stable_state=round(elapsed, 3),
                           core_steps=expected[name][2]['steps'],
                           registers=expected[name][2]['regs'][:15])
                measurements.append(row)
                print(json.dumps(row), flush=True)
            assert 'CRASH none' in command(port, 'crash show')
        finally:
            # The normal loader clears our sentinel/branches and also restores
            # its OK binding. Dismiss the opening manual through the USB key.
            try:
                port.open(args.directory + '/autoexec.m61')
                port.pump(.5)
                port.close_app()
                expect(port, expected['neutral'][0]['regs'][:15])
            finally:
                port.send(0x13)
                port.attached = False
                port.pump(.3)
        result = dict(identity=identity.__dict__, cases=measurements,
                      ram_loop_stop_addresses=loop_backs, returned_to_title=True,
                      scope='Boundary fixtures; no uninterrupted full hardware race. '
                            'USB keys exercise runtime input, not physical GPIO scanning.')
        (args.output_dir / 'measurements.json').write_text(json.dumps(result, indent=2) + '\n')
    print('RACE HIL PASS; original loader reopened, physical screen restored.', flush=True)


if __name__ == '__main__':
    main()
