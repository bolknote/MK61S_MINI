#!/usr/bin/env python3
"""Build the reproducible calculator RACE package; --check verifies it."""
import argparse
import json
from pathlib import Path
import sys
from game import create_game, check_layout

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from program_pack import program_binary


def outputs():
    banks, info = create_game().link()
    check_layout(info)
    image = b''.join(banks.get(bank, bytes(112)) for bank in range(32))
    out = ROOT / 'programs/games/RACE'
    return {
        out / 'race.bin': program_binary(image),
        out / 'autoexec.m61': (b'open? manual.md\nreinit\nbind key 13 down run :help\n'
                               b'load 0000 race.bin\nrun\nret\n\n'
                               b':help\nopen? manual.md\nret\n'),
        ROOT / 'tools/race/race.map.json':
            (json.dumps(info, indent=2, ensure_ascii=False) + '\n').encode(),
    }, info


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    files, info = outputs()
    stale = []
    for path, data in files.items():
        if args.check:
            if not path.exists() or path.read_bytes() != data:
                stale.append(str(path.relative_to(ROOT)))
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
    if stale:
        raise SystemExit('Regenerate with tools/race/build.py: ' + ', '.join(stale))
    print(f'RACE: {info["occupied_bytes"]} bytes used; '
          f'{info["free_bytes"]} free; generated files {"verified" if args.check else "written"}')


if __name__ == '__main__':
    main()
