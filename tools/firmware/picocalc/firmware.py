#!/usr/bin/env python3
"""Build PicoCalc firmware and APPs through the public firmware launcher."""
import argparse
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', action='store_true', help='build firmware and the APP collection')
    parser.add_argument('--package', action='store_true', help='package an already verified build, after --build if selected')
    parser.add_argument('--list-profiles', action='store_true')
    parser.add_argument('--profile', choices=['picocalc-pico-h'], default='picocalc-pico-h')
    parser.add_argument('--fetch-sdk', action='store_true', help='fetch pinned dependencies while building')
    parser.add_argument('--sdk', type=Path)
    parser.add_argument('--toolchain', type=Path)
    parser.add_argument('--rustc', type=Path)
    parser.add_argument('--jobs', type=int, default=4)
    parser.add_argument('--build-path', type=Path, default=ROOT / '.build/picocalc-pico-h')
    parser.add_argument('--output-dir', type=Path, default=ROOT / '.build/firmware/picocalc-pico-h')
    args = parser.parse_args(argv)
    if args.jobs < 1:
        parser.error('--jobs must be positive')
    if args.list_profiles:
        if args.build or args.package:
            parser.error('--list-profiles cannot be combined with build actions')
        print('picocalc-pico-h\tPicoCalc / Pico H (RP2040)')
        return 0
    if not args.build and not args.package:
        parser.print_help()
        return 0
    commands = []
    if args.build:
        firmware = [sys.executable, str(ROOT / 'tools/firmware/picocalc/build_picocalc.py'),
                    '--profile', args.profile, '--build-path', str(args.build_path),
                    '--output-dir', str(args.output_dir), '--jobs', str(args.jobs)]
        apps = [sys.executable, str(ROOT / 'tools/apps/system/build_picocalc_apps.py'),
                '--build-dir', str(args.build_path.with_name(args.build_path.name + '-apps')),
                '--output-dir', str(args.output_dir / 'apps')]
        if args.fetch_sdk:
            firmware.append('--fetch-sdk')
        if args.sdk:
            firmware += ['--sdk', str(args.sdk)]
        if args.toolchain:
            firmware += ['--toolchain', str(args.toolchain)]
            apps += ['--toolchain', str(args.toolchain)]
        if args.rustc:
            apps += ['--rustc', str(args.rustc)]
        commands += [firmware, apps]
    if args.package:
        commands.append([sys.executable, str(ROOT / 'tools/firmware/picocalc/package_picocalc.py'),
                         '--directory', str(args.output_dir)])
    try:
        for command in commands:
            subprocess.run(command, check=True)
    except subprocess.CalledProcessError as error:
        return error.returncode if error.returncode > 0 else 1
    except OSError as error:
        print(f'PicoCalc build: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
