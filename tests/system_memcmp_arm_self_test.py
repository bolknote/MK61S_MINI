#!/usr/bin/env python3
"""Execute ARM memcmp: unsigned lexicographic order, exact bounds, readonly, ABI."""
import argparse
import hashlib
import json
from pathlib import Path
import random
import shutil
import subprocess
import tempfile
from check_stm32_vectors import ElfImage
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS, UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE, UC_MEM_WRITE
from unicorn.arm_const import (UC_CPU_ARM_CORTEX_M0, UC_CPU_ARM_CORTEX_M4,
    UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R4, UC_ARM_REG_R11,
    UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_XPSR)

ROOT = Path(__file__).resolve().parents[1]


def verify(elf, cpu, names):
    image = ElfImage(elf)
    machine = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
    machine.ctl_set_cpu_model(UC_CPU_ARM_CORTEX_M0 if cpu == 'm0' else UC_CPU_ARM_CORTEX_M4)
    for address, size in ((0x20000000, 0x100000), (0x08000000, 0x100000),
                          (0x10000000, 0x200000), (0x30000000, 4096)):
        machine.mem_map(address, size)
    image.load(machine)
    stop, stack, left, right = 0x30000000, 0x200fe000, 0x20010000, 0x20050000
    rng = random.Random(610425)
    pattern = bytes(rng.getrandbits(8) for _ in range(65536 + 128))
    cases = []
    sizes = [*range(130), 255, 256, 257, 511, 512, 513, 1023, 1024, 1025,
             4095, 4096, 4097, 16384, 65536]
    for n in sizes:
        positions = (range(n) if n <= 16 else sorted({0, 1, 3, 4, 7, 8, 15, 16, n // 2, n - 1}))
        for a in range(4):
            for b in range(4):
                cases.append((n, a, b, -1, 0, 0, False))
                for at in positions:
                    cases.extend([(n, a, b, at, 0x7f, 0x80, False),
                                  (n, a, b, at, 0xff, 0, False)])
    for value in range(256):
        for other in (0, 1, 127, 128, 254, 255):
            cases.append((1, value % 4, other % 4, 0, value, other, False))
    for n in sizes:
        for a in range(4):
            cases.append((n, a, a, -1, 0, 0, True))
    for _ in range(500):
        n = rng.randrange(8193)
        cases.append((n, rng.randrange(16), rng.randrange(16), rng.randrange(n) if n else -1,
                      rng.randrange(256), rng.randrange(256), False))
    cases.append((0, 0, 0, -1, 0, 0, 'null'))
    saved = {reg: 0x72816201 + reg * 314 for reg in range(UC_ARM_REG_R4, UC_ARM_REG_R11 + 1)}
    active = [0, 0, 0]

    def access(_machine, kind, address, size, _value, _user):
        n, a, b = active
        if cpu == 'm0':
            assert size in (1, 2, 4) and address % size == 0, ('alignment', hex(address), size, active)
        on_stack = stack - 64 <= address and address + size <= stack
        if kind == UC_MEM_WRITE:
            assert on_stack, ('memcmp wrote outside stack', hex(address), size, active)
        else:
            assert on_stack or any(start <= address and address + size <= start + n for start in (a, b)), \
                ('read beyond input span', hex(address), size, active)

    machine.hook_add(UC_HOOK_MEM_READ | UC_HOOK_MEM_WRITE, access)

    def call(name, a, b, n, expected):
        active[:] = [n, a, b]
        for reg, value in saved.items():
            machine.reg_write(reg, value)
        for reg, value in ((UC_ARM_REG_R0, a), (UC_ARM_REG_R1, b), (UC_ARM_REG_R2, n),
                           (UC_ARM_REG_SP, stack), (UC_ARM_REG_LR, stop | 1), (UC_ARM_REG_XPSR, 0x01000000)):
            machine.reg_write(reg, value)
        try:
            machine.emu_start(image.symbols[name] | 1, stop, count=1500000)
        except Exception:
            print('FAIL', name, n, hex(a), hex(b), hex(machine.reg_read(UC_ARM_REG_PC)), flush=True)
            raise
        assert machine.reg_read(UC_ARM_REG_PC) == stop, (name, n, 'return')
        actual = machine.reg_read(UC_ARM_REG_R0)
        if actual & 0x80000000:
            actual -= 0x100000000
        assert (actual > 0) - (actual < 0) == (expected > 0) - (expected < 0), \
            (name, n, hex(a), hex(b), 'unsigned lexical result', actual, expected)
        assert machine.reg_read(UC_ARM_REG_SP) == stack, (name, n, 'stack')
        assert all(machine.reg_read(reg) == value for reg, value in saved.items()), (name, n, 'callee saved')

    results = []
    for name in names:
        count = 0
        for n, aa, ba, at, av, bv, same in cases:
            a, b = left + aa, right + ba
            first, second = bytearray(pattern[:n]), bytearray(pattern[:n])
            expected = 0
            if at >= 0:
                first[at], second[at] = av, bv
                expected = av - bv
                # A later, opposite difference catches native little-endian
                # word comparisons which ignore the first differing byte.
                if av != bv and at + 1 < n:
                    first[at + 1], second[at + 1] = (255, 0) if av < bv else (0, 255)
            machine.mem_write(a, bytes(first))
            machine.mem_write(b, bytes(second))
            if same:
                b = a
                expected = 0
            if same == 'null':
                a = b = 0
            call(name, a, b, n, expected)
            count += 1
        # Read-only input spans may overlap, in either direction.
        for n in range(130):
            for aa in range(4):
                for delta in (-17, -4, -1, 0, 1, 4, 17):
                    a = left + 32 + aa
                    b = a + delta
                    low = min(a, b)
                    content = pattern[:n + abs(delta)]
                    machine.mem_write(low, content)
                    first = content[a - low:a - low + n]
                    second = content[b - low:b - low + n]
                    expected = (first > second) - (first < second)
                    call(name, a, b, n, expected)
                    count += 1
        row = dict(name=name, cases=count, bytes=image.sizes.get(name), status='PASS')
        results.append(row)
        print(row, flush=True)
    return dict(cpu=cpu, elf_sha256=hashlib.sha256(elf.read_bytes()).hexdigest(), results=results)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--arm-toolchain-bin', type=Path)
    parser.add_argument('--elf', type=Path)
    parser.add_argument('--cpu', choices=('m0', 'm4'))
    parser.add_argument('--names', nargs='+', default=['memcmp'])
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.elf:
        assert args.cpu, 'Pass --cpu with --elf'
        result = verify(args.elf, args.cpu, args.names)
    else:
        compiler = shutil.which('arm-none-eabi-gcc')
        tc = args.arm_toolchain_bin or (Path(compiler).parent if compiler else None)
        assert tc, 'Pass --arm-toolchain-bin'
        variants = [('m0', 'sdk/portable/memory.c', 'memcmp', []),
                    ('m4', 'sdk/portable/memory.c', 'memcmp', []),
                    ('m4', 'code/system_memory.c', 'memcmp', ['-DMK61_MEMORY_TEST_BUILD=1'])]
        result = []
        with tempfile.TemporaryDirectory(prefix='mk61-memcmp-arm-') as tmp:
            elf = Path(tmp) / 'compare.elf'
            for cpu, source, name, defines in variants:
                for lto in (False, True):
                    command = [str(tc / 'arm-none-eabi-gcc'), '-mcpu=' + ('cortex-m0plus' if cpu == 'm0' else 'cortex-m4'),
                        '-mthumb', '-Os', '-std=c11', '-Wall', '-Wextra', '-Werror', '-fno-builtin',
                        '-ffunction-sections', '-fdata-sections', *(['-flto'] if lto else []), *defines,
                        str(ROOT / source), '-I' + str(ROOT / 'code'), '-nostdlib',
                        '-Wl,--gc-sections,-Ttext=0x20000000,--section-start=.time_critical.memcmp=0x20001000,-e,' + name,
                        '-o', str(elf)]
                    subprocess.run(command, check=True)
                    row = verify(elf, cpu, [name])
                    row.update(source=source, lto=lto)
                    result.append(row)
    if args.output:
        args.output.write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()
