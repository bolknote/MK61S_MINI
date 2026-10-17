#!/usr/bin/env python3
"""Real resident USB start must coexist with Flash staging on native F411.

Only time and peripheral service are stubbed. The USB session, lazy retained
buffers, cache and allocator execute from the exact firmware ELF. Use the
negative oracle to reproduce the old exclusive-OVERLAY conflict.
"""
import argparse
from pathlib import Path

from unicorn.arm_const import UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3
from run_usb_screen_cold_buffers_arm_tests import Buffers, OWNER


class StageBuffers(Buffers):
    def __init__(self, path):
        self.session_size = 0
        super().__init__(path)
        self.allocators = {}
        for name, address in self.elf.symbols.items():
            if '14LifetimeBuffer7acquire' in name:
                self.allocators[address & ~1] = True
            elif '5Lease7acquireE' in name:
                self.allocators[address & ~1] = False

    def hook(self, uc, address, size, context):
        lifetime = getattr(self, 'allocators', {}).get(address)
        if lifetime is not None:
            owner = uc.reg_read(UC_ARM_REG_R1 if lifetime else UC_ARM_REG_R2)
            if owner == OWNER['USB_SCREEN']:
                self.session_size = uc.reg_read(UC_ARM_REG_R2 if lifetime else UC_ARM_REG_R3)
        super().hook(uc, address, size, context)


def check(path, stage_first, expect_conflict):
    m = StageBuffers(path)
    assert m.call('24prepare_retained_buffers') == 1
    stage_size = 640 * 4
    stage = m.acquire(0, 3, 'VFAT_STAGE', stage_size) if stage_first else 0
    if stage_first:
        assert stage
        m.uc.mem_write(stage, b'\xA5' * stage_size)
    started = m.call('_ZN10usb_screen5startEv')
    if expect_conflict and stage_first:
        assert started == 0
        assert bytes(m.uc.mem_read(stage, stage_size)) == b'\xA5' * stage_size
    elif expect_conflict:
        assert started == 1 and not m.acquire(0, 3, 'VFAT_STAGE', stage_size)
    else:
        assert started == 1
        session = m.word(m.elf.symbols['_ZN10usb_screen12_GLOBAL__N_1L7sessionE'])
        assert session and m.session_size >= 1536
        original = bytes(m.uc.mem_read(session, m.session_size))
        if not stage_first:
            stage = m.acquire(0, 3, 'VFAT_STAGE', stage_size)
        assert stage, 'USB Screen prevents the editor/terminal from binding its stage index'
        assert stage + stage_size <= session or session + m.session_size <= stage
        m.uc.mem_write(stage, b'\xA5' * stage_size)
        assert m.call('_ZN10usb_screen5startEv') == 1
        assert bytes(m.uc.mem_read(session, m.session_size)) == original
        assert bytes(m.uc.mem_read(stage, stage_size)) == b'\xA5' * stage_size
        m.release(0)
        assert m.word(m.elf.symbols['_ZN10usb_screen12_GLOBAL__N_1L7sessionE']) == session
        assert bytes(m.uc.mem_read(session, m.session_size)) == original
    print(('Stage-first' if stage_first else 'USB-first') +
          (': old exclusive arena conflict REPRODUCED' if expect_conflict else
           ': real USB session + full Flash stage index, independent bytes and lifetimes PASS'), flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--resident-elf', required=True, type=Path)
    ap.add_argument('--expect-conflict', action='store_true')
    args = ap.parse_args()
    for stage_first in (False, True):
        check(args.resident_elf, stage_first, args.expect_conflict)


if __name__ == '__main__':
    main()
