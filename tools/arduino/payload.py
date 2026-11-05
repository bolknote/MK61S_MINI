"""Compose/check the Arduino native platform from shared repository sources."""

import sys as _repo_sys
from pathlib import Path as _RepoPath
_repo_sys.path.insert(0, str(_RepoPath(__file__).resolve().parents[2]))
import argparse
import errno
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys


def pairs(project, target):
    sys.path.insert(0, str(project / 'tools/firmware/stm32'))
    from tools.firmware.stm32.native_sdk import validate_sdk
    sdk = validate_sdk(project / 'third_party/stm32f4')
    metadata = json.loads((project / 'tools/arduino/payload.json').read_text())
    if metadata['schema'] != 1:
        raise ValueError('unsupported Arduino native payload schema')
    files = dict(metadata['files'])
    sdk_manifest = json.loads((sdk / 'manifest.json').read_text())
    for name in ['manifest.json', *sdk_manifest['files']]:
        files['third_party/stm32f4/' + name] = 'system/stm32f4/' + name
    for source, destination in files.items():
        for name in (source, destination):
            relative = PurePosixPath(name)
            if relative.is_absolute() or '..' in relative.parts or '\\' in name or ':' in name:
                raise ValueError('invalid native payload path: ' + name)
        yield project / source, target / destination


def arduino_data_directory():
    override = os.environ.get('ARDUINO_DIRECTORIES_DATA')
    if override:
        return Path(override).expanduser().resolve()
    config = Path(os.environ.get('MK61_ARDUINO_CONFIG_FILE') or
                  Path.home() / '.arduinoIDE/arduino-cli.yaml')
    if config.is_file():
        inside = False
        for line in config.read_text(encoding='utf-8-sig').splitlines():
            if line.strip() == 'directories:':
                inside = True
            elif inside and line and not line[0].isspace() and not line.startswith('#'):
                inside = False
            elif inside:
                match = re.match(r'\s+data:\s*(.*?)\s*$', line)
                if match and match[1]:
                    value = match[1]
                    if value.startswith('"'):
                        value = json.loads(value)
                    elif value.startswith("'") and value.endswith("'"):
                        value = value[1:-1].replace("''", "'")
                    return Path(value).expanduser().resolve()
    if sys.platform == 'darwin':
        return Path.home() / 'Library/Arduino15'
    return Path.home() / '.arduino15'


def compatible_compiler(candidate, version, check_headers=False):
    from tools.firmware.stm32.native_sdk import toolchain_bin, verify_toolchain_version
    binary = toolchain_bin(candidate)
    verify_toolchain_version(binary, version)
    if check_headers:
        subprocess.run([str(binary / 'arm-none-eabi-g++'), '-mcpu=cortex-m4', '-mthumb',
                        '-mfpu=fpv4-sp-d16', '-mfloat-abi=hard', '-x', 'c++',
                        '-std=gnu++17', '-fsyntax-only', '-'],
                       input='#include <cstdlib>\n#include <cstdint>\n', text=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True)
    return binary


def find_arduino_compiler(data_directory, version):
    packages = Path(data_directory) / 'packages'
    # Arduino stores compilers at packages/vendor/tools/tool/version/bin.
    for candidate in sorted(packages.glob('*/tools/*/*'), reverse=True):
        if not candidate.is_dir():
            continue
        try:
            return compatible_compiler(candidate, version, check_headers=True)
        except (ValueError, OSError, subprocess.CalledProcessError):
            continue


def compiler_path(project, target, selected, install, data_directory=None):
    sys.path.insert(0, str(project / 'tools/firmware/stm32'))
    from tools.firmware.stm32.native_sdk import toolchain_bin, verify_toolchain_version
    version = json.loads((project / 'tools/firmware/stm32/toolchain-lock.json').read_text())['version']
    local = target / 'platform.local.txt'
    if not selected and local.is_file():
        for line in local.read_text().splitlines():
            if line.startswith('compiler.path='):
                candidate = Path(line.split('=', 1)[1])
                if not install:
                    selected = candidate
                else:
                    try:
                        selected = compatible_compiler(candidate, version, check_headers=True)
                    except (ValueError, OSError, subprocess.CalledProcessError):
                        pass
    if not selected and install:
        selected = find_arduino_compiler(data_directory or arduino_data_directory(), version)
        if selected:
            print('Reusing GNU Arm GCC from Arduino: ' + str(selected))
    if not selected:
        owned = target / 'tools/toolchains' / ('xpack-arm-none-eabi-gcc-' + version)
        if owned.is_dir():
            selected = owned
        elif install:
            sys.path.insert(0, str(project / 'tools'))
            from tools.firmware.stm32.install_gcc_dependencies import install as install_gcc
            selected = install_gcc(project, target / 'tools/toolchains')
        else:
            raise ValueError('native GNU Arm compiler is missing; reinstall the MK61s board')
    binary = toolchain_bin(selected)
    verify_toolchain_version(binary, version)
    return binary


def write_compiler(target, binary):
    path = target / 'platform.local.txt'
    lines = path.read_text().splitlines() if path.is_file() else []
    lines = [line for line in lines if not line.startswith('compiler.path=')]
    lines.append('compiler.path=' + str(binary).replace('\\', '/') + '/')
    path.write_text('\n'.join(lines) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['install', 'check'])
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--target', type=Path, required=True)
    parser.add_argument('--toolchain', type=Path)
    args = parser.parse_args()
    project, target = args.project.resolve(), args.target.resolve()
    try:
        files = list(pairs(project, target))
        for source, destination in files:
            if not source.is_file():
                raise ValueError('native platform source is missing: ' + str(source))
            if args.operation == 'install':
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
            elif not destination.is_file() or source.read_bytes() != destination.read_bytes():
                raise ValueError('installed native platform is stale/incomplete: ' + str(destination))
        selected = (args.toolchain or os.environ.get('MK61_ARDUINO_TOOLCHAIN') or os.environ.get('MK61_GCC_TOOLCHAIN')) if args.operation == 'install' else None
        binary = compiler_path(project, target, selected,
            args.operation == 'install')
        if args.operation == 'install':
            write_compiler(target, binary)
            # Remove only files owned by the retired board-private USB shim.
            for name in ('library.properties', 'src/USBDevice.h', 'src/USBDevice.cpp'):
                old = target / 'libraries/USBDevice' / name
                if old.is_file():
                    old.unlink()
            # Arduino scans directories as libraries even after their owned
            # headers are gone. Remove empty containers, retaining user files.
            for name in ('libraries/USBDevice/src', 'libraries/USBDevice', 'libraries'):
                old = target / name
                if old.is_dir():
                    try:
                        old.rmdir()
                    except OSError as error:
                        if error.errno not in (errno.ENOTEMPTY, errno.EEXIST, errno.ENOENT):
                            raise
        print('Native GNU Arm: ' + str(binary))
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(1, str(error) + '\n')


if __name__ == '__main__':
    main()
