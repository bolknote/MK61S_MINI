#!/usr/bin/env python3
"""Reference builds must preserve omitted, board-dependent config defaults."""
from pathlib import Path
import runpy
import shlex
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
resolve = runpy.run_path(str(ROOT / 'tools/.mk61-gcc/build-standalone.py'))['reference_features']

class ReferenceDefaults(unittest.TestCase):
    def test_implicit_board_defaults_and_command_forms(self):
        compiler = shutil.which('c++')
        if not compiler:
            self.skipTest('C++ preprocessor unavailable')
        with tempfile.TemporaryDirectory(prefix='MK61 reference defaults ') as directory:
            root = Path(directory)
            source = root / 'terminal.cpp'
            source.write_text('unused: reference preprocessing reads config.h')
            (root / 'config.h').write_text('#ifndef FEATURE\n#define FEATURE BOARD\n#endif\n')
            output, dependency = root / 'must not exist.o', root / 'must not exist.d'
            for board in ('0', '1'):
                for form in ('arguments', 'command'):
                    with self.subTest(board=board, form=form):
                        command = [compiler, '-DBOARD='+board, '-flto', '-MMD',
                                   '-MF', str(dependency), '-c', str(source), '-o', str(output)]
                        entry = {'file': str(source), form: command if form=='arguments'
                                 else shlex.join(command)}
                        self.assertEqual(resolve(entry, ['FEATURE','MK61_ENABLE_LTO']),
                                         {'FEATURE':board,'MK61_ENABLE_LTO':'1'})
                        self.assertFalse(output.exists())
                        self.assertFalse(dependency.exists())
            command = [compiler, '-DBOARD=0', '-DFEATURE=1', '-c', str(source), '-o', str(output)]
            self.assertEqual(resolve({'file':str(source),'arguments':command},
                                     ['FEATURE','MK61_ENABLE_LTO']),
                             {'FEATURE':'1','MK61_ENABLE_LTO':'0'})

if __name__ == '__main__':
    unittest.main()
