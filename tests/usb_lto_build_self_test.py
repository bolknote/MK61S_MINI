#!/usr/bin/env python3
"""Test both Arduino USB prelink adapters and the actual-call ELF gate."""
import importlib.util
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
HERE = Path(__file__).resolve()
SOURCES = ('src/cdc/usbd_cdc.c', 'src/usbd_conf.c')


def fake_compiler(arguments):
    if len(arguments) == 1 and arguments[0].startswith('@'):
        arguments = shlex.split(Path(arguments[0][1:]).read_text())
    if arguments and arguments[0] == '--fake-compiler':
        arguments = arguments[1:]
    if '--fail' in arguments:
        return 9
    destination = Path(arguments[arguments.index('-o') + 1])
    destination.write_text(json.dumps(arguments))
    return 0


class UsbLtoBuildTest(unittest.TestCase):
    def exercise(self, powershell=False, fail=False):
        with tempfile.TemporaryDirectory(prefix='mk61 usb lto ') as temporary:
            base = Path(temporary)
            build = base / 'build with spaces'
            library = base / 'core with spaces' / 'USBDevice'
            objects = []
            for source in SOURCES:
                path = library / source
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()
                obj = build / 'libraries' / 'USBDevice' / (Path(source).name + '.o')
                obj.parent.mkdir(parents=True, exist_ok=True)
                obj.write_text('original LTO object')
                objects.append(obj)
            suffix = 'ps1' if powershell else 'py'
            helper = ROOT / 'tools' / '.mk61-gcc' / ('protect-usb-lto.' + suffix)
            fake = base / 'fake compiler'
            shutil.copyfile(HERE, fake)
            fake.chmod(0o755)
            launcher = ([shutil.which('pwsh'), '-NoLogo', '-NoProfile', '-File']
                        if powershell else [sys.executable])
            options = ['-c', '-flto', '-Os', '-DNAME="space value"', '-I' + str(library)]
            if fail:
                options.append('--fail')
            result = subprocess.run([*launcher, str(helper), str(build), str(library),
                                     str(fake), '--fake-compiler', *options],
                                    capture_output=True, text=True)
            if fail:
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(objects[0].read_text(), 'original LTO object')
                return
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            for source, obj in zip(SOURCES, objects):
                self.assertEqual(json.loads(obj.read_text()),
                                 options + ['-fno-lto', str(library / source), '-o', str(obj)])
            self.assertEqual(result.stdout.count('USB LTO barrier:'), 2)

    def test_native(self):
        self.exercise()

    def test_native_failure(self):
        self.exercise(fail=True)

    @unittest.skipUnless(shutil.which('pwsh'), 'PowerShell unavailable')
    def test_powershell(self):
        self.exercise(powershell=True)

    @unittest.skipUnless(shutil.which('pwsh'), 'PowerShell unavailable')
    def test_powershell_failure(self):
        self.exercise(powershell=True, fail=True)

    def test_elf_call_gate(self):
        spec = importlib.util.spec_from_file_location('gate', ROOT / 'tests/check_usb_cdc_rx_elf.py')
        gate = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gate)
        protected = ' 8032aaa: f7fb fbb2 bl 802e212 <__wrap_USBD_CDC_ClearBuffer>\n'
        unprotected = ' 8033f52: f7ff ffc9 bl 8033ee8 <USBD_CDC_ClearBuffer>\n'
        gate.check(protected)
        for invalid in (unprotected, protected + unprotected,
                        '0802e0e6 <__wrap_USBD_CDC_ClearBuffer>:\n'):
            with self.assertRaises(ValueError):
                gate.check(invalid)


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1].startswith('@'):
        raise SystemExit(fake_compiler(sys.argv[1:]))
    if len(sys.argv) > 1 and sys.argv[1] == '--fake-compiler':
        raise SystemExit(fake_compiler(sys.argv[2:]))
    unittest.main()
