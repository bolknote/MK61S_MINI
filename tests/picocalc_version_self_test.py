#!/usr/bin/env python3
"""Execute the SDK version block against real and changed version.hpp inputs."""
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]


class VersionTests(unittest.TestCase):
    def test_sdk_reads_the_same_header_as_firmware_and_manifest(self):
        cmake=shutil.which('cmake')
        self.assertIsNotNone(cmake)
        source=(ROOT/'ports/picocalc/CMakeLists.txt').read_text()
        start=source.index('set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS')
        end=source.index('\n',source.index('pico_set_program_version(',start))
        block=source[start:end]
        self.assertIn('version.hpp',block)
        self.assertNotRegex(block,r'pico_set_program_version\([^\n]*"\d+\.\d+\.\d+"')
        with tempfile.TemporaryDirectory(prefix='mk61-pico-version-') as directory:
            path=Path(directory)
            wrapper='function(pico_set_program_version target value)\n  file(WRITE "${CMAKE_CURRENT_LIST_DIR}/result.txt" "${value}")\nendfunction()\n'+block+'\n'
            (path/'test.cmake').write_text(wrapper)
            current=(ROOT/'ports/picocalc/version.hpp').read_text()
            for header in (current,'namespace picocalc { constexpr char VERSION[]="12.34.567"; }'):
                (path/'version.hpp').write_text(header)
                subprocess.run([cmake,'-P',str(path/'test.cmake')],check=True,capture_output=True,text=True)
                expected=re.search(r'VERSION\[\]\s*=\s*"(\d+\.\d+\.\d+)"',header)[1]
                self.assertEqual((path/'result.txt').read_text(),expected)
            (path/'version.hpp').write_text('constexpr char VERSION[]="invalid";')
            result=subprocess.run([cmake,'-P',str(path/'test.cmake')],capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0)
            self.assertIn('semantic VERSION',result.stderr)


if __name__=='__main__':unittest.main()
