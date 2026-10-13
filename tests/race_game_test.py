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
from game import create_game, check_layout


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
        assert self.state['frame'] == screen('L3 n01  20  '), self.state

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
    for _ in range(12):
        state = race.send('next')
        frame = state['frame']
        assert sum(bool(mask & 128) for mask in frame) == 1, state
        assert frame[0] & 127 == 0x39 and frame[11] & 127 == 0x0F, state
        assert frame[5] & 8 and frame[6] & 8, state
        frames.append(tuple(frame))
    assert len(set(frames[:6])) >= 5, frames
    for lateral in range(-12, 13):
        for phase in (0, 6, 16, 26, 32):
            race.fixture(lateral=lateral, phase=phase, rival=-8, bend=0, recovery=15)
            state = race.send('next')
            if state['regs'][8] != 15 and state['regs'][5] != 0:
                assert sum(bool(mask & 128) for mask in state['frame']) == 1, state
    race.send('help')
    assert race.state['running'], race.state
    print('RACE: growing wall flow, corners, guide, rival clipping and OK help', flush=True)
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
            hits.append(state['regs'][6] * 36 + state['regs'][5])
            lives -= 1
        if lives == 0:
            break
    assert len(hits) == 3 and all(b - a >= 15 for a, b in zip(hits, hits[1:])), hits
    assert race.state['frame'][:5] == screen('CrASH')[:5], race.state
    race.send('stop'); assert not race.state['running']
    race.angle('GRD'); race.send('start')
    assert race.state['regs'][4:9] == [0, 0, 0, 3, 0], race.state
    race.close()

    race = Race()
    for _ in range(33):
        race.send('next')
    assert race.state['regs'][7] == 2 and race.state['regs'][8] == 15, race.state
    for _ in range(2): race.send('next')
    assert race.state['regs'][7] == 2, race.state
    race.close()

    race = Race()
    race.fixture(lateral=-12, phase=32, rival=-8, bend=0)
    race.angle('P'); race.send('next')
    assert race.state['regs'][7] == 2, race.state
    assert race.state['regs'][8] == 15, race.state
    race.close()

    race = Race()
    race.fixture(lateral=12, phase=35, completed=19, lives=1, bend=0)
    race.angle('G'); race.send('next')
    assert race.state['regs'][7] == 0 and race.state['regs'][6] == 19, race.state
    assert race.state['frame'][:5] == screen('CrASH')[:5], race.state
    race.close()
    print('RACE: wall/rival damage, cooldown, restart and fatal finish priority', flush=True)


def test_full_race():
    race = Race()
    steps = []
    last_tick = 0
    for tick in range(720):
        if tick % 3 == 0:
            lateral = race.state['regs'][4]
            target = -9 if race.state['regs'][10] > 0 else 9
            delta = target - lateral
            race.angle('GRD' if abs(delta) <= 2 else 'G' if delta > 0 else 'P')
        state = race.send('next')
        current = state['regs'][6] * 36 + state['regs'][5]
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
    print(f'RACE: 720 frames, 20 sections, 3 lives; core steps/frame '
          f'{min(steps)}..{max(steps)}, mean {sum(steps)/len(steps):.1f}', flush=True)


if __name__ == '__main__':
    test_package()
    test_switch()
    test_motion_and_overlays()
    test_collisions()
    test_full_race()
