#!/usr/bin/env python3
"""Keep the measured F411 emulator code native while cold firmware uses LTO."""
from pathlib import Path
import subprocess
import sys


def protect(build: Path, sketch: Path, command: list[str]) -> None:
    lto = False
    for argument in command:
        if argument == '-flto' or argument.startswith('-flto='):
            lto = True
        elif argument == '-fno-lto':
            lto = False
    if not lto or '-DSTM32F411xE' not in command:
        return
    source = sketch / 'mk61emu_core.cpp'
    matches = list((build / 'sketch').rglob(source.name + '.o'))
    if not source.is_file() or len(matches) != 1:
        raise ValueError(f'expected F411 core source and one object, found {len(matches)}')
    # Arduino archives sketch objects after prelink hooks. Preserve the
    # compilation database for APP packing and compile with the same C++ flags.
    subprocess.run([*command, '-fno-lto', '-I' + str(sketch), str(source),
                    '-o', str(matches[0])], check=True)
    print('Core LTO barrier: mk61emu_core.cpp (F411)', flush=True)


if __name__ == '__main__':
    if len(sys.argv) < 4:
        raise SystemExit('usage: protect-core-lto.py BUILD SKETCH CXX [FLAGS...]')
    protect(Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3:])
