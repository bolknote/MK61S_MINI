#!/usr/bin/env python3
"""Play an installed Runner on Classic through ordinary USB Screen events.

Start from the calculator, with the desktop serial client disconnected. No
firmware, files, registers or program bytes are patched. Volatile game reset
is explicit; the ordinary launcher is returned to its start unless requested otherwise.
The same benchmark can exercise the original and optimized game packages.
"""
import argparse
from decimal import Decimal
import json
from pathlib import Path
import re
import time

from hil_multi_device_identity import parse_identity
from hil_portable_apps import ScreenPort, cobs_decode
from hil_portable_system_apps import png

DIGITS = (4, 9, 8, 7, 14, 13, 12, 19, 18, 17)
LADDERS = {1: (3, 9), 2: (3, 7, 9, 11), 3: (7, 11)}


class GamePort(ScreenPort):
    def __init__(self, path):
        super().__init__(path, keyboard_layout=1)
        self.accept_frames = False

    def receive_packet(self, encoded):
        try:
            kind = cobs_decode(encoded)[3]
        except AssertionError:
            if not self.accept_frames:
                return
            raise
        if not self.accept_frames and kind in (0x10, 0x12, 0x20, 0x21, 0x22):
            return
        if kind in (0x21, 0x22) and not hasattr(self, 'frame_id'):
            return
        super().receive_packet(encoded)

    def attach_waiting(self, timeout=3):
        self.accept_frames = True
        super().attach_waiting(timeout)


def registers(port):
    report = port.command('reg', timeout=10)
    values = {int(r, 16): int(Decimal(n).scaleb(int(e))) for r, n, e in re.findall(
        r'(?m)^R([0-9A-F]) =\s*([+\-]?[0-9.]+)\s+([+\-]?[0-9]{2})\r?$', report)}
    assert len(values) in (15, 16), report
    return [values[i] for i in range(len(values))]


def hole_cell(state):
    pointer = state[11]
    if pointer <= 36:
        return pointer  # Original Runner package, for hardware A/B checks.
    index, remainder = divmod(pointer-16*112-12, 28)
    assert remainder == 0 and 0 <= index < 36, state
    return index+1


def complete_frame(state):
    column, floor = state[4:6]
    if not (1 <= column <= 12 and 1 <= floor <= 3):
        return False
    masks = [107 if x == column else 126 if x in LADDERS[floor] else 8
             for x in range(1, 13)]
    hole = hole_cell(state)
    if hole and (hole - 1) // 12 + 1 == floor:
        masks[(hole - 1) % 12] = 0
    words = [sum(masks[base+i] << (8*i) for i in range(3)) for base in (0,3,6,9)]
    if state[3] in (1,2) and state[14] == 16*112+(floor-1)*336-27:
        # R0/R3 are input scratch after atomic publication. Phase 1/2 is
        # written only after the complete frame; phase 3 excludes calculation.
        return state[3] in (1,2) and state[1:3] == words[1:3]
    return state[:4] == words


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', required=True)
    parser.add_argument('--public-id', required=True)
    parser.add_argument('--build-id', required=True)
    parser.add_argument('--directory', default='/games/Runner')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--benchmark-only', action='store_true')
    parser.add_argument('--timer-ms', type=int, help='also check monotonic expiration and manual pause')
    parser.add_argument('--leave-calculator', action='store_true')
    parser.add_argument('--confirm-game-reset', action='store_true', required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    cases = []
    started = time.monotonic()
    with GamePort(args.port) as p:
        identity = parse_identity(p.command('identity'))
        assert identity.public == args.public_id.upper(), identity
        assert identity.build == args.build_id.upper(), identity
        assert identity.profile.startswith('classic-'), identity

        def tap(digit):
            p.send(0x30, bytes((DIGITS[digit], 1)))
            p.send(0x30, bytes((DIGITS[digit], 0)))
            p.pump(.03)

        def sample(name, column, floor, hole=None, timeout=20):
            begin = time.monotonic()
            progress = begin
            while time.monotonic()-begin < timeout:
                state = registers(p)
                if state[4:6] == [column, floor] and (hole is None or hole_cell(state) == hole) and complete_frame(state):
                    p.pump(.15)
                    png(p.frames[-1], args.output / (name+'.png'))
                    row = dict(case=name, seconds=round(time.monotonic()-begin, 3), registers=state)
                    cases.append(row)
                    print(json.dumps(row), flush=True)
                    return state
                if time.monotonic()-progress > 5:
                    print('Waiting', name, 'position/hole/timer=', state[4:6]+[hole_cell(state), state[13]], flush=True)
                    progress = time.monotonic()
                p.pump(.05)
            raise AssertionError((name, column, floor, hole, state))

        try:
            assert 'Calculator reinitialized.' in p.command('reinit')
            p.attach()
            p.open(args.directory.rstrip('/')+'/autoexec.m61'); p.pump(.8)
            opening_manual = p.frames[-1]
            png(opening_manual, args.output/'manual.png')
            p.key(39)
            sample('start', 1, 2, 0)
            for column in range(2, 6):
                tap(6); sample('bench-walk-'+str(column), column, 2)
            p.send(0x30, bytes((DIGITS[6], 1))); p.pump(3)
            held = registers(p)
            p.send(0x30, bytes((DIGITS[6], 0))); p.pump(.1)
            deadline = time.monotonic()+15
            while time.monotonic() < deadline:
                released = registers(p)
                if released[7] == 0 and complete_frame(released):
                    break
                p.pump(.1)
            else:
                raise AssertionError(('release not consumed', released))
            assert held[4] > 5, held
            p.pump(2)
            assert registers(p)[4:6] == released[4:6], 'Movement stuck after release'
            row = dict(case='bench-hold', seconds=3, columns=held[4]-5,
                       columns_after_release=released[4]-5, released_registers=released)
            cases.append(row); print(json.dumps(row), flush=True)
            tap(0); sample('bench-restart', 1, 2, 0)
            tap(9); state = sample('bench-burn', 1, 2, 14)
            remaining = state[13]
            sample('bench-restored', 1, 2, 0, timeout=100)
            if args.timer_ms:
                cases[-1]['hole_state_at_start'] = remaining
                assert abs(cases[-1]['seconds']-args.timer_ms/1000) < .7, cases[-1]
                for digit, label, flag in ((6, 'moving', 7), (4, 'blocked', 6)):
                    tap(9); sample('timer-'+label+'-burn', 1, 2, 14)
                    born = time.monotonic()
                    p.send(0x30, bytes((DIGITS[digit], 1)))
                    deadline = born + args.timer_ms/1000 + 2
                    while time.monotonic() < deadline:
                        state = registers(p)
                        if not hole_cell(state) and complete_frame(state): break
                        p.pump(.04)
                    else:
                        raise AssertionError(('timer extended by '+label, state))
                    elapsed = time.monotonic()-born
                    assert args.timer_ms/1000-.5 <= elapsed <= args.timer_ms/1000+1.5, elapsed
                    if label == 'blocked': assert state[4:6] == [1, 2], state
                    p.send(0x30, bytes((DIGITS[digit], 0))); p.pump(.1)
                    deadline = time.monotonic()+10
                    while time.monotonic() < deadline:
                        released = registers(p)
                        if released[flag] == 0 and complete_frame(released): break
                        p.pump(.04)
                    assert released[flag] == 0 and complete_frame(released), released
                    cases.append(dict(case='timer-'+label+'-restored', seconds=round(elapsed,3),
                                      registers=state, released_registers=released))
                    print(json.dumps(cases[-1]), flush=True)
                    tap(0); sample('timer-'+label+'-reset', 1, 2, 0)
                tap(9); sample('timer-help-burn', 1, 2, 14)
                p.pump(1.8)
                frame_start = len(p.frames); p.key(37)
                deadline = time.monotonic()+10
                while opening_manual not in p.frames[frame_start:] and time.monotonic() < deadline:
                    p.pump(.04)
                assert opening_manual in p.frames[frame_start:], 'Timed manual did not open'
                p.pump(5)
                assert hole_cell(registers(p)) == 14, 'Timer ran through the manual'
                p.key(39); sample('timer-help-return', 1, 2, 14)
                sample('timer-help-restored', 1, 2, 0, timeout=10)
                assert 1.5 < cases[-1]['seconds'] < 3.3, cases[-1]
            else:
                cases[-1]['remaining_ticks_at_start'] = remaining
            if not args.benchmark_only:
                for column in (2, 3):
                    tap(6); sample('ladder-walk-'+str(column), column, 2)
                tap(2); sample('lower-floor', 3, 1)
                tap(8); sample('middle-floor', 3, 2)
                for column in range(4, 8):
                    tap(6); sample('upper-walk-'+str(column), column, 2)
                tap(8); sample('upper-floor', 7, 3)
                tap(9); sample('burn-right', 7, 3, 32)
                tap(6); sample('fall', 8, 2, 32)
                tap(4); sample('tap-left', 7, 2)
                # Normal viewers synthesize releases and pause the game.
                before_help = len(p.frames)
                p.key(37)
                deadline = time.monotonic()+10
                while opening_manual not in p.frames[before_help:] and time.monotonic() < deadline:
                    p.pump(.05)
                assert opening_manual in p.frames[before_help:], 'Help did not open'
                png(opening_manual, args.output/'help.png')
                p.key(39); sample('help-return', 7, 2)
            p.key(39)
            deadline = time.monotonic()+15
            while time.monotonic() < deadline and any(registers(p)):
                p.pump(.1)
            assert not any(registers(p)), 'ESC did not clear calculator'
            assert 'CRASH none' in p.command('crash show')
            cases.append(dict(case='exit', registers=registers(p)))
            if not args.leave_calculator:
                p.open(args.directory.rstrip('/')+'/autoexec.m61'); p.pump(.8)
                p.key(39); sample('ready', 1, 2, 0)
            result = dict(passed=True, identity=identity.__dict__, cases=cases,
                          timer_ms=args.timer_ms,
                          elapsed_seconds=round(time.monotonic()-started, 3),
                          left_at_start=not args.leave_calculator,
                          scope='Physical Classic; ordinary USB Screen keys; no game-state fixtures. '
                                'Timings include register polling and 150 ms framebuffer delivery allowance; '
                                'they do not depend on a version-specific frame marker.')
            (args.output/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
            print('Classic Runner checks PASS', flush=True)
        finally:
            if p.attached:
                p.send(0x31); p.send(0x13); p.attached=False; p.accept_frames=False; p.pump(.2)
            (args.output/'transcript.txt').write_text(p.text.decode('cp1251','replace'))


if __name__ == '__main__':
    main()
