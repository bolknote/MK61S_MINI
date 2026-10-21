#!/usr/bin/env python3
"""Keep diagnostic source copying bounded when output is inside the repo."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from build_m0_math_compare import copy_snapshot


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory(prefix='mk61-math-snapshot-')
        self.addCleanup(self.temporary.cleanup)
        self.source = Path(self.temporary.name) / 'project'
        (self.source / 'code').mkdir(parents=True)
        (self.source / 'code/math.cpp').write_text('math source\n')
        cmake = self.source / 'ports/picocalc/CMakeLists.txt'
        cmake.parent.mkdir(parents=True)
        cmake.write_text('unmodified project configuration\n')

    def test_workspace_build_output_and_caches_are_not_copied(self):
        for name in ['.build', '.git', '__pycache__']:
            (self.source / name).mkdir()
            (self.source / name / 'sentinel').write_text('generated\n')
        output = self.source / '.build/timing'
        destination = output / 'source'
        output.mkdir()
        copy_snapshot(self.source, destination, output)
        self.assertEqual((destination / 'code/math.cpp').read_text(), 'math source\n')
        for name in ['.build', '.git', '__pycache__']:
            self.assertFalse((destination / name).exists())

    def test_arbitrary_nested_output_is_excluded_without_its_siblings(self):
        parent = self.source / 'measurements'
        parent.mkdir()
        (parent / 'kept.txt').write_text('source evidence\n')
        output = parent / 'comparison'
        output.mkdir()
        (output / 'result.json').write_text('{}\n')
        destination = output / 'source'
        copy_snapshot(self.source, destination, output)
        self.assertEqual((destination / 'measurements/kept.txt').read_text(),
                         'source evidence\n')
        self.assertFalse((destination / 'measurements/comparison').exists())

    def test_preserved_link_needs_only_reference_metadata(self):
        output = self.source / '.build/timing'
        destination = output / 'source'
        copy_snapshot(self.source, destination, output, reference_only=True)
        files = [p.relative_to(destination) for p in destination.rglob('*') if p.is_file()]
        self.assertEqual(files, [Path('ports/picocalc/CMakeLists.txt')])
        self.assertEqual((destination / files[0]).read_text(),
                         'unmodified project configuration\n')
        self.assertEqual((self.source / files[0]).read_text(),
                         'unmodified project configuration\n')

    def test_input_cannot_be_overwritten(self):
        with self.assertRaises(ValueError):
            copy_snapshot(self.source, self.source, self.source.parent)


if __name__ == '__main__':
    unittest.main()
