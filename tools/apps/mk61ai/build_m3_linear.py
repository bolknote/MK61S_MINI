#!/usr/bin/env python3
"""Build optional SRAM-only MK61AI modules for STM32, without device I/O."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import zlib

ROOT = Path(__file__).resolve().parents[3]
SDK = ROOT / 'sdk/coproc'
sys.path.insert(0, str(SDK))
from elf32 import ELF

DEFAULT_TOOL = Path('/Users/bolk/Library/Arduino15/packages/STMicroelectronics/tools/'
                    'xpack-arm-none-eabi-gcc/14.2.1-1.1/bin')


def build(output, toolchain=DEFAULT_TOOL, integer=False, *, draft=False):
    if integer and draft:
        raise ValueError('Choose either the INT8 matrix backend or the draft module')
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    app = ROOT / 'examples/portable-apps/MK61AI'
    stem = 'M3DRAFT' if draft else 'M3LINE'
    source = app / ('m3_draft_module.c' if draft else
                    'm3_int8_module.c' if integer else 'm3_linear_module.c')
    tool = lambda name: str(Path(toolchain) / ('arm-none-eabi-' + name))
    flags = ['-mcpu=cortex-m3', '-mthumb', '-mfloat-abi=soft', '-std=c11', '-Os', '-g',
             '-mword-relocations', '-ffreestanding', '-fno-builtin', '-fno-common',
             '-fno-stack-protector', '-fno-unwind-tables', '-fno-asynchronous-unwind-tables',
             '-ffp-contract=off', '-ffunction-sections', '-fdata-sections',
             '-Wall', '-Wextra', '-Werror', '-I' + str(SDK)]
    elf, binary = output / f'{stem}.elf', output / f'{stem}.bin'
    command = [tool('gcc'), *flags, '-nostdlib', str(source), '-Wl,-T,' + str(SDK / 'module.ld'),
               '-Wl,--emit-relocs,--gc-sections,-Map=' + str(output / f'{stem}.map'),
               '-o', str(elf), '-lgcc']
    with (output / 'build.log').open('w') as log:
        subprocess.run(command, check=True, stdout=log, stderr=subprocess.STDOUT)
    subprocess.run([tool('objcopy'), '-O', 'binary', '-j', '.image', str(elf), str(binary)], check=True)
    e = ELF(elf)
    image = binary.read_bytes()
    memory = e.symbols['__memory_end']['value'] - 0x20000000
    relocs = []
    for address, kind in e.relocations():
        if kind == 2:
            relocs.append(address - 0x20000000)
        elif kind not in (3, 10, 30, 42):
            raise ValueError('Unsupported module relocation ' + str(kind))
    relocs = sorted(set(relocs))
    if memory > 6144 or len(relocs) > 64:
        raise ValueError('M3 module exceeds resident budget')
    for at in relocs:
        assert at % 4 == 0 and at + 4 <= len(image)
        assert 0x20000000 <= struct.unpack_from('<I', image, at)[0] <= 0x20000000 + memory
    for name, symbol in e.symbols.items():
        if symbol['index'] == 0:
            raise ValueError('Undefined module symbol ' + name)
    payload = image + b''.join(struct.pack('<I', at) for at in relocs)
    input_limit, output_limit = (240, 8) if draft else (512, 512)
    words = [0x314d3353, 1, 64, 64 + len(payload), len(image), memory - len(image),
             e.entry - 0x20000000, len(relocs), input_limit, output_limit, 512, 2000,
             zlib.crc32(payload), 0, 0x70301]
    header = struct.pack('<15I', *words)
    package = output / f'{stem}.S3M'
    package.write_bytes(header + struct.pack('<I', zlib.crc32(header)) + payload)
    (output / 'disassembly.txt').write_text(subprocess.check_output([tool('objdump'), '-d', str(elf)], text=True))
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    inputs = [source, SDK / 'stm3_module.h', SDK / 'module.ld', SDK / 'elf32.py', Path(__file__)]
    if not draft: inputs.append(app / 'm3_linear_protocol.h')
    if integer: inputs.append(app / 'm3_q4_kernels.h')
    result = dict(package=str(package), sha256=sha(package), package_bytes=package.stat().st_size,
                  image_bytes=len(image), bss_bytes=memory-len(image), memory_bytes=memory,
                  memory_limit=6144, relocations=relocs,
                  slice_us=2000, pico_dma_channels=0,
                  source_sha256={str(p.relative_to(ROOT)): sha(p) for p in inputs}, hardware_verified=False)
    if draft:
        result.update(role='draft token predictor', maximum_history=118)
    else:
        result.update(arithmetic='Q4 nibbles, group32 INT8 activations' if integer else 'Q4 bit planes, LUT_FLOAT32',
                      maximum_columns=512, maximum_rows=2)
    (output / 'manifest.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-dir', type=Path)
    variant = parser.add_mutually_exclusive_group()
    variant.add_argument('--int8', action='store_true')
    variant.add_argument('--draft', action='store_true')
    parser.add_argument('--arm-toolchain-bin', type=Path, default=DEFAULT_TOOL)
    args = parser.parse_args()
    name = 'm3-draft' if args.draft else 'm3-int8' if args.int8 else 'm3-linear'
    folder = args.build_dir or ROOT / '.build/mk61ai' / name / 'module'
    print(json.dumps(build(folder, args.arm_toolchain_bin, args.int8, draft=args.draft), indent=2))
