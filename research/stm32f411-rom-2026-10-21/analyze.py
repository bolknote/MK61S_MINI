#!/usr/bin/env python3
"""Reproduce ROM unpacking and bounded ARM execution of useful candidates."""
import hashlib
import json
from pathlib import Path
import random
import struct
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / '.build/stm32f411-rom-20261021/deps'))
from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_MCLASS
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS, UC_PROT_READ, UC_PROT_EXEC
from unicorn.arm_const import *

BASE, SIZE, STOP, SP = 0x1FFF0000, 0x7800, 0x08000000, 0x2001F000
SHA256 = '1796e27fcebdbd19307669a496efd704e18095a253e857716ce45450f3f599f0'

class Machine:
    def __init__(self):
        raw = (HERE / 'capture/rom-a.bin').read_bytes()
        assert len(raw) == SIZE and hashlib.sha256(raw).hexdigest() == SHA256
        self.uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
        self.uc.ctl_set_cpu_model(UC_CPU_ARM_CORTEX_M4)
        self.uc.mem_map(BASE, 0x8000, UC_PROT_READ | UC_PROT_EXEC)
        self.uc.mem_write(BASE, raw)
        self.uc.mem_map(0x20000000, 0x20000)
        self.uc.mem_map(STOP, 0x10000)
        # No memory hooks: Unicorn 2.1.4 misexecutes the SUBS/IT/STMDB loop
        # with either read/write instrumentation enabled. Compare RAM after
        # return instead, and validate the actual ROM address on hardware.

    def call(self, entry, *args, abi=True):
        uc = self.uc
        saved = {r: (0xA75D184B + r * 0x1321) & 0xFFFFFFFF for r in range(UC_ARM_REG_R4, UC_ARM_REG_R11 + 1)}
        for r, value in saved.items(): uc.reg_write(r, value)
        for r, value in zip((UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3), args):
            uc.reg_write(r, value)
        uc.reg_write(UC_ARM_REG_SP, SP)
        uc.reg_write(UC_ARM_REG_LR, STOP | 1)
        uc.reg_write(UC_ARM_REG_XPSR, 0x01000000)
        uc.emu_start(entry | 1, STOP, count=1000000)
        assert uc.reg_read(UC_ARM_REG_PC) == STOP, ('not returned', hex(entry))
        assert uc.reg_read(UC_ARM_REG_SP) == SP, ('SP', hex(entry))
        if abi:
            for r, value in saved.items(): assert uc.reg_read(r) == value, ('callee saved', r)
        return uc.reg_read(UC_ARM_REG_R0)

def unpack():
    machine = Machine()
    machine.call(0x1FFF41D4)
    raw = bytes(machine.uc.mem_read(0x20000000, 0x844))
    (HERE / 'relocated-ram.bin').write_bytes(raw)
    disasm = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_MCLASS)
    disasm.skipdata = True
    lines = [f'{i.address:08x}: {i.bytes.hex():10s} {i.mnemonic:8s} {i.op_str}'
             for i in disasm.disasm(raw, 0x20000000)]
    (HERE / 'relocated-ram.S').write_text('\n'.join(lines) + '\n')
    return {'address': '20000000', 'bytes_including_padding': len(raw),
            'sha256': hashlib.sha256(raw).hexdigest(), 'method': 'execute ROM scatter initializer 0x1FFF41D4 in Unicorn without running bootloader peripheral setup'}

def test_fill():
    m = Machine()
    rng = random.Random(0x61411)
    cases = [(n, a, c) for n in (*range(65), 127, 128, 129, 255, 256, 257, 511, 512, 1023, 1024, 4096)
             for a in range(8) for c in (0, 1, 0xA5, 255)]
    cases += [(rng.randrange(8193), rng.randrange(32), rng.getrandbits(32)) for _ in range(2000)]
    for n, align, value in cases:
        start = 0x20004000 + align
        m.uc.mem_write(0x20000000, b'\x5A' * 0x20000)
        try:
            result = m.call(0x1FFF3BD4, start, n, value)
        except BaseException as error:
            raise AssertionError(('fill case', n, align, value, str(error))) from error
        assert result == start, ('return', n, align, hex(result), hex(start))
        assert bytes(m.uc.mem_read(start, n)) == bytes([value & 255]) * n
        assert bytes(m.uc.mem_read(start - 16, 16)) == b'\x5A' * 16
        assert bytes(m.uc.mem_read(start + n, 16)) == b'\x5A' * 16
        expected = bytearray(b'\x5A' * 0x20000)
        expected[start-0x20000000:start-0x20000000+n] = bytes([value & 255]) * n
        actual = bytearray(m.uc.mem_read(0x20000000,0x20000))
        # The only stack instructions are PUSH/POP {r4,r5} (8 bytes).
        expected[SP-0x20000000-8:SP-0x20000000] = actual[SP-0x20000000-8:SP-0x20000000]
        assert expected == actual, ('non-destination write', n, align)
    return {'address': '1FFF3BD4', 'thumb_pointer': '1FFF3BD5', 'signature': 'r0=destination, r1=size, r2=fill; returns destination',
            'cases': len(cases), 'memory_bounds_and_callee_saved': 'PASS',
            'emulator_note': 'Actual ROM address and unmodified bytes. Unicorn 2.1.4 memory hooks misexecute the SUBS/IT/STMDB loop, so hooks are disabled and the entire 128 KiB SRAM is compared after every call (excluding the eight stack bytes). Actual chip tests are separate.'}

def test_misc():
    m = Machine()
    for n in (0, 4, 8, 16, 256, 512, 1024):
        source = bytes((i * 71 + 3) & 255 for i in range(n))
        m.uc.mem_write(0x20004000, source)
        m.uc.mem_write(0x20008000, b'\xA5' * (n + 16))
        assert m.call(0x1FFF0A4C, 0x20008000, 0x20004000, n) == 0x20008000
        assert bytes(m.uc.mem_read(0x20008000, n)) == source
    counterexamples=[]
    for n in (1, 3, 5, 255, 257, 513):
        m.uc.mem_write(0x20004000, b'\x11' * 1024)
        m.uc.mem_write(0x20008000, b'\xA5' * 1024)
        m.call(0x1FFF0A4C, 0x20008000, 0x20004000, n)
        written=bytes(m.uc.mem_read(0x20008000,1024)).count(0x11)
        counterexamples.append({'requested':n,'written':written})
        assert written != n
    for value in (0, 1, 0x12345678, 0xFFFFFFFF, 0xABCDEF01):
        for digits in range(9):
            m.call(0x1FFF27C0,value,0x20004000,digits)
            expected=f'{value:08X}'[:digits].encode('utf-16le')
            assert bytes(m.uc.mem_read(0x20004000,2*digits)) == expected
    for value in range(65536):
        assert m.call(0x1FFF3A60,value) == ((value>>8)|(value<<8))&65535
    return {'copy_address':'1FFF0A4C','copy_counterexamples':counterexamples,
            'hex_utf16_address':'1FFF27C0','hex_cases':45,
            'bswap16_address':'1FFF3A60','bswap_cases':65536}

def main():
    report = {'rom_sha256': SHA256, 'unpack': unpack(), 'fill': test_fill(), 'misc':test_misc()}
    (HERE / 'validation.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2), flush=True)

if __name__ == '__main__': main()
