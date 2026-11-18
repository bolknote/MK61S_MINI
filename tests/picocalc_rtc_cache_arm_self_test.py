#!/usr/bin/env python3
"""Run the linked BIOS RTC cache and its real STM32 HAL calendar on Cortex-M3.

Models RTC registers/W0C flags only. Instruction counts are not hardware timing.
"""
from pathlib import Path
import argparse
import hashlib
import json
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'sdk/coproc'), str(ROOT/'tests')]
from elf32 import ELF
from unicorn_runtime import Uc
from unicorn import UC_ARCH_ARM, UC_MODE_MCLASS, UC_MODE_THUMB, UC_HOOK_CODE, UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE
from unicorn.arm_const import UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC


class Machine:
    RTC = 0x40002800
    STOP = 0x0800fff0

    def __init__(self, path):
        self.elf = ELF(path)
        self.u = Uc(UC_ARCH_ARM, UC_MODE_MCLASS | UC_MODE_THUMB)
        for base, size in [(0x08000000, 0x10000), (0x20000000, 0x10000),
                           (0x40000000, 0x30000), (0xe000e000, 0x2000)]:
            self.u.mem_map(base, size)
        for segment in self.elf.segments:
            if segment['data']:
                self.u.mem_write(segment['address'], segment['data'])
        self.fix_crl = None
        self.instructions = self.counter_reads = 0
        self.tick_on_read = False
        self.u.hook_add(UC_HOOK_CODE, self.code)
        self.u.hook_add(UC_HOOK_MEM_READ, self.read)
        self.u.hook_add(UC_HOOK_MEM_WRITE, self.write)
        self.put(self.RTC, 2)       # Existing ALRIE, no SECIE.
        self.put(self.RTC+4, 0x28)  # RSF and read-only RTOFF.
        self.put(self.address('hrtc'), self.RTC)
        self.set_calendar(24, 2, 28)
        self.set_counter(86399)

    def address(self, name):
        return self.elf.symbols[name]['value']

    def get(self, at):
        return struct.unpack('<I', self.u.mem_read(at, 4))[0]

    def put(self, at, value):
        self.u.mem_write(at, struct.pack('<I', value))

    def set_calendar(self, year, month, day):
        self.u.mem_write(self.address('hrtc')+12, bytes([3, month, day, year]))

    def set_counter(self, value):
        self.put(self.RTC+24, value >> 16)
        self.put(self.RTC+28, value & 65535)

    def tick(self, seconds):
        value = (self.get(self.RTC+24) << 16) | self.get(self.RTC+28)
        self.set_counter(value+seconds)
        self.put(self.RTC+4, self.get(self.RTC+4) | 1)

    def code(self, u, pc, size, context):
        if self.fix_crl is not None:
            self.put(self.RTC+4, self.fix_crl)
            self.fix_crl = None
        self.instructions += 1

    def read(self, u, access, at, size, value, context):
        if at in (self.RTC+24, self.RTC+28):
            self.counter_reads += 1
            if self.tick_on_read:
                self.tick_on_read = False
                self.tick(1)

    def write(self, u, access, at, size, value, context):
        if at == self.RTC+4:
            old = self.get(at)
            self.fix_crl = (old & value & 15) | (old & 32) | (value & 16)

    def call(self, name):
        self.instructions = self.counter_reads = 0
        self.u.reg_write(UC_ARM_REG_SP, 0x20004f00)
        self.u.reg_write(UC_ARM_REG_LR, self.STOP | 1)
        self.u.emu_start(self.address(name) | 1, self.STOP, timeout=1000000, count=100000)
        assert self.u.reg_read(UC_ARM_REG_PC) == self.STOP, name
        assert self.u.reg_read(UC_ARM_REG_SP) == 0x20004f00, name
        assert self.fix_crl is None
        return {'instructions': self.instructions, 'counter_reads': self.counter_reads}

    def snapshot(self):
        date = bytes(self.u.mem_read(self.address('rtc_date'), 4))
        time = bytes(self.u.mem_read(self.address('rtc_time'), 3))
        return date, time

    def expect(self, year, month, day, hour, minute, second):
        date = bytes(self.u.mem_read(self.address('rtc_date'), 4))
        time = bytes(self.u.mem_read(self.address('rtc_time'), 3))
        assert (date[3],date[1],date[2]) == (year,month,day), date
        assert tuple(time) == (hour,minute,second), time


def run(path):
    m = Machine(path)
    m.call('bios_rtc_cache_changed')
    initial = m.call('bios_rtc_cache_poll')
    m.expect(24,2,28,23,59,59)
    idle = m.call('bios_rtc_cache_poll')
    assert idle['counter_reads'] == 0 and idle['instructions'] < 25
    m.tick(1)
    m.put(m.RTC+4, m.get(m.RTC+4) | 2)  # Alarm at leap-day midnight.
    midnight = m.call('bios_rtc_cache_poll')
    m.expect(24,2,29,0,0,0)
    assert m.get(m.RTC+4) & 2
    assert m.get(m.RTC) == 2
    m.tick(86400)
    m.call('bios_rtc_cache_poll')
    m.expect(24,3,1,0,0,0)
    m.set_calendar(24,12,31)
    m.set_counter(86399)
    m.call('bios_rtc_cache_changed')
    m.call('bios_rtc_cache_poll')
    m.expect(24,12,31,23,59,59)
    old = m.snapshot()
    m.call('bios_rtc_cache_changed')
    m.tick_on_read = True
    m.call('bios_rtc_cache_poll')
    assert m.snapshot() == old
    m.call('bios_rtc_cache_poll')
    m.expect(25,1,1,0,0,0)
    m.tick(3*86400 + 45296)
    m.call('bios_rtc_cache_poll')
    m.expect(25,1,4,12,34,56)
    m.put(m.RTC+4, m.get(m.RTC+4) | 1)  # SECF one RTCCLK before CNT.
    m.call('bios_rtc_cache_poll')
    m.expect(25,1,4,12,34,56)
    assert not (m.get(m.RTC+4) & 1)
    m.set_counter(45297)  # CNT advances without another SECF event.
    m.call('bios_rtc_cache_poll')
    m.expect(25,1,4,12,34,57)
    assert m.call('bios_rtc_cache_poll')['counter_reads'] == 0
    result = {'status':'PASS', 'physical_io':False, 'hardware_timing':False,
              'elf_sha256':hashlib.sha256(Path(path).read_bytes()).hexdigest(),
              'initial':initial, 'unchanged_second':idle, 'leap_midnight':midnight,
              'cases':['real HAL calendar rollover', 'leap day', 'year change', 'second during refresh',
                       'latched alarm preserved', 'sleep-sized counter jump', 'no SECIE enabled', 'stack preserved',
                       'early SECF then counter update without another flag']}
    return result


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--elf', type=Path, required=True)
    ap.add_argument('--output', type=Path)
    args = ap.parse_args()
    result = run(args.elf)
    text = json.dumps(result, indent=2)+'\n'
    if args.output: args.output.write_text(text)
    print(text, end='')
