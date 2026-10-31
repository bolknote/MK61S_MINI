#!/usr/bin/env python3
"""ARM memchr early-hit/object-end tests at an unreadable memory boundary.

C11 7.24.5.1 requires sequential-stop behavior: count may exceed the object
when a match is found within it. These are functional tests, never timings.
"""
import argparse
import hashlib
import json
from pathlib import Path

from check_stm32_vectors import ElfImage
from unicorn import (Uc, UcError, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS,
                     UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE,
                     UC_HOOK_MEM_READ_UNMAPPED, UC_MEM_WRITE)
from unicorn.arm_const import (UC_CPU_ARM_CORTEX_M0, UC_CPU_ARM_CORTEX_M4,
    UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R4,
    UC_ARM_REG_R11, UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC,
    UC_ARM_REG_XPSR)


def cases():
    for size in [*range(1, 130), 255, 256, 257, 511, 512, 513, 4096]:
        hits = range(size) if size <= 16 else sorted({0, 1, 2, 3, 4, 5, 6, 7,
                                                    8, 15, 16, size // 2, size - 1})
        for value in (0, -1, 0x123400A5):
            for hit in hits:
                for count in sorted({size, size + 1, size + 8, 0xffffffff}):
                    yield size, value, hit, count
            # An absent character is defined only within the valid object.
            yield size, value, -1, size
    yield 0, -1, -1, 0


def verify(path, cpu, names, keep_going=False, guard=0x20080000):
    elf = ElfImage(path)
    machine = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
    machine.ctl_set_cpu_model(UC_CPU_ARM_CORTEX_M0 if cpu == 'm0' else UC_CPU_ARM_CORTEX_M4)
    assert 0x20001000 <= guard <= 0x20080000 and guard % 32 == 0
    stack, stop = 0x200fe000, 0x30000000
    for address, size in ((0x20000000, 0x80000), (0x200f0000, 0x10000),
                          (0x08000000, 0x100000), (0x10000000, 0x200000),
                          (stop, 4096)):
        machine.mem_map(address, size)
    elf.load(machine)
    saved = {reg: 0x72816201 + reg * 314 for reg in range(UC_ARM_REG_R4, UC_ARM_REG_R11 + 1)}
    active = {}

    def access(_machine, kind, address, size, _value, _user):
        if cpu == 'm0':
            assert size in (1, 2, 4) and address % size == 0, ('alignment', address, size)
        on_stack = stack - 64 <= address and address + size <= stack
        if kind == UC_MEM_WRITE:
            assert on_stack, ('write outside stack', hex(address), size)
        else:
            assert on_stack or any(lo <= address and address + size <= hi
                                   for lo, hi in active['read']), ('read outside object/code', hex(address), size)

    def unmapped(_machine, _kind, address, size, _value, _user):
        active['memory_fault'] = dict(address=hex(address), bytes=size)
        return False

    machine.hook_add(UC_HOOK_MEM_READ | UC_HOOK_MEM_WRITE, access)
    machine.hook_add(UC_HOOK_MEM_READ_UNMAPPED, unmapped)
    corpus = list(cases())
    results = []
    for name in names:
        start = elf.symbols[name] & ~1
        size = elf.sizes[name]
        if not size:
            size = (elf.symbols[name + '_end'] & ~1) - start
        section = next(s for s in elf.sections if s[2] & 4 and s[3] <= start
                       and start + size <= s[3] + s[5])
        offset = section[4] + start - section[3]
        row = dict(name=name, body_bytes=size,
                   body_sha256=hashlib.sha256(elf.data[offset:offset + size]).hexdigest(),
                   cases=0, failures=0, examples=[])
        for object_size, value, hit, count in corpus:
            pointer = guard - object_size
            wanted = value & 255
            data = bytearray(bytes((wanted ^ 1, wanted ^ 128)) * (object_size // 2 + 1))[:object_size]
            if hit >= 0:
                data[hit] = wanted
            if data:
                machine.mem_write(pointer, bytes(data))
            expected = pointer + hit if hit >= 0 else 0
            active.clear()
            active.update(read=[(pointer, guard), (start, start + size)])
            for reg, initial in saved.items():
                machine.reg_write(reg, initial)
            for reg, initial in ((UC_ARM_REG_R0, pointer), (UC_ARM_REG_R1, value & 0xffffffff),
                                 (UC_ARM_REG_R2, count), (UC_ARM_REG_SP, stack),
                                 (UC_ARM_REG_LR, stop | 1), (UC_ARM_REG_XPSR, 0x01000000)):
                machine.reg_write(reg, initial)
            row['cases'] += 1
            try:
                machine.emu_start(start | 1, stop, count=1500000)
                assert machine.reg_read(UC_ARM_REG_PC) == stop, 'did not return'
                assert machine.reg_read(UC_ARM_REG_R0) == expected, 'wrong first match'
                assert machine.reg_read(UC_ARM_REG_SP) == stack, 'stack changed'
                assert all(machine.reg_read(reg) == initial for reg, initial in saved.items()), 'callee-saved register changed'
            except (UcError, AssertionError) as error:
                row['failures'] += 1
                if len(row['examples']) < 8:
                    row['examples'].append(dict(object_bytes=object_size, pointer=hex(pointer),
                        value=value, first_match=hit, count=count, expected=hex(expected),
                        pc=hex(machine.reg_read(UC_ARM_REG_PC)), failure=repr(error),
                        memory_fault=active.get('memory_fault')))
                if not keep_going:
                    break
        row['status'] = 'FAIL' if row['failures'] else 'PASS'
        results.append(row)
        print(json.dumps(row), flush=True)
    return dict(status='FAIL' if any(r['failures'] for r in results) else 'PASS',
                cpu=cpu, scope='Functional early-hit/object-end/guard tests, not hardware timing',
                guard=hex(guard), boundary='unmapped page' if guard==0x20080000 else 'read hook emulates MPU boundary',
                full_cases_per_body=len(corpus),
                elf_sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest(), results=results)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--elf', type=Path, required=True)
    parser.add_argument('--cpu', choices=('m0', 'm4'), required=True)
    parser.add_argument('--names', nargs='+', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--keep-going', action='store_true')
    parser.add_argument('--guard', type=lambda v:int(v,0), default=0x20080000)
    args = parser.parse_args()
    result = verify(args.elf, args.cpu, args.names, args.keep_going, args.guard)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    raise SystemExit(1 if result['status'] != 'PASS' else 0)
