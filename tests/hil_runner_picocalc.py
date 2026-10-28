#!/usr/bin/env python3
"""Play the installed Runner through real USB Screen keys on one Pico UID.

No register fixtures, program patches, file writes or firmware installation.
Resets the volatile game; the caller preserves/restores the calculator and
firmware. Screenshots are received framebuffers, not reconstructed game art.
"""
import argparse
from decimal import Decimal
import json
from pathlib import Path
import re
import time
from hil_picocalc_software import calculator
from hil_picocalc_apps import AppsPort
from hil_portable_apps import cobs_decode
from hil_portable_system_apps import png

DIGITS = (20, 21, 16, 11, 22, 17, 12, 23, 18, 13)
OK, ESC = 29, 39
LADDERS = {1: (3, 9), 2: (3, 7, 9, 11), 3: (7, 11)}


class GamePort(AppsPort):
    def __init__(self, path):
        super().__init__(path, keyboard_layout=0)
        self.accept_frames = False

    def receive_packet(self, encoded):
        # A desktop client can leave already queued pages after DETACH.
        # Discard that incomplete session before our own CAPS/FRAME_BEGIN.
        kind = cobs_decode(encoded)[3]
        if not self.accept_frames and kind in (0x10, 0x12, 0x20, 0x21, 0x22):
            return
        if kind in (0x21, 0x22) and not hasattr(self, 'frame_id'):
            return
        super().receive_packet(encoded)

    def attach_waiting(self, timeout=3):
        self.accept_frames = True
        super().attach_waiting(timeout)


def registers(port):
    text = port.command('reg', timeout=10)
    result = {int(r, 16): int(Decimal(n).scaleb(int(e)))
              for r, n, e in re.findall(r'(?m)^R([0-9A-F]) =\s*([+\-]?[0-9.]+)\s+([+\-]?[0-9]{2})\r?$', text)}
    assert len(result) in (15, 16), text
    return [result[i] for i in range(len(result))]


def complete_frame(state):
    column, floor = state[4:6]
    if not (1 <= column <= 12 and 1 <= floor <= 3 and state[14] == 9999):
        return False
    masks = [126 if x in LADDERS[floor] else 8 for x in range(1, 13)]
    masks[column - 1] = 107
    hole = state[11]
    if hole and (hole - 1) // 12 + 1 == floor:
        masks[(hole - 1) % 12] = 0
    return state[:4] == [sum(masks[base + i] << (i * 8) for i in range(3))
                         for base in (0, 3, 6, 9)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', required=True)
    parser.add_argument('--uid', required=True)
    parser.add_argument('--build-id', required=True)
    parser.add_argument('--directory', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--confirm-game-reset', action='store_true', required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    p = GamePort(args.port)
    cases = []
    started = time.monotonic()

    def tap(key):
        raw = DIGITS[key] if key <= 9 else OK if key == 0x13 else ESC
        p.send(0x30, bytes((raw, 1)))
        p.send(0x30, bytes((raw, 0)))
        p.pump(.03)

    def sample(name, column, floor, hole=None, timeout=30):
        begin = time.monotonic()
        progress = begin
        last = None
        while time.monotonic() - begin < timeout:
            last = registers(p)
            if last[4:6] == [column, floor] and (hole is None or last[11] == hole) and complete_frame(last):
                p.pump(.25)
                assert p.frames
                png(p.frames[-1], args.output / (name + '.png'))
                record = dict(case=name, seconds=round(time.monotonic() - begin, 3),
                              column=column, floor=floor, hole=last[11], timer=last[13], registers=last)
                cases.append(record)
                print(json.dumps(record), flush=True)
                return last
            if time.monotonic() - progress >= 5:
                print(f'Waiting {name}: column={last[4]} floor={last[5]} hole={last[11]} timer={last[13]}', flush=True)
                progress = time.monotonic()
            p.pump(.15)
        raise AssertionError((name, column, floor, hole, last))

    try:
        p.drain()
        p.commands()
        assert 'UID=' + args.uid in p.command('identity')
        initial = p.expect('BUILD=' + args.build_id.upper(), 'FIRMWARE_CRC=valid')
        calculator(p)
        assert 'ERROR' not in p.command('reinit')
        p.native_display = True
        p.attach()
        p.open(args.directory.rstrip('/') + '/autoexec.m61')
        p.pump(.5)
        p.expect('SERVICE=VIEWER')
        p.key(39)
        p.expect('M61_ACTIVE=1', 'RUN=1', 'SERVICE=CLOSED', timeout=20)
        sample('start', 1, 2, 0)
        tap(6); sample('tap-right', 2, 2)
        tap(6); sample('ladder-entry', 3, 2)
        tap(2); sample('lower-floor', 3, 1)
        tap(8); sample('middle-floor', 3, 2)
        for column in range(4, 8):
            tap(6); sample('walk-' + str(column), column, 2)
        tap(8); sample('upper-floor', 7, 3)
        tap(9); sample('burn-right', 7, 3, 32)
        tap(6); sample('fall', 8, 2, 32)
        sample('restored', 8, 2, 0, timeout=150)
        tap(0); sample('restart', 1, 2, 0)
        p.send(0x30, bytes((DIGITS[6], 1)))
        p.pump(5)
        held = registers(p)
        p.send(0x30, bytes((DIGITS[6], 0)))
        p.pump(.4)
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            released = registers(p)
            if released[7] == 0 and complete_frame(released):
                break
            p.pump(.15)
        else:
            raise AssertionError(('release not consumed', released))
        assert held[4] > 1, held
        sample('held-right', released[4], 2)
        p.pump(5)
        after = registers(p)
        assert after[4] == released[4] and after[7] == 0, (released, after)
        cases.append(dict(case='hold-release', columns_in_five_seconds=held[4] - 1,
                          held_registers=held, released_registers=released))
        tap(4); sample('tap-left', released[4] - 1, 2)
        position = registers(p)[4:6]
        tap(0x13); p.expect('SERVICE=VIEWER')
        p.pump(.2); png(p.frames[-1], args.output / 'help.png')
        p.key(39); p.expect('SERVICE=CLOSED', 'M61_ACTIVE=1')
        sample('help-return', *position)
        tap(0x14)
        final = p.expect('SERVICE=CLOSED', 'M61_ACTIVE=0', 'RUN=0', timeout=30)
        assert all(value == 0 for value in registers(p))
        p.pump(.2); png(p.frames[-1], args.output / 'exit.png')
        result = dict(passed=True, uid=args.uid, build_id=args.build_id,
                      elapsed_seconds=round(time.monotonic() - started, 3),
                      cases=cases, initial=initial, final=final,
                      scope='Physical PicoCalc; ordinary native USB Screen key events; no game-state fixtures. '
                            'Per-action latency includes serial observation and framebuffer delivery.')
        (args.output / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
        print('Runner virtual-screen hardware checks passed', flush=True)
    finally:
        if not (args.output / 'result.json').is_file():
            (args.output / 'result.json').write_text(json.dumps(dict(
                passed=False, uid=args.uid, build_id=args.build_id,
                elapsed_seconds=round(time.monotonic()-started,3), cases=cases),
                ensure_ascii=False, indent=2)+'\n')
        if p.attached:
            p.send(0x31); p.send(0x13); p.attached = False; p.pump(.1)
        (args.output / 'transcript.txt').write_text(p.text.decode('utf-8', 'replace'))
        p.__exit__(None, None, None)


if __name__ == '__main__':
    main()
