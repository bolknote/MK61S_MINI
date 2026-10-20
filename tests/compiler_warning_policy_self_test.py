#!/usr/bin/env python3
"""Qualified SDK notices must not hide warnings from firmware or other SDKs."""

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
GCC = '/sdk/packages/STMicroelectronics/tools/xpack-arm-none-eabi-gcc/14.2.1-1.1/bin/arm-none-eabi-g++'
LIBRARY = GCC.rsplit('/', 1)[0] + '/../lib/gcc/arm-none-eabi/14.2.1'
STARTUP_WARNING = (
    LIBRARY + '/../../../../arm-none-eabi/bin/ld: warning: ' +
    LIBRARY + '/thumb/v7e-m+fp/hard/crtn.o: '
    'missing .note.GNU-stack section implies executable stack')
STRCPY_WARNING = STARTUP_WARNING.replace(
    LIBRARY + '/thumb/v7e-m+fp/hard/crtn.o', 'libc_a-strcpy.o')


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

    def test_startup_notice_requires_the_actual_pinned_toolchain(self):
        commands = [{'file': '/project/main.cpp', 'arguments': [GCC, '-c', 'main.cpp']}]
        self.assertEqual(unexpected_warnings(STARTUP_WARNING, commands), [])
        self.assertEqual(unexpected_warnings(STRCPY_WARNING, commands), [])
        windows = STARTUP_WARNING.replace('/sdk/', 'C:/SDK/').replace('/', '\\')
        commands[0]['arguments'][0] = GCC.replace('/sdk/', 'C:/SDK/').replace('/', '\\') + '.exe'
        self.assertEqual(unexpected_warnings(windows, commands), [])
        self.assertEqual(unexpected_warnings(STARTUP_WARNING, self.commands()), [STARTUP_WARNING])
        self.assertEqual(unexpected_warnings(STRCPY_WARNING, self.commands()), [STRCPY_WARNING])
        commands[0]['arguments'][0] = GCC.replace('14.2.1-1.1', '15.2.1-1.1')
        self.assertEqual(unexpected_warnings(STARTUP_WARNING, commands), [STARTUP_WARNING])

    def test_new_startup_or_project_assembly_warnings_are_rejected(self):
        commands = [{'file': '/project/main.cpp', 'command': f'"{GCC}" -c main.cpp'}]
        self.assertEqual(unexpected_warnings(STARTUP_WARNING, commands), [])
        for warning in (STARTUP_WARNING.replace('crtn.o', 'crtbegin.o'),
                        STRCPY_WARNING.replace('libc_a-strcpy.o', 'libc_a-unknown.o'),
                        STARTUP_WARNING.replace('14.2.1-1.1', '15.2.1-1.1'),
                        STARTUP_WARNING.replace('v7e-m+fp/hard', 'v6-m/nofp'),
                        STARTUP_WARNING.replace(LIBRARY + '/thumb/v7e-m+fp/hard/crtn.o',
                                                '/project/native_eabi_arm.S.o'),
                        STARTUP_WARNING.replace('missing .note.GNU-stack section implies executable stack',
                                                'unexpected startup condition')):
            self.assertEqual(unexpected_warnings(warning, commands), [warning])

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
