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
SOURCES = ('src/cdc/usbd_cdc.c', 'src/usb_device_core.c')


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


class CoreLtoBuildTest(unittest.TestCase):
    def exercise(self, flags=None, fail=False, missing=False):
        with tempfile.TemporaryDirectory(prefix='mk61 core lto ') as temporary:
            base = Path(temporary)
            build = base / 'build with spaces'
            sketch = base / 'sketch with spaces'
            sketch.mkdir()
            (sketch / 'mk61emu_core.cpp').touch()
            obj = build / 'sketch/mk61emu_core.cpp.o'
            obj.parent.mkdir(parents=True)
            obj.write_text('original LTO object')
            cold = obj.with_name('terminal.cpp.o')
            cold.write_text('cold LTO object')
            if missing:
                obj.unlink()
            fake = base / 'fake compiler'
            shutil.copyfile(HERE, fake)
            fake.chmod(0o755)
            options = flags if flags is not None else ['-c', '-flto', '-Os',
                '-std=gnu++17', '-fno-exceptions', '-DSTM32F411xE',
                '-DMK61_BOARD_CLASSIC_V3', '-DNAME="space value"',
                '-IC:/Program Files/STM32/core', r'-IE:\Arduino core\inc']
            if fail:
                options = options + ['--fail']
            launcher = [sys.executable]
            result = subprocess.run([*launcher,
                str(ROOT / 'tools/arduino/compat/protect-core-lto.py'),
                str(build), str(sketch), str(fake), '--fake-compiler', *options],
                capture_output=True, text=True)
            self.assertEqual(cold.read_text(), 'cold LTO object')
            if fail or missing:
                self.assertNotEqual(result.returncode, 0)
                return
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            if flags is not None:
                self.assertEqual(obj.read_text(), 'original LTO object')
                return
            expected = options + ['-fno-lto', '-I' + str(sketch),
                str(sketch / 'mk61emu_core.cpp'), '-o', str(obj)]
            self.assertEqual(json.loads(obj.read_text()), expected)
            self.assertIn('Core LTO barrier:', result.stdout)

    def test_native_f411(self):
        self.exercise()

    def test_native_skips_f401_and_non_lto(self):
        for flags in (['-flto', '-DSTM32F401xC'], ['-Os', '-DSTM32F411xE'],
                      ['-flto=auto', '-fno-lto', '-DSTM32F411xE']):
            self.exercise(flags=flags)

    def test_native_failure_and_missing_object(self):
        self.exercise(fail=True)
        self.exercise(missing=True)


    def test_native_arduino_installs_shared_policy_hook(self):
        text = (ROOT / 'tools/arduino/hardware/mk61/stm32/platform.txt').read_text()
        self.assertIn('recipe.hooks.linking.prelink.20.pattern=', text)
        self.assertIn('mk61-native-prelink.py', text)
        self.assertIn('mk61-native-prelink.ps1', text)

    def test_native_frontends_use_shared_cmake_barriers(self):
        cmake = (ROOT / 'tools/firmware/stm32/CMakeLists.txt').read_text()
        self.assertIn('native_compile_policy.json', cmake)
        self.assertIn('COMPILE_OPTIONS ${_mk61_values}', cmake)
        self.assertIn('NOT _mk61_mcu STREQUAL MK61_TARGET_MCU', cmake)
        policy = json.loads((ROOT / 'tools/firmware/stm32/native_compile_policy.json').read_text())
        units = {v['source']: v for v in policy['units']}
        self.assertEqual(units['mk61emu_core.cpp']['mcu'], 'f411')
        for source in ('mk61emu_core.cpp', 'stm32f4_usbd_core.c', 'stm32f4_usbd_cdc.c'):
            self.assertIn('-fno-lto', units[source]['flags'])
        for name, destination in (
                ('tools/firmware/cli/mk61-firmware.sh', 'tools/firmware/stm32/build-gcc.cmd'),
                ('tools/firmware/cli/mk61-firmware.ps1', 'Invoke-F401GccBundleBuild'),
                ('tests/run_f411_release_matrix.sh', 'build-standalone.py')):
            self.assertTrue(destination in (ROOT / name).read_text(), name)


class NativeArduinoPolicyTest(unittest.TestCase):
    def exercise(self, powershell=False, mcu='f401', failure=None):
        with tempfile.TemporaryDirectory(prefix='mk61 native prelink ') as temporary:
            base = Path(temporary)
            tools = base / 'installed board/tools'
            tools.mkdir(parents=True)
            original = ROOT / 'tools/arduino/hardware/mk61/stm32/tools'
            for name in ('mk61-native-prelink.py', 'mk61-native-prelink.ps1', 'mk61-safe-tool.ps1'):
                shutil.copy2(original / name, tools / name)
            shutil.copy2(ROOT / 'tools/firmware/stm32/native_compile_policy.json', tools)
            policy = json.loads((tools / 'native_compile_policy.json').read_text())
            build, sketch = base / 'build with spaces', base / 'original sketch'
            snapshot = build / 'sketch'
            snapshot.mkdir(parents=True)
            sketch.mkdir()
            entries = []
            for unit in policy['units']:
                source = snapshot / unit['source']
                source.touch()
                obj = source.with_name(source.name + '.o')
                if failure != 'metadata':
                    obj.write_text('original LTO object')
                entries.append({'file': str(source), 'arguments': ['original'], 'directory': str(build)})
            cold = snapshot / 'terminal.cpp.o'
            if failure != 'metadata':
                cold.write_text('cold LTO object')
            if failure == 'missing':
                (snapshot / 'native_eabi.cpp.o').unlink()
            (build / 'compile_commands.json').write_text(json.dumps(entries))
            fake = base / 'fake compiler'
            shutil.copyfile(HERE, fake)
            fake.chmod(0o755)
            options = ['--fake-compiler', '-c', '-flto', '-Os', '-std=gnu++17',
                       '-fno-exceptions', '-DMK61_NATIVE_RUNTIME=1',
                       '-DSTM32F411xE' if mcu == 'f411' else '-DSTM32F401xC',
                       '-DNAME="space value"', '-I', str(sketch)]
            if failure == 'compiler':
                options.append('--fail')
            suffix = 'ps1' if powershell else 'py'
            launcher = ([shutil.which('pwsh'), '-NoLogo', '-NoProfile', '-File']
                        if powershell else [sys.executable])
            result = subprocess.run([*launcher, str(tools / ('mk61-native-prelink.' + suffix)),
                str(build), str(sketch), str(fake), *options], capture_output=True, text=True)
            if failure in ('missing', 'compiler'):
                self.assertNotEqual(result.returncode, 0)
                return
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            if failure == 'metadata':
                self.assertFalse(list(snapshot.glob('*.o')))
                return
            self.assertEqual(cold.read_text(), 'cold LTO object')
            updated = json.loads((build / 'compile_commands.json').read_text())
            for unit, entry in zip(policy['units'], updated):
                obj = snapshot / (unit['source'] + '.o')
                if unit.get('mcu') and unit['mcu'] != mcu:
                    self.assertEqual(obj.read_text(), 'original LTO object')
                    continue
                actual = json.loads(obj.read_text())
                self.assertEqual(actual[-3:], [str(snapshot / unit['source']), '-o', str(obj)])
                self.assertIn(str(sketch), actual)
                for flag in unit['flags']:
                    self.assertIn(flag, actual)
                for definition in unit['defines']:
                    self.assertIn('-D' + definition, actual)
                if unit['source'].endswith('.c'):
                    self.assertIn('-std=gnu17', actual)
                    self.assertNotIn('-std=gnu++17', actual)
                    self.assertNotIn('-fno-exceptions', actual)
                self.assertEqual(entry['arguments'][2:], actual)  # executable and fixture switch

    def test_python_policy(self):
        for mcu in ('f401', 'f411'):
            with self.subTest(mcu=mcu):
                self.exercise(mcu=mcu)
        for failure in ('missing', 'compiler', 'metadata'):
            with self.subTest(failure=failure):
                self.exercise(failure=failure)

    @unittest.skipUnless(shutil.which('pwsh'), 'PowerShell unavailable')
    def test_powershell_policy(self):
        for mcu in ('f401', 'f411'):
            with self.subTest(mcu=mcu):
                self.exercise(powershell=True, mcu=mcu)
        for failure in ('missing', 'compiler', 'metadata'):
            with self.subTest(failure=failure):
                self.exercise(powershell=True, failure=failure)


class UsbLtoBuildTest(unittest.TestCase):
    def exercise(self, fail=False, owned=None, missing_owned=False):
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
            # HAL supplies weak empty hooks; its strong USB bridge must remain
            # visible to LTO. Rewriting that bridge instead of the core target
            # unit previously let MSP initialization disappear on real F411.
            bridge = build / 'libraries/USBDevice/usbd_conf.c.o'
            bridge.write_text('strong HAL callbacks in LTO')
            cdc_interface = build / 'libraries/USBDevice/usbd_cdc_if.c.o'
            cdc_interface.write_text('generic CDC interface')
            serial = build / 'libraries/USBDevice/USBSerial.cpp.o'
            serial.write_text('Arduino Serial object')
            request = build / 'libraries/USBDevice/usb_device_ctlreq.c.o'
            request.write_text('generic control requests')
            snapshot = build / 'sketch'
            snapshot.mkdir()
            for name in ('stm32f4_usb_device.cpp','stm32f4_usbd_ctlreq.c','stm32f4_usbd_cdc.c','stm32f4_usb_serial_stub.cpp','stm32f4_cdc_if.c'):
                (snapshot / name).write_text('// snapshot fixture')
            if missing_owned:
                (snapshot / 'stm32f4_usb_device.cpp').unlink()
            helper = ROOT / 'tools/arduino/compat/protect-usb-lto.py'
            fake = base / 'fake compiler'
            shutil.copyfile(HERE, fake)
            fake.chmod(0o755)
            launcher = [sys.executable]
            options = ['-c', '-flto', '-Os', '-DNAME="space value"', '-I' + str(library),
                       '-IC:/Program Files/STM32/USBDevice/inc',
                       '-Id:/Arduino/core/inc', r'-IE:\Arduino core\USBDevice\inc',
                       '-I', 'F:/separate include option']
            if owned:
                options += ['-D' + owned, '-include', 'stm32f4_usbd_def.h']
            if fail:
                options.append('--fail')
            result = subprocess.run([*launcher, str(helper), str(build), str(library),
                                     str(fake), '--fake-compiler', *options],
                                    capture_output=True, text=True)
            if fail or missing_owned:
                self.assertNotEqual(result.returncode, 0)
                if fail:self.assertEqual(objects[0].read_text(), 'original LTO object')
                return
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            expected = options
            for source, obj in zip(SOURCES, objects):
                extra = ['-fno-lto']
                actual = library/source
                if owned and source == 'src/cdc/usbd_cdc.c':
                    extra += ['-DMK61_USB_BUILD_CDC=1']
                    actual = snapshot/'stm32f4_usbd_cdc.c'
                self.assertEqual(json.loads(obj.read_text()),
                                 expected + extra + ['-I'+str(snapshot), str(actual), '-o', str(obj)])
            self.assertEqual(result.stdout.count('USB LTO barrier:'), 2)
            if owned:
                interface_args=json.loads(cdc_interface.read_text())
                self.assertIn('-DMK61_USB_BUILD_CDC_IF=1',interface_args)
                self.assertIn('-std=gnu++17',json.loads(serial.read_text()))
                bridge_args=json.loads(bridge.read_text())
                request_args=json.loads(request.read_text())
                normalize=str
                self.assertIn(normalize(str(snapshot/'stm32f4_usb_device.cpp')),bridge_args)
                self.assertIn(normalize(str(snapshot/'stm32f4_usbd_ctlreq.c')),request_args)
                self.assertIn('-DMK61_USB_BUILD_BRIDGE=1',bridge_args)
                self.assertIn('-DMK61_USB_BUILD_CTLREQ=1',request_args)
                self.assertIn('-fno-exceptions',bridge_args)
                self.assertNotIn('-fno-lto',bridge_args)
                self.assertNotIn('-fno-lto',request_args)
                self.assertIn('stm32f4_usbd_def.h',bridge_args)
            else:
                self.assertEqual(bridge.read_text(), 'strong HAL callbacks in LTO')
                self.assertEqual(request.read_text(), 'generic control requests')

    def exercise_private(self, missing=False, fail=False):
        with tempfile.TemporaryDirectory(prefix='mk61 private usb ') as temporary:
            build = Path(temporary) / 'build with spaces'
            sketch = build / 'sketch'
            sketch.mkdir(parents=True)
            sources = ('stm32f4_usbd_core.c', 'stm32f4_usbd_cdc.c')
            for source in sources:
                (sketch/source).touch()
                (sketch/(source+'.o')).write_text('LTO object')
            if missing:
                (sketch/(sources[1]+'.o')).unlink()
            fake = Path(temporary) / 'fake compiler'
            shutil.copyfile(HERE, fake); fake.chmod(0o755)
            launcher = [sys.executable]
            options = ['--fake-compiler', '-c', '-flto', '-DSTM32F401xC',
                       '-DMK61_ARDUINO_OWNED_USB=1', '-DNAME="space value"']
            if fail: options += ['--fail']
            result = subprocess.run([*launcher,
                str(ROOT/'tools/arduino/compat/protect-usb-lto.py'),
                str(build), str(Path(temporary)/'unused Core library'),
                str(fake), *options], capture_output=True, text=True)
            if missing or fail:
                self.assertNotEqual(result.returncode, 0)
            else:
                self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
                for source in sources:
                    command = json.loads((sketch/(source+'.o')).read_text())
                    self.assertIn('-fno-lto', command)
                    self.assertEqual(command[-3:], [str(sketch/source), '-o', str(sketch/(source+'.o'))])
                self.assertEqual(result.stdout.count('Owned USB LTO barrier:'), 2)

    def test_private_board_owned_engine(self):
        for missing, fail in ((False,False),(True,False),(False,True)):
            self.exercise_private(missing=missing, fail=fail)


    def test_native(self):
        self.exercise()

    def test_native_owned_f4_snapshot(self):
        for mcu in ('STM32F401xC','STM32F401xE','STM32F411xE'):
            self.exercise(owned=mcu)
        self.exercise(owned='STM32F411xE',missing_owned=True)


    def test_native_failure(self):
        self.exercise(fail=True)


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
            helper = ROOT / 'tools/arduino/hardware/mk61/stm32/tools/mk61-safe-tool.ps1'
            result = subprocess.run([
                shutil.which('pwsh'), '-NoLogo', '-NoProfile', '-File', str(helper),
                str(base), str(fake), '--fake-compiler', *flags,
            ], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(json.loads(output.read_text()),
                             [arg.replace('\\', '/') for arg in flags])


    def test_elf_call_gate(self):
        spec = importlib.util.spec_from_file_location('gate', ROOT / 'tests/check_usb_cdc_rx_elf.py')
        gate = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gate)
        protected = ' 8032aaa: f7fb fbb2 bl 802e212 <__wrap_USBD_CDC_ClearBuffer>\n'
        unprotected = ' 8033f52: f7ff ffc9 bl 8033ee8 <USBD_CDC_ClearBuffer>\n'
        hardware = ('08010000 <USBD_LL_Init>:\n'
                    ' 8010000: f7fb fbb2 bl 8010100 <HAL_PCD_Init>\n'
                    '08010100 <HAL_PCD_Init>:\n'
                    ' 8010100: f7fb fbb2 bl 8010200 <HAL_PCD_MspInit>\n'
                    '08010200 <HAL_PCD_MspInit>:\n'
                    ' 8010200: f7fb fbb2 bl 8010300 <pin_function>\n')
        gate.check(protected + hardware)
        inlined = ('08010000 <USBD_LL_Init>:\n'
                   ' 8010000: f7fb fbb2 bl 8010300 <pin_function>\n')
        gate.check(protected + inlined)
        # The broken F411 image had valid receive wrappers but HAL's empty
        # default MSP hook was folded away with all USB GPIO configuration.
        lost_msp = ('08010000 <USBD_LL_Init>:\n'
                    ' 8010000: f7fb fbb2 bl 8010100 <HAL_PCD_Init>\n'
                    '08010100 <HAL_PCD_Init>:\n'
                    ' 8010100: 4770 bx lr\n')
        for invalid in (protected, protected + lost_msp,
                        unprotected + hardware, protected + unprotected + hardware,
                        '0802e0e6 <__wrap_USBD_CDC_ClearBuffer>:\n'):
            with self.assertRaises(ValueError):
                gate.check(invalid)

    def test_elf_gate_uses_exact_build_toolchain(self):
        spec = importlib.util.spec_from_file_location('gate', ROOT / 'tests/check_usb_cdc_rx_elf.py')
        gate = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gate)
        with tempfile.TemporaryDirectory(prefix='mk61 binutils ') as temporary:
            root = Path(temporary)
            database = root / 'compile_commands.json'
            for suffix in ('', '.exe'):
                compiler = root / ('arm-none-eabi-g++' + suffix)
                for name in ('size', 'nm', 'objdump'):
                    (root / ('arm-none-eabi-' + name + suffix)).touch()
                database.write_text(json.dumps([{
                    'directory': str(root), 'arguments': [str(compiler), '-c'],
                }]))
                expected = root / ('arm-none-eabi-objdump' + suffix)
                self.assertEqual(gate.objdump_from_database(database), expected)
                expected.unlink()
                with self.assertRaisesRegex(ValueError, 'objdump tool not found'):
                    gate.objdump_from_database(database)


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1].startswith('@'):
        raise SystemExit(fake_compiler(sys.argv[1:]))
    if len(sys.argv) > 1 and sys.argv[1] == '--fake-compiler':
        raise SystemExit(fake_compiler(sys.argv[2:]))
    unittest.main()
