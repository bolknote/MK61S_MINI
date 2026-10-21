#!/usr/bin/env python3
"""Prove the frozen benchmark baseline has the old public entry's instructions."""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
from check_stm32_vectors import ElfImage


def function_bytes(path, name):
    image = ElfImage(path)
    address, size = image.symbols[name] & ~1, image.sizes[name]
    section = next(s for s in image.sections if s[1] != 8 and
                   s[3] <= address and address + size <= s[3] + s[5])
    offset = section[4] + address - section[3]
    return path.read_bytes()[offset:offset + size]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--arm-toolchain-bin', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    results = []
    for cpu in ('cortex-m0plus', 'cortex-m4'):
        bodies = []
        for name in ('memcmp', 'baseline'):
            source = args.output / (cpu + '-' + name + '.c')
            elf = source.with_suffix('.elf')
            source.write_text('#include "' + str(HERE / 'baseline-memory.h') + '"\n' +
                              ('__attribute__((noipa)) ' if name == 'baseline' else '') +
                              'int ' + name + '(const void *a,const void *b,size_t n)'
                              '{return mk61_memory_compare(a,b,n);}\n')
            subprocess.run([str(args.arm_toolchain_bin / 'arm-none-eabi-gcc'),
                            '-mcpu=' + cpu, '-mthumb', '-Os', '-flto', '-fno-builtin',
                            '-ffunction-sections', '-fdata-sections', '-nostdlib', str(source),
                            '-Wl,--gc-sections,-Ttext=0x20000000,-e,' + name, '-o', str(elf)], check=True)
            bodies.append(function_bytes(elf, name))
        assert bodies[0] == bodies[1], cpu
        results.append(dict(cpu=cpu, status='PASS', bytes=len(bodies[0]),
                            code_sha256=hashlib.sha256(bodies[0]).hexdigest(),
                            method='Separate single-entry LTO builds; old public C entry and frozen noipa baseline are byte-identical'))
    (args.output / 'result.json').write_text(json.dumps(results, indent=2) + '\n')
    print(json.dumps(results, indent=2))


if __name__ == '__main__':
    main()
