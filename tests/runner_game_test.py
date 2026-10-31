#!/usr/bin/env python3
"""Independent game rules against the real ROM, M61 runner and published LCD.

Fixtures cover art and edge transitions; complete campaigns use only keys.
"""
from collections import deque
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from m8_codec import encode as encode_m8

BOARDS = (
    dict(links=({3, 9}, {7, 11}), start=12, enemies=(35, 36), gold=(0, 23, 24), period=2000),
    dict(links=({2, 10}, {4, 8}), start=17, enemies=(0, 35), gold=(11, 12, 30), period=1000),
    dict(links=({1, 12}, {5, 9}), start=18, enemies=(5, 35), gold=(6, 22, 24), period=1000),
)
MAPS = json.loads((ROOT / 'tools/runner/runner.map.json').read_text())['levels']


def move(board, cell, key):
    floor, col = divmod(cell, 12)
    if key == 4:
        return cell-1 if col else cell
    if key == 6:
        return cell+1 if col < 11 else cell
    if key == 8:
        return cell+12 if floor < 2 and col+1 in board['links'][floor] else cell
    if key == 2:
        return cell-12 if floor and col+1 in board['links'][floor-1] else cell
    return cell


def distance(board, target):
    d, queue = {target: 0}, deque([target])
    while queue:
        cell = queue.popleft()
        for key in (4, 6, 8, 2):
            next_cell = move(board, cell, key)
            if next_cell not in d:
                d[next_cell] = d[cell]+1
                queue.append(next_cell)
    return d


class Game:
    def __init__(self, binary, level=None, start=0):
        self.temp = tempfile.TemporaryDirectory(prefix='runner-game-')
        self.directory = Path(self.temp.name)
        for path in (ROOT / 'programs/games/Runner').iterdir():
            if path.is_file():
                shutil.copy2(path, self.directory / path.name)
        if level:
            (self.directory / 'autoexec.m61').write_text(
                f'open level{level}.m61\n:done\nwait 30\nrun :done\n')
        self.process = subprocess.Popen([binary, self.directory], stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, text=True,
            env={**os.environ, 'MK61_RUNNER_START_MS': str(start)})
        self.level, self.count, self.samples = level or 1, 0, {}
        self.read()

    def read(self):
        line = self.process.stdout.readline()
        assert line, ('runner exited', self.process.poll())
        self.state = json.loads(line)
        assert self.state['lcd_custom'] <= 8, self.state
        self.count += 1
        return self.state

    def send(self, command):
        self.process.stdin.write(command+'\n')
        self.process.stdin.flush()
        return self.read()

    def frame(self, n=1):
        return self.send(f'frame {n}')

    def tap(self, key):
        self.send(f'tap {key:X}')
        return self.frame()

    def fixture(self, hero, enemy=36, mask=0, hole=36, second=36, procedure='draw'):
        action = MAPS[self.level-1]['labels'][procedure]+1
        return self.send(f'fixture {hero} {enemy} {mask} {hole} {second} {action}')

    def check(self):
        s, board = self.state, BOARDS[self.level-1]
        hero, enemy, offset, hole, second = map(int, s['regs'][4:9])
        assert s['active'] and s['segmented'] and not s['auto'], s
        assert offset % 36 == 0 and 0 <= offset <= 252
        if hero < 0:
            return
        assert hero < 36 and 0 <= enemy <= 36 and 0 <= second <= 36
        assert hole == 36 or 12 <= hole < 36
        floor, col = divmod(hero, 12)
        ladders = (board['links'][floor-1] if floor else set()) | (board['links'][floor] if floor < 2 else set())
        expected = [126 if x+1 in ladders else 8 for x in range(12)]
        if not (offset//36 & (1 << floor)):
            expected[board['gold'][floor] % 12] = 201
        expected[col] = 107
        if hole//12 == floor:
            expected[hole % 12] = 0
        for guard in (enemy, second):
            if guard//12 == floor:
                expected[guard % 12] = 119
        assert s['frame'] == expected, (self.level, s, expected)

    def close(self):
        self.process.stdin.close()
        assert self.process.wait(timeout=10) == 0
        self.temp.cleanup()


def art_and_transitions(binary):
    total, walk = 0, []
    for number, board in enumerate(BOARDS, 1):
        g = Game(binary, number)
        try:
            g.check()
            i = 0
            # Every floor/column and all non-winning gold masks, through the
            # real frame composer. Restart periodically keeps clock events
            # separate from the deliberately injected art fixtures.
            for mask in range(7):
                for hero in range(36):
                    if i % 15 == 0:
                        g.tap(0)
                    g.fixture(hero, mask=mask)
                    assert g.state['regs'][4:9] == [hero, 36, 36*mask, 36, 36]
                    g.check()
                    i += 1
            for hero in (0, 11, 12, 23, 24, 35):
                for enemy in range(37):
                    if enemy==hero:
                        continue  # Contact is a terminal state, covered below.
                    if i % 15 == 0:
                        g.tap(0)
                    g.fixture(hero, enemy=enemy)
                    g.check()
                    i += 1
            for floor in (1, 2):
                for col in range(12):
                    g.tap(0)
                    hole = floor*12+col
                    # A trapped guard remains visible and harmless in its hole.
                    g.fixture(floor*12+(col+6) % 12, enemy=hole, hole=hole)
                    g.check()
            for hero in range(36):
                for key in (4, 6, 8, 2):
                    g.tap(0)
                    g.fixture(hero)
                    g.tap(key)
                    expected = move(board, hero, key)
                    assert g.state['regs'][4] == expected, (number, hero, key, g.state)
                    expected_mask = sum(1 << n for n, cell in enumerate(board['gold']) if cell == expected)
                    assert g.state['regs'][6] == 36*expected_mask
                    g.check()
                    if key == 6 and expected != hero:
                        walk.append(g.state['steps'])
                for key, shift in ((7, -1), (9, 1)):
                    g.tap(0)
                    g.fixture(hero)
                    g.tap(key)
                    floor, col = divmod(hero, 12)
                    protected = board['links'][floor-1] if floor else set()
                    if floor < 2:
                        protected = protected | board['links'][floor]
                    allowed = floor > 0 and 0 <= col+shift < 12 and col+shift+1 not in protected
                    expected = hero+shift if allowed else 36
                    assert g.state['regs'][7] == expected, (number, hero, key, g.state)
                    if allowed:
                        assert g.state['timer_ms'] == 4000
                    g.check()
            # Both guards independently follow legal shortest paths, including
            # ladders, while a guard in the active hole stays there.
            for hero in range(36):
                distances = distance(board, hero)
                for enemy in (0, 5, 11, 12, 18, 23, 24, 29, 35):
                    if enemy == hero:
                        continue
                    g.tap(0)
                    g.fixture(hero, enemy=enemy, procedure='enemies')
                    after = int(g.state['regs'][5])
                    assert after in {move(board, enemy, key) for key in (4, 6, 8, 2)}
                    assert distances[after] == distances[enemy]-1
            total += g.count
        finally:
            g.close()
    return total, max(walk)


def clocks_controls_and_loss(binary):
    for start in (0, 0xFFFFFF00):
        g = Game(binary, start=start)
        try:
            start_enemy = g.state['regs'][5]
            assert g.send('advance 1999')['steps'] <= 2
            assert g.state['regs'][5] == start_enemy
            g.send('advance 31')
            assert g.state['regs'][5] != start_enemy, 'idle must be real time'
            g.check()
            g.tap(0)
            g.send('inject 1 6')
            g.send('advance 2000')
            g.frame()  # A tap during composition belongs to the next frame.
            assert g.state['regs'][4] == 13 and g.state['regs'][9:13] == [0]*4, g.state
            g.tap(0)
            g.send('down 6'); g.frame(2)
            assert g.state['regs'][4] == 14
            g.send('up 6'); g.frame(2)
            assert g.state['regs'][4] == 14
            g.send('down 4'); g.send('down 6'); g.frame()
            assert g.state['regs'][4] == 14, g.state
            g.send('up 4'); g.frame()
            assert g.state['regs'][4] == 15
            g.send('up 6')
            g.tap(0)
            g.tap(9)
            assert g.state['regs'][7] == 13
            g.send('advance 3999')
            assert g.state['regs'][7] == 13
            g.send('advance 1')
            g.send('advance 30')
            assert g.state['regs'][7] == 36
            g.check()
            g.tap(0); g.tap(9); g.tap(6)
            assert g.state['regs'][4] == 1, g.state  # fall into lower floor
            g.check()
            before = g.state['timer_ms']
            g.send('manual-ms 5000'); g.tap(0x13)
            assert g.state['timer_ms'] == before-120
            g.send('manual-ms 0')
            g.tap(0); g.tap(9)
            g.send('advance 500')
            before = g.state['timer_ms']
            g.tap(5)
            assert g.state['regs'][15] == -3
            during = g.state['timer_ms']
            assert during == before-120
            g.send('advance 899')
            assert g.state['timer_ms'] == during
            g.send('advance 1')
            assert g.state['timer_ms'] == during
            g.check()
            # Contact ends play, directions cannot revive the player, 0 resets
            # gold, enemies and the hole; this also exercises two guards.
            g.fixture(13, enemy=14)
            g.tap(6)
            assert g.state['regs'][4] == -1 and g.state['timer_ms'] == 0
            dead = g.state['frame']
            g.tap(4); g.send('advance 8000')
            assert g.state['frame'] == dead
            g.tap(0)
            assert g.state['regs'][4:9] == [12, 35, 0, 36, 36]
            g.tap(0x14)
            s = g.state
            assert not s['active'] and not s['running'] and s['auto'] and not s['segmented']
            assert s['regs'] == [0]*16
        finally:
            g.close()


def campaign(binary):
    g = Game(binary)
    try:
        for number, board in enumerate(BOARDS, 1):
            g.level = number
            assert g.state['regs'][4] == board['start'], g.state
            # Find a complete live route. The search state includes the gold
            # mask and the real-time cadence (120 ms between ordinary taps).
            # BFS predicts guards independently of the generator's lookup data.
            initial = (board['start'], *board['enemies'], 0, 0)
            queue, previous = deque([initial]), {initial: None}
            goal = None
            while queue:
                state = queue.popleft()
                hero, e1, e2, mask, tick = state
                if mask == 7:
                    goal = state
                    break
                for key in (4, 6, 8, 2):
                    target = move(board, hero, key)
                    if target == hero or target in (e1, e2):
                        continue
                    new_tick = tick+1
                    enemies = [e1, e2]
                    # Clock is serviced before the key's action, as in M61.
                    if (new_tick*120)//board['period'] != (tick*120)//board['period']:
                        d = distance(board, hero)
                        for index, enemy in enumerate(enemies):
                            if enemy == 36:
                                continue
                            options = [enemy]+[move(board, enemy, k) for k in (8, 2, 4, 6)]
                            enemies[index] = min(options, key=d.__getitem__)
                        if hero in enemies or target in enemies:
                            continue
                    new_mask = mask | sum(1 << n for n, cell in enumerate(board['gold']) if target == cell)
                    next_state = (target, *enemies, new_mask, new_tick)
                    if new_tick > 100 or next_state in previous:
                        continue
                    previous[next_state] = (state, key)
                    queue.append(next_state)
            assert goal, ('no winning route', number)
            route = []
            while previous[goal]:
                goal, key = previous[goal]
                route.append(key)
            route.reverse()
            for key in route:
                g.tap(key)
                g.check()
                assert g.state['regs'][4] >= 0 or g.state['regs'][4] == -2, (number, route, g.state)
            assert g.state['regs'][4] == -2 and g.state['regs'][6] == 252, g.state
            g.samples[f'level{number}_clear'] = g.state
            if number < 3:
                g.send('advance 1500')
        assert g.state['frame'][:3] == [119, 56, 56], g.state  # ALL CLEAr
        g.send('advance 1500')
        g.tap(0)
        assert g.state['regs'][4:9] == [12, 35, 0, 36, 36], g.state
        if os.environ.get('MK61_RUNNER_FRAMES'):
            Path(os.environ['MK61_RUNNER_FRAMES']).write_text(json.dumps(g.samples, indent=2)+'\n')
    finally:
        g.close()
    return g.samples


def timed_balance_campaign(binary):
    # Winning routes verified with one move of EVERY guard before each hero
    # action. These routes require burning on levels 2/3. No state fixtures,
    # frozen guards or host-computed moves are supplied to the running game.
    routes = ('66244668666666666484444444444',
              '669666644444444448668667644474484',
              '44844446964426666666666684')
    g = Game(binary, start=0xFFFFFF00)
    try:
        for repeat in range(2):
            for number, (board, route) in enumerate(zip(BOARDS, routes), 1):
                g.level = number
                assert g.state['regs'][4] == board['start'], g.state
                for key in route:
                    g.send(f'advance {board["period"]-120}')
                    assert g.state['regs'][4] >= 0, (repeat, number, key, g.state)
                    g.tap(int(key))
                    assert g.state['regs'][4] != -1, (repeat, number, route, g.state)
                    g.check()
                assert g.state['regs'][4] == -2 and g.state['regs'][6] == 252
                g.send('advance 1500')
            g.tap(0)
            assert g.state['regs'][4:9] == [12,35,0,36,36], g.state
    finally:
        g.close()


def busy_frames(binary):
    g = Game(binary, 2)
    try:
        # Explicit world fixture only; the actual key arrives during a native
        # render. No complete-frame drain precedes delivery of DOWN and UP.
        g.send('world 17 36 0 36 36')
        g.send('step-ms 200')
        for _ in range(100):
            g.send('observe 20')
            if g.state['running']:
                break
        else:
            raise AssertionError('native render did not start')
        g.send('down 6'); g.send('up 6')
        for _ in range(300):
            g.send('observe 20')
            if g.state['regs'][4] == 18 and g.state['regs'][3] == 1 and not g.state['running']:
                break
        else:
            raise AssertionError(('tap during render was lost', g.state))
        assert g.state['regs'][9:13] == [0]*4, g.state
        g.check()
        # Expiry is latched even while a slow native frame is in progress.
        g.send('advance 4000')
        g.send('step-ms 0'); g.frame()
        assert g.state['regs'][14] >= 0 and g.state['timer_ms'] > 0, g.state
    finally:
        g.close()


def main():
    binary = str(Path(sys.argv[1]).resolve())
    for path in (ROOT / 'programs/games/Runner').iterdir():
        payload = path.read_bytes() if path.suffix == '.bin' else encode_m8(path.read_text())
        assert len(payload) <= (4096 if path.suffix == '.bin' else 1536), path
    total, walk = art_and_transitions(binary)
    clocks_controls_and_loss(binary)
    campaign(binary)
    timed_balance_campaign(binary)
    busy_frames(binary)
    assert walk <= 24, walk
    print(f'Runner real ROM: {total} art/transition states; 3 levels, live campaign, '
          f'2 successive campaigns with a guard turn before EVERY hero action, '
          f'gold, traps, loss/restart, input during busy frames, clock wrap/pause and exit: OK; walk <= {walk} steps')


if __name__ == '__main__':
    main()
