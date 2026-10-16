#!/usr/bin/env python3
"""The expected disabled-tone notice must not hide other Core warnings."""

import unittest
import json
from pathlib import Path
import subprocess
import sys
import tempfile

from check_compiler_warnings import unexpected_warnings


SOURCE = '/sdk/packages/STMicroelectronics/hardware/stm32/2.12.0/cores/arduino/Tone.cpp'
EXPECTED = (SOURCE + ':135:2: warning: #warning '
            '"TIMER_TONE or HAL_TIM_MODULE_ENABLED not defined" [-Wcpp]')


class CompilerWarningPolicyTest(unittest.TestCase):
    def commands(self, flags=('-DHAL_TIM_MODULE_ONLY', '-flto'), source=SOURCE):
        return [{'file': source, 'arguments': ['arm-none-eabi-g++', *flags]}]

    def test_pinned_notice_requires_actual_disabled_timer_wrapper(self):
        self.assertEqual(unexpected_warnings(EXPECTED, self.commands()), [])
        self.assertEqual(unexpected_warnings(EXPECTED, self.commands(('-flto',))),
                         [EXPECTED])
        windows = EXPECTED.replace('/', '\\')
        self.assertEqual(unexpected_warnings(windows, self.commands(
            source=SOURCE.replace('/', '\\'))), [])

    def test_new_tone_warning_or_different_source_is_rejected(self):
        for warning in (EXPECTED.replace('TIMER_TONE or HAL_TIM_MODULE_ENABLED not defined',
                                        'unfamiliar timer configuration'),
                        EXPECTED.replace(':135:2:', ':136:2:'),
                        EXPECTED.replace('/2.12.0/', '/2.13.0/'),
                        EXPECTED.replace(SOURCE, '/project/Tone.cpp')):
            self.assertEqual(unexpected_warnings(warning, self.commands()), [warning])

    def test_other_compiler_warnings_remain_errors(self):
        unknown = '/project/sound_driver.cpp:1:2: warning: unused variable [-Wunused]'
        lto = 'lto-wrapper: warning: using serial compilation of 12 LTRANS jobs'
        self.assertEqual(unexpected_warnings(EXPECTED + '\n' + unknown,
                                            self.commands()), [unknown])
        self.assertEqual(unexpected_warnings(lto, self.commands()), [])
        self.assertEqual(unexpected_warnings(lto, self.commands(('-Os',))), [lto])

    def test_cmake_command_form_preserves_warning_policy(self):
        lto = 'lto-wrapper: warning: using serial compilation of 12 LTRANS jobs'
        commands = [{'file': '/project/terminal.cpp',
                     'command': 'arm-none-eabi-g++ -Os -flto -c terminal.cpp'}]
        self.assertEqual(unexpected_warnings(lto, commands), [])
        self.assertEqual(unexpected_warnings(EXPECTED, commands), [EXPECTED])

    def test_release_gate_rejects_unfamiliar_tone_notice(self):
        with tempfile.TemporaryDirectory(prefix='mk61-warning-policy-') as temporary:
            root = Path(temporary)
            database = root / 'compile_commands.json'
            database.write_text(json.dumps(self.commands()))
            log = root / 'compile.log'
            checker = Path(__file__).with_name('check_compiler_warnings.py')
            command = [sys.executable, str(checker), '--log', str(log),
                       '--compile-commands', str(database)]
            log.write_text(EXPECTED + '\n')
            self.assertEqual(subprocess.run(command, capture_output=True).returncode, 0)
            log.write_text(EXPECTED + '\n' + EXPECTED.replace(
                'TIMER_TONE or HAL_TIM_MODULE_ENABLED not defined', 'unexpected Tone condition'))
            rejected = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(rejected.returncode, 1)
            self.assertIn('unexpected Tone condition', rejected.stderr)


if __name__ == '__main__':
    unittest.main()
