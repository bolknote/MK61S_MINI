#!/usr/bin/env python3
"""Cold USB Screen must leave real F411 lazy font/VM buffers usable.

Runs the resident's actual USB start, nano malloc and shared-memory manager.
Only millis is stubbed; no physical device or game/file writes. The negative
oracle can qualify the original failing ELF with --expect-cold-failure.
"""
import argparse
import re
import struct
from pathlib import Path

from run_portable_system_arm_tests import Elf, ROOT
from unicorn import Uc, UC_ARCH_ARM, UC_HOOK_CODE, UC_MODE_MCLASS, UC_MODE_THUMB
from unicorn.arm_const import (UC_ARM_REG_C1_C0_2, UC_ARM_REG_FPEXC,
                               UC_ARM_REG_IPSR, UC_ARM_REG_LR, UC_ARM_REG_PC,
                               UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2,
                               UC_ARM_REG_R3, UC_ARM_REG_SP)

OWNER_NAMES = re.findall(r'MK61_SHARED_MEMORY_OWNER\(\s*([A-Z_]+)',
                        (ROOT / 'code/shared_memory_owner_catalog.inc').read_text())
OWNER = {name: i for i, name in enumerate(OWNER_NAMES)}


class Buffers:
    STOP = 0x080FF000
    OBJECT = 0x2001C800

    def __init__(self, path):
        self.elf = Elf(path)
        assert 'mk61_lazy_workspace_bytes' in self.elf.symbols
        assert 'mk61_lazy_bulk_bytes' in self.elf.symbols
        self.uc = Uc(UC_ARCH_ARM, UC_MODE_MCLASS | UC_MODE_THUMB)
        self.uc.mem_map(0x08000000, 0x100000)
        self.uc.mem_map(0x20000000, 0x20000)
        self.elf.load(self.uc)
        self.uc.reg_write(UC_ARM_REG_C1_C0_2, 0xF00000)
        self.uc.reg_write(UC_ARM_REG_FPEXC, 0x40000000)
        self.millis = self.elf.symbols['millis'] & ~1
        self.uc.hook_add(UC_HOOK_CODE, self.hook)

    def hook(self, uc, address, size, context):
        if address == self.millis:
            uc.reg_write(UC_ARM_REG_R0, 0)
            uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))

    def call(self, name, *args):
        self.uc.reg_write(UC_ARM_REG_SP, self.elf.symbol('_estack') - 16)
        self.uc.reg_write(UC_ARM_REG_LR, self.STOP | 1)
        for register, value in zip((UC_ARM_REG_R0, UC_ARM_REG_R1,
                                    UC_ARM_REG_R2, UC_ARM_REG_R3), args):
            self.uc.reg_write(register, value)
        address = self.elf.symbols.get(name)
        if address is None:
            address = self.elf.symbol(name)
        self.uc.emu_start(address | 1, self.STOP, count=2000000)
        assert self.uc.reg_read(UC_ARM_REG_PC) == self.STOP, name
        return self.uc.reg_read(UC_ARM_REG_R0)

    def word(self, address):
        return struct.unpack('<I', self.uc.mem_read(address, 4))[0]

    def acquire(self, slot, arena, owner, size=8192):
        obj = self.OBJECT + slot * 64
        self.uc.mem_write(obj, bytes(48))
        if not self.call('_ZN13shared_memory5Lease7acquire', obj, arena,
                         OWNER[owner], size):
            return 0
        return self.word(obj + 4)

    def release(self, slot):
        self.call('_ZN13shared_memory5Lease5reset', self.OBJECT + slot * 64)

    def heap(self):
        return self.word(self.elf.symbol('11heap_cursor'))

    def invariant(self):
        # Release ELFs may garbage-collect the host-only invariant checker.
        # These cases have no independent OverlayBuffer: prove the two live
        # boundaries directly using the actual exported allocator capacities.
        lower = (self.heap() + 7) & ~7
        upper = self.elf.symbol('__mk61_dynamic_end')
        assert self.call('_ZN13shared_memory8capacity', 3) + \
            self.call('_ZN13shared_memory8capacity', 4) == upper - lower


def start_font_buffers(path, warm, expect_failure):
    m = Buffers(path)
    previous = []
    if warm:
        for slot, arena, owner in ((0, 0, 'LANGUAGE_VM'), (1, 2, 'DISPLAY_FONT')):
            address = m.acquire(slot, arena, owner)
            assert address
            data = bytes([0x61 + slot]) * 8192
            m.uc.mem_write(address, data)
            previous.append((address, data))
            m.release(slot)
    assert m.call('_ZN10usb_screen5startEv') == 1
    pinned_heap = m.heap()
    for address, data in previous:
        assert bytes(m.uc.mem_read(address, len(data))) == data
    # This is the same first allocation path needed by native loadfont.
    workspace = m.acquire(2, 0, 'SETUP')
    bulk = m.acquire(3, 2, 'DISPLAY_FONT')
    if expect_failure and not warm:
        assert not workspace or not bulk, 'original cold-start failure absent'
        print('Original ELF: USB first blocks cold font buffers REPRODUCED')
        return
    assert workspace and bulk, 'USB first blocked lazy font buffers'
    assert m.heap() == pinned_heap, 'font path unexpectedly moved pinned memory'
    m.uc.mem_write(workspace, bytes([0xA5]) * 8192)
    assert not (workspace < bulk + 8192 and bulk < workspace + 8192)
    for address, data in previous:
        if address == bulk:
            assert bytes(m.uc.mem_read(address, len(data))) == data
    if not expect_failure:
        cache = m.word(m.elf.symbol('11image_cacheE'))
        assert cache, 'USB first silently disabled the configured VM cache'
        # This qualification profile has a 24-KiB value-initialized cache.
        # No lookup, publication, source compilation or language state yet.
        assert m.elf.symbols['mk61_lazy_vm_cache_bytes'] == 24576 + 32
        assert cache + 24576 <= pinned_heap
        assert bytes(m.uc.mem_read(cache, 24576)) == bytes(24576)
        assert m.call('19prepare_image_cache') == 1
        # Preparation must be idempotent even while the buffers are in use.
        assert m.call('24prepare_retained_buffers') == 1
        assert m.heap() == pinned_heap
        assert m.word(m.elf.symbol('11image_cacheE')) == cache
        assert bytes(m.uc.mem_read(workspace, 8192)) == bytes([0xA5]) * 8192
    assert m.call('_ZN10usb_screen5startEv') == 1
    m.invariant()
    m.release(2)
    m.release(3)
    m.invariant()
    print(('Warm' if warm else 'Cold') +
          ' USB-first: font buffers, stable heap, idempotency' +
          (', VM cache' if not expect_failure else '') + ' PASS')


def refusal(path):
    m = Buffers(path)
    before = m.heap()
    m.uc.reg_write(UC_ARM_REG_IPSR, 16)
    assert m.call('_ZN10usb_screen5startEv') == 0
    assert m.heap() == before
    m.uc.reg_write(UC_ARM_REG_IPSR, 0)
    capacity = m.call('_ZN13shared_memory8capacity', 3)
    overlay = m.acquire(0, 3, 'USB_SCREEN', capacity)
    assert overlay
    sentinel = bytes([0xB7]) * capacity
    m.uc.mem_write(overlay, sentinel)
    before = m.heap()
    assert m.call('_ZN10usb_screen5startEv') == 0
    assert m.call('_ZN10usb_screen6activeEv') == 0
    assert m.heap() == before
    assert bytes(m.uc.mem_read(overlay, capacity)) == sentinel
    m.invariant()
    print('USB preparation: IRQ/OOM refusal, live memory unchanged PASS')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--resident-elf', type=Path, required=True)
    parser.add_argument('--expect-cold-failure', action='store_true')
    args = parser.parse_args()
    start_font_buffers(args.resident_elf, False, args.expect_cold_failure)
    start_font_buffers(args.resident_elf, True, args.expect_cold_failure)
    if not args.expect_cold_failure:
        refusal(args.resident_elf)


if __name__ == '__main__':
    main()
