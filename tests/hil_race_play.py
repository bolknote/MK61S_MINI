#!/usr/bin/env python3
"""Drive RACE on Mini with an explicit 50 ms control window before each tick.

A temporary M61 launcher installs readonly observation traps. They emit register
snapshots and wait 50 ms at the local tick address, allowing real USB steering
keys to arrive. Local addresses can also match instructions in other banks.
The controller follows the published guide. Physics and all game
state remain ROM bytecode; no register fixtures. The temporary launcher is
removed afterwards. This is not an uninstrumented frame-rate measurement.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import statistics
from decimal import Decimal
import sys
import time

from hil_c6_system_bootstrap import read_file, write_file
from hil_multi_device_identity import parse_identity
from hil_portable_apps import ScreenPort
from hil_portable_system_apps import png
from hil_race_game import registers, command
from hil_rtc_alarm import Port, warm_reset
from hil_usb_disk_transaction import listing_entries
from hil_c6_programs_deploy import payload_for

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/race'))
from game import packed, screen, SECTION_FRAMES, create_game


def load_title(port, directory):
    port.open(directory + '/autoexec.m61')
    port.pump(.5)
    port.close_app()
    words = packed(screen('rACE L3 20СП'))
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        if registers(port)[:4] == words:
            port.pump(.3)
            return
        port.pump(.1)
    raise AssertionError('normal loader did not return to the title')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', required=True)
    parser.add_argument('--public-id', required=True)
    parser.add_argument('--build-id', required=True)
    parser.add_argument('--directory', default='/RACE')
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--confirm-game-reset', action='store_true')
    args = parser.parse_args()
    if not args.confirm_game_reset:
        parser.error('pass --confirm-game-reset to reset the current game')
    args.output_dir.mkdir(parents=True, exist_ok=True)
    timeline = []
    keys = []
    profile = ''
    _, info = create_game().link()
    tick = info['labels']['tick'] % 112
    stops = [info['labels'][name] % 112 for name in ('finish_stop', 'defeat_stop')]
    assert len(set([tick, *stops])) == 3
    temporary = args.directory + '/_speedtest.m61'
    loader = (ROOT / 'programs/games/RACE/autoexec.m61').read_text().replace('open? manual.md\n', '', 1)
    loader = loader.replace('load 0000 race.bin\n',
                            f'trap {tick} run :sample\n' +
                            ''.join(f'trap {address} run :observe\n' for address in stops) +
                            'load 0000 race.bin\n')
    loader += '\n:sample\nreg\nwait 50\nret\n\n:observe\nreg\nret\n'
    # Release the previous USB Screen overlay before the C9 mutation.
    raw = Port(args.port, require_echo=True)
    temporary_exists = False
    try:
        identity = parse_identity(raw.command('identity'))
        assert identity.public == args.public_id.upper() and identity.build == args.build_id.upper(), identity
        assert identity.profile == 'mini-v3-a00', identity
        raw, path, _ = warm_reset(raw, args.port, identity.public)
        assert parse_identity(raw.command('identity')) == identity
        entries = listing_entries(raw.command('ls ' + args.directory))
        assert not any(e.split('\t')[-1].lower() == '_speedtest.m61' for e in entries)
        write_file(raw, args.directory + '/manual.md', payload_for(ROOT / 'programs/games/RACE/manual.md'))
        write_file(raw, temporary, loader.encode('ascii'))
        temporary_exists = True
        read_file(raw, temporary, loader.encode('ascii'))
    finally:
        raw.close()
    block_pattern = re.compile(rb'R0 = [\s\S]*?IP: (\d+)\r?\n')
    try:
        with ScreenPort(path, keyboard_layout=0) as port:
            for name in ('race.bin', 'autoexec.m61'):
                read_file(port, args.directory + '/' + name,
                          (ROOT / 'programs/games/RACE' / name).read_bytes())
            try:
                port.attach()
                command(port, 'open "' + temporary + '"')
                deadline = time.monotonic() + 8
                while registers(port)[:4] != packed(screen('rACE L3 20СП')):
                    assert time.monotonic() < deadline, 'test launcher did not reach title'
                port.key(9)
                command(port, 'prof start')
                text_position = len(port.text)
                started = time.monotonic()
                port.key(30)
                last_key = 9
                last_section = -1
                final = None
                samples = 0
                deadline = started + 240
                while time.monotonic() < deadline:
                    port.pump(.01)
                    match = block_pattern.search(port.text, text_position)
                    if match is None:
                        continue
                    text_position = match.end()
                    report = match.group().decode('cp1251')
                    values = {int(index, 16): int(Decimal(value).scaleb(int(exponent)))
                              for index, value, exponent in re.findall(
                                  r'(?m)^R([0-9A-E]) =\s*([+-]?[0-9.]+)\s+([+-]?[0-9]{2})\r?$', report)}
                    assert len(values) == 15, report
                    state = [values[i] for i in range(15)]
                    lateral, phase, completed, lives = state[4:8]
                    if lives == 0 and state[:2] == packed(screen('CrASH'))[:2]:
                        raise AssertionError(f'guided race crashed: {state}')
                    if completed == 20 and 1 <= lives <= 3 and state[:4] == packed(screen(f'FInISH 20 L{lives}')):
                        final = state
                        break
                    if int(match.group(1)) != tick or not (1 <= lives <= 3 and 0 <= completed < 20):
                        continue
                    samples += 1
                    row = dict(seconds=round(time.monotonic() - started, 4),
                               completed=completed, phase=phase, lateral=lateral,
                               rival=state[10], lives=lives)
                    timeline.append(row)
                    if completed != last_section:
                        print(json.dumps(row), flush=True)
                        last_section = completed
                    masks = [(word >> shift) & 255 for word in state[:4] for shift in (0, 8, 16)]
                    points = [i for i, mask in enumerate(masks) if mask & 128]
                    assert len(points) <= 1, masks
                    direction = points[0] - 5 if points else 0
                    desired = 9 if direction == 0 else 4 if direction > 0 else 14
                    if desired != last_key:
                        port.key(desired)
                        keys.append(dict(seconds=round(time.monotonic() - started, 4), key=desired))
                        last_key = desired
                assert final is not None, ('race did not finish', timeline[-5:], port.text[-400:])
                duration = time.monotonic() - started
                port.pump(.5)
                png(port.frames[-1], args.output_dir / 'finish.png')
                profile = command(port, 'prof stop')
                assert 'KBD overflow=0' in profile, profile
                assert 'CRASH none' in command(port, 'crash show')
                # Context save/restore redraws are not game frames. Deduplicate
                # local-address trap aliases by the logical section/phase pair.
                observations = []
                for row in timeline:
                    if not observations or (row['completed'], row['phase']) != (
                            observations[-1]['completed'], observations[-1]['phase']):
                        observations.append(row)
                assert len(observations) == 20 * SECTION_FRAMES, observations
                intervals = [b['seconds'] - a['seconds']
                             for a, b in zip(observations, observations[1:])]
                result = dict(identity=identity.__dict__, seconds_to_finish=round(duration, 3),
                              lives_remaining=final[7], completed=final[6],
                              logical_frames=20 * SECTION_FRAMES, control_samples=samples,
                              distinct_frame_observations=len(observations), control_wait_ms=50,
                              observed_tick_interval_seconds=dict(
                                  median=round(statistics.median(intervals), 4),
                                  minimum=round(min(intervals), 4),
                                  maximum=round(max(intervals), 4)),
                              registers=final, timeline=timeline, key_events=keys,
                              race_bin_sha256=hashlib.sha256((ROOT / 'programs/games/RACE/race.bin').read_bytes()).hexdigest(),
                              controller='Readonly M61 traps emit snapshots and wait 50 ms at the local tick address. '
                                         'Local-address aliases can produce extra snapshots. '
                                         'Host follows the published guide using binary USB keys. '
                                         'No register fixtures or host physics. Timing includes observation hooks.')
                (args.output_dir / 'measurements.json').write_text(json.dumps(result, indent=2) + '\n')
                (args.output_dir / 'profile.txt').write_text(profile)
                print(json.dumps({key: result[key] for key in
                                  ('seconds_to_finish', 'lives_remaining', 'observed_tick_interval_seconds')}), flush=True)
            except BaseException:
                (args.output_dir / 'failed-run.json').write_text(json.dumps(dict(timeline=timeline, key_events=keys), indent=2) + '\n')
                if port.frames:
                    png(port.frames[-1], args.output_dir / 'failed-run.png')
                raise
            finally:
                try:
                    load_title(port, args.directory)
                    port.key(9)
                finally:
                    port.send(0x13)
                    port.attached = False
                    port.pump(.3)
    finally:
        if temporary_exists:
            raw = Port(path, require_echo=True)
            try:
                raw, path, _ = warm_reset(raw, path, identity.public)
                reply = raw.command('rm "' + temporary + '"')
                assert 'Removed 1 entry.' in reply, reply
                temporary_exists = False
            finally:
                raw.close()
            # Restore the normal title after freeing the C9 upload workspace.
            with ScreenPort(path, keyboard_layout=0) as port:
                try:
                    port.attach()
                    load_title(port, args.directory)
                    port.key(9)
                finally:
                    port.send(0x13)
                    port.attached = False
                    port.pump(.3)
    result.update(temporary_launcher_removed=True, normal_title_restored=True)
    (args.output_dir / 'measurements.json').write_text(json.dumps(result, indent=2) + '\n')
    print('RACE hardware guide test PASS; temporary launcher removed, original title restored.', flush=True)


if __name__ == '__main__':
    main()
