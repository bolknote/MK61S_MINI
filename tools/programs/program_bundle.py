#!/usr/bin/env python3
"""Preview, package or install programs compatible with a concrete firmware bundle."""
import argparse
import json
from pathlib import Path
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'dev/lib'), str(ROOT)]
from program_collection import capabilities, display, export, MkcSession, plan, synchronize, resolved_build_flags


def archive_disk(bundle, output):
    if output.is_relative_to(bundle):
        raise ValueError('release archive must be outside its source directory')
    with tempfile.NamedTemporaryFile(prefix=output.stem, suffix='.zip', dir=output.parent, delete=False) as staged:
        temporary = Path(staged.name)
    try:
        with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(bundle.rglob('*')):
                relative = path.relative_to(bundle)
                if relative.parts[0] in ('Games', 'Programs') or path.name == '.catalog.lock':
                    continue
                archive.write(path, (Path(bundle.name)/relative).as_posix())
        with zipfile.ZipFile(temporary) as archive:
            bad_file = archive.testzip()
            if bad_file is not None:
                raise ValueError('release archive CRC mismatch: ' + bad_file)
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--install', action='store_true', help='Install through MKC; default is preview only')
    parser.add_argument('--verify', action='store_true', help='Also download uploaded files and compare their contents')
    parser.add_argument('--port')
    parser.add_argument('--mock', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--export', type=Path, help='Create a new distribution directory')
    parser.add_argument('--release-disk', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--archive', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--json', action='store_true', help='Print the selection manifest')
    parser.add_argument('--write-capabilities', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--profile', help=argparse.SUPPRESS)
    parser.add_argument('--mcu', choices=['f401', 'f411'], help=argparse.SUPPRESS)
    parser.add_argument('--firmware', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--compile-commands', type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.write_capabilities:
        if not all((args.profile, args.mcu, args.firmware)):
            parser.error('capability generation requires profile, MCU and sealed firmware')
        flags = resolved_build_flags(args.compile_commands) if args.compile_commands else (args.bundle/'build.flags').read_text()
        cap = capabilities(flags, args.profile, args.mcu, args.firmware)
        (args.bundle/'program-capabilities.json').write_text(json.dumps(cap, indent=2)+'\n')
        return
    if args.release_disk and (args.export or args.install):
        parser.error('--release-disk is exclusive with --install and --export')
    if args.archive and not args.release_disk:
        parser.error('--archive requires --release-disk')
    if args.install and args.export:
        parser.error('--install and --export are mutually exclusive')
    bundle = args.bundle.resolve()
    selection = plan(bundle, prefer_bundle=not args.release_disk)
    if args.json:
        print(json.dumps(selection, ensure_ascii=False, indent=2))
    else:
        display(selection)
    if args.export:
        export(selection, args.export, system=bundle/'System')
    if args.release_disk:
        export(selection, bundle/'Disk', system=bundle/'System', manifest=bundle/'programs-manifest.json')
        if args.archive:
            archive_disk(bundle, args.archive.resolve())
    if args.install:
        session = MkcSession(selection['capabilities'], port=args.port, mock=args.mock)
        try:
            result = synchronize(selection, session, verify=args.verify)
            print('Programs installed: ' + json.dumps(result, ensure_ascii=False))
        finally:
            session.close()


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError) as error:
        raise SystemExit('Program bundle: ' + str(error))
