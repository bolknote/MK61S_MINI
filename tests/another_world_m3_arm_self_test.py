#!/usr/bin/env python3
"""Execute the packaged M3 PCM mixer as relocated Thumb-2 code."""
import argparse
from pathlib import Path
import random
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "sdk/coproc"), str(ROOT / "tests")]
from elf32 import ELF
from unicorn_runtime import Uc
from unicorn import UC_ARCH_ARM, UC_MODE_MCLASS, UC_MODE_THUMB, UC_HOOK_CODE, UC_HOOK_MEM_WRITE
from unicorn.arm_const import (UC_CPU_ARM_CORTEX_M3, UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2,
                               UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_XPSR)

BASE, MODULE, INPUT, OUTPUT, JOB, STACK, STOP = (0x20000000, 0x20010000, 0x20002000, 0x20002400,
                                                 0x20002800, 0x2000F000, 0x20018000)


def signed(byte):
    return byte if byte < 128 else byte - 256


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--module", type=Path, default=ROOT / ".build/another-app/m3/AWPCM")
    args = parser.parse_args()
    elf = ELF(args.module.with_suffix(".elf"))
    image = args.module.with_suffix(".bin").read_bytes()
    assert not [r for r in elf.relocations() if r[1] == 2]
    u = Uc(UC_ARCH_ARM, UC_MODE_MCLASS | UC_MODE_THUMB)
    u.ctl_set_cpu_model(UC_CPU_ARM_CORTEX_M3)
    u.mem_map(BASE, 0x20000)
    u.mem_write(MODULE, image)
    entry = MODULE + (elf.entry - BASE)
    instructions = [0]

    def tick(_u, _address, _size, _data):
        instructions[0] += 1

    def write(_u, _kind, address, size, _value, _data):
        allowed = ((OUTPUT <= address and address + size <= OUTPUT + 72) or
                   (JOB <= address and address + size <= JOB + 24) or
                   (STACK - 4096 <= address and address + size <= STACK))
        assert allowed, (hex(address), size)

    u.hook_add(UC_HOOK_CODE, tick)
    u.hook_add(UC_HOOK_MEM_WRITE, write)

    def invoke(operation):
        instructions[0] = 0
        for reg, value in ((UC_ARM_REG_R0, operation), (UC_ARM_REG_R1, 0), (UC_ARM_REG_R2, JOB),
                           (UC_ARM_REG_SP, STACK), (UC_ARM_REG_LR, STOP | 1), (UC_ARM_REG_XPSR, 0x1000000)):
            u.reg_write(reg, value)
        u.emu_start(entry | 1, STOP, count=100000)
        assert u.reg_read(UC_ARM_REG_PC) == STOP and u.reg_read(UC_ARM_REG_SP) == STACK
        return u.reg_read(UC_ARM_REG_R0), instructions[0]

    rng = random.Random(0xA770)
    maximum = 0
    for case in range(100):
        frames = 1 + case % 64
        packet = bytearray(44)
        struct.pack_into("<IHBBHH", packet, 0, 0x314D5741, case, frames, 0, 1000, 0)
        channels = []
        for channel in range(4):
            fraction, volume, step = rng.randrange(256), rng.randrange(64), rng.randrange(1, 667)
            n = ((fraction + (frames - 1) * step) >> 8) + 2
            if len(packet) + n > 512:
                continue
            packet[7] |= 1 << channel
            struct.pack_into("<HBBBBH", packet, 12 + channel * 8, len(packet), n, frames, fraction, volume, step)
            source = bytes(rng.randrange(256) for _ in range(n))
            packet.extend(source)
            channels.append((fraction, volume, step, source))
        u.mem_write(INPUT, bytes(packet))
        u.mem_write(OUTPUT, bytes(72))
        u.mem_write(JOB, struct.pack("<6I", INPUT, len(packet), OUTPUT, 72, 0, 0))
        status, count = invoke(0)
        maximum = max(maximum, count)
        while status == 0:
            status, count = invoke(1)
            maximum = max(maximum, count)
        assert status == 1
        output = bytes(u.mem_read(OUTPUT, 8 + frames))
        assert struct.unpack_from("<IBBH", output) == (0x314D5750, frames, 0, case)
        for i in range(frames):
            sample = 0
            for fraction, volume, step, source in channels:
                phase = fraction + i * step
                index, frac = phase >> 8, phase & 255
                value = (signed(source[index]) * (255 - frac) + signed(source[index + 1]) * frac) >> 8
                sample = max(-128, min(127, sample + int(value * volume / 64)))
            assert output[8 + i] == 128 + int(sample / 2), (case, i)
    print(f"100 relocated Cortex-M3 jobs matched; max {maximum} instructions per call")


if __name__ == "__main__":
    main()
