#!/usr/bin/env python3
"""Complete all three MIT Semion quests on Classic, with real file saves.

--prepare uses the host only and pins every input. --run opens only the named
Classic. It installs the three quests, retains their two save slots, and never
flashes, resets, formats, deletes files, or writes the clock. Keys are injected
USB matrix events; mechanical keys and LCD readability still need a human.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]
import argparse
import binascii
import hashlib
import json
import os
import re
import signal
import stat
import subprocess
import time

from hil_c6_system_bootstrap import read_file, write_file
from hil_portable_apps import ScreenPort
from hil_portable_system_apps import png
from hil_rtc_alarm import PROMPT
import hil_classic_cdc_guard as cdc_guard
from hil_urq import DIGITS, ESC, OK, RIGHT, USER, saved
from tools.apps.urq.extra_games import locked_sources
import urq_library_self_test as library

LEFT, SHIFT_LEFT, SHIFT_RIGHT = 38, 27, 28
WINS = {'semion_escape': 'выбираетесь из клетки', 'semion_road': 'прошли пятую серию',
        'semion_snow': 'прошли десятую серию'}
CALCULATOR_FIXTURES = ROOT / 'tests/fixtures/urq/classic_menu'


class CalculatorInputError(AssertionError):
    pass


def number_field(frame):
    # Standard Classic segmented X value occupies y24..55. The last-key
    # mnemonic and the storage badge are above it and cannot acknowledge X.
    assert len(frame) == 1536
    return frame[3 * 192:7 * 192]


def calculator_status(frame):
    # mnemo.hpp places the variable key mnemonic at column10 (x120), Y=0.
    # Keep the RUN/trap and angle-label area to its left, over both pages.
    return frame[:120] + frame[192:312]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def prepare(args):
    locked_sources()
    library.HOST = args.host.resolve()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    hints = subprocess.check_output([str(args.footer.resolve())])
    assert len(hints) == 7 * 192 and len({hints[i:i+192] for i in range(0, len(hints), 192)}) == 7
    (output / 'footers.bin').write_bytes(hints)
    pins = [Path(__file__), args.host, args.footer, output / 'footers.bin',
            ROOT / 'tests/urq_classic_footer.cpp', ROOT / 'tests/urq_library_self_test.py',
            ROOT / 'tests/hil_portable_apps.py', ROOT / 'tests/hil_rtc_alarm.py',
            ROOT / 'tests/hil_c6_system_bootstrap.py', ROOT / 'tests/hil_urq.py',
            ROOT / 'tests/hil_usb_disk_transaction.py', ROOT / 'tools/apps/urq/extra-games.json']
    for name in ('URQ.APP', 'URQUI.APP'):
        pins.append(args.apps_dir / name)
    pins.extend(CALCULATOR_FIXTURES / name for name in ('calculator_0.raw', 'calculator_123.raw', 'system_menu.raw'))
    # Capture the local Python import closure, including image, license and
    # library helpers; no runtime source can silently change after review.
    for module in tuple(sys.modules.values()):
        source = getattr(module, '__file__', None)
        if source:
            path = Path(source).resolve()
            if path.suffix == '.py' and path.is_relative_to(ROOT):
                pins.append(path)
    games = {}
    for key, route in library.SEMION_ROUTES.items():
        folder = library.game_folder(key)
        files = sorted(path for path in folder.iterdir() if path.suffix in ('.urq', '.uqd', '.wbmp'))
        pins.extend(files)
        model = library.Player(key)
        try:
            checkpoints = {}
            middle_index = len(route) // 2 + 1
            for index, command in enumerate(route):
                assert len(model.state['actions']) <= 10
                model.route([command])
                if index == len(route) - 1:
                    assert WINS[key] in model.text().lower()
                if index in (middle_index, len(route) - 1):
                    name = 'middle' if index == middle_index else 'final'
                    core = output / (key + '-' + name + '-expected.core.urs')
                    model.step('s:' + str(core))
                    checkpoints[name] = {'index': index, 'state': model.state, 'core': str(core)}
                    pins.append(core)
            games[key] = {'route': route, 'files': {path.name: str(path.resolve()) for path in files},
                          'remote': '/URQ/' + key, 'checkpoints': checkpoints,
                          'save_slots': {'middle': 2, 'final': 1}}
        finally:
            model.close()
    phase = {'version': 1, 'public_id': args.public_id.upper(), 'port': args.port,
             'expected_build': args.build_crc.upper(), 'apps_dir': str(args.apps_dir.resolve()),
             'host': str(args.host.resolve()), 'games': games,
             'packages_installed': args.installed,
             'calculator_checks': 'Fresh exact X=123 frame after Cx/USB123; failures collected independently; overall result remains FAIL',
             'pins': {str(path.resolve()): sha(path) for path in pins},
             'scope': 'Three complete quests; package installation and slot1/2 saves only; no flash/reset/format/delete/RTC writes',
             'mechanical_key_test': False, 'lcd_readability_test': False,
             'maximum_run_seconds': 1800, 'maximum_cleanup_seconds': 60}
    write_json(output / 'phase.json', phase)
    print('HOST preparation PASS:', output / 'phase.json', sha(output / 'phase.json'))


def canonical(frame):
    # disk_activity::Overlay: LEFT=176, WIDTH=16, PAGES=2. This independent
    # resident badge may animate above the same game/menu/calculator bitmap.
    return frame[:176] + bytes(16) + frame[192:368] + bytes(16) + frame[384:]


class BoundedScreenPort(ScreenPort):
    def __init__(self, path, deadline):
        self.deadline = deadline
        super().__init__(path)

    def command(self, command, timeout=5):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('Classic phase deadline expired')
        reply = super().command(command, min(timeout, remaining))
        echo = r'(?m)^(?:[^\r\n]*>\s*)?' + re.escape(command) + r'\r?$'
        assert re.search(echo, reply), 'Uncorrelated reply; mutating commands are never retried'
        return reply


class QuestRun:
    def __init__(self, port, output, hints, deadline):
        self.p, self.output, self.deadline = port, output, deadline
        self.hints = dict(zip(('paging', 'reading', 'actions', 'anykey', 'saved'),
                              (hints[i:i+192] for i in range(0, len(hints), 192))))
        self.menu_header = hints[5 * 192:5 * 192 + 160]
        self.active = False
        self.modal = 'game'
        self.steps = []
        self.navigation = []
        self.menu_serial = 0
        self.zero_field = number_field((CALCULATOR_FIXTURES / 'calculator_0.raw').read_bytes())
        self.number123_field = number_field((CALCULATOR_FIXTURES / 'calculator_123.raw').read_bytes())
        self.calculator_header = calculator_status((CALCULATOR_FIXTURES / 'calculator_0.raw').read_bytes())
        self.system_menu = canonical((CALCULATOR_FIXTURES / 'system_menu.raw').read_bytes())
        self.identity = None
        self.foreground_checks = []

    def wait(self, after, predicate, timeout=25):
        until = min(self.deadline, time.monotonic() + timeout)
        while time.monotonic() < until:
            if len(self.p.frames) > after and predicate(self.p.frames[-1]):
                self.p.pump(.06)
                if predicate(self.p.frames[-1]):
                    return self.p.frames[-1]
            self.p.pump(.04)
        if self.p.frames:
            png(self.p.frames[-1], self.output / 'timeout.png')
            for index, frame in enumerate(self.p.frames[-12:]):
                png(frame, self.output / ('timeout-frame-%02d.png' % index))
        raise TimeoutError('Expected Classic screen did not arrive')

    def change(self, key, predicate=lambda frame: True):
        self.p.pump(.08)
        old, after = canonical(self.p.frames[-1]), len(self.p.frames)
        self.p.key(key)
        return self.wait(after, lambda frame: canonical(frame) != old and predicate(frame))

    def kind(self):
        tail = self.p.frames[-1][-192:]
        return next((name for name, hint in self.hints.items() if tail == hint), 'other')

    def main_menu(self, frame):
        return len(self.menu_header) == 160 and frame[:160] == self.menu_header

    def settle(self, status):
        expected = 'anykey' if status == 2 else 'reading'
        assert status in (1, 2), status
        for _ in range(200):
            self.p.pump(.08)
            kind = self.kind()
            if kind == expected:
                return
            if kind == 'paging':
                after = len(self.p.frames)
                self.p.key(OK)
                self.wait(after, lambda frame: frame[-192:] in self.hints.values())
            elif kind == 'saved':
                self.change(RIGHT)
            else:
                self.wait(len(self.p.frames), lambda frame: frame[-192:] in
                          (self.hints['paging'], self.hints[expected]))
        raise AssertionError('Too many story pages')

    def open(self, remote, status):
        after = len(self.p.frames)
        self.p.open(remote + '/game.urq')
        self.active, self.modal = True, 'game'
        self.wait(after, lambda frame: frame[-192:] in self.hints.values())
        self.settle(status)

    def choose(self, model, command, index):
        if command == 'k:13':
            assert model.state['status'] == 2 and self.kind() == 'anykey'
            self.change(OK, lambda frame: frame[-192:] != self.hints['anykey'])
        else:
            assert model.state['status'] == 1 and self.kind() == 'reading'
            action = next(i for i, item in enumerate(model.state['actions']) if item['command'] == command)
            assert action < 10
            self.change(OK, lambda frame: frame[-192:] == self.hints['actions'])
            # Test cancellation and reopening once per quest. No action is sent.
            if index == 0:
                original = canonical(self.p.frames[-1])
                for forward, backward in ((RIGHT, LEFT), (SHIFT_RIGHT, SHIFT_LEFT)):
                    self.change(forward)
                    self.change(backward)
                    assert canonical(self.p.frames[-1]) == original, 'Action navigation did not return'
                self.change(ESC, lambda frame: frame[-192:] == self.hints['reading'])
                self.change(OK, lambda frame: frame[-192:] == self.hints['actions'])
            self.change(DIGITS[(action + 1) % 10], lambda frame: frame[-192:] != self.hints['actions'])
        model.route([command])
        self.settle(model.state['status'])
        self.steps.append({'index': index, 'command': command, 'status': model.state['status'],
                           'frame_sha256': hashlib.sha256(self.p.frames[-1]).hexdigest()})
        print('Step', index + 1, command, 'PASS', flush=True)

    def menu(self, index, slot=None):
        self.change(USER, self.main_menu)
        self.modal = 'menu'
        if index == 1:
            original = canonical(self.p.frames[-1])
            self.menu_serial += 1
            prefix = 'menu-%02d' % self.menu_serial
            png(self.p.frames[-1], self.output / (prefix + '-original.png'))
            for forward, backward in ((RIGHT, LEFT), (SHIFT_RIGHT, SHIFT_LEFT)):
                self.change(forward)
                png(self.p.frames[-1], self.output / (prefix + '-forward-%d.png' % forward))
                self.change(backward, lambda frame: canonical(frame) == original)
                png(self.p.frames[-1], self.output / (prefix + '-back-%d.png' % backward))
                self.navigation.append({'menu': self.menu_serial, 'pair': [forward, backward],
                                        'returned_frame_sha256': hashlib.sha256(original).hexdigest()})
        for _ in range(index):
            self.change(RIGHT)
        self.change(OK)
        self.modal = ('confirm' if index == 5 else 'slots' if index in (1, 2) else
                      'inventory' if index == 3 else 'game')
        if slot is not None:
            for _ in range(slot):
                self.change(RIGHT)
            self.change(OK, lambda frame: frame[-192:] == self.hints['saved'])
            self.modal = 'game'

    def save(self, slot):
        self.menu(1, slot)
        png(self.p.frames[-1], self.output / ('slot' + str(slot + 1) + '-saved.png'))
        self.change(RIGHT)  # dismiss the notice; RIGHT cannot resume ANYKEY

    def load(self, slot, status):
        self.menu(2, slot)
        self.change(RIGHT)
        self.settle(status)

    def inventory(self, name):
        self.menu(3)
        png(self.p.frames[-1], self.output / (name + '-inventory.png'))
        self.change(ESC, lambda frame: frame[-192:] == self.hints['reading'])
        self.modal = 'game'

    def exit(self):
        self.menu(5)
        self.p.key(OK)
        self.closed()

    def closed(self):
        until = min(self.deadline, time.monotonic() + 20)
        while time.monotonic() < until:
            self.p.pump(.05)
            if PROMPT.search(self.p.text[self.p.open_text_start:]):
                assert b'Open failed!' not in self.p.text[self.p.open_text_start:]
                self.active, self.modal = False, 'game'
                self.p.pump(.3)
                return
        raise TimeoutError('URQ did not return to calculator')

    def known_foreground(self, frame):
        return canonical(frame) == self.system_menu or calculator_status(frame) == self.calculator_header

    def fresh_foreground(self, timeout=5):
        after = len(self.p.frames)
        self.p.send(0x16)  # REQUEST_KEYFRAME; resends the live surface, no redraw
        return self.wait(after, self.known_foreground, timeout)

    def normalise_foreground(self, name, timeout=5):
        assert not self.active
        frame = self.fresh_foreground(timeout)
        png(frame, self.output / (name + '-foreground-before.png'))
        escaped = canonical(frame) == self.system_menu
        if escaped:
            after = len(self.p.frames)
            # menu.cpp KEY_ESC_PRESS returns -1; mk61_menu_hook then invokes
            # leave_menu_mode(), which restores the base-loop input owner.
            self.p.key(ESC)
            self.wait(after, lambda value: calculator_status(value) == self.calculator_header, timeout)
            frame = self.fresh_foreground(timeout)
        assert calculator_status(frame) == self.calculator_header, 'Unknown or running foreground'
        self.foreground_checks.append({'point': name, 'known_system_menu_escaped_once': escaped,
                                       'fresh_stopped_calculator': True})
        png(frame, self.output / (name + '-calculator.png'))

    def calculator(self, name):
        self.normalise_foreground(name)
        self.p.key(0)  # Cx; no old calculator state is saved or restored
        self.wait_number(-1, self.zero_field)
        png(self.p.frames[-1], self.output / (name + '-calculator-zero.png'))
        after = len(self.p.frames)
        for digit in (1, 2, 3):
            self.p.key(DIGITS[digit])
        self.wait_number(after, self.number123_field)
        png(self.p.frames[-1], self.output / (name + '-calculator-123.png'))
        self.p.key(0)

    def wait_number(self, after, expected, timeout=5):
        started = time.monotonic()
        self.last_number_wait = {'after_frame': after, 'frames_before': len(self.p.frames),
                                 'expected': '0' if expected == self.zero_field else '123',
                                 'fresh_frame_required': after >= 0}
        try:
            return self.wait(after, lambda frame: number_field(frame) == expected, timeout)
        except TimeoutError as error:
            if time.monotonic() >= self.deadline:
                raise
            raise CalculatorInputError('No fresh frame with the exact expected X value') from error
        finally:
            self.last_number_wait.update(frames_after=len(self.p.frames),
                elapsed_seconds=round(time.monotonic() - started, 3),
                last_field_sha256=hashlib.sha256(number_field(self.p.frames[-1])).hexdigest() if self.p.frames else None,
                last_field_matches=bool(self.p.frames and number_field(self.p.frames[-1]) == expected))

    def check_calculator(self, name):
        try:
            self.calculator(name)
            return {'result': 'PASS', 'fresh_exact_x123': True, 'numeric_wait': self.last_number_wait}
        except CalculatorInputError as error:
            png(self.p.frames[-1], self.output / (name + '-calculator-failed.png'))
            assert not self.active and calculator_status(self.p.frames[-1]) == self.calculator_header, 'Unknown or running foreground'
            # A failed independent numeric check may not hide a lost terminal
            # or another foreground owner. No key or command is retried.
            identity = self.p.command('identity')
            assert self.identity is not None
            for field in ('public', 'usb', 'build', 'profile'):
                expected = re.search(r'\b' + field + r'=([^\s]+)', self.identity).group(1)
                assert field + '=' + expected in identity
            return {'result': 'FAIL', 'error': str(error), 'fresh_exact_x123': False,
                    'stopped_calculator_and_terminal_confirmed': True, 'numeric_wait': self.last_number_wait}

    def abort(self):
        self.deadline = time.monotonic() + 50
        self.p.deadline = self.deadline
        if not self.active:
            return
        if self.kind() == 'paging':
            self.p.key(ESC)
            self.p.key(ESC)
            self.closed()
        elif self.modal == 'confirm':
            self.p.key(OK)
            self.closed()
        else:
            if self.modal in ('slots', 'inventory'):
                self.change(ESC)
                self.modal = 'game'
            if self.modal == 'menu':
                self.change(ESC)
                self.modal = 'game'
            self.exit()


def verify_save(port, key, remote, name, expected, output):
    wire, draft = saved(port, remote)
    assert not draft
    (output / (name + '.urs')).write_bytes(wire)
    size = int.from_bytes(wire[40:44], 'little')
    core = wire[48:48 + size]
    assert core[:6] == b'URQS\x03\0'
    assert binascii.crc32(core[32:]) == int.from_bytes(core[28:32], 'little')
    path = output / (name + '.core.urs')
    path.write_bytes(core)
    player = library.Player(key)
    try:
        player.step('l:' + str(path))
        assert player.state == expected['state'], (key, name, player.state, expected['state'])
    finally:
        player.close()
    reference = Path(expected['core']).read_bytes()
    assert core[32:44] == reference[32:44], 'PC/RNG/pause mismatch'
    assert core[52:54] == reference[52:54], 'Procedure depth mismatch'
    context = int.from_bytes(core[58:60], 'little')
    reference_context = int.from_bytes(reference[58:60], 'little')
    assert context == reference_context, 'Text context length mismatch'
    assert not context or core[-context:] == reference[-context:], 'Text context mismatch'
    return {'bytes': len(wire), 'sha256': hashlib.sha256(wire).hexdigest(),
            'state_matches_host': True, 'rng_pause_depth_context_match': True}


def verify_grant(phase, phase_path, grant_path):
    assert grant_path is not None, 'A fresh finite Classic window is required'
    grant = json.loads(grant_path.read_text())
    assert grant['status'] == 'ROOT_EXPLICIT_PHASE_GO'
    assert grant['uid'] == phase['public_id'] == 'AEB505B6E0067623'
    assert grant['phase_sha256'] == sha(phase_path)
    now = time.time()
    assert grant['not_before_utc_epoch'] <= now < grant['start_before_utc_epoch'], 'Start window expired'
    assert grant['start_before_utc_epoch'] - grant['not_before_utc_epoch'] <= 300
    assert now + phase['maximum_run_seconds'] + phase['maximum_cleanup_seconds'] + 20 <= grant['finish_before_utc_epoch']
    return grant


def supervise(args):
    """The parent never opens CDC; prove the child has exited before RELEASE."""
    output = args.output_dir.resolve()
    phase_path = output / 'phase.json'
    phase = json.loads(phase_path.read_text())
    grant = verify_grant(phase, phase_path, args.grant)
    for path, digest in phase['pins'].items():
        assert sha(path) == digest, 'Changed phase input: ' + path
    binding = cdc_guard.current_binding(phase['port'])
    cdc_guard.require_no_holders(binding)
    closure = {'status': 'RUNNING', 'phase_sha256': sha(phase_path), 'grant_sha256': sha(args.grant),
               'os_binding': binding, 'named_holders_before': 'none', 'child_reaped': False}
    child = None
    try:
        command = [sys.executable, str(Path(__file__).resolve()), '--device', '--grant',
                   str(args.grant.resolve()), '--output-dir', str(output)]
        child = subprocess.Popen(command)
        closure['child_pid'] = child.pid
        seconds = min(phase['maximum_run_seconds'] + phase['maximum_cleanup_seconds'] + 10,
                      grant['finish_before_utc_epoch'] - time.time() - 10)
        try:
            code = child.wait(timeout=seconds)
        except BaseException:
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=5)
            raise
        closure.update(exit_code=code, child_reaped=True)
        report = json.loads((output / 'result.json').read_text())
        assert report['phase_sha256'] == sha(phase_path), 'Stale child report'
        assert report['fd_closed'], 'Child reported an unclosed descriptor'
        assert cdc_guard.current_binding(phase['port']) == binding, 'OS USB binding changed'
        cdc_guard.require_no_holders(binding)
        closure.update(postclose_named_holders='none', lease='released')
        assert code == 0 and report['result'] == 'PASS', 'Hardware checks failed; see result.json'
        closure['status'] = 'PASS'
    except BaseException as error:
        closure.update(status='HOLD', error=repr(error))
        raise
    finally:
        close_failure = None
        if child is not None and child.poll() is not None:
            closure.update(child_reaped=True, exit_code=child.returncode)
            try:
                assert cdc_guard.current_binding(phase['port']) == binding, 'OS USB binding changed'
                cdc_guard.require_no_holders(binding)
                closure.update(postclose_named_holders='none', lease='released')
            except BaseException as error:
                closure['status'] = 'HOLD'
                closure['close_error'] = repr(error)
                closure['lease'] = 'unreleased'
                close_failure = error
        write_json(output / 'closure.json', closure)
        if close_failure is not None and sys.exc_info()[1] is None:
            raise close_failure


def run(args):
    phase_path = args.output_dir.resolve() / 'phase.json'
    phase = json.loads(phase_path.read_text())
    assert re.fullmatch(r'[0-9A-F]{8}', phase['expected_build']), 'Prepare again with the granted current firmware CRC'
    assert phase['version'] == 1 and set(phase['games']) == set(library.SEMION_ROUTES)
    assert 0 < phase['maximum_run_seconds'] <= 1800 and 0 < phase['maximum_cleanup_seconds'] <= 60
    for path, digest in phase['pins'].items():
        assert sha(path) == digest, 'Changed phase input: ' + path
    grant = verify_grant(phase, phase_path, args.grant)
    binding = cdc_guard.current_binding(phase['port'])
    cdc_guard.require_no_holders(binding)
    library.HOST = Path(phase['host'])
    output = args.output_dir.resolve()
    report = {'phase_sha256': sha(phase_path), 'physical_key_test': False, 'lcd_readability_test': False,
              'input_source': 'USB Screen virtual matrix events on real Classic', 'games': {}, 'calculator_checks': [],
              'firmware_flashed': False, 'reset': False, 'format': False, 'clock_written': False}
    started = time.monotonic()
    port = None
    def expired(_signal, _frame):
        raise TimeoutError('Classic phase deadline expired')
    old_alarm = signal.signal(signal.SIGALRM, expired)
    old_term = signal.signal(signal.SIGTERM, expired)
    signal.alarm(phase['maximum_run_seconds'])
    try:
        assert time.time() < grant['start_before_utc_epoch'], 'Start window expired before CDC open'
        with BoundedScreenPort(phase['port'], started + phase['maximum_run_seconds']) as port:
            assert cdc_guard.current_binding(phase['port']) == binding, 'OS USB binding changed during open'
            descriptor, pathname = os.fstat(port.fd), os.stat(phase['port'])
            assert stat.S_ISCHR(descriptor.st_mode) and descriptor.st_rdev == pathname.st_rdev
            run = QuestRun(port, output, (output / 'footers.bin').read_bytes(), started + phase['maximum_run_seconds'])
            try:
                identity = port.command('identity')
                assert 'public=' + phase['public_id'] in identity and 'build=' + phase['expected_build'] in identity
                assert 'profile=classic-v3-uc1609' in identity
                report['identity'] = identity
                run.identity = identity
                report['health_before'] = {cmd: port.command(cmd, timeout=15) for cmd in ('df', 'crash show', 'ls /')}
                assert 'FIRMWARE CRC state=valid' in report['health_before']['df']
                assert 'CRASH none' in report['health_before']['crash show']
                report['apps'] = {}
                for name in ('URQ.APP', 'URQUI.APP'):
                    local = Path(phase['apps_dir']) / name
                    read_file(port, '/Apps/' + name, local.read_bytes())
                    report['apps'][name] = sha(local)
                if not phase['packages_installed']:
                    port.command('mkdir /URQ')
                for key, game in phase['games'].items():
                    remote = game['remote']
                    if not phase['packages_installed']:
                        port.command('mkdir "' + remote + '"')
                    for name, local in game['files'].items():
                        data = Path(local).read_bytes()
                        if not phase['packages_installed']:
                            write_file(port, remote + '/' + name, data)
                        read_file(port, remote + '/' + name, data)
                port.attach()
                report['calculator_precondition'] = run.check_calculator('before-first-game')
                assert report['calculator_precondition']['result'] == 'PASS', 'Calculator input owner precondition failed'
                for key, game in phase['games'].items():
                    print('Playing', key, flush=True)
                    model = library.Player(key)
                    run.steps = []
                    run.navigation = []
                    inventory_checked = False
                    try:
                        run.open(game['remote'], model.state['status'])
                        png(port.frames[-1], output / (key + '-title.png'))
                        for index, command in enumerate(game['route']):
                            run.choose(model, command, index)
                            if model.state['items'] and model.state['status'] == 1 and not inventory_checked:
                                run.inventory(key)
                                inventory_checked = True
                            if index == game['checkpoints']['middle']['index']:
                                png(port.frames[-1], output / (key + '-middle.png'))
                                run.save(game['save_slots']['middle'] - 1)
                                run.exit()
                                middle = verify_save(port, key, game['remote'] + '/slot%d.urs' % game['save_slots']['middle'],
                                                     key + '-middle', game['checkpoints']['middle'], output)
                                report['calculator_checks'].append({'game': key, 'point': 'middle',
                                    **run.check_calculator(key + '-middle')})
                                first = library.Player(key)
                                try:
                                    run.open(game['remote'], first.state['status'])
                                finally:
                                    first.close()
                                run.load(game['save_slots']['middle'] - 1, model.state['status'])
                        assert WINS[key] in model.text().lower()
                        png(port.frames[-1], output / (key + '-win.png'))
                        run.save(game['save_slots']['final'] - 1)
                        run.exit()
                        final = verify_save(port, key, game['remote'] + '/slot%d.urs' % game['save_slots']['final'],
                                            key + '-final', game['checkpoints']['final'], output)
                        report['calculator_checks'].append({'game': key, 'point': 'final',
                            **run.check_calculator(key + '-final')})
                        report['games'][key] = {'result': 'PASS', 'steps': run.steps,
                                               'middle_save': middle, 'final_save': final,
                                               'load_in_fresh_app_and_continue': True,
                                               'calculator_return': all(check['result'] == 'PASS' for check in report['calculator_checks'] if check['game'] == key),
                                               'inventory_screen': inventory_checked,
                                               'menu_navigation': run.navigation}
                        write_json(output / 'progress.json', report)
                    finally:
                        model.close()
                report['health_after'] = {cmd: port.command(cmd, timeout=15) for cmd in ('df', 'crash show', 'ls /URQ')}
                report['foreground_checks'] = run.foreground_checks
                assert 'FIRMWARE CRC state=valid' in report['health_after']['df']
                assert 'CRASH none' in report['health_after']['crash show']
                report['result'] = 'PASS' if all(check['result'] == 'PASS' for check in report['calculator_checks']) else 'FAIL'
                assert report['result'] == 'PASS', 'Independent calculator input checks failed; quest results retained'
            finally:
                signal.alarm(phase['maximum_cleanup_seconds'])
                original_error = sys.exc_info()[1]
                try:
                    if run.active:
                        run.abort()
                    if port.attached:
                        port.send(0x13)
                        port.attached = False
                        port.pump(.2)
                except BaseException as error:
                    report['cleanup_error'] = repr(error)
                    if original_error is None:
                        raise
    except BaseException as error:
        report.update(result='FAIL', error=repr(error))
        raise
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old_alarm)
        signal.signal(signal.SIGTERM, old_term)
        report['duration_seconds'] = round(time.monotonic() - started, 3)
        report['fd_closed'] = port is None or (port.fd < 0 and port.lock_fd < 0)
        write_json(output / 'result.json', report)
    print('Classic: three complete quests, midgame reloads, portable saves and calculator return PASS')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--prepare', action='store_true')
    mode.add_argument('--run', action='store_true')
    mode.add_argument('--device', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--grant', type=Path)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--port', default='/dev/cu.usbmodem2068336B47311')
    parser.add_argument('--public-id', default='AEB505B6E0067623')
    parser.add_argument('--build-crc', default='PENDING')
    parser.add_argument('--host', type=Path, default=ROOT / '.build/urq-tests/urq-host')
    parser.add_argument('--footer', type=Path, default=ROOT / '.build/urq-tests/urq-classic-footer')
    parser.add_argument('--apps-dir', type=Path, default=ROOT / 'tmp/urq/classic-ui-dist')
    parser.add_argument('--installed', action='store_true', help='Prepare verification of already installed packages')
    args = parser.parse_args()
    if args.prepare:
        prepare(args)
    elif args.device:
        run(args)
    else:
        supervise(args)


if __name__ == '__main__':
    main()
