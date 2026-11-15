#!/usr/bin/env python3
"""Check idle APP input-pump cost in the actual ARM firmware."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]
from check_stm32_vectors import ElfImage
from unicorn_runtime import Uc
from unicorn import UC_ARCH_ARM, UC_MODE_MCLASS, UC_MODE_THUMB, UC_HOOK_CODE
from unicorn.arm_const import (UC_CPU_ARM_CORTEX_M0, UC_ARM_REG_R0, UC_ARM_REG_R1,
                               UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC,
                               UC_ARM_REG_XPSR)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--firmware', type=Path, required=True)
    args = parser.parse_args()
    image = ElfImage(args.firmware)
    uc = Uc(UC_ARCH_ARM, UC_MODE_MCLASS | UC_MODE_THUMB)
    uc.ctl_set_cpu_model(UC_CPU_ARM_CORTEX_M0)
    uc.mem_map(0x10000000, 0x200000)
    uc.mem_map(0x20000000, 0x42000)
    image.load(uc)
    symbols = {
        'pulse': '_ZN8picocalc8controls5pulseEhm',
        'service': '_ZN8picocalc8controls7serviceEm',
        'pressed': '_ZN8picocalc8controls7pressedEhm',
    }

    def call(name, first, second=0):
        steps = [0]
        def count(_uc, _address, _size, _user):
            steps[0] += 1
        hook = uc.hook_add(UC_HOOK_CODE, count)
        uc.reg_write(UC_ARM_REG_SP, 0x2003fff0)
        uc.reg_write(UC_ARM_REG_LR, 0x101ff001)
        uc.reg_write(UC_ARM_REG_R0, first)
        uc.reg_write(UC_ARM_REG_R1, second)
        uc.reg_write(UC_ARM_REG_XPSR, 0x01000000)
        uc.emu_start(image.symbols[symbols[name]] | 1, 0x101ff000, count=100000)
        assert uc.reg_read(UC_ARM_REG_PC) == 0x101ff000, name
        uc.hook_del(hook)
        return uc.reg_read(UC_ARM_REG_R0), steps[0]

    idle = [call('service', now)[1] for now in (1000, 1001, 1002)]
    assert max(idle) < 100, f'idle input pump regressed: {idle} instructions'
    call('pulse', ord('x'), 1100)
    call('pulse', ord('x'), 1101)
    assert call('pressed', ord('x'), 1280)[0] == 1
    call('service', 1281)
    assert call('pressed', ord('x'), 1281)[0] == 0
    assert call('service', 1282)[1] < 100, 'renewed pulse left the idle pump busy'
    call('pulse', ord('a'), 0xffffff4c)
    assert call('pressed', ord('a'), 0xffffffff)[0] == 1
    assert call('pressed', ord('a'), 0)[0] == 0
    call('service', 0)
    assert call('service', 1)[1] < 100, 'wrapped pulse left the idle pump busy'
    print(f'ARM idle input pump: {idle} instructions; renewed and wrapped pulses PASS')


if __name__ == '__main__':
    main()
