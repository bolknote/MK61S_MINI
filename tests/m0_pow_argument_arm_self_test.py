#!/usr/bin/env python3
"""Check the RP2040 pow argument against exact integer multiplication."""
import argparse
import hashlib
import itertools
import json
from pathlib import Path
import random
import struct

from native_eabi_m0_arm_self_test import Machine, SP, STOP
from unicorn import UC_HOOK_MEM_WRITE
from unicorn.arm_const import (UC_ARM_REG_R0, UC_ARM_REG_R2, UC_ARM_REG_R3,
    UC_ARM_REG_R4, UC_ARM_REG_R11, UC_ARM_REG_SP, UC_ARM_REG_LR,
    UC_ARM_REG_XPSR, UC_ARM_REG_PC)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--elf', type=Path, required=True)
    parser.add_argument('--samples', type=int, default=100000)
    parser.add_argument('--frame-bytes', type=int, choices=(44, 60), default=60)
    parser.add_argument('--json', type=Path, required=True)
    args = parser.parse_args()
    assert args.samples >= 0
    machine = Machine(args.elf, True)
    uc = machine.uc
    assert 'mk61_m0_pow_argument' in machine.elf.symbols, 'RP2040 ELF required'

    # Independently bound every base-2^16 column, including the final carry.
    # This justifies the two-word accumulators and zero fourth output word.
    base = 1 << 16
    amax, bmax = [base-1]*5, [base-1]*3+[31]
    carry = 0
    maxima = []
    for column in range(2, 8):
        total = carry + sum(amax[i]*bmax[column-i]
            for i in range(5) if 0 <= column-i < 4)
        assert total < 1 << 34
        maxima.append(total)
        carry = total >> 16
    assert maxima[-1] < 1 << 21 and carry < 32
    omitted_max = (base-1)**2 * (1+2*base)
    assert omitted_max < 1 << 50 < 1 << 53
    assert (80+53-32)-21 <= 80

    rng = random.Random(0x2353)
    edges = {0, (1 << 64)-1, 0xffff0000ffff0000, 0xffff00000000ffff}
    for bit in range(64):
        edges.update(n for n in [(1 << bit)-1, 1 << bit, (1 << bit)+1]
                     if n < 1 << 64)
    boundary = itertools.product(sorted(edges), [0, 1, 0xffff],
        [0, 1, 0xffff, (1 << 32)-1, 1 << 52, (1 << 53)-1],
        [53, 63, 64, 65, 70])
    random_cases = ((rng.getrandbits(64), rng.getrandbits(16),
                    rng.getrandbits(53), rng.randrange(53, 71))
                    for _ in range(args.samples))
    saved = {r: (0xa75d184b+r*0x1321) & 0xffffffff
             for r in range(UC_ARM_REG_R4, UC_ARM_REG_R11+1)}
    result_address = SP-256

    def bounded_write(_uc, _access, address, size, _value, _data):
        assert (SP-args.frame_bytes <= address and address+size <= SP) or (
            result_address <= address and address+size <= result_address+16), (
                'write outside function frame/result', hex(address), size)

    uc.hook_add(UC_HOOK_MEM_WRITE, bounded_write)
    digest = hashlib.sha256()
    count = 0
    for low, high, sy, shift in itertools.chain(boundary, random_cases):
        full = (low+(high << 64))*sy
        omitted = ((low & 0xffff)*(sy & 0xffff) +
            (((low & 0xffff)*((sy >> 16) & 0xffff) +
              ((low >> 16) & 0xffff)*(sy & 0xffff)) << 16))
        expected = (full-omitted) >> shift
        assert 0 <= (full >> shift)-expected <= 1
        for register, value in saved.items():
            uc.reg_write(register, value)
        for register, value in [(UC_ARM_REG_R0, result_address),
                (UC_ARM_REG_R2, low & 0xffffffff), (UC_ARM_REG_R3, low >> 32),
                (UC_ARM_REG_SP, SP), (UC_ARM_REG_LR, STOP | 1),
                (UC_ARM_REG_XPSR, 0x01000000)]:
            uc.reg_write(register, value)
        uc.mem_write(SP, struct.pack('<IIQI', high, 0, sy, shift))
        uc.emu_start(machine.elf.symbols['mk61_m0_pow_argument'] | 1,
                     STOP, count=1000)
        assert uc.reg_read(UC_ARM_REG_PC) == STOP
        assert uc.reg_read(UC_ARM_REG_SP) == SP
        for register, value in saved.items():
            assert uc.reg_read(register) == value, ('callee-saved', register)
        hi, lo = struct.unpack('<QQ', uc.mem_read(result_address, 16))
        got = (hi << 64) | lo
        assert got == expected, (hex(low), high, hex(sy), shift,
                                 hex(got), hex(expected))
        digest.update(struct.pack('<QIIQQQ', low, high, shift, sy, lo, hi))
        count += 1
    report = dict(status='PASS', cases=count,
        elf_sha256=hashlib.sha256(args.elf.read_bytes()).hexdigest(),
        column_maxima=maxima, result_sha256=digest.hexdigest(),
        oracle='Exact Python product minus three omitted bottom terms; '
               'exact equality and at most one unit below full product.',
        abi=f'R4-R11 and SP preserved; writes confined to the {args.frame_bytes}-byte frame '
            'and 16-byte result. Includes shifts 63/64/65 and all 18 shifts.',
        frame_bytes=args.frame_bytes)
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2), flush=True)


if __name__ == '__main__':
    main()
