#!/usr/bin/env python3
"""Build the reproducible MK61 Runner prototype; --check verifies its files."""
import argparse
import json
from pathlib import Path
import sys
from game import create_game, launcher, check_layout

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from program_pack import program_binary


def outputs():
    banks, info = create_game().link()
    check_layout(info)
    image = b''.join(banks.get(bank, bytes(112)) for bank in range(32))
    out = ROOT / 'programs/games/Runner'
    return {
        out / 'runner.bin': program_binary(image),
        out / 'autoexec.m61': launcher(info),
        ROOT / 'tools/runner/runner.map.json':
            (json.dumps(info, indent=2, ensure_ascii=False) + '\n').encode(),
    }, info


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    files, info = outputs()
    for path, data in files.items():
        if args.check:
            if not path.is_file() or path.read_bytes() != data:
                raise SystemExit('Regenerate with python3 tools/runner/build.py: ' + str(path.relative_to(ROOT)))
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
    print(f'Runner: {info["occupied_bytes"]} calculator bytes; '
          f'{len(files[ROOT / "programs/games/Runner/autoexec.m61"])} M61 bytes; '
          f'files {"verified" if args.check else "written"}')


if __name__ == '__main__':
    main()
