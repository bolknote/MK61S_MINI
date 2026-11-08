#!/usr/bin/env python3
"""selected-frequency Turochamp on Classic, same installed game and new resident.

Installs the repository game if /Games is absent, leaves it and the selected
new profile on the board. Does not restore old firmware, files or registers.
"""
import argparse
import json
import statistics
import time
from pathlib import Path
from hil_compute_clock import connect, identify, set_profile, DIRECTORY
from hil_c6_system_bootstrap import write_file, read_file
from hil_vm_cache_latency import PingPort, fast_control
from hil_turochamp_performance import Font, ROOT, encode, search, stop_game


def required_files():
    # Classic uses the compact font. Source modules stay byte-identical;
    # Pico-only font assets and documentation are outside this timed test.
    return [path for path in sorted((ROOT / 'programs/games/Turochamp').iterdir())
            if path.suffix.lower() in ('.tbi', '.m61') or path.name == 'Turochamp.FMK']


class TimedPingPort(PingPort):
    def __init__(self, path):
        self.frame_times = []
        super().__init__(path)

    def receive_packet(self, encoded):
        count = len(self.frames)
        super().receive_packet(encoded)
        if len(self.frames) > count:
            self.frame_times.append(time.monotonic())

    def __exit__(self, kind, value, traceback):
        try:
            if kind is not None and self.attached:
                stop_game(self)
                if self.measuring:
                    self.end_measurement()
                self.send(0x13)
                self.pump(.2)
        finally:
            super().__exit__(kind, value, traceback)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', default='/dev/cu.usbmodem2068336B47311')
    parser.add_argument('--build', required=True)
    parser.add_argument('--selector', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--profiles', type=int, nargs='+', default=[0, 1, 0], choices=range(3))
    parser.add_argument('--final-profile', type=int, default=0, choices=range(3))
    args = parser.parse_args()
    args.build_id, args.no_profile, args.reset_before = args.build, True, True
    args.game_dir, args.timeout = '/Games/Turochamp', 180
    args.output.mkdir(parents=True, exist_ok=False)
    font = Font((ROOT / 'programs/games/Turochamp/Turochamp.FMK').read_bytes())
    with connect(args.port, args.build) as port:
        fast_control(port)
        root = port.command('ls')
        assert DIRECTORY[1:] not in root
        if 'Games/' not in root:
            port.command('mkdir /Games')
            port.command('mkdir /Games/Turochamp')
            for path in required_files():
                data = path.read_bytes() if path.suffix.lower() in ('.fmk', '.wbmp') else encode(path.read_text())
                write_file(port, args.game_dir + '/' + path.name, data)
                read_file(port, args.game_dir + '/' + path.name, data)
        else:
            listing = port.command('ls "' + args.game_dir + '"').casefold()
            for path in required_files():
                data = path.read_bytes() if path.suffix.lower() in ('.fmk', '.wbmp') else encode(path.read_text())
                if ('\t' + path.name.casefold() + '\r') not in listing:
                    write_file(port, args.game_dir + '/' + path.name, data)
                read_file(port, args.game_dir + '/' + path.name, data)
        port.command('mkdir "' + DIRECTORY + '"')
        write_file(port, DIRECTORY + '/CLKSET.APP', args.selector.read_bytes())
        read_file(port, DIRECTORY + '/CLKSET.APP', args.selector.read_bytes())
    stages = []
    try:
        for stage_index, profile in enumerate(args.profiles):
            stage = f'{stage_index}-{(96,108,120)[profile]}MHz'
            set_profile(args, profile)
            stage_dir = args.output / stage
            stage_dir.mkdir()
            runs = []
            with TimedPingPort(args.port) as port:
                identify(port, args.build)
                port.attach()
                for repeat in range(3):
                    out = stage_dir / f'run-{repeat}'
                    out.mkdir()
                    port.begin_measurement()
                    row = search(port, font, args, repeat, out)
                    port.end_measurement()
                    row.update(pongs=len(port.pings), pong_max_s=max(port.pings),
                               host_poll_max_s=port.maximum_host_poll_gap)
                    runs.append(row)
                    (stage_dir / 'runs.json').write_text(json.dumps(runs, indent=2) + '\n')
                port.send(0x13)
                port.pump(.2)
                (stage_dir / 'terminal.bin').write_bytes(port.text)
            stages.append(dict(stage=stage, profile=profile, runs=runs,
                               warm_median_s=statistics.median(row['seconds'] for row in runs[1:])))
            (args.output / 'stages.json').write_text(json.dumps(stages, indent=2) + '\n')
        set_profile(args, args.final_profile)
    finally:
        with connect(args.port, args.build) as port:
            for name in ('select.txt', 'profile.txt', 'CLKSET.APP'):
                port.command('rm "' + DIRECTORY + '/' + name + '"')
            port.command('rmdir "' + DIRECTORY + '"')
            health = {name: port.command(name, timeout=15)
                      for name in ('identity', 'df', 'crash show', 'mpu status')}
            (args.output / 'final-health.json').write_text(json.dumps(health, indent=2) + '\n')
            assert 'CRASH none' in health['crash show'] and 'layout=ok' in health['mpu status']
    assert len(stages) == len(args.profiles)
    assert len({row['board_frame_sha256'] for stage in stages for row in stage['runs']}) == 1
    print('Chessselected-frequency, exact420-node/e2e3 board and strict USB PONG PASS', flush=True)


if __name__ == '__main__':
    main()
