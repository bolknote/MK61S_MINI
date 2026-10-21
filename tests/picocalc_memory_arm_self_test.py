#!/usr/bin/env python3
"""Check linked Pico memcpy/memmove routing and execute the retained ROM memset bridge."""
import argparse
import hashlib
import json
import struct
from pathlib import Path

from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS
from unicorn.arm_const import (
    UC_CPU_ARM_CORTEX_M0, UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2,
    UC_ARM_REG_R4, UC_ARM_REG_R11, UC_ARM_REG_SP, UC_ARM_REG_LR,
    UC_ARM_REG_PC, UC_ARM_REG_XPSR,
)
from check_stm32_vectors import ElfImage

ROOT = Path(__file__).resolve().parents[1]


def verify(elf, rom):
    image = ElfImage(elf)
    machine = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
    machine.ctl_set_cpu_model(UC_CPU_ARM_CORTEX_M0)
    machine.mem_map(0, 0x4000)
    machine.mem_map(0x10000000, 0x200000)
    machine.mem_map(0x20000000, 0x100000)
    machine.mem_map(0x30000000, 4096)
    machine.mem_write(0, rom.read_bytes())
    image.load(machine)
    stop, sp, dest = 0x30000000, 0x200fe000, 0x200e0000
    saved = {reg: 0x7a610000 + reg for reg in range(UC_ARM_REG_R4, UC_ARM_REG_R11 + 1)}

    def call(name, args):
        registers = dict(saved)
        registers.update(zip((UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2), args))
        registers.update({UC_ARM_REG_SP: sp, UC_ARM_REG_LR: stop | 1, UC_ARM_REG_XPSR: 0x01000000})
        for reg, value in registers.items():
            machine.reg_write(reg, value)
        machine.emu_start(image.symbols[name] | 1, stop, count=100000)
        assert machine.reg_read(UC_ARM_REG_PC) == stop, (name, 'return')
        assert machine.reg_read(UC_ARM_REG_SP) == sp, (name, 'SP')
        assert all(machine.reg_read(reg) == value for reg, value in saved.items()), (name, 'AAPCS')
        return machine.reg_read(UC_ARM_REG_R0)

    copy = image.symbols['__wrap_memcpy']
    assert 0x20000000 <= copy < 0x20042000, ('memcpy must execute in SRAM', hex(copy))
    for alias in ('__wrap___aeabi_memcpy', '__wrap___aeabi_memcpy4', '__wrap___aeabi_memcpy8'):
        assert image.symbols[alias] == copy, alias
    runtime = image.symbols['_ZN8picocalc14native_runtimeE']
    assert struct.unpack('<I', machine.mem_read(runtime + 22 * 4, 4))[0] == copy
    assert struct.unpack('<I', machine.mem_read(runtime + 23 * 4, 4))[0] == image.symbols['__wrap_memset']

    move = image.symbols['__wrap_memmove']
    assert 0x20000000 <= move < 0x20042000, ('memmove must execute in SRAM', hex(move))
    for alias in ('__wrap___aeabi_memmove', '__wrap___aeabi_memmove4', '__wrap___aeabi_memmove8'):
        assert image.symbols[alias] == move, alias
    assert struct.unpack('<I', machine.mem_read(runtime + 24 * 4, 4))[0] == move

    table = image.symbols['aeabi_mem_funcs']
    assert image.symbols['aeabi_mem_funcs_end'] - table == 16
    assert struct.unpack('<4I', machine.mem_read(table, 16)) == (0x534d, 0x434d, 0x3453, 0x3443)
    call('__aeabi_mem_init', ())
    expected = (0x26b9, 0x261d, 0x26ad, 0x2605)
    assert struct.unpack('<4I', machine.mem_read(table, 16)) == expected
    results = []
    for name, alignment in [('__wrap_memset', 1), ('__wrap___aeabi_memset', 1),
                            ('__wrap___aeabi_memset4', 4), ('__wrap___aeabi_memset8', 8)]:
        cases = 0
        for size in [*range(258), 511, 512, 513, 1024, 4096]:
            for offset in range(0, 8, alignment):
                for value in (0, 0xa5, 0x1234, 0xffffffff):
                    machine.mem_write(dest - 16, b'\x5a' * (size + 48))
                    pointer = dest + offset
                    args = (pointer, value, size) if name == '__wrap_memset' else (pointer, size, value)
                    returned = call(name, args)
                    if name == '__wrap_memset':
                        assert returned == pointer, (name, 'ISO C return')
                    expected_bytes = b'\x5a' * (16 + offset) + bytes([value & 255]) * size + b'\x5a' * (32 - offset)
                    assert bytes(machine.mem_read(dest - 16, size + 48)) == expected_bytes, (name, size, offset, value)
                    cases += 1
        results.append(dict(name=name, cases=cases, status='PASS'))
    return dict(status='PASS', elf_sha256=hashlib.sha256(elf.read_bytes()).hexdigest(),
                bootrom_sha256=hashlib.sha256(rom.read_bytes()).hexdigest(),
                memcpy_address=hex(copy), memcpy_bytes=image.sizes['__wrap_memcpy'],
                memmove_address=hex(move), memmove_bytes=image.sizes['__wrap_memmove'],
                runtime_slots='memcpy=22, memset=23, memmove=24', rom_mem_funcs=[hex(value) for value in expected],
                results=results)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf', type=Path)
    parser.add_argument('--bootrom', type=Path, default=ROOT / 'research/rp2040-memset-2026-10-21/capture/bootrom.bin')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = verify(args.elf, args.bootrom)
    print(json.dumps(result, indent=2))
    if args.output:
        args.output.write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()
