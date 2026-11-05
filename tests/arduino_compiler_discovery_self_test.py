#!/usr/bin/env python3
"""Exercise Unix Arduino compiler discovery with real version executables."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('arduino_payload', ROOT / 'tools/.mk61-arduino-board/payload.py')
payload = importlib.util.module_from_spec(spec)
spec.loader.exec_module(payload)


def compiler(root, version='14.2.1'):
    binary = root / 'bin'
    binary.mkdir(parents=True)
    for name in ('gcc', 'g++', 'ar', 'ranlib', 'objcopy', 'size', 'nm', 'objdump', 'c++filt', 'gcc-ar'):
        executable = binary / ('arm-none-eabi-' + name)
        executable.write_text('#!/bin/sh\nprintf "%s\\n" ' + version + '\n')
        executable.chmod(0o755)
    return binary.resolve()


def rejected(call):
    try:
        call()
    except (ValueError, OSError):
        return
    raise AssertionError('invalid compiler was accepted')


def main():
    with tempfile.TemporaryDirectory(prefix='mk61 compiler discovery ') as temporary:
        work = Path(temporary).resolve()
        data = work / 'custom Arduino15'
        good = compiler(data / 'packages/STMicroelectronics/tools/xpack-arm-none-eabi-gcc/0.0.0')
        wrong = compiler(data / 'packages/arduino/tools/arm-none-eabi-gcc/14.2.1-1.1', '13.3.1')
        incomplete = compiler(data / 'packages/arduino/tools/arm-none-eabi-gcc/99-incomplete')
        (incomplete / 'arm-none-eabi-gcc-ar').unlink()
        compiler(data / 'packages/arduino/hardware/stm32/14.2.1-1.1')
        downloads = []

        def install(project, install_root):
            downloads.append(install_root)
            root = install_root / 'xpack-arm-none-eabi-gcc-14.2.1-1.1'
            compiler(root)
            return root

        config = work / 'IDE settings.yaml'
        with mock.patch.dict(os.environ, {'ARDUINO_DIRECTORIES_DATA': str(data),
                                         'MK61_ARDUINO_CONFIG_FILE': str(config)}), \
                mock.patch.dict(sys.modules, {'install_gcc_dependencies': SimpleNamespace(install=install)}):
            target = work / 'sketchbook/hardware/mk61/stm32'
            assert payload.arduino_data_directory() == data
            assert payload.compiler_path(ROOT, target, None, True) == good
            assert not downloads
            target.mkdir(parents=True, exist_ok=True)
            payload.write_compiler(target, good)
            assert payload.compiler_path(ROOT, target, None, False) == good
            (target / 'platform.local.txt').write_text('compiler.path=' + str(incomplete) + '\n')
            rejected(lambda: payload.compiler_path(ROOT, target, None, False))
            assert payload.compiler_path(ROOT, target, None, True) == good
            explicit = compiler(work / 'explicit compiler')
            assert payload.compiler_path(ROOT, target, explicit, True) == explicit
            rejected(lambda: payload.compiler_path(ROOT, target, wrong, True))
            assert not downloads
            (good / 'arm-none-eabi-gcc-ar').unlink()
            assert payload.compiler_path(ROOT, target, None, True).is_relative_to(target / 'tools/toolchains')
            assert len(downloads) == 1
            assert payload.compiler_path(ROOT, target, None, True).is_relative_to(target / 'tools/toolchains')
            assert len(downloads) == 1

            # Honour the IDE's configured data root, including quoted paths;
            # the Arduino CLI environment override takes precedence over it.
            os.environ['ARDUINO_DIRECTORIES_DATA'] = ''
            configured = work / "Arduino data with ' quote"
            for scalar in (str(configured), json.dumps(str(configured)),
                           "'" + str(configured).replace("'", "''") + "'"):
                config.write_text('directories:\n  data: ' + scalar + '\nother:\n  data: /wrong\n', encoding='utf-8-sig')
                assert payload.arduino_data_directory() == configured
            os.environ['ARDUINO_DIRECTORIES_DATA'] = str(data)
            assert payload.arduino_data_directory() == data
            os.environ['ARDUINO_DIRECTORIES_DATA'] = ''
            config.unlink()
            with mock.patch.object(Path, 'home', return_value=work):
                expected = work / ('Library/Arduino15' if sys.platform == 'darwin' else '.arduino15')
                assert payload.arduino_data_directory() == expected
    print('Arduino compiler discovery: actual version, complete tools, package-only search, reuse/no download, explicit override, read-only checks, fallback/cache and IDE data roots PASS')


if __name__ == '__main__':
    main()
