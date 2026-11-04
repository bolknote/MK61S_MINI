"""Compose/check the Arduino native platform from shared repository sources."""
import argparse
import errno
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys


def pairs(project, target):
    sys.path.insert(0, str(project / 'tools/.mk61-gcc'))
    from native_sdk import validate_sdk
    sdk = validate_sdk(project / 'third_party/stm32f4')
    metadata = json.loads((project / 'tools/.mk61-arduino-board/payload.json').read_text())
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


def compiler_path(project, target, selected, install):
    sys.path.insert(0, str(project / 'tools/.mk61-gcc'))
    from native_sdk import toolchain_bin, verify_toolchain_version
    version = json.loads((project / 'tools/.mk61-gcc/toolchain-lock.json').read_text())['version']
    local = target / 'platform.local.txt'
    if not selected and local.is_file():
        for line in local.read_text().splitlines():
            if line.startswith('compiler.path='):
                candidate = Path(line.split('=', 1)[1])
                if not install or candidate.is_dir():
                    selected = candidate
    if not selected:
        owned = target / 'tools/toolchains' / ('xpack-arm-none-eabi-gcc-' + version)
        if owned.is_dir():
            selected = owned
        elif install:
            sys.path.insert(0, str(project / 'tools'))
            from install_gcc_dependencies import install as install_gcc
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
