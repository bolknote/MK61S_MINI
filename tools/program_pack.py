#!/usr/bin/env python3
"""Pack a program as CRC32 (little endian) + optimal ZX0 for load <addr> <file.bin>."""
import argparse
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def program_binary(image: bytes) -> bytes:
    if not image or len(image) > 32 * 112:
        raise ValueError('Program must fit 32 banks (3584 bytes)')
    with tempfile.TemporaryDirectory(prefix='mk61-program-pack-') as temp:
        source = Path(temp) / 'program.bin'
        output = Path(temp) / 'program.bin'
        source.write_bytes(image)
        subprocess.run(['bash', str(ROOT / 'tools/build_mk61_program_pack.sh'),
                        str(source), str(output)],
                       check=True, stdout=subprocess.PIPE)
        return output.read_bytes()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    args.output.write_bytes(program_binary(args.input.read_bytes()))
