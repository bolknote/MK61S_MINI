#!/usr/bin/env python3
"""Build all three Runner levels; --check verifies the generated files."""
import argparse
import json
from pathlib import Path
import sys
from game import create_game, launcher, check_layout, campaign, LEVELS

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from program_pack import program_binary


def outputs():
    out = ROOT / 'programs/games/Runner'
    files, levels = {out / 'autoexec.m61': campaign()}, []
    for number in range(1, len(LEVELS)+1):
        assembler, tables = create_game(number)
        banks, info = assembler.link()
        check_layout(info, banks)
        image = b''.join(banks.get(bank, bytes(112)) for bank in range(32))
        files[out / f'runner{number}.bin'] = program_binary(image)
        info.update(tables=tables, level=number, board=LEVELS[number-1])
        files[out / f'level{number}.m61'] = launcher(info, number)
        levels.append(info)
    info = dict(levels=levels, occupied_bytes=max(x['occupied_bytes'] for x in levels))
    files[ROOT / 'tools/runner/runner.map.json'] = (json.dumps(info, indent=2) + '\n').encode()
    return files, info


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
    scripts = [len(data) for path,data in files.items() if path.suffix == '.m61']
    print(f'Runner: {len(info["levels"])} levels; max {info["occupied_bytes"]} calculator bytes; '
          f'M61 {"/".join(map(str,scripts))} bytes; '
          f'files {"verified" if args.check else "written"}')


if __name__ == '__main__':
    main()
