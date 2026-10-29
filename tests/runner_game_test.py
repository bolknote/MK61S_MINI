#!/usr/bin/env python3
"""Drive the real M61 bindings and calculator ROM, then inspect actual frames."""
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from m8_codec import encode as encode_m8

LADDERS = {1: {3, 9}, 2: {3, 7, 9, 11}, 3: {7, 11}}


def hole_cell(state):
    pointer = state['regs'][11]
    return 0 if pointer == 0 else (pointer - 16*112 - 12)//28 + 1


class Game:
    def __init__(self, binary):
        self.process = subprocess.Popen([binary, str(ROOT / 'programs/games/Runner')],
                                        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        text=True)
        self.count, self.max_steps = 0, 0
        self.samples = {}
        self.redraw_request = json.loads((ROOT / 'tools/runner/runner.map.json').read_text())['labels']['draw'] + 1
        self.state = self.read()

    def read(self, active=True):
        line = self.process.stdout.readline()
        assert line, ('runner exited', self.process.poll())
        state = json.loads(line)
        if active:
            assert state['active'], state
            assert state['segmented'] and not state['auto'], state
        assert state['lcd_custom'] <= 2, state
        self.count += 1
        self.max_steps = max(self.max_steps, state['steps'])
        self.state = state
        return state

    def send(self, command, active=True):
        if command.startswith('fixture '):
            command += f' {self.redraw_request}'
        self.process.stdin.write(command + '\n')
        self.process.stdin.flush()
        return self.read(active)

    def frame(self, count=1):
        return self.send(f'frame {count}')

    def tap(self, key):
        self.send(f'tap {key:X}')
        return self.frame()

    def check(self, column, floor, hole=None):
        state = self.state
        assert state['regs'][4:6] == [column, floor], state
        assert state['regs'][14] == 16*112 + (floor-1)*336 - 27, state
        expected = [126 if x in LADDERS[floor] else 8 for x in range(1, 13)]
        expected[column - 1] = 107
        hole = hole_cell(state) if hole is None else hole
        if hole and (hole - 1) // 12 + 1 == floor:
            expected[(int(hole) - 1) % 12] = 0
        assert state['frame'] == expected, (column, floor, state, expected)

    def sample(self, name):
        self.samples[name] = self.state

    def close(self):
        self.process.stdin.close()
        assert self.process.wait(timeout=10) == 0


def main():
    bundle = ROOT / 'programs/games/Runner'
    for path in bundle.iterdir():
        payload = path.read_bytes() if path.suffix == '.bin' else encode_m8(path.read_text())
        assert len(payload) <= (4096 if path.suffix == '.bin' else 1536), path
    assert max(map(len, (bundle / 'autoexec.m61').read_text().splitlines())) <= 239
    game = Game(sys.argv[1])
    try:
        game.check(1, 2)
        assert game.state['manuals'] == 1
        game.sample('start')
        # WAIT paces frames; idle simulation resumes without a C/P press.
        before = game.state['frame']
        assert game.send('advance 29')['steps'] == 0
        assert game.state['frame'] == before
        assert game.send('advance 1')['steps'] <= 2
        game.check(1, 2)
        idle_steps = game.state['steps']
        assert idle_steps <= 2, game.state
        game.tap(8); game.check(1, 2)  # no ladder at column 1
        game.send('down 6'); game.frame(); game.check(2, 2)
        walk_steps = game.state['steps']
        assert walk_steps <= 20, game.state
        game.frame(); game.check(3, 2)
        game.send('up 6'); game.frame(2); game.check(3, 2)
        # Both edges arrive during the frame wait. The short tap survives.
        game.tap(4); game.check(2, 2)
        game.tap(4); game.check(1, 2)
        game.tap(4); game.check(1, 2)  # left boundary
        game.send('down 6'); game.frame(2); game.check(3, 2)
        game.send('up 6'); game.tap(2); game.check(3, 1)
        game.sample('lower')
        game.tap(2); game.check(3, 1)  # bottom boundary
        game.send('down 8'); game.frame(2); game.check(3, 2)
        game.send('up 8'); game.frame(); game.check(3, 2)
        game.tap(8); game.check(3, 2)  # this ladder ends here
        game.send('down 6'); game.frame(4); game.check(7, 2)
        game.send('up 6'); game.tap(8); game.check(7, 3)
        game.sample('upper')
        game.tap(8); game.check(7, 3)
        game.tap(2); game.check(7, 2)
        game.tap(2); game.check(7, 2)  # this ladder does not reach bottom
        game.send('down 9'); game.frame(); game.check(7, 2)
        assert hole_cell(game.state) == 20 and game.state['regs'][13] == 18
        game.sample('burn_right')
        game.frame(2)
        assert game.state['regs'][13] == 16  # held fire does not reopen it
        game.send('up 9')
        game.tap(6); game.check(8, 1)
        game.sample('fall')
        game.frame(15)
        assert game.state['regs'][11] == game.state['regs'][13] == 0
        game.tap(9); game.check(8, 1)  # solid bottom
        assert game.state['regs'][11] == 0
        game.tap(6); game.check(9, 1)
        game.tap(8); game.check(9, 2)
        game.sample('restored')
        game.tap(7)
        assert hole_cell(game.state) == 20  # burn left from column 9
        game.tap(0); game.check(1, 2)
        # Both vertical directions cancel while the horizontal hold survives.
        game.send('down 6'); game.send('down 8'); game.send('down 2')
        game.frame(); game.check(1, 2)
        game.frame(); game.check(2, 2)
        game.send('up 8'); game.frame(); game.check(2, 2)
        game.send('up 2'); game.frame(); game.check(3, 2)
        game.send('up 6'); game.frame(); game.check(3, 2)
        game.tap(0); game.check(1, 2)
        assert game.state['regs'][11] == game.state['regs'][13] == 0
        game.send('down 6'); game.send('down 4'); game.frame(); game.check(1, 2)
        game.send('up 4'); game.frame(); game.check(2, 2)
        game.send('up 6'); game.frame(); game.check(2, 2)
        # Manual capture synthesizes UP, so movement cannot stick after OK.
        game.send('down 6'); game.frame(); game.check(3, 2)
        manuals = game.state['manuals']
        game.tap(0x13); game.check(3, 2)
        assert game.state['manuals'] == manuals + 1
        assert game.state['regs'][7] == 0
        game.frame(); game.check(3, 2)
        game.tap(0); game.check(1, 2)
        # Independent art oracle: all 36 positions, and a hole in every
        # burnable column of both upper floors (all four packed frame words).
        for floor in (1, 2, 3):
            for column in range(1, 13):
                game.send(f'fixture {column} {floor} 0 0')
                game.check(column, floor)
        for floor in (2, 3):
            for column in range(1, 13):
                if column in LADDERS[floor]:
                    continue
                hero = 12 if column != 12 else 1
                hole = (floor - 1) * 12 + column
                game.send(f'fixture {hero} {floor} {hole} 18')
                game.check(hero, floor)
                assert game.state['regs'][13] == 17
        # All 72 generated burn transitions: boundaries, lower floor and
        # every protected ladder are checked against the independent map.
        for floor in (1, 2, 3):
            for column in range(1, 13):
                for key, offset in ((7, -1), (9, 1)):
                    game.send(f'fixture {column} {floor} 0 0')
                    game.tap(key)
                    neighbor = column + offset
                    allowed = floor > 1 and 1 <= neighbor <= 12 and neighbor not in LADDERS[floor]
                    expected_hole = (floor-1)*12 + neighbor if allowed else 0
                    assert hole_cell(game.state) == expected_hole, game.state
                    game.check(column, floor)
        # Right boundary and protected ladders, after clearing the fixture.
        game.send('fixture 12 2 0 0'); game.tap(6); game.check(12, 2)
        game.tap(9)
        assert game.state['regs'][11] == 0
        game.send('fixture 2 2 0 0'); game.tap(9); game.check(2, 2)
        assert game.state['regs'][11] == 0
        game.send('fixture 8 3 0 0'); game.tap(7); game.check(8, 3)
        assert game.state['regs'][11] == 0
        # The 18-frame timer restores the actual visible floor.
        game.send('fixture 5 2 0 0'); game.tap(9); game.check(5, 2)
        game.frame(17)
        timer_steps = game.state['steps']
        assert timer_steps <= 200, game.state
        assert game.state['regs'][13] == 1
        game.check(5, 2)
        game.frame(); game.check(5, 2)
        assert game.state['regs'][11] == game.state['regs'][13] == 0
        if os.environ.get('MK61_RUNNER_FRAMES'):
            Path(os.environ['MK61_RUNNER_FRAMES']).write_text(json.dumps(game.samples, indent=2) + '\n')
        game.send('tap 14')
        stopped = game.send('frame', active=False)
        assert not stopped['active'] and not stopped['running'] and not stopped['segmented'], stopped
        assert stopped['auto'] and stopped['regs'] == [0] * 16, stopped
        print(f'Runner real ROM: {game.count} states; 36 sprites; hold/tap, '
              f'ladders, burn/fall/restore, help, restart and exit: OK; max batch {game.max_steps} core steps')
        print(f'Runner cost: idle={idle_steps}, walk={walk_steps}, timer17={timer_steps} core steps')
    finally:
        game.close()


if __name__ == '__main__':
    main()
