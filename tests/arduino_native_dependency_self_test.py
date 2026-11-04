#!/usr/bin/env python3
"""Native Arduino header gates retain escaped Windows/Unix dependency paths."""
import unittest
from pathlib import Path
from check_standalone_sdk_build import include_paths, make_dependencies, check_paths


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


if __name__ == '__main__':
    unittest.main()
