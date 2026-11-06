"""Grant and USB release failures must stop before the next hardware owner."""
import argparse
import copy
import json
from pathlib import Path
import tempfile
import subprocess
import sys
import time
from types import SimpleNamespace
import unittest
from unittest import mock

import hil_urq_semion as hil
import hil_classic_cdc_guard as guard

FOOTER_TOOL = hil.ROOT / '.build/urq-tests/ryu/urq-classic-footer'

class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='urq-controller-')
        self.addCleanup(self.temporary.cleanup)
        self.output = Path(self.temporary.name)
        self.phase = {'public_id': 'AEB505B6E0067623', 'port': '/dev/exact',
                      'maximum_run_seconds': 1800, 'maximum_cleanup_seconds': 60, 'pins': {}}
        self.grant = {'status': 'ROOT_EXPLICIT_PHASE_GO', 'uid': self.phase['public_id'],
                      'not_before_utc_epoch': 990, 'start_before_utc_epoch': 1100,
                      'finish_before_utc_epoch': 4000}
        self.args = SimpleNamespace(output_dir=self.output, grant=self.output / 'grant.json')
        self.phase_path = self.output / 'phase.json'
        self.save()
        self.addCleanup(mock.patch.stopall)
        mock.patch.object(hil.time, 'time', return_value=1000).start()
        self.binding = mock.patch.object(hil.cdc_guard, 'current_binding', return_value={'usb': 'exact'}).start()
        self.holders = mock.patch.object(hil.cdc_guard, 'require_no_holders').start()
        self.device = mock.patch.object(hil, 'BoundedScreenPort', side_effect=AssertionError('CDC opened in parent')).start()
        self.child = mock.Mock(pid=12345, returncode=0)
        self.child.wait.return_value = self.child.poll.return_value = 0
        self.spawn = mock.patch.object(hil.subprocess, 'Popen', return_value=self.child).start()

    def save(self):
        self.phase_path.write_text(json.dumps(self.phase))
        self.grant['phase_sha256'] = hil.sha(self.phase_path)
        self.args.grant.write_text(json.dumps(self.grant))
        (self.output / 'result.json').write_text(json.dumps(
            {'result': 'PASS', 'fd_closed': True, 'phase_sha256': hil.sha(self.phase_path)}))

    def test_expired_window_never_queries_or_opens_device(self):
        self.grant['start_before_utc_epoch'] = 999
        self.save()
        with self.assertRaisesRegex(AssertionError, 'expired'):
            hil.supervise(self.args)
        self.binding.assert_not_called()
        self.spawn.assert_not_called()
        self.device.assert_not_called()

    def test_changed_source_never_queries_or_opens_device(self):
        source = self.output / 'source.py'
        source.write_text('changed')
        self.phase['pins'][str(source)] = '0' * 64
        self.save()
        with self.assertRaisesRegex(AssertionError, 'Changed phase input'):
            hil.supervise(self.args)
        self.binding.assert_not_called()
        self.spawn.assert_not_called()

    def test_existing_holder_prevents_child_start(self):
        self.holders.side_effect = AssertionError('Existing owner')
        with self.assertRaisesRegex(AssertionError, 'Existing owner'):
            hil.supervise(self.args)
        self.spawn.assert_not_called()

    def test_success_requires_reap_and_os_release(self):
        hil.supervise(self.args)
        result = json.loads((self.output / 'closure.json').read_text())
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(result['exit_code'], 0)
        self.assertTrue(result['child_reaped'])
        self.assertEqual(result['postclose_named_holders'], 'none')
        self.assertEqual(result['lease'], 'released')
        self.child.wait.assert_called_once()
        self.device.assert_not_called()

    def test_failed_checks_release_port_but_never_pass(self):
        self.child.wait.return_value = self.child.poll.return_value = self.child.returncode = 1
        with self.assertRaisesRegex(AssertionError, 'Hardware checks failed'):
            hil.supervise(self.args)
        result = json.loads((self.output / 'closure.json').read_text())
        self.assertEqual((result['status'], result['lease']), ('HOLD', 'released'))
        self.assertTrue(result['child_reaped'])

    def test_late_holder_cannot_leave_successful_release(self):
        self.holders.side_effect = [None, None, AssertionError('Late holder')]
        with self.assertRaisesRegex(AssertionError, 'Late holder'):
            hil.supervise(self.args)
        result = json.loads((self.output / 'closure.json').read_text())
        self.assertEqual((result['status'], result['lease']), ('HOLD', 'unreleased'))


class BindingTests(unittest.TestCase):
    def fixture(self):
        serial = '2068336B4731'
        path = '/dev/cu.usbmodem' + serial + '1'
        tree = [{'IOObjectClass': 'IOUSBHostDevice', 'USB Serial Number': serial,
                 'idVendor': 0x0483, 'idProduct': 0x5740, 'IORegistryEntryID': 1,
                 'IORegistryEntryChildren': [{'IOObjectClass': 'IOUSBHostInterface', 'USB Serial Number': serial,
                 'IORegistryEntryChildren': [{'IOObjectClass': 'AppleUSBACMData',
                 'IORegistryEntryChildren': [{'IOObjectClass': 'IOSerialBSDClient',
                 'IORegistryEntryID': 2, 'IOCalloutDevice': path,
                 'IODialinDevice': path.replace('/cu.', '/tty.')}]}]}]}]
        return tree, path

    def test_exact_binding_and_wrong_usb_serial(self):
        tree, path = self.fixture()
        binding = guard.os_binding(tree, path)
        self.assertEqual(binding['usb'], '2068336B4731')
        tree[0]['USB Serial Number'] = 'other'
        with self.assertRaises(AssertionError):
            guard.os_binding(tree, path)

    def test_duplicate_binding_and_wrong_tty_are_rejected(self):
        tree, path = self.fixture()
        with self.assertRaises(AssertionError):
            guard.os_binding(tree + copy.deepcopy(tree), path)
        leaf = tree[0]['IORegistryEntryChildren'][0]['IORegistryEntryChildren'][0]['IORegistryEntryChildren'][0]
        leaf['IODialinDevice'] = '/dev/tty.other'
        with self.assertRaises(AssertionError):
            guard.os_binding(tree, path)


class FrameTests(unittest.TestCase):
    def foreground_run(self, directory, initial, exit_works=True):
        zero = (hil.CALCULATOR_FIXTURES / 'calculator_0.raw').read_bytes()
        menu = (hil.CALCULATOR_FIXTURES / 'system_menu.raw').read_bytes()

        class Port:
            def __init__(self):
                self.frames = [initial]
                self.current = initial
                self.keys = []

            def send(self, kind):
                if kind != 0x16:
                    raise AssertionError('Unexpected protocol message')
                self.frames.append(self.current)

            def key(self, key):
                self.keys.append(key)
                if key == hil.ESC and exit_works and hil.canonical(self.current) == hil.canonical(menu):
                    self.current = zero
                    self.frames.append(zero)

            def pump(self, _duration):
                time.sleep(.001)

        port = Port()
        run = hil.QuestRun(port, directory, bytes(960), time.monotonic() + 2)
        return run, port

    def test_known_system_menu_uses_exactly_one_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            menu = (hil.CALCULATOR_FIXTURES / 'system_menu.raw').read_bytes()
            run, port = self.foreground_run(Path(directory), menu)
            run.normalise_foreground('known', .05)
            self.assertEqual(port.keys, [hil.ESC])
            self.assertTrue(run.foreground_checks[-1]['fresh_stopped_calculator'])

    def test_calculator_foreground_does_not_receive_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            zero = (hil.CALCULATOR_FIXTURES / 'calculator_0.raw').read_bytes()
            run, port = self.foreground_run(Path(directory), zero)
            run.normalise_foreground('known', .05)
            self.assertEqual(port.keys, [])

    def test_unknown_foreground_receives_no_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            run, port = self.foreground_run(Path(directory), bytes(1536))
            with self.assertRaises(TimeoutError):
                run.normalise_foreground('unknown', .01)
            self.assertEqual(port.keys, [])

    def test_escape_is_never_retried(self):
        with tempfile.TemporaryDirectory() as directory:
            menu = (hil.CALCULATOR_FIXTURES / 'system_menu.raw').read_bytes()
            run, port = self.foreground_run(Path(directory), menu, False)
            with self.assertRaises(TimeoutError):
                run.normalise_foreground('stuck', .01)
            self.assertEqual(port.keys, [hil.ESC])

    def test_calculator_status_excludes_only_the_source_mnemonic_area(self):
        zero = (hil.CALCULATOR_FIXTURES / 'calculator_0.raw').read_bytes()
        changed = bytearray(zero)
        changed[120] ^= 1
        changed[192 + 120] ^= 1
        self.assertEqual(hil.calculator_status(zero), hil.calculator_status(changed))
        changed[119] ^= 1
        self.assertNotEqual(hil.calculator_status(zero), hil.calculator_status(changed))

    def test_failed_numeric_check_continues_only_with_confirmed_foreground(self):
        with tempfile.TemporaryDirectory() as directory:
            frame = (hil.CALCULATOR_FIXTURES / 'calculator_0.raw').read_bytes()
            identity = 'public=AEB505B6E0067623 usb=2068336B4731 build=6186AE4B profile=classic-v3-uc1609'
            port = SimpleNamespace(frames=[frame], command=mock.Mock(return_value=identity))
            run = hil.QuestRun(port, Path(directory), bytes(960), time.monotonic() + 2)
            run.identity = identity
            run.last_number_wait = {'fresh_frame_required': True}
            with mock.patch.object(run, 'calculator', side_effect=hil.CalculatorInputError('wrong value')):
                result = run.check_calculator('failed')
            self.assertEqual(result['result'], 'FAIL')
            self.assertTrue(result['stopped_calculator_and_terminal_confirmed'])
            port.command.assert_called_once_with('identity')

    def test_unknown_foreground_stops_after_numeric_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            frame = bytearray((hil.CALCULATOR_FIXTURES / 'calculator_0.raw').read_bytes())
            frame[0] ^= 1
            port = SimpleNamespace(frames=[bytes(frame)], command=mock.Mock())
            run = hil.QuestRun(port, Path(directory), bytes(960), time.monotonic() + 2)
            with mock.patch.object(run, 'calculator', side_effect=hil.CalculatorInputError('wrong value')):
                with self.assertRaisesRegex(AssertionError, 'Unknown or running'):
                    run.check_calculator('failed')
            port.command.assert_not_called()

    def test_transport_failure_is_not_collected_as_a_numeric_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            frame = (hil.CALCULATOR_FIXTURES / 'calculator_0.raw').read_bytes()
            port = SimpleNamespace(frames=[frame], command=mock.Mock(side_effect=TimeoutError('transport')))
            run = hil.QuestRun(port, Path(directory), bytes(960), time.monotonic() + 2)
            with mock.patch.object(run, 'calculator', side_effect=hil.CalculatorInputError('wrong value')):
                with self.assertRaisesRegex(TimeoutError, 'transport'):
                    run.check_calculator('failed')

    def numeric_run(self, directory, mode):
        zero = (hil.CALCULATOR_FIXTURES / 'calculator_0.raw').read_bytes()
        value = (hil.CALCULATOR_FIXTURES / 'calculator_123.raw').read_bytes()

        class Frames:
            def __init__(self):
                self.frames = [value if mode == 'noevent' else zero]
                self.pumps = 0

            def pump(self, _duration):
                self.pumps += 1
                if mode == 'delayed':
                    self.frames.append(value if self.pumps >= 3 else zero)
                elif mode == 'wrong':
                    self.frames.append(zero)
                time.sleep(.001)

        port = Frames()
        run = hil.QuestRun(port, directory, bytes(960), time.monotonic() + 2)
        return run, hil.number_field(value)

    def test_delayed_exact_x123_is_accepted_after_fresh_frame(self):
        with tempfile.TemporaryDirectory() as directory:
            run, value = self.numeric_run(Path(directory), 'delayed')
            result = run.wait_number(1, value, .1)
            self.assertEqual(hil.number_field(result), value)
            self.assertGreaterEqual(run.p.pumps, 3)

    def test_fresh_wrong_numeric_value_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            run, value = self.numeric_run(Path(directory), 'wrong')
            with self.assertRaises(hil.CalculatorInputError):
                run.wait_number(1, value, .01)

    def test_old_x123_without_new_event_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            run, value = self.numeric_run(Path(directory), 'noevent')
            with self.assertRaises(hil.CalculatorInputError):
                run.wait_number(1, value, .01)

    def test_real_disk_overlay_frames_keep_menu_and_selection_equal(self):
        folder = hil.ROOT / 'tests/fixtures/urq/classic_menu'
        on = (folder / 'disk_on.raw').read_bytes()
        off = (folder / 'disk_off.raw').read_bytes()
        self.assertEqual(len(on), 1536)
        self.assertNotEqual(on, off)
        self.assertEqual(hil.canonical(on), hil.canonical(off))
        # Pixels immediately outside the documented 16x16 badge stay strict.
        # Top and right touch the screen edge; left and bottom have real
        # neighbouring pixels, including both corners below the badge.
        for index in (0, 175, 192, 367, 384, 560, 575, 1535):
            changed = bytearray(off)
            changed[index] ^= 1
            self.assertNotEqual(hil.canonical(off), hil.canonical(changed), index)

    def test_inventory_header_cannot_be_mistaken_for_main_menu(self):
        hints = subprocess.check_output([str(FOOTER_TOOL)])
        self.assertEqual(len(hints), 7 * 192)
        menu = hints[5 * 192:6 * 192] + bytes(7 * 192)
        inventory = hints[6 * 192:7 * 192] + bytes(7 * 192)
        # The old heuristic accepted both, including the previous inventory.
        self.assertGreater(sum(byte == 255 for byte in menu[:176]), 90)
        self.assertGreater(sum(byte == 255 for byte in inventory[:176]), 90)
        run = hil.QuestRun(None, Path('/unused'), hints, time.monotonic() + 2)
        self.assertTrue(run.main_menu(menu))
        self.assertFalse(run.main_menu(inventory))

    def test_wait_rechecks_predicate_after_receiving_more_frames(self):
        class Frames:
            def __init__(self):
                self.frames = [b'expected']
                self.pumps = 0

            def pump(self, _duration):
                self.pumps += 1
                if self.pumps == 1:
                    self.frames.append(b'intermediate')
                elif self.pumps == 2:
                    self.frames.append(b'expected')

        port = Frames()
        run = hil.QuestRun(port, Path('/unused'), bytes(960), time.monotonic() + 2)
        self.assertEqual(run.wait(0, lambda frame: frame == b'expected'), b'expected')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--footer', type=Path, default=FOOTER_TOOL)
    options, remaining = parser.parse_known_args()
    FOOTER_TOOL = options.footer.resolve()
    unittest.main(argv=[sys.argv[0], *remaining])
