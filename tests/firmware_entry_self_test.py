#!/usr/bin/env python3
"""Exercise both public launcher adapters and the PicoCalc build sequence."""
import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('pico_firmware', ROOT / 'tools/firmware/picocalc/firmware.py')
pico = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pico)


class FirmwareEntryTest(unittest.TestCase):
    def launchers(self):
        if shutil.which('bash'):
            yield ['bash', str(ROOT / 'tools/mk61-firmware.cmd')]
        if shutil.which('pwsh'):
            yield ['pwsh', '-NoLogo', '-NoProfile', '-File',
                   str(ROOT / 'tools/firmware/cli/mk61-firmware.ps1')]

    def test_dispatch_outside_checkout(self):
        with tempfile.TemporaryDirectory(prefix='mk61 launcher ') as directory:
            for launcher in self.launchers():
                with self.subTest(launcher=launcher[0]):
                    targets = subprocess.run([*launcher, '--list-targets'], cwd=directory,
                                             capture_output=True, text=True)
                    self.assertEqual(targets.returncode, 0, targets.stderr)
                    self.assertIn('stm32', targets.stdout)
                    self.assertIn('picocalc-pico-h', targets.stdout)
                    for target in ('stm32', 'picocalc-pico-h'):
                        result = subprocess.run([*launcher, '--target', target, '--list-profiles'],
                                                cwd=directory, capture_output=True, text=True)
                        self.assertEqual(result.returncode, 0, result.stderr)
                        self.assertIn('classic-v3' if target == 'stm32' else 'picocalc-pico-h', result.stdout)
                    for arguments in (['--target'], ['--target', 'unknown', '--build']):
                        result = subprocess.run([*launcher, *arguments], cwd=directory,
                                                capture_output=True, text=True)
                        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)

    def test_build_and_package_use_one_output_directory(self):
        with mock.patch.object(pico.subprocess, 'run') as run:
            self.assertEqual(pico.main(['--build', '--package', '--fetch-sdk',
                '--output-dir', '/tmp/pico output', '--build-path', '/tmp/pico build',
                '--toolchain', '/tmp/arm tools', '--rustc', '/tmp/rust compiler']), 0)
        commands = [call.args[0] for call in run.call_args_list]
        self.assertEqual([Path(command[1]).name for command in commands],
                         ['build_picocalc.py', 'build_picocalc_apps.py', 'package_picocalc.py'])
        self.assertIn('/tmp/pico output', commands[0])
        self.assertIn('/tmp/pico output/apps', commands[1])
        self.assertIn('/tmp/pico output', commands[2])
        self.assertIn('--fetch-sdk', commands[0])
        for command in commands[:2]:
            self.assertIn('/tmp/arm tools', command)
        self.assertIn('/tmp/rust compiler', commands[1])

    def test_failure_stops_before_apps_or_packaging(self):
        with mock.patch.object(pico.subprocess, 'run',
                               side_effect=subprocess.CalledProcessError(7, 'compiler')) as run:
            self.assertEqual(pico.main(['--build', '--package']), 7)
            self.assertEqual(run.call_count, 1)

    def test_package_does_not_rebuild_firmware(self):
        with mock.patch.object(pico.subprocess, 'run') as run:
            self.assertEqual(pico.main(['--package']), 0)
            self.assertEqual(run.call_count, 1)
            self.assertEqual(Path(run.call_args.args[0][1]).name, 'package_picocalc.py')


if __name__ == '__main__':
    unittest.main()
