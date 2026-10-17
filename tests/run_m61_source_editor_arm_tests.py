#!/usr/bin/env python3
"""A root M61 launch after SRCEDIT must leave room for larger language APPs.

Execute the resident's actual root-frame setup, cache eviction and allocator.
Stop before reading script contents; only the MPU peripheral update is stubbed.
The negative oracle reproduces the original editor/M61/VM fragmentation.
"""
import argparse
from pathlib import Path

from unicorn.arm_const import UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_R0
from run_usb_screen_cold_buffers_arm_tests import Buffers, OWNER


class ScriptBuffers(Buffers):
    def __init__(self, path):
        super().__init__(path)
        self.activate = self.elf.symbol('14activate_frame') & ~1
        self.mpu = self.elf.symbol('17set_app_execution') & ~1
        self.prepared = False

    def hook(self, uc, address, size, context):
        if address == getattr(self, 'mpu', None):
            uc.reg_write(UC_ARM_REG_R0, 1)
            uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))
        elif address == getattr(self, 'activate', None):
            self.prepared = True
            uc.reg_write(UC_ARM_REG_PC, self.STOP)
        else:
            super().hook(uc, address, size, context)


def check(path, active, expect_conflict):
    m = ScriptBuffers(path)
    assert m.call('_ZN10usb_screen5startEv') == 1
    assert m.acquire(0, 3, 'VFAT_STAGE', 640 * 4)
    cached = m.elf.symbol('11g_app_cacheE')
    assert m.call('_ZN13shared_memory5Lease7acquire', cached, 4,
                  OWNER['LOADABLE_MODULE'], 18220) == 1
    address = m.word(cached + 4)
    m.uc.mem_write(address, b'\xB7' * 18220)
    if active:
        m.uc.mem_write(m.elf.symbol('12g_call_depthE'), b'\x01')
    frame = m.OBJECT + 128
    m.uc.mem_write(frame, bytes(128))
    m.call('10load_frame', frame)
    assert m.prepared
    runtime = m.word(m.elf.symbol('15runtime_storageE'))
    assert runtime
    if active:
        assert m.word(cached + 4) == address
        assert bytes(m.uc.mem_read(address, 18220)) == b'\xB7' * 18220
        print('M61 startup preserves a live native APP and its bytes PASS', flush=True)
        return
    m.call('_ZN13shared_memory5Lease5reset', cached)
    for size in (19460, 20468, 20480):  # LANGVM, BASIC, hard APP limit.
        loaded = m.acquire(1, 4, 'LOADABLE_MODULE', size)
        assert bool(loaded) != expect_conflict, (size, loaded, hex(runtime))
        if loaded:
            assert loaded + size <= runtime
            m.release(1)
    print('Editor -> M61 -> VM: ' +
          ('old fragmentation REPRODUCED' if expect_conflict else
           'all APPs through 20 KiB fit PASS'), flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--resident-elf', required=True, type=Path)
    ap.add_argument('--expect-conflict', action='store_true')
    args = ap.parse_args()
    check(args.resident_elf, False, args.expect_conflict)
    check(args.resident_elf, True, args.expect_conflict)


if __name__ == '__main__':
    main()
