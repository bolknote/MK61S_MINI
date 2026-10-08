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
            options = ['-c', '-flto', '-Os', '-DNAME="space value"', '-I' + str(library),
                       '-IC:/Program Files/STM32/USBDevice/inc',
                       '-Id:/Arduino/core/inc', r'-IE:\Arduino core\USBDevice\inc',
                       '-I', 'F:/separate include option']
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
            expected = [arg.replace('\\', '/') for arg in options] if powershell else options
            for source, obj in zip(SOURCES, objects):
                self.assertEqual(json.loads(obj.read_text()),
                                 expected + ['-fno-lto', str(library / source), '-o', str(obj)])
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

    @unittest.skipUnless(shutil.which('pwsh'), 'PowerShell unavailable')
    def test_powershell_linker_paths(self):
        with tempfile.TemporaryDirectory(prefix='mk61 link paths ') as temporary:
            base = Path(temporary)
            fake = base / 'fake compiler'
            shutil.copyfile(HERE, fake)
            fake.chmod(0o755)
            output = base / 'firmware.elf'
            flags = ['-LC:/Build with spaces', '-L', 'D:/separate library option',
                     '-Wl,--default-script=C:/Build with spaces/mk61-portable.ld',
                     r'-Wl,--script=C:\Arduino core\system\ldscript.ld',
                     '-Wl,-Map,C:/Build with spaces/code.ino.map',
                     '-Wl,--wrap=USBD_CDC_ClearBuffer', r'C:\Build\code.ino.cpp.o',
                     '-o', str(output)]
            helper = ROOT / 'tools/.mk61-arduino-board/hardware/mk61/stm32/tools/mk61-safe-tool.ps1'
            result = subprocess.run([
                shutil.which('pwsh'), '-NoLogo', '-NoProfile', '-File', str(helper),
                str(base), str(fake), '--fake-compiler', *flags,
            ], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(json.loads(output.read_text()),
                             [arg.replace('\\', '/') for arg in flags])

    @unittest.skipUnless(shutil.which('pwsh') and shutil.which('cc'),
                         'PowerShell or C compiler unavailable')
    def test_powershell_compiles_with_windows_include_path(self):
        with tempfile.TemporaryDirectory(prefix='mk61 usb headers ') as temporary:
            base = Path(temporary)
            # On POSIX this is a relative directory named C:. The same native
            # -File argument parsing that breaks Windows drives happens here,
            # without needing a Windows runner to reproduce the missing header.
            include = (base / 'STM32 core/USBDevice/inc' if sys.platform == 'win32'
                       else Path('C:/STM32 core/USBDevice/inc'))
            (base / include).mkdir(parents=True)
            (base / include / 'usbd_cdc.h').write_text('#define USB_HEADER_OK 42\n')
            build = base / 'build'
            library = base / 'USBDevice'
            objects = []
            for source in SOURCES:
                path = library / source
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('#include "usbd_cdc.h"\n'
                                '_Static_assert(USB_HEADER_OK == 42, "header");\n'
                                '_Static_assert(sizeof(NAME) == 12, "macro quotes");\n'
                                'int usb_test(void) { return USB_HEADER_OK; }\n')
                obj = build / 'libraries' / 'USBDevice' / (path.name + '.o')
                obj.parent.mkdir(parents=True, exist_ok=True)
                obj.write_bytes(b'original LTO object')
                objects.append(obj)
            result = subprocess.run([
                shutil.which('pwsh'), '-NoLogo', '-NoProfile', '-File',
                str(ROOT / 'tools/.mk61-gcc/protect-usb-lto.ps1'),
                str(build), str(library), shutil.which('cc'),
                '-c', '-flto', '-std=c11', '-DNAME="space value"', '-I' + str(include),
            ], cwd=base, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            for obj in objects:
                self.assertNotEqual(obj.read_bytes(), b'original LTO object')
                self.assertGreater(obj.stat().st_size, 100)
            self.assertEqual(result.stdout.count('USB LTO barrier:'), 2)

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
