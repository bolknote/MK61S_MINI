#!/usr/bin/env python3
"""Pack a binary program as ztart/zin commands using the vendored optimal ZX0.

The first call builds a small C++17 host tool; subsequent calls reuse it.
Each zin line is a separate basE91 block in one continuous ZX0 stream.
"""
import argparse
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def program_lines(image: bytes, address: int = 0) -> list[str]:
    if not image or not 0 <= address < 10000 or address + len(image) > 10000:
        raise ValueError('Program must fit addresses 0000..9999')
    with tempfile.TemporaryDirectory(prefix='mk61-program-pack-') as temp:
        source = Path(temp) / 'program.bin'
        output = Path(temp) / 'program.m61'
        source.write_bytes(image)
        subprocess.run(['bash', str(ROOT / 'tools/build_mk61_program_pack.sh'),
                        str(source), str(output), str(address)],
                       check=True, stdout=subprocess.PIPE)
        return output.read_text(encoding='ascii').splitlines(keepends=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('--address', type=int, default=0)
    args = parser.parse_args()
    print(''.join(program_lines(args.input.read_bytes(), args.address)), end='')
