#!/usr/bin/env python3
"""Check new raw-code placements, including literal pools and native mod4=2.

This is a new-placement qualification, not a repeat of the original corpus.
It executes the frozen 1152-case matrix once per new Flash leaf, observes all
data accesses/control flow, and records the first failure without retries.
"""
import argparse
import json
from pathlib import Path
import struct
import sys

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[2] / 'tests')]
from prepare import FLASH_BASE, FLASH_BYTES, GUARD, pin
from build import load_template
from check_stm32_vectors import ElfImage


def check(template):
    from unicorn import Uc, UC_ARCH_ARM, UC_MODE_MCLASS, UC_MODE_THUMB
    from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE
    import unicorn.arm_const as a
    u = Uc(UC_ARCH_ARM, UC_MODE_MCLASS | UC_MODE_THUMB)
    u.ctl_set_cpu_model(a.UC_CPU_ARM_CORTEX_M4)
    u.mem_map(FLASH_BASE, FLASH_BYTES)
    u.mem_map(0x20000000, 0x20000)
    ElfImage(Path(template['resident_elf']['path'])).load(u)
    fixture = Path(template['fixture']['path']).read_bytes()
    u.mem_write(template['fixture_base'], fixture)
    stop, sp, operand = FLASH_BASE + FLASH_BYTES - 16, 0x2001fff0, 0x20004000
    active, counts = {}, dict(calls=0, data_reads=0, maximum_stack_bytes=0)

    def code(uc, address, size, user):
        del uc, user
        assert active['entry'] <= address and address + size <= active['code_end'], ('PC escaped leaf', hex(address), active)

    def read(uc, access, address, size, value, user):
        del uc, access, value, user
        if active['entry'] <= address and address + size <= active['code_end']:
            return  # A literal pool must be inside the copied symbol.
        if sp - 64 <= address and address + size <= sp:
            counts['maximum_stack_bytes'] = max(counts['maximum_stack_bytes'], sp - address)
            return
        assert active['pointer'] <= address and address + size <= active['read_end'], ('read envelope', hex(address), size, active)
        assert size < 4 or address % 4 == 0, ('unaligned word', hex(address), size)
        counts['data_reads'] += 1

    def write(uc, access, address, size, value, user):
        del uc, access, value, user
        assert sp - 64 <= address and address + size <= sp, ('non-frame write', hex(address), active)
        counts['maximum_stack_bytes'] = max(counts['maximum_stack_bytes'], sp - address)

    u.hook_add(UC_HOOK_CODE, code)
    u.hook_add(UC_HOOK_MEM_READ, read)
    u.hook_add(UC_HOOK_MEM_WRITE, write)
    leaves = [dict(x, address=template['fixture_base'] + x['offset']) for x in template['leaves']]
    leaves.append(dict(name='actual_native_mod4_2', address=template['actual_native_address'] & ~1,
                       bytes=template['actual_native_bytes']))
    for leaf in leaves:
        entry = leaf['address']
        byte_only = leaf['name'] in ('native_control', 'sdk_control', 'byte1', 'byte4', 'actual_native_mod4_2')
        for key in template['keys']:
            flash_pointer = template['fixture_base'] + key['offset']
            text = fixture[key['offset']:key['offset'] + key['length'] + 1]
            # Independently check expected first hit before executing the code.
            expected_offset = text.find(bytes([key['character'] & 255]))
            assert expected_offset == key['expected']
            for bank in ('SRAM', 'Flash'):
                pointer = operand + GUARD + key['alignment'] if bank == 'SRAM' else flash_pointer
                sram = b'\xa5' * (GUARD + key['alignment']) + text + b'\xa5' * GUARD
                u.mem_write(operand, sram)
                decisive = pointer + (expected_offset + 1 if expected_offset >= 0 else len(text))
                active.update(leaf=leaf['name'], case=key['index'] * 2 + int(bank == 'Flash'), bank=bank,
                              entry=entry, code_end=entry + leaf['bytes'], pointer=pointer,
                              read_end=decisive if byte_only else (decisive + 3) & ~3)
                saved = {getattr(a, 'UC_ARM_REG_R' + str(i)): 0xa1740000 + i * 0x1011 for i in range(4, 12)}
                for r, value in saved.items():
                    u.reg_write(r, value)
                for r, value in [(a.UC_ARM_REG_R0, pointer), (a.UC_ARM_REG_R1, key['character'] & 0xffffffff),
                                 (a.UC_ARM_REG_SP, sp), (a.UC_ARM_REG_LR, stop | 1),
                                 (a.UC_ARM_REG_XPSR, 0x01000000), (a.UC_ARM_REG_PRIMASK, 0),
                                 (a.UC_ARM_REG_CONTROL, 0)]:
                    u.reg_write(r, value)
                u.emu_start(entry | 1, stop, count=100000)
                assert u.reg_read(a.UC_ARM_REG_PC) == stop, ('leaf did not return', active)
                assert u.reg_read(a.UC_ARM_REG_R0) == (pointer + expected_offset if expected_offset >= 0 else 0), active
                assert u.reg_read(a.UC_ARM_REG_SP) == sp and all(u.reg_read(r) == v for r, v in saved.items()), ('AAPCS', active)
                assert u.reg_read(a.UC_ARM_REG_PRIMASK) == u.reg_read(a.UC_ARM_REG_CONTROL) == 0, active
                assert bytes(u.mem_read(operand, len(sram))) == sram, ('input modified', active)
                counts['calls'] += 1
        print(leaf['name'], 'new placement: 1152 cases PASS', flush=True)
    assert bytes(u.mem_read(template['fixture_base'], len(fixture))) == fixture
    return dict(status='PASS_HOST_NEW_FLASH_PLACEMENTS', **counts, leaves=len(leaves),
                literal_pool_escape=False, input_or_Flash_write=False, physical_IO=0, physical_speed_claim=False)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--template', required=True, type=Path)
    p.add_argument('--output-dir', required=True, type=Path)
    args = p.parse_args()
    template = load_template(args.template)
    args.output_dir.mkdir(parents=True, exist_ok=False)
    try:
        result = check(template)
    except BaseException as e:
        (args.output_dir / 'FIRST_FAILURE.json').write_text(json.dumps(dict(type=type(e).__name__, message=str(e), retries=0), indent=2) + '\n')
        raise
    result.update(template=pin(args.template), source=pin(Path(__file__)))
    path = args.output_dir / 'RESULTS.json'
    path.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(pin(path)))


if __name__ == '__main__':
    main()
