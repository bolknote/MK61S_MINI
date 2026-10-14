"""Drive actual RACE bytecode through the real ROM and M61 binary loader."""
import json
from pathlib import Path
import subprocess
import sys
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/elite'))
from assembler import screen
sys.path.insert(0, str(ROOT / 'tools/race'))
from game import (create_game, check_layout, scene_frame, SECTION_FRAMES, RECOVERY,
                  THUNK_BANK, THUNK_STRIDE, SPRITES_PER_RIVAL)


def test_package():
    directory = ROOT / 'programs/games/RACE'
    for path in [*directory.glob('*.m61'), *directory.glob('*.md')]:
        assert path.stat().st_size <= 1536, (path, path.stat().st_size)
    banks, info = create_game().link()
    check_layout(info)
    image = b''.join(banks.get(bank, bytes(112)) for bank in range(32))
    binary = (directory / 'race.bin').read_bytes()
    assert int.from_bytes(binary[:4], 'little') == zlib.crc32(image)
    print('RACE: package CRC, bank layout and device file-size limits', flush=True)


class Race:
    def __init__(self):
        self.process = subprocess.Popen(
            [sys.argv[1], str(ROOT / 'programs/games/RACE')],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)
        self.state = self.read()
        assert not self.state['running']
        assert self.state['frame'] == screen('rACE L3 20СП'), self.state
        self.send('angle GRD', reply=False)
        self.send('start')
        assert self.state['regs'][4:9] == [0, 0, 0, 3, 0], self.state
        assert self.state['frame'] == screen('L3 n00  20  '), self.state

    def read(self):
        line = self.process.stdout.readline()
        assert line, ('runner exited', self.process.poll())
        state = json.loads(line)
        assert not state['error'], state
        assert state['segmented'] and not state['auto'], state
        assert state['changes'] <= 1, ('partial visible frame', state)
        words = state['regs'][:4]
        assert all(int(word) == word and 0 <= word <= 16777215 for word in words), state
        frame = [(int(word) >> shift) & 255 for word in words for shift in (0, 8, 16)]
        assert state['frame'] == frame, ('published buffer differs', state)
        return state

    def send(self, command, reply=True):
        self.process.stdin.write(command + '\n')
        self.process.stdin.flush()
        if reply:
            self.state = self.read()
        return self.state

    def angle(self, mode):
        self.send('angle ' + mode, reply=False)

    def fixture(self, **values):
        fields = dict(lateral=4, phase=5, completed=6, lives=7, recovery=8, bend=9, rival=10)
        for name, value in values.items():
            self.send(f'set {fields[name]} {value}', reply=False)
        if 'rival' in values:
            base = THUNK_BANK * 112 - THUNK_STRIDE + (values['rival'] + 1) * SPRITES_PER_RIVAL * THUNK_STRIDE
            self.send(f'set 11 {base}', reply=False)

    def close(self):
        self.process.stdin.close()
        assert self.process.wait(timeout=10) == 0


def test_switch():
    for mode, expected in [('P', -1), ('GRD', 0), ('G', 1)]:
        race = Race()
        race.angle(mode)
        state = race.send('next')
        assert state['regs'][4] == expected, (mode, state)
        race.close()
    race = Race()
    race.angle('G'); race.send('next')
    race.angle('GRD'); state = race.send('next')
    assert state['regs'][4] == 1, state
    race.angle('P'); state = race.send('next')
    assert state['regs'][4] == 0, state
    print('RACE: Р/ГРД/Г read during RUN; neutral releases a turn', flush=True)
    race.close()


def test_motion_and_overlays():
    race = Race()
    frames = []
    for phase in range(1, SECTION_FRAMES):
        state = race.send('next')
        frame = state['frame']
        assert sum(bool(mask & 128) for mask in frame) == 1, state
        assert frame[0] & 127 == 0x39 and frame[11] & 127 == 0x0F, state
        assert frame[5] & 8 and frame[6] & 8, state
        frames.append(tuple(frame))
    assert len(set(frames)) == SECTION_FRAMES - 1, frames
    for rival in (-1, 0, 1):
        for lateral in range(-2, 3):
            for phase in range(1, SECTION_FRAMES):
                race.fixture(lateral=lateral, phase=phase - 1,
                             rival=rival, bend=0, recovery=0)
                state = race.send('next')
                assert state['frame'] == scene_frame(lateral, phase, rival), state
                assert sum(bool(mask & 128) for mask in state['frame']) == 1, state
    race.send('help')
    assert race.state['running'], race.state
    print('RACE: all 75 complete sprites, palette reuse, guide, rival and OK help', flush=True)
    race.close()


def test_collisions():
    race = Race()
    race.angle('P')
    hits = []
    lives = 3
    for _ in range(80):
        state = race.send('next')
        if state['regs'][7] != lives:
            assert state['regs'][7] == lives - 1, state
            hits.append(state['regs'][6] * SECTION_FRAMES + state['regs'][5])
            lives -= 1
        if lives == 0:
            break
    assert len(hits) == 3 and all(b - a >= RECOVERY for a, b in zip(hits, hits[1:])), hits
    assert race.state['frame'][:5] == screen('CrASH')[:5], race.state
    race.send('stop'); assert not race.state['running']
    race.angle('GRD'); race.send('start')
    assert race.state['regs'][4:9] == [0, 0, 0, 3, 0], race.state
    race.close()

    race = Race()
    for _ in range(SECTION_FRAMES):
        race.send('next')
    assert race.state['regs'][7] == 2 and race.state['regs'][8] == RECOVERY, race.state
    for _ in range(2): race.send('next')
    assert race.state['regs'][7] == 2, race.state
    race.close()

    race = Race()
    race.fixture(lateral=-2, phase=SECTION_FRAMES - 1, rival=-1, bend=0)
    race.angle('P'); race.send('next')
    assert race.state['regs'][7] == 2, race.state
    assert race.state['regs'][8] == RECOVERY, race.state
    race.close()

    race = Race()
    race.fixture(lateral=2, phase=SECTION_FRAMES - 1, completed=19, lives=1, bend=0)
    race.angle('G'); race.send('next')
    assert race.state['regs'][7] == 0 and race.state['regs'][6] == 19, race.state
    assert race.state['frame'][:5] == screen('CrASH')[:5], race.state
    race.close()
    print('RACE: wall/rival damage, cooldown, restart and fatal finish priority', flush=True)


def test_full_race():
    race = Race()
    steps = []
    last_tick = 0
    for tick in range(20 * SECTION_FRAMES):
        points = [cell for cell, mask in enumerate(race.state['frame']) if mask & 128]
        assert len(points) <= 1, race.state
        direction = (points[0] - 5) if points else 0
        race.angle('GRD' if direction == 0 else 'G' if direction > 0 else 'P')
        state = race.send('next')
        current = state['regs'][6] * SECTION_FRAMES + state['regs'][5]
        assert current == last_tick + 1, state
        assert state['regs'][7] == 3, (tick, state)
        last_tick = current
        steps.append(state['steps'])
    assert race.state['frame'] == screen('FInISH 20 L3'), race.state
    assert race.state['regs'][6] == 20 and race.state['regs'][5] == 0, race.state
    race.send('stop'); assert not race.state['running']
    frame = race.state['frame']; race.send('next')
    assert race.state['frame'] == frame and race.state['regs'][6] == 20, race.state
    race.angle('GRD'); race.send('start')
    assert race.state['regs'][4:9] == [0, 0, 0, 3, 0], race.state
    race.close()
    assert sum(steps) / len(steps) <= 60, ('frame computation budget exceeded', steps)
    print(f'RACE: {20 * SECTION_FRAMES} frames, 20 sections, 3 lives via visible guide; core steps/frame '
          f'{min(steps)}..{max(steps)}, mean {sum(steps)/len(steps):.1f}', flush=True)


if __name__ == '__main__':
    test_package()
    test_switch()
    test_motion_and_overlays()
    test_collisions()
    test_full_race()
