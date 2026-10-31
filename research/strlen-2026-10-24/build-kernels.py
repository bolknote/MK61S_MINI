#!/usr/bin/env python3
"""Build SDK baseline, actual newlib and isolated strlen candidates."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
from check_stm32_vectors import ElfImage


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build(tc, output, cpu, base=0x20000000):
    output.mkdir(parents=True, exist_ok=False)
    common = [str(tc / 'arm-none-eabi-gcc'), '-mcpu=' + ('cortex-m0plus' if cpu == 'm0' else 'cortex-m4'), '-mthumb']
    if cpu == 'm4':
        common += ['-mfpu=fpv4-sp-d16', '-mfloat-abi=hard']
    flags = ['-Os', '-fno-builtin', '-ffunction-sections', '-fdata-sections', '-falign-functions=16',
             '-I' + str(ROOT / 'code'), '-I' + str(ROOT / 'sdk/portable')]
    archive = Path(subprocess.check_output(common + ['-print-file-name=libc.a'], text=True).strip()).resolve()
    member = 'libc_a-strlen-stub.o' if cpu == 'm0' else 'libc_a-strlen.o'
    (output / 'libc-original.o').write_bytes(subprocess.check_output([tc / 'arm-none-eabi-ar', 'p', archive, member]))
    library = ElfImage(output / 'libc-original.o')
    assert library.sizes['strlen'] > 0
    subprocess.run([tc / 'arm-none-eabi-objcopy', '--redefine-sym', 'strlen=libc_strlen',
                    output / 'libc-original.o', output / 'libc.o'], check=True)
    subprocess.run(common + flags + ['-Dstrlen=baseline', '-c', str(ROOT / 'sdk/portable/memory.c'),
                    '-o', str(output / 'baseline.o')], check=True)
    subprocess.run(common + flags + ['-c', str(HERE / 'candidates.S'), '-o', str(output / 'candidates.o')], check=True)
    subprocess.run(common + flags + ['-DMK61_RUNTIME_POINTER=bench_strlen_runtime', '-c',
                    str(ROOT / 'sdk/portable/system/runtime.S'), '-o', str(output / 'runtime-all.o')], check=True)
    subprocess.run([tc / 'arm-none-eabi-objcopy', '--redefine-sym', 'strlen=runtime_strlen',
                    '--keep-global-symbol=runtime_strlen', '--keep-global-symbol=bench_strlen_runtime',
                    output / 'runtime-all.o', output / 'runtime.o'], check=True)
    subprocess.run(common + flags + ['-c', str(HERE / 'runtime_binding.c'),
                    '-o', str(output / 'runtime-binding.o')], check=True)
    subprocess.run([tc / 'arm-none-eabi-objcopy', '--keep-global-symbol=baseline',
                    output / 'baseline.o', output / 'baseline-only.o'], check=True)
    names = ['baseline', 'libc_strlen', 'byte1', 'byte4', 'word1', 'word2', 'word4']
    if cpu == 'm4':
        names += ['dsp1', 'dsp4', 'dsp8', 'dsp32']
    names += ['runtime_strlen']
    command = common + ['-nostdlib', '-Wl,--gc-sections,-Ttext=' + hex(base) + ',-e,byte1' +
        ''.join(',-u,' + name for name in names), str(output / 'baseline.o'), str(output / 'libc.o'),
        str(output / 'candidates.o'), str(output / 'runtime.o'), str(output / 'runtime-binding.o'),
        '-o', str(output / 'kernels.elf')]
    subprocess.run(command, check=True)
    subprocess.run([tc / 'arm-none-eabi-objcopy', '-O', 'binary', output / 'kernels.elf', output / 'kernels.bin'], check=True)
    (output / 'disassembly.txt').write_text(subprocess.check_output([tc / 'arm-none-eabi-objdump', '-d',
                                                                   output / 'kernels.elf'], text=True))
    image = ElfImage(output / 'kernels.elf')
    result = dict(status='BUILT_NOT_HARDWARE_QUALIFIED', cpu=cpu, base=base, ELF_sha256=sha(output / 'kernels.elf'),
        compiler=subprocess.check_output([tc / 'arm-none-eabi-gcc', '--version'], text=True).splitlines()[0],
        source={str(path.relative_to(ROOT)):sha(path) for path in [HERE / 'candidates.S',
            ROOT / 'sdk/portable/memory.c', ROOT / 'sdk/portable/system/runtime.S', HERE / 'runtime_binding.c',
            ROOT / 'code/loadable_system_runtime.def']},
        libc=dict(archive=str(archive), member=member, object_sha256=sha(output / 'libc-original.o')),
        functions={name:dict(entry=hex(image.symbols[name] | 1), bytes=image.sizes[name],
            read_granule=8 if cpu == 'm4' and name in ['libc_strlen', 'dsp8', 'dsp32'] else
                         1 if name in ['baseline', 'byte1', 'byte4'] else 4,
            prefix_read_bytes=7 if name == 'libc_strlen' and cpu == 'm4' else 0,
            runtime_target='word4' if name == 'runtime_strlen' else None) for name in names},
        link_command=command, hardware_access=False)
    (output / 'kernels.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--arm-toolchain-bin', type=Path, required=True)
    parser.add_argument('--cpu', choices=['m0', 'm4'], required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--base', type=lambda value:int(value, 0), default=0x20000000)
    args = parser.parse_args()
    print(json.dumps(build(args.arm_toolchain_bin, args.output.resolve(), args.cpu, args.base), indent=2))
