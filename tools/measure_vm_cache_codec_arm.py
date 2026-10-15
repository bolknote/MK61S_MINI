#!/usr/bin/env python3
"""Execute the research codec on Cortex-M4 ISA, not a device cycle benchmark.

Uses the production memcpy and checked host compressed CRC. Bounds-checks
memory writes, immutable source, stack restoration and callee-saved registers.
No I/O, caches, interrupts, Flash wait states, VM/APP lifetimes or real timing.
"""
import argparse
import json
from pathlib import Path
import struct
import subprocess
import sys
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
from check_stm32_vectors import ElfImage
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS, UC_HOOK_CODE, UC_HOOK_MEM_WRITE
from unicorn.arm_const import (UC_CPU_ARM_CORTEX_M4, UC_ARM_REG_SP, UC_ARM_REG_LR,
                               UC_ARM_REG_PC, UC_ARM_REG_R0, UC_ARM_REG_R4, UC_ARM_REG_R11,
                               UC_ARM_REG_XPSR)

A, B, C, D, J, SP, STOP = 0x20000000, 0x20004000, 0x2000A000, 0x2000E000, 0x2000F000, 0x2001F000, 0x080FF000


def build(toolchain, output):
    common = ['-Os', '-mcpu=cortex-m4', '-mthumb', '-mfpu=fpv4-sp-d16', '-mfloat-abi=hard',
              '-fno-builtin', '-ffunction-sections', '-fdata-sections', '-fstack-usage']
    commands = [[toolchain / 'arm-none-eabi-g++', *common, '-std=c++17', '-fno-exceptions', '-fno-rtti',
                 '-c', ROOT / 'tests/experimental/vm_cache_lzss_arm_probe.cpp', '-o', output / 'codec.o'],
                [toolchain / 'arm-none-eabi-gcc', *common, '-DMK61_MEMORY_TEST_BUILD',
                 '-c', ROOT / 'code/system_memory.c', '-o', output / 'memory.o'],
                [toolchain / 'arm-none-eabi-g++', *common, '-nostdlib',
                 '-Wl,-Ttext=0x08010000,-e,bench_encode,--undefined=bench_decode,--gc-sections',
                 output / 'codec.o', output / 'memory.o', '-o', output / 'codec.elf']]
    for cmd in commands:
        subprocess.run(list(map(str, cmd)), check=True)
    return ElfImage(output / 'codec.elf'), commands


def measure(elf, raw):
    u = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
    u.ctl_set_cpu_model(UC_CPU_ARM_CORTEX_M4)
    u.mem_map(0x08000000, 0x100000)
    u.mem_map(0x20000000, 0x20000)
    elf.load(u)
    assert 32 <= len(raw) <= 9728
    capacity = len(raw) * 2 + 32
    u.mem_write(A, raw)
    u.mem_write(B, b'\xA7' * (capacity + 16))
    u.mem_write(C, b'\xA7' * (len(raw) + 16))
    writable = []
    count, low = [0], [SP]

    def write(uc, access, address, size, value, user):
        del uc, access, value, user
        assert any(lo <= address and address + size <= hi for lo, hi in writable), ('out-of-bounds write', hex(address), size)

    def instruction(uc, address, size, user):
        del address, size, user
        count[0] += 1
        low[0] = min(low[0], uc.reg_read(UC_ARM_REG_SP))

    u.hook_add(UC_HOOK_MEM_WRITE, write)
    u.hook_add(UC_HOOK_CODE, instruction)

    def call(name, job, ranges):
        nonlocal writable
        u.mem_write(J, struct.pack('<7I', *job))
        count[0], low[0] = 0, SP
        writable = [(SP - 4096, SP), *ranges]
        saved = {r: (0xAC611337 + r * 0x1021) & 0xFFFFFFFF for r in range(UC_ARM_REG_R4, UC_ARM_REG_R11 + 1)}
        for r, value in saved.items():
            u.reg_write(r, value)
        u.reg_write(UC_ARM_REG_SP, SP)
        u.reg_write(UC_ARM_REG_LR, STOP | 1)
        u.reg_write(UC_ARM_REG_R0, J)
        u.reg_write(UC_ARM_REG_XPSR, 0x01000000)
        u.emu_start(elf.symbols[name] | 1, STOP, count=1000000)
        assert u.reg_read(UC_ARM_REG_PC) == STOP and u.reg_read(UC_ARM_REG_SP) == SP
        assert u.reg_read(UC_ARM_REG_R0) == 1
        assert all(u.reg_read(r) == value for r, value in saved.items())
        return dict(instructions=count[0], maximum_stack_bytes=SP - low[0])

    encode = call('bench_encode', (A, len(raw), B, capacity, len(raw), D, 0),
                  [(B, B + capacity), (D, D + 256), (J + 24, J + 28)])
    n = struct.unpack('<I', u.mem_read(J + 24, 4))[0]
    packed = bytes(u.mem_read(B, n))
    assert u.mem_read(B + n, capacity + 16 - n) == b'\xA7' * (capacity + 16 - n)
    decode = call('bench_decode', (B, n, C, len(raw), len(raw), D, 0), [(C, C + len(raw))])
    assert bytes(u.mem_read(C, len(raw))) == raw and bytes(u.mem_read(A, len(raw))) == raw
    assert u.mem_read(C + len(raw), 16) == b'\xA7' * 16
    assert bytes(u.mem_read(B, n)) == packed
    return dict(raw_bytes=len(raw), packed_bytes=n, packed_crc32=zlib.crc32(packed),
                encode=encode, decode=decode, roundtrip=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--model', type=Path, required=True, help='physical model with host codec measurements')
    ap.add_argument('--arm-toolchain-bin', type=Path, required=True)
    ap.add_argument('--output-dir', type=Path, required=True)
    args = ap.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    elf, commands = build(args.arm_toolchain_bin, args.output_dir)
    source = json.loads(args.model.read_text())
    rows = {}
    for image in source['report']['modules']:
        row = measure(elf, Path(image['file']).read_bytes())
        host = source['measurements'][image['name']]
        assert row['packed_bytes'] == host['lzss']['bytes'] and row['packed_crc32'] == host['lzss']['packed_crc32']
        rows[str(image['id'])] = dict(name=image['name'], **row)
        print(image['name'], row['encode'], row['decode'], flush=True)
    cost = {}
    for label, scenario in source['report']['scenarios'].items():
        costs = []
        for p in scenario['passes']:
            encode = sum(rows[i]['encode']['instructions'] * n for i, n in p['packed_modules'].items())
            decode = sum(rows[i]['decode']['instructions'] * n for i, n in p['thawed_modules'].items())
            costs.append(dict(encode_instructions=encode, decode_instructions=decode,
                              codec_instructions=encode + decode,
                              with_full_sizing_pass_instructions=2 * encode + decode,
                              excluded_copy_bytes=p['codec_copy_bytes'] + p['compacted_bytes']))
        cost[label] = costs
    rom = sum(s[5] for s in elf.sections if s[2] & 2 and s[1] != 8)
    result = dict(status='PASS', modules=rows, scenarios=cost,
                  standalone_allocated_rom_bytes=rom,
                  standalone_mutable_static_bytes=sum(s[5] for s in elf.sections if s[2] & 3 == 3),
                  dictionary_workspace_bytes=256, commands=[list(map(str, c)) for c in commands],
                  qualification='Cortex-M4 instruction counts, bounds/roundtrip/ABI and standalone footprint only; NOT Cortex cycles, installed Flash delta or device speedup. Full sizing pass also reported; failed encode attempts and cache copy/compaction costs excluded.')
    (args.output_dir / 'report.json').write_text(json.dumps(result, indent=2) + '\n')
    print('ARM codec roundtrip/host CRC/write bounds/ABI PASS; standalone ROM', rom, flush=True)


if __name__ == '__main__':
    main()
