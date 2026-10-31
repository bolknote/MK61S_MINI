#!/usr/bin/env python3
"""Replay the physical L2 delayed-frame failure without serial I/O or builds."""
import argparse
import ast
import copy
import hashlib
import json
from pathlib import Path

from runner_screen_oracle import expected

HERE = Path(__file__).resolve().parent
FIXTURE = json.loads((HERE / 'fixtures/runner_hil_l2_frame_delay.json').read_bytes())


class Replay:
    def __init__(self, fixture):
        self.fixture = fixture
        self.now = fixture['start']
        self.index = 0
        self.timeline = []
        self.text = b''
        self.update()

    def monotonic(self): return self.now

    def update(self):
        self.timeline = [(f['t'], f['decoded']) for f in self.fixture['frames'] if f['t'] <= self.now]

    def pump(self, seconds):
        self.now += max(seconds, 0)
        self.update()

    def registers(self, _):
        if self.index >= len(self.fixture['snapshots']):
            self.now += 20
            return self.fixture['snapshots'][-1]['regs'][:]
        row = self.fixture['snapshots'][self.index]
        self.index += 1
        self.now = max(self.now, row['t'])
        self.update()
        return row['regs'][:]


def nested(path, name, namespace):
    module = ast.parse(path.read_bytes())
    main = next(n for n in module.body if isinstance(n, ast.FunctionDef) and n.name == 'main')
    node = next(n for n in ast.walk(main) if isinstance(n, ast.FunctionDef) and n.name == name)
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path) + ':' + name, 'exec'), namespace)
    return namespace[name]


def run_wait(source, fixture, timeout=20):
    replay = Replay(fixture)
    config = dict(fixture['config'], links=tuple(map(set, fixture['config']['links'])))
    function = nested(source, 'state_match', dict(p=replay, time=replay, registers=replay.registers,
                      BOARDS=(None, config), expected=expected))
    state = function(lambda r: r[4] == fixture['target'] and r[13] == 0, level=2, timeout=timeout)
    return replay, state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--legacy-source', type=Path)
    parser.add_argument('--runner', type=Path, help='existing real-ROM HOST runner; never builds it')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    source = HERE / 'hil_runner_campaign.py'
    replay, state = run_wait(source, FIXTURE)
    assert replay.index == 2 and state[4] == 18 and state[5:9] == [1, 0, 36, 34], state
    assert 83.480 <= replay.now < 83.51, replay.now

    # Frame equality never waives the completed-calculation marker.
    phase = copy.deepcopy(FIXTURE)
    phase['snapshots'][1]['regs'][3] = 4
    later, _ = run_wait(source, phase)
    assert later.index == 5 and later.now > 84.97

    missing = copy.deepcopy(FIXTURE)
    missing['frames'] = missing['frames'][:1]
    try:
        run_wait(source, missing, timeout=.5)
    except AssertionError as error:
        assert error.args[0][0] == 'state timeout'
    else:
        raise AssertionError('Missing target framebuffer was accepted')

    # Never queue a burn/move after a fresh snapshot has already reported loss.
    sent = []
    dead = [0] * 15
    dead[4] = -1
    action = nested(source, 'action', dict(registers=lambda _: dead, p=None,
                    tap=lambda key: sent.append(key)))
    try:
        action(9, level=2)
    except AssertionError as error:
        assert error.args[0][0] == 'action after defeat'
    else:
        raise AssertionError('Defeated hero accepted a new action')
    assert sent == []

    result = dict(status='HOST_PHYSICAL_TRACE_REPLAY_PASS', device_IO=0, new_builds=0,
                  fixed_return_seconds=replay.now, fixed_register_queries=replay.index,
                  fixed_guards=[state[5], state[8]], fixture_wire_sha256=FIXTURE['wire_sha256'],
                  controls=['frame after snapshot without another blocking CLI read',
                            'matching frame requires completed phase1', 'missing frame rejects',
                            'defeated snapshot prevents key transmission'])
    if args.legacy_source:
        assert hashlib.sha256(args.legacy_source.read_bytes()).hexdigest() == FIXTURE['legacy_HIL_sha256']
        old, old_state = run_wait(args.legacy_source, FIXTURE)
        assert old.index == 5 and old_state[5:9] == [14, 0, 36, 32]
        result.update(legacy_return_seconds=old.now, legacy_register_queries=old.index,
                      legacy_guards=[old_state[5], old_state[8]],
                      avoided_wait_seconds=old.now - replay.now, extra_guard_turns_avoided=2)
    if args.runner:
        from runner_game_test import Game
        observed = {}
        for extra_wait in (True, False):
            game = Game(str(args.runner.resolve()), 2)
            try:
                game.send('advance 1000'); game.tap(6)
                assert game.state['regs'][4:9] == [18, 1, 0, 36, 34]
                if extra_wait:
                    game.send('advance 880'); game.send('advance 1000')
                    assert game.state['regs'][4:9] == [18, 14, 0, 36, 32]
                    game.send('advance 1000')
                else:
                    game.send('advance 880')
                game.tap(6)
                game.send('advance 880')
                before_burn = game.state['regs'][4:9]
                game.tap(9)
                after_burn = game.state['regs'][4:9]
                if extra_wait:
                    assert before_burn == after_burn == [-1, 16, 0, 36, 19]
                else:
                    assert before_burn == [19, 14, 0, 36, 32]
                    assert after_burn == [19, 14, 0, 20, 32]
                observed['legacy_wait' if extra_wait else 'without_extra_wait'] = dict(
                    before_burn=before_burn, after_burn=after_burn)
            finally:
                game.close()
        result['existing_ROM_runner_sha256'] = hashlib.sha256(args.runner.read_bytes()).hexdigest()
        result['real_ROM_targeted_prefix'] = observed
    if args.output:
        args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
