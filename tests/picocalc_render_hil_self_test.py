#!/usr/bin/env python3
"""Exercise render HIL bounds and interrupted-run cleanup without a device."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import hil_picocalc_render_i2c_sd as hil


class Port:
    text = b''

    def __init__(self, failure):
        self.failure = failure
        self.commands_seen = []
        self.closed = False

    def expect(self, *args):
        return 'errors=25 IP=24 RUN=0 BUSY=0'

    def command(self, command):
        self.commands_seen.append(command)
        if command == 'prof':
            if self.failure == 'profile query':
                raise RuntimeError(self.failure)
            return 'PROFILE=STOPPED'
        return command

    def commands(self):
        pass

    def pump(self, seconds):
        if seconds == 3.2:
            raise RuntimeError(self.failure)

    def status(self):
        return self.expect()

    def __exit__(self, *args):
        self.closed = True


class RenderHilTest(unittest.TestCase):
    def test_sample_checks_deltas_and_card_limit(self):
        before = 'UI_SKIPS=5 I2C_IRQS=10 I2C_TIMEOUTS=0 I2C_ABORTS=25 SD_SPEED_FALLBACKS=1 SD_SPI_HZ=12500000'
        after = ('UI_SKIPS=35 I2C_IRQS=40 I2C_TIMEOUTS=0 I2C_ABORTS=25 SD_SPEED_FALLBACKS=1 '
                 'SD_SPI_HZ=12500000 SD_SAFE_HZ=12500000 SD_ADVERTISED_HZ=25000000')
        hil.stable_sample(before, after)
        for old, new in (('I2C_TIMEOUTS=0', 'I2C_TIMEOUTS=1'), ('I2C_ABORTS=25', 'I2C_ABORTS=26'),
                         ('SD_SPEED_FALLBACKS=1', 'SD_SPEED_FALLBACKS=2'),
                         ('SD_SPI_HZ=12500000', 'SD_SPI_HZ=20833333'),
                         ('SD_ADVERTISED_HZ=25000000', 'SD_ADVERTISED_HZ=1000000')):
            with self.assertRaises(AssertionError):
                hil.stable_sample(before, after.replace(old, new))

    def test_high_ip_uses_program_mode(self):
        p = Port('unused')
        with patch.object(hil, 'raw') as raw:
            hil.restore_ip(p, 104)
        self.assertEqual([call.args[1] for call in raw.call_args_list], [b'g99', b'fe', b'[[[[[', b'fn'])

    def test_interrupted_runs_restore_and_close(self):
        for failure in ('profile query', 'measurement'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / 'manifest.json').write_text(json.dumps({'build_id': '12345678', 'uf2_sha256': 'test'}))
                output = root / 'result'
                p = Port(failure)
                argv = ['hil', '--port', 'fake', '--uid', 'TEST', '--firmware-directory', str(root), '--output', str(output)]
                with patch.object(sys, 'argv', argv), patch.object(hil, 'connect', return_value=p), \
                     patch.object(hil, 'healthy'), patch.object(hil, 'calculator'), patch.object(hil, 'restore'), \
                     patch.object(hil, 'restore_ip') as restore_ip:
                    with self.assertRaisesRegex(RuntimeError, failure):
                        hil.main()
                restore_ip.assert_called_once_with(p, 24)
                self.assertEqual(p.commands_seen.count('prof stop'), int(failure == 'measurement'))
                self.assertTrue(p.closed)
                result = json.loads((output / 'result.json').read_text())
                self.assertFalse(result['passed'])
                self.assertTrue(result['calculator_state_restored'])


if __name__ == '__main__':
    unittest.main()
