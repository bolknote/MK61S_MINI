#!/usr/bin/env python3
"""Install the locked standalone GNU Arm compiler on macOS/Linux."""

import sys as _repo_sys
from pathlib import Path as _RepoPath
_repo_sys.path.insert(0, str(_RepoPath(__file__).resolve().parents[3]))
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tools.firmware.stm32.native_sdk import toolchain_bin, validate_sdk, verify_toolchain_version


def install(project, install_root, archive_path=None):
    lock = json.loads((project / 'tools/firmware/stm32/toolchain-lock.json').read_text())
    contract = json.loads((project / 'dev/lib/release-contract.json').read_text())
    validate_sdk(project / 'third_party/stm32f4')
    if lock['schema'] != 1 or lock['version'] != contract['toolchain']['gnu_arm']:
        raise ValueError('GNU Arm lock version does not match the release contract')
    machine = platform.machine().lower()
    arch = {'aarch64': 'arm64', 'x86_64': 'x64', 'amd64': 'x64',
            'armv7l': 'arm', 'armv6l': 'arm'}.get(machine, machine)
    host = ('darwin' if sys.platform == 'darwin' else 'linux') + '-' + arch
    asset = lock['assets'].get(host)
    if not asset:
        raise ValueError('unsupported GNU Arm host platform: ' + host)
    folder = 'xpack-arm-none-eabi-gcc-' + lock['version']
    target = install_root / folder
    if target.is_dir():
        binary = toolchain_bin(target)
        verify_toolchain_version(binary, lock['version'])
        return binary
    install_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.install-', dir=install_root) as directory:
        stage = Path(directory)
        archive = Path(archive_path).resolve() if archive_path else stage / asset['archive']
        if not archive_path:
            print('Downloading ' + asset['archive'], flush=True)
            with urllib.request.urlopen(asset['url'], timeout=120) as source, archive.open('wb') as output:
                shutil.copyfileobj(source, output)
        digest = hashlib.sha256()
        with archive.open('rb') as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(block)
        if digest.hexdigest() != asset['sha256']:
            raise ValueError('GNU Arm archive checksum mismatch: ' + str(archive))
        unpack = stage / 'unpack'
        unpack.mkdir()
        # Only the exact archive from the pinned SHA256 lock reaches tar.
        subprocess.run(['tar', '-xzf', str(archive), '-C', str(unpack)], check=True)
        source = unpack / folder
        binary = toolchain_bin(source)
        verify_toolchain_version(binary, lock['version'])
        (source / 'mk61-install.json').write_text(json.dumps({
            'version': lock['version'], 'platform': host,
            'archive_sha256': digest.hexdigest()}, indent=2) + '\n')
        source.rename(target)
    return target / 'bin'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--install-root', type=Path)
    parser.add_argument('--archive-path', type=Path)
    args = parser.parse_args()
    if os.name == 'nt':
        parser.error('Windows uses tools/firmware/stm32/install_gcc_dependencies.ps1 (PowerShell, no Python)')
    project = Path(__file__).resolve().parents[3]
    try:
        binary = install(project, (args.install_root or project / '.build/toolchains').resolve(), args.archive_path)
        print('GNU Arm: ' + str(binary))
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(1, str(error) + '\n')


if __name__ == '__main__':
    main()
