#!/usr/bin/env python3
"""Native Arduino header gates retain escaped Windows/Unix dependency paths."""
import unittest
import json
import tempfile
from pathlib import Path
from unittest import mock
from check_standalone_sdk_build import include_paths, make_dependencies, check_paths, check


class Dependencies(unittest.TestCase):
    def test_both_include_argument_formats(self):
        self.assertEqual(include_paths(['cc', '-I/one', '-I', '/two with spaces',
            '-isystem', '/three']), [Path('/one'), Path('/two with spaces'), Path('/three')])

    def test_make_escapes_and_continuations(self):
        values = make_dependencies('C:/build/core.o: C:/source/core.c \\\n C:/Arduino\\ IDE/cores/mk61/Arduino.h C\\:/native/sdk.h\n')
        self.assertEqual(values, ['C:/source/core.c', 'C:/Arduino IDE/cores/mk61/Arduino.h', 'C:/native/sdk.h'])
        check_paths(values)

    def test_vendor_paths_cannot_hide_in_make_escaping(self):
        for path in ('C:/Users/Name/AppData/Local/Arduino15/packages/STMicroelectronics/Core.h',
                     '/tmp/foreign/cores/arduino/Arduino.h',
                     '/tmp/foreign/libraries/SrcWrapper/HAL.c'):
            with self.subTest(path=path), self.assertRaises(ValueError):
                check_paths(make_dependencies('object.o: ' + path + '\n'))

    def test_utf8_build_metadata_under_windows_ansi_default(self):
        with tempfile.TemporaryDirectory(prefix='mk61 SDK Роман ') as temporary:
            root = Path(temporary)
            sdk = root / 'system/stm32f4'
            (sdk / 'cmsis/include').mkdir(parents=True)
            (sdk / 'manifest.json').write_text('{}', encoding='utf-8')
            source, output = root / 'source.cpp', root / 'source.cpp.o'
            database = root / 'compile_commands.json'
            database.write_text(json.dumps([{'file': str(source), 'arguments': [
                'gcc', '-I', str(sdk / 'cmsis/include'), '-c', str(source), '-o', str(output)]}],
                ensure_ascii=False), encoding='utf-8')
            escaped = str(source).replace('\\', '/').replace(' ', '\\ ')
            output.with_suffix('.d').write_text('object.o: ' + escaped + '\n', encoding='utf-8')
            original_read = Path.read_text

            def ansi_default(path, *args, **kwargs):
                if not args and 'encoding' not in kwargs:
                    kwargs['encoding'] = 'cp1252'
                return original_read(path, *args, **kwargs)

            with mock.patch.object(Path, 'read_text', ansi_default):
                self.assertEqual(check(database, arduino=True), sdk)


if __name__ == '__main__':
    unittest.main()
