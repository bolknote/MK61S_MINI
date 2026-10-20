#!/usr/bin/env python3
"""Run the shipped terminal APPs with the exact resident service table.

Only peripheral state, console output and calculator memory are adapted. The
packed ARM APP, native numeric runtime, service addresses and AAPCS layouts are
the real production artifacts. Exercise three legal APP relocation addresses.
"""
import argparse
import binascii
import re
import struct
import tempfile
from pathlib import Path

from unicorn import UC_HOOK_MEM_INVALID
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3, UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_SP
from run_portable_app_arm_tests import ROOT, run
from run_portable_system_arm_tests import Elf, Machine


class TerminalMachine(Machine):
    def __init__(self, resident, address_index):
        super().__init__(resident, True, address_index)
        self.elf = Elf(resident)
        def invalid(uc, access, address, size, value, context):
            print('invalid memory', hex(address), size, 'PC', hex(uc.reg_read(UC_ARM_REG_PC)),
                  'LR', hex(uc.reg_read(UC_ARM_REG_LR)), 'base', hex(self.base),
                  'request', self.words(self.request, 8), flush=True)
            return False
        self.uc.hook_add(UC_HOOK_MEM_INVALID, invalid)
        header = (ROOT / 'code/terminal_command_driver.hpp').read_text()
        body = header.split('struct Services {', 1)[1].split('\n};', 1)[0]
        self.fields = [m.group(1) or 'ring' for m in re.finditer(
            r'\(\*(\w+)\)|const u8 \*ring;', body)]
        original = self.elf.symbol('terminal_command_driver12_GLOBAL__N_1L8servicesE')
        table = bytes(self.uc.mem_read(original, 8 + 4 * len(self.fields)))
        assert struct.unpack_from('<II', table) == (len(table), 3)
        self.request = self.input
        self.table = self.input + 64
        self.argument = self.input + 512
        self.history = self.input + 768
        self.signature = self.input + 1400
        self.put(self.history, 256, 8, self.input+800, self.input+801,
                 self.input+832, self.input+1090, self.input+1110)
        self.uc.mem_write(self.table, table)
        self.uc.mem_write(self.signature, b'12345678\n\0')
        self.native = {}
        for i, name in enumerate(self.fields):
            address = struct.unpack_from('<I', table, 8 + 4 * i)[0]
            if name not in ('ring', 'value_fits'):
                assert address & 1, (name, hex(address))
                assert address & ~1 not in self.native, (name, self.native)
                self.native[address & ~1] = name
        self.memory = bytearray(10000)
        self.steps, self.bank, self.instruction = 105, 0, 0
        self.expanded = False
        self.console = bytearray()
        self.raw_writes, self.fractions, self.patterns = [], [], []
        self.random_calls, self.reactions = 0, 0
        self.crash_clears = 0
        self.crash_record = None
        self.disk_full = False
        self.persisted = 0
        self.diagnostic_clears = 0
        self.rtc_sets, self.alarm_calls = [], []
        self.alarm = bytes(12)
        self.read_failure = False
        self.scratch_busy = False

    def hook(self, uc, address, size, ctx):
        pending = getattr(self, 'ref_write_return', None)
        if pending and address == pending[0]:
            _, kind, reg, value = pending
            if uc.reg_read(UC_ARM_REG_R0):
                self.refs[kind, reg] = value
            self.ref_write_return = None
        if hasattr(self, 'syscall') and address == (self.syscall & ~1) and uc.reg_read(UC_ARM_REG_R0) == 22:
            # Execute the real resident validation and register/stack writer.
            payload = self.words(uc.reg_read(UC_ARM_REG_SP), 1)[0]
            self.ref_write_return = (uc.reg_read(UC_ARM_REG_LR) & ~1,
                                     uc.reg_read(UC_ARM_REG_R1), uc.reg_read(UC_ARM_REG_R2),
                                     struct.unpack('<d', uc.mem_read(payload, 8))[0])
            return
        if address not in getattr(self, 'native', {}):
            return super().hook(uc, address, size, ctx)
        name = self.native[address]
        # Callback addresses come from the exact resident table.
        a, b, c, d = [uc.reg_read(r) for r in
                      (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3)]
        result = 1
        if name == 'output':
            self.console += bytes(uc.mem_read(b, c))
        elif name == 'number':
            value = a if not b & 256 or a < 0x80000000 else a - 0x100000000
            text = format(value, 'X') if b & 255 == 16 else str(value)
            self.console += text.encode()
        elif name == 'core_info':
            self.put(a, self.steps, 10000, self.bank, self.instruction,
                     self.expanded, 42, 2)
        elif name == 'core_page':
            uc.mem_write(a, bytes(self.memory[self.bank*112:self.bank*112+self.steps]).ljust(113, b'\0'))
        elif name == 'core_read':
            assert a < len(self.memory)
            uc.mem_write(b, bytes((self.memory[a],)))
        elif name == 'core_write':
            assert a < len(self.memory) and b < 256
            self.memory[a] = b
        elif name == 'core_apply':
            assert b == 112
            self.memory[:112] = uc.mem_read(a, b)
            if d:
                self.expanded, self.extended, self.steps = True, True, 112
        elif name == 'core_insert':
            assert a < self.steps and b < 256
            self.memory[a+1:self.steps] = self.memory[a:self.steps-1]
            self.memory[a] = b
        elif name in ('register_text', 'stack_text'):
            uc.mem_write(b, b' 1.2345678  00\0')
            result = b
        elif name == 'chip_text':
            uc.mem_write(a, b'0123456789ABC\0')
        elif name == 'ring_chip':
            self.put(a, self.signature, b*21)
        elif name == 'error_reaction':
            self.reactions += 1
        elif name == 'crash_copy':
            result = self.crash_record is not None
            if result:
                uc.mem_write(a, self.crash_record)
        elif name == 'crash_metadata':
            self.put(a, 0x12345678)
            uc.mem_write(a+4, b'0123456789ABCDEF\0')
            self.put(a+24, self.signature)
        elif name == 'crash_persist':
            self.persisted += 1
        elif name == 'path_target':
            uc.mem_write(d, struct.pack('<HB', 0xFFFF, c) + b'CRASH\0'.ljust(32, b'\0'))
            result = 0
        elif name == 'path_status':
            result = self.signature
        elif name == 'mpu_snapshot':
            uc.mem_write(a, bytes((1, 1, 1, 1, 1, 8, 4, 0)) + bytes(40))
        elif name == 'mpu_backend':
            result = self.signature
        elif name == 'watchdog_snapshot':
            uc.mem_write(a, bytes(68))
        elif name == 'watchdog_running':
            result = 0
        elif name == 'storage_info':
            self.put(a, 1, 0, 524288, 12, 1024, 10, 2, 512, 128, 1)
        elif name == 'nor_snapshot':
            result = 0
        elif name == 'power_snapshot':
            uc.mem_write(a, bytes(48))
        elif name == 'power_threshold':
            uc.mem_write(a, struct.pack('<6H', 2700, 2800, 2900, 2800, 2900, 3000))
        elif name == 'firmware_verify':
            uc.mem_write(a, bytes(28))
        elif name == 'firmware_failure':
            result = 0
        elif name == 'firmware_build':
            result = 0x12345678
        elif name == 'vfat_diagnostic':
            result = self.signature + 32
            uc.mem_write(result, bytes(28))
        elif name == 'msc_diagnostic':
            uc.mem_write(a, bytes(8))
        elif name in ('vfat_clear', 'msc_clear'):
            self.diagnostic_clears += 1
        elif name == 'crash_clear':
            self.crash_clears += 1
        elif name in ('crash_flags', 'crash_layout'):
            result = 0
        elif name == 'write_raw':
            self.raw_writes.append((a, bytes(uc.mem_read(b, 12))))
        elif name == 'write_fraction':
            self.fractions.append((a, b))
        elif name == 'random7':
            self.random_calls += 1
            result = 1234
        elif name == 'help_signature':
            result = self.signature
        elif name == 'help_fallback':
            self.console += b'fallback\r\n'
        elif name in ('led_pattern', 'sound_pattern'):
            assert 0 < b <= 16
            self.patterns.append((name, bytes(uc.mem_read(a, b * (4 if name == 'led_pattern' else 8)))))
        elif name == 'rtc_snapshot':
            uc.mem_write(a, struct.pack('<H5BxIIB3x', 2026, 10, 20, 12, 34, 56, 500, 999, 1))
        elif name == 'rtc_set':
            self.rtc_sets.append(bytes(uc.mem_read(a, 8)))
        elif name == 'rtc_alarm_read':
            uc.mem_write(b, self.alarm)
        elif name == 'rtc_alarm_set':
            self.alarm_calls.append(('set', a, bytes(uc.mem_read(b, 12))))
        elif name in ('rtc_alarm_after', 'rtc_alarm_cancel'):
            self.alarm_calls.append((name, a, b))
            if name == 'rtc_alarm_after':
                result = b != 0
        elif name == 'rtc_backup':
            result = 0
        else:
            raise AssertionError(('unmodeled terminal peripheral', name, a, b, c, d))
        uc.reg_write(UC_ARM_REG_R0, result)
        uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))

    def system(self, op, a, b, c, p):
        if op == 9 and self.disk_full:
            return 0
        if op == 8:  # Resolve full paths through the public resident API.
            path = self.string(c)
            for inode, (kind, name, _data) in self.files.items():
                if kind == b and name == path:
                    self.file(p, inode)
                    return 0
            return 4
        if op == 13 and a == 1 and self.scratch_busy:
            return 0
        return super().system(op, a, b, c, p)

    def load_terminal(self, package):
        self.kind, variants, self.image_size, self.entry, self.crc = package
        self.base, self.image = variants[self.address_index]
        self.uc.mem_write(self.pool_begin, b'\xcd' * (self.pool_end-self.pool_begin))
        self.uc.mem_write(self.base, self.image)
        self.uc.ctl_remove_cache(self.pool_begin, self.pool_end)
        assert self.call(0, self.api, self.crc, 4) == 0

    def execute(self, command, argument='', expected=1, address=0):
        self.console.clear()
        self.uc.mem_write(self.argument, argument.encode() + b'\0')
        self.put(self.request, 32, 3, self.table, self.argument,
                 command, 0xFFFF, address, self.history)
        result = self.call(0x54434D44, self.request, 32)
        assert result == expected, (command, argument, result, self.console)
        assert not self.leases, ('terminal leaked a scratch lease', self.leases)
        return bytes(self.console)


def qualify(m, terminal, clock, commands):
    c = lambda name: commands['CMD_' + name]
    m.load_terminal(terminal)
    assert b'overflow' in m.execute(c('HIN'), '9999 1122', 0)
    m.execute(c('HIN'), '0111 11223344')
    assert m.memory[111:115] == bytes.fromhex('11223344')
    text = m.execute(c('HOUT'), '111 4')
    assert b'11223344' in text, text
    m.execute(c('ASM'), '0104 0 1')
    assert m.memory[104:106] == b'\x00\x01'
    m.expanded, m.extended, m.steps = False, False, 105
    m.execute(c('INS'), '104 FF')
    assert m.memory[104] == 255
    m.execute(c('INS'), '105 FF', 0)
    m.execute(c('REG_SET'), 'R0= -123.25')
    assert -123.25 in m.refs.values(), m.refs
    m.execute(c('REG_SET'), 'R0= random')
    assert m.fractions == [(0, 1234)]
    m.execute(c('REG_SET'), 'RF= random', 0)
    assert m.random_calls == 1
    m.expanded, m.extended, m.steps = True, True, 112
    m.execute(c('REG_SET'), 'RF= raw 0123456789AB')
    assert m.raw_writes == [(15, bytes(range(12)))]
    m.execute(c('REG_SET'), 'R1= 1e100', 0)
    m.execute(c('POKE'), 'X -12.5')
    assert -12.5 in m.refs.values()
    m.execute(c('POKE'), 'X1 42', 0)
    m.execute(c('POKE'), 'X 1e100', 0)
    m.execute(c('LED'), '1,20,0')
    assert m.patterns[-1][0] == 'led_pattern'
    assert struct.unpack('<BxHBxH', m.patterns[-1][1]) == (1, 20, 0, 0)
    m.execute(c('LED'), '2', 0)
    m.execute(c('LED'), '1,65536,0', 0)
    m.execute(c('BEEP'), '440,100,0,20')
    assert m.patterns[-1][0] == 'sound_pattern'
    assert struct.unpack('<HHHBxHHHBx', m.patterns[-1][1]) == (440, 100, 0, 100, 0, 20, 0, 100)
    m.execute(c('BEEP'), '440', 0)
    assert b'CRASH none reset=' in m.execute(c('CRASH'))
    m.execute(c('CRASH'), 'clear')
    assert m.crash_clears == 1
    m.execute(c('CRASH'), 'save /CRASH.TXT', 0)
    record = [0] * 48
    record[:4] = [0x4331364D, 1, 192, 7]
    wire = struct.pack('<48I', *record)
    m.crash_record = wire[:-4] + struct.pack('<I', binascii.crc32(wire[4:-4]))
    assert b'CRASH' in m.execute(c('CRASH'), 'show')
    m.scratch_busy = True
    assert b'busy' in m.execute(c('CRASH'), 'show', 0)
    assert b'busy' in m.execute(c('CRASH'), 'save /CRASH.TXT', 0)
    m.scratch_busy = False
    m.disk_full = True
    assert b'failed' in m.execute(c('CRASH'), 'save /CRASH.TXT', 0)
    m.disk_full = False
    assert b'saved' in m.execute(c('CRASH'), 'save /CRASH.TXT')
    assert m.persisted == 1
    assert any(b'CRASH' in data for _, _, data in m.files.values())
    for name, token in (('MPU', b'MPU'), ('WATCHDOG', b'WDOG'),
                        ('FS_STAT', b'FIRMWARE'), ('VFAT_LOG', b'MSC startup'),
                        ('RING', b'ring M dump')):
        assert token in m.execute(c(name)), name
    m.execute(c('VFAT_LOG'), 'clear')
    assert m.diagnostic_clears == 2
    for name in ('ISA', 'LIST', 'DUMP', 'PUB', 'LASM', 'REG_DUMP', 'STACK', '1302'):
        assert m.execute(c(name)), name
    assert b'empty' in m.execute(c('HISTORY'))
    # A wrapped line in the terminal's actual history wire layout.
    head, count, text, start, length = [m.input + n for n in (800, 801, 832, 1090, 1110)]
    m.uc.mem_write(head, b'\x07\x01')
    m.uc.mem_write(text, b'BC' + bytes(253) + b'A')
    m.uc.mem_write(start, bytes(14) + struct.pack('<H', 255))
    m.uc.mem_write(length, bytes(7) + b'\x03')
    m.put(m.history, 256, 8, head, count, text, start, length)
    assert b'1: ABC' in m.execute(c('HISTORY'))
    assert b'fallback' in m.execute(c('HELP'))
    m.files = {41: (4, '/System/HELP0.TXT', b'12345678\nfirst\r\n'),
               42: (4, '/System/HELP1.TXT', b'12345678\nsecond\r\n')}
    text = m.execute(c('HELP'))
    assert b'first\r\nsecond\r\n' in text, text
    m.files[42] = (4, '/System/HELP1.TXT', b'bad')
    assert b'fallback' in m.execute(c('HELP'))
    m.execute(256 + c('HELP'), expected=0)
    for offset, bad in ((0, 28), (4, 99), (8, 0), (12, 0)):
        m.execute(c('HELP'))
        saved = bytes(m.uc.mem_read(m.request + offset, 4))
        m.put(m.request + offset, bad)
        assert m.call(0x54434D44, m.request, 32) == 0
        m.uc.mem_write(m.request + offset, saved)
    for offset in (0, 4):
        saved = bytes(m.uc.mem_read(m.table + offset, 4))
        m.put(m.table + offset, 99)
        assert m.call(0x54434D44, m.request, 32) == 0
        m.uc.mem_write(m.table + offset, saved)
    m.load_terminal(clock)
    assert b'2026-10-20 12:34:56' in m.execute(c('DATE'))
    assert b'.499' in m.execute(c('DATE'), 'ms')
    m.execute(c('DATE'), '2028-02-29 01:02:03')
    assert m.rtc_sets[-1][:7] == struct.pack('<H5B', 2028, 2, 29, 1, 2, 3)
    m.execute(c('DATE'), '2027-02-29 01:02:03', 0)
    assert b'RTC ALARM A off' in m.execute(c('ALARM'))
    m.execute(c('ALARM'), 'A in 30')
    assert m.alarm_calls[-1][:3] == ('rtc_alarm_after', 0, 30)
    m.execute(c('ALARM'), 'B off')
    assert m.alarm_calls[-1][:2] == ('rtc_alarm_cancel', 1)
    m.execute(c('ALARM'), 'A in 0', 0)
    m.execute(c('HELP'), expected=0)


def check_graphics_disk_lifetime(m):
    """Execute the F401 lifetime and the real USB preparation refusal."""
    def native(symbol, *arguments):
        uc = m.uc
        uc.reg_write(UC_ARM_REG_SP, m.stack_top)
        uc.reg_write(UC_ARM_REG_LR, m.stop | 1)
        for register, value in zip((UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3), arguments):
            uc.reg_write(register, value)
        if len(arguments) > 4:
            m.put(m.stack_top, *arguments[4:])
        uc.emu_start(m.elf.symbol(symbol) | 1, m.stop, count=1000000)
        assert uc.reg_read(UC_ARM_REG_PC) == m.stop
        return uc.reg_read(UC_ARM_REG_R0)
    guard = '_ZN14basic_graphics17prepare_disk_modeEv'
    dispatch = '_ZN14basic_graphics8dispatchERNS_7RequestE'
    request = m.input + 256
    def graphics(operation, count=0):
        wire = bytearray(72)
        struct.pack_into('<6d', wire, 0, 1, 1, 0, 0, 0, 0)
        wire[66:68] = bytes((count, operation))
        m.uc.mem_write(request, bytes(wire))
        assert native(dispatch, request) == 0
    assert native(guard) == 1
    graphics(7, 2)  # PSET opens a real resident session and canvas.
    assert native(guard) == 0
    assert native('_ZN16usb_mass_storage7prepareEv') == 0
    graphics(14)  # INPUT suspension must preserve the session.
    assert native(guard) == 0
    assert native('_ZN16usb_mass_storage7prepareEv') == 0
    graphics(15)
    graphics(3)  # END releases it; no APP bytes execute after this point.
    assert native(guard) == 1
    owners = re.findall(r'MK61_SHARED_MEMORY_OWNER\(\s*([A-Z_]+)',
                        (ROOT / 'code/shared_memory_owner_catalog.inc').read_text())
    # Fixture bookkeeping is outside the allocator's measured physical pool.
    cells = 0x2001C000
    m.uc.mem_write(cells, bytes(128))
    acquire = '_ZN13shared_memory5Lease7acquire'
    extra = ()
    if not any(acquire in name for name in m.elf.symbols):
        acquire = '_ZN13shared_memory5Lease12acquire_impl'
        extra = (0,)
    assert native(acquire, cells, 3, owners.index('VFAT_STAGE'), 2560, *extra) == 1
    assert native(acquire, cells+64, 4, owners.index('LOADABLE_MODULE'), 20480, *extra) == 1
    native('_ZN13shared_memory5Lease5reset', cells+64)
    native('_ZN13shared_memory5Lease5reset', cells)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--resident-elf', type=Path, required=True)
    parser.add_argument('--terminal', type=Path, required=True)
    parser.add_argument('--clock', type=Path, required=True)
    args = parser.parse_args()
    ids = (ROOT / 'code/terminal_command_ids.hpp').read_text().split('enum : u8 {', 1)[1].split('};', 1)[0]
    commands = {name: i for i, name in enumerate(re.findall(r'\bCMD_[A-Z0-9_]+\b', ids))}
    elf = Elf(args.resident_elf)
    assert elf.symbols.get("mk61_terminal_commands_as_app") == 1
    assert elf.symbols.get("mk61_terminal_command_abi") == 3
    low = (elf.fixture_buffer_begin() + 2048 + 31) & ~31
    end = elf.symbol('__mk61_dynamic_end')
    with tempfile.TemporaryDirectory(prefix='mk61-terminal-arm-') as directory:
        work = Path(directory)
        reader = work / 'reader'
        run(['c++', '-std=c++17', '-O2', '-I'+str(ROOT/'code'), ROOT/'tests/portable_app_format_self_test.cpp',
             ROOT/'code/loadable_module_format.cpp', ROOT/'code/zx0.cpp', '-o', reader])
        packages = []
        for path in (args.terminal, args.clock):
            packed = path.read_bytes()
            image, memory, entry = struct.unpack_from('<III', packed, 28)
            crc = struct.unpack_from('<I', packed, 52)[0]
            high = end - ((memory + 31) & ~31)
            assert low <= high, 'terminal APP does not fit real F401 RAM'
            variants = []
            for address in (low, ((low+high)//2)&~31, high):
                target = work / 'image.bin'
                run([reader, path, target, hex(address)])
                variants.append((address, target.read_bytes()))
            packages.append((path.stem, variants, image, entry, crc))
        for index in range(3):
            m = TerminalMachine(args.resident_elf, index)
            qualify(m, *packages, commands)
            check_graphics_disk_lifetime(m)
            print(f'terminal/CLOCK ARM relocation {index + 1}/3: OK', flush=True)


if __name__ == '__main__':
    main()
