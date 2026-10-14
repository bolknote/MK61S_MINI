#!/usr/bin/env python3
"""Qualify owned startup, clock, time and STOP in an actual production ELF.

Only oscillator/status transitions and advancing hardware counters are modeled.
Reset_Handler, preinit, C++ constructors and time/STOP functions execute as ARM.
"""
import argparse
import struct
from pathlib import Path
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_MCLASS, UC_MODE_THUMB
from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE
from unicorn.arm_const import *
from run_portable_system_arm_tests import Elf

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('elf', type=Path)
parser.add_argument('--mcu', choices=['f401', 'f411'], required=True)
parser.add_argument('--no-stop', action='store_true', help='profile deliberately omits STOP support')
args = parser.parse_args()
e = Elf(args.elf)
u = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
u.ctl_set_cpu_model(UC_CPU_ARM_CORTEX_M4)
for base, size in [(0x08000000, 0x100000), (0x20000000, 0x20000),
                   (0x40000000, 0x30000), (0x50000000, 0x20000),
                   (0xE0001000, 0x1000), (0xE000E000, 0x2000)]:
    u.mem_map(base, size)
u.reg_write(UC_ARM_REG_C1_C0_2, 0xF00000)
u.reg_write(UC_ARM_REG_FPEXC, 1 << 30)
e.load(u)
# Copy each PT_LOAD's physical image, including the .data initializer in Flash.
h = struct.unpack_from('<16sHHIIIIIHHHHHH', e.data)
for i in range(h[10]):
    kind, offset, _vaddr, paddr, filesz, _memsz, _flags, _align = struct.unpack_from(
        '<8I', e.data, h[5] + i * h[9])
    if kind == 1 and filesz:
        u.mem_write(paddr, e.data[offset:offset + filesz])

RCC = 0x40023800
PWR = 0x40007000
FLASH = 0x40023C00
SYSTICK = 0xE000E010
ICSR = 0xE000ED04
DWT = 0xE0001000
PENDING = 1 << 26
frequency = 96000000 if args.mcu == 'f411' else 84000000
ram_end = 0x20020000 if args.mcu == 'f411' else 0x20010000
stop = 0x080FF000
u.mem_write(stop, bytes.fromhex('7047'))
sp = ram_end - 16


def get(address):
    return struct.unpack('<I', u.mem_read(address, 4))[0]


def put(address, value):
    u.mem_write(address, struct.pack('<I', value & 0xFFFFFFFF))


def symbol(name):
    if name in e.symbols:
        return e.symbols[name]
    matches = [v for n, v in e.symbols.items() if n.startswith(name + '.')]
    assert len(matches) == 1, (name, matches)
    return matches[0]


uw = symbol('uwTick')
core_clock = symbol('SystemCoreClock')
reads = {'icsr': [], 'val': []}
advancing_tick = False
advancing_cycles = False
pending_writes = {}
wfi_count = 0


def memory(uc, access, address, size, value, _):
    if access == 16:
        if address == RCC:
            cr = get(address)
            cr = (cr & ~((1 << 1) | (1 << 17) | (1 << 25))) | \
                ((cr & 1) << 1) | ((cr & (1 << 16)) << 1) | \
                ((cr & (1 << 24)) << 1)
            put(address, cr)
        elif address == RCC + 8:
            cfgr = get(address)
            put(address, (cfgr & ~12) | ((cfgr & 3) << 2))
        elif address == PWR + 4:
            # The F4 regulator-ready flag depends on PLLON. This ordering
            # must be modeled: an unconditional "ready" concealed a boot hang.
            assert get(RCC) & (1 << 24), 'VOSRDY must not be awaited before PLLON'
            put(address, (get(address) & ~(1 << 14)) | ((get(RCC) >> 24 & 1) << 14))
        elif address == ICSR and reads['icsr']:
            put(address, reads['icsr'].pop(0))
        elif address == SYSTICK + 8 and reads['val']:
            put(address, reads['val'].pop(0))
        elif address == uw and advancing_tick:
            put(address, get(address) + 1)
        elif address == DWT + 4 and advancing_cycles:
            put(address, get(address) + frequency // 1000000)
    elif access == 17 and address == ICSR:
        pending_writes[address] = get(address) & ~(value & (1 << 25) and PENDING)


# Main is the endpoint of startup qualification; application setup is covered on boards.
main = symbol('main') & ~1
startup = True


def code(uc, address, size, _):
    global wfi_count
    for address_written, value in list(pending_writes.items()):
        put(address_written, value)
    pending_writes.clear()
    if startup and address == main:
        uc.emu_stop()
    if bytes(uc.mem_read(address, 2)) == bytes.fromhex('30bf'):
        # Unicorn does not implement a physical STOP wakeup.
        assert get(0xE000ED10) & 4, 'WFI must follow SLEEPDEEP'
        wfi_count += 1
        uc.reg_write(UC_ARM_REG_PC, (address + 2) | 1)


u.hook_add(UC_HOOK_MEM_READ, memory)
u.hook_add(UC_HOOK_MEM_WRITE, memory)
u.hook_add(UC_HOOK_CODE, code)
# Poison initialized/zeroed RAM. Retained crash bytes must survive the reset.
sdata, edata = symbol('_sdata'), symbol('_edata')
sbss, ebss = symbol('_sbss'), symbol('_ebss')
u.mem_write(sdata, b'\xCC' * (edata - sdata))
u.mem_write(sbss, b'\xCC' * (ebss - sbss))
retained = symbol('mk61_crash_record')
retained_bytes = bytes((i * 73 + 19) & 255 for i in range(192))
u.mem_write(retained, retained_bytes)
put(symbol('mk61_early_dfu_request'), 0)
put(symbol('mk61_early_dfu_request') + 4, 0)
put(RCC, 1)
put(RCC + 0x74, 1 << 27)  # POR, no retained DFU retry
u.reg_write(UC_ARM_REG_SP, sp)
u.reg_write(UC_ARM_REG_XPSR, 0x01000000)
u.emu_start(symbol('Reset_Handler') | 1, stop, timeout=10000000, count=1000000)
assert u.reg_read(UC_ARM_REG_PC) == main, hex(u.reg_read(UC_ARM_REG_PC))
assert get(core_clock) == frequency
assert bytes(u.mem_read(retained, 192)) == retained_bytes
assert get(uw) == 0
assert get(0xE000ED08) == 0x08000000
assert get(0xE000ED88) & 0x00F00000 == 0x00F00000
assert get(SYSTICK + 4) == frequency // 1000 - 1
assert get(SYSTICK) & 7 == 7
assert get(DWT) & 1
assert not (get(ICSR) & PENDING)
startup = False


def call(name, *values):
    u.reg_write(UC_ARM_REG_XPSR, 0x01000000)
    u.reg_write(UC_ARM_REG_SP, sp)
    u.reg_write(UC_ARM_REG_LR, stop | 1)
    for reg, value in zip([UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2,
                          UC_ARM_REG_R3], list(values) + [0] * 4):
        u.reg_write(reg, value)
    u.emu_start(symbol(name) | 1, stop, timeout=5000000, count=1000000)
    assert u.reg_read(UC_ARM_REG_PC) == stop, (name, hex(u.reg_read(UC_ARM_REG_PC)))
    assert u.reg_read(UC_ARM_REG_SP) == sp
    return u.reg_read(UC_ARM_REG_R0)


# Clock and USB frequency, warm reconfiguration after STOP, caller interrupt mask.
for mask in (0, 1):
    u.reg_write(UC_ARM_REG_PRIMASK, mask)
    put(RCC, 1)
    put(RCC + 8, 0)
    call('SystemClock_Config')
    assert u.reg_read(UC_ARM_REG_PRIMASK) == mask
    pll = get(RCC + 4)
    m, n, p, q = pll & 63, (pll >> 6) & 511, 2 * (((pll >> 16) & 3) + 1), pll >> 24 & 15
    assert pll & (1 << 22) and 25000000 // m * n // p == frequency
    assert 25000000 // m * n // q == 48000000
    assert get(RCC + 8) & 0xFCFF == 0x100A
    assert get(FLASH) & 15 == (3 if args.mcu == 'f411' else 2)
    put(SYSTICK + 8, frequency // 2000)
    call('SystemClock_Config')
    assert get(core_clock) == frequency
    assert get(SYSTICK + 8) == frequency // 2000, \
        'USB resume on an already running PLL must preserve the time counter'

# Counter reload, pending interrupt, rollover during sampling, uint32 wrap.
reload = frequency // 1000 - 1
for ms, before, after, counters, expected in [
    (0, 0, 0, [0], 0),
    (5, 0, 0, [reload], 5000),
    (5, 0, 0, [reload // 2], 5500),
    (5, PENDING, PENDING, [0], 6000),
    (5, PENDING, PENDING, [reload], 6000),
    (5, 0, PENDING, [1, reload], 6000),
    (4294967, 0, 0, [reload // 2], (4294967000 + 500) & 0xFFFFFFFF),
]:
    for mask in (0, 1):
        put(uw, ms)
        reads['icsr'] = [before, after]
        reads['val'] = list(counters)
        u.reg_write(UC_ARM_REG_PRIMASK, mask)
        assert call('micros') == expected
        assert u.reg_read(UC_ARM_REG_PRIMASK) == mask
        assert not reads['icsr'] and not reads['val']
put(uw, 0xFFFFFFFF)
call('SysTick_Handler')
assert get(uw) == 0
# DWT delay must work through its counter wrap, without relying on SysTick IRQs.
advancing_cycles = True
for mask in (0, 1):
    u.reg_write(UC_ARM_REG_PRIMASK, mask)
    put(DWT + 4, 0xFFFFFF00)
    call('delayMicroseconds', 10)
    elapsed = (get(DWT + 4) - 0xFFFFFF00) & 0xFFFFFFFF
    assert 10 * frequency // 1000000 <= elapsed <= 13 * frequency // 1000000
    assert u.reg_read(UC_ARM_REG_PRIMASK) == mask
    advancing_tick = mask == 0
    call('delay', 2)
    assert u.reg_read(UC_ARM_REG_PRIMASK) == mask
    if mask == 0:
        advancing_tick = False
advancing_cycles = False
# STOP keeps the caller mask and backup settings, enters low-power regulator WFI.
if not args.no_stop:
    for mask in (0, 1):
        u.reg_write(UC_ARM_REG_PRIMASK, mask)
        put(PWR, 0x100 | (1 << 14) | 2)
        call('HAL_PWR_EnterSTOPMode', 1, 1)
        assert get(PWR) == (0x100 | (1 << 14) | 1)
        assert not (get(0xE000ED10) & 4)
        assert u.reg_read(UC_ARM_REG_PRIMASK) == mask
    assert wfi_count == 2
# Direction changes leave the formerly driven keyboard row charged briefly.
# Qualification must wait for the same settling interval as ordinary scans;
# an actual held key must still prevent STOP after that interval.
if not args.no_stop:
    gpio_b = 0x40020400
    decay_started = None
    held_rows = 0
    keyboard_test = True
    keyboard_pending_writes = {}

    def keyboard_memory(uc, access, address, size, value, _):
        global decay_started
        if not keyboard_test:
            return
        if access == 17 and address == gpio_b + 0x0C:
            if (value >> 16 & 3) == 2:  # PB8 becomes an input with pulldown.
                decay_started = get(DWT + 4)
        elif access == 16 and address == gpio_b + 0x10:
            unsettled = decay_started is not None and \
                ((get(DWT + 4) - decay_started) & 0xFFFFFFFF) < frequency // 5000
            put(address, held_rows | ((1 << 8) if unsettled else 0))
        elif access == 17 and address == 0x40013C14:  # EXTI PR is W1C.
            keyboard_pending_writes[address] = get(address) & ~value

    def keyboard_code(uc, address, size, _):
        for target, value in list(keyboard_pending_writes.items()):
            put(target, value)
        keyboard_pending_writes.clear()

    u.hook_add(UC_HOOK_MEM_READ, keyboard_memory)
    u.hook_add(UC_HOOK_MEM_WRITE, keyboard_memory)
    u.hook_add(UC_HOOK_CODE, keyboard_code)
    advancing_cycles = True
    u.reg_write(UC_ARM_REG_PRIMASK, 0)
    assert call('_ZN3kbd17prepare_stop_wakeEv') == 1
    assert call('_ZN3kbd17stop_wake_pendingEv') == 0, \
        'charged scan row must settle before arming STOP'
    call('_ZN3kbd16cancel_stop_wakeEv')
    held_rows = 1 << 8
    assert call('_ZN3kbd17prepare_stop_wakeEv') == 1
    assert call('_ZN3kbd17stop_wake_pendingEv') == 1, \
        'a key held through settling must still abort STOP'
    call('_ZN3kbd16cancel_stop_wakeEv')
    keyboard_test = False
    advancing_cycles = False

print('Owned runtime production ARM model: reset/data/BSS/noinit, preinit, clock/USB48, SysTick, micros boundaries, DWT wrap' + ('; STOP omitted by profile PASS' if args.no_stop else ' and STOP PASS'))
