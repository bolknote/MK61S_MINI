#!/usr/bin/env python3
"""Execute the actual owned startup with empty/nonempty sections and constructors.

The production runtime model separately executes real SystemInit/clock/STOP.
These freestanding fixtures exercise bounds, call order, retained memory,
stack alignment and strong IRQ overrides without peripheral approximations.
"""
import argparse
import struct
import subprocess
import tempfile
from pathlib import Path

from unicorn import Uc, UC_ARCH_ARM, UC_MODE_MCLASS, UC_MODE_THUMB, UC_HOOK_CODE, UC_HOOK_MEM_WRITE
from unicorn.arm_const import UC_ARM_REG_PC, UC_ARM_REG_SP, UC_ARM_REG_XPSR, UC_CPU_ARM_CORTEX_M4
from check_stm32_vectors import ElfImage, check_vectors

ROOT = Path(__file__).resolve().parents[1]
SOURCE = r'''
typedef void (*callback)(void);
volatile unsigned trace __attribute__((section(".noinit")));
volatile unsigned retained[4] __attribute__((section(".noinit")));
@DATA@
static void check_memory(void) {
@CHECK@
  for(unsigned i = 0; i < 4; ++i)
    if(retained[i] != 0xA7A7A7A7U) trace = 0xBAD;
}
void SystemInit(void) { trace = 1; }
static void before(void) { check_memory(); trace = trace*10 + 2; }
static void construct(void) { check_memory(); trace = trace*10 + 3; }
@PRE@
@INIT@
void RTC_Alarm_IRQHandler(void) { trace = 0x61A1A2A3U; }
int main(void) { check_memory(); trace = trace*10 + 4; return 0; }
'''
LINKER = r'''
ENTRY(Reset_Handler)
MEMORY {
  FLASH (rx) : ORIGIN = 0x08000000, LENGTH = 512K
  RAM (rwx) : ORIGIN = 0x20000000, LENGTH = @RAM@
}
_estack = ORIGIN(RAM) + LENGTH(RAM);
SECTIONS {
  .isr_vector : { KEEP(*(.isr_vector)) } > FLASH
  .text : { *(.text*) *(.rodata*) } > FLASH
  .preinit_array (READONLY) : {
    __preinit_array_start = .; KEEP(*(.preinit_array*)) __preinit_array_end = .;
  } > FLASH
  .init_array (READONLY) : {
    __init_array_start = .; KEEP(*(.init_array*)) __init_array_end = .;
  } > FLASH
  .data : { _sdata = .; *(.data*) . = ALIGN(4); _edata = .; } > RAM AT> FLASH
  _sidata = LOADADDR(.data);
  .bss : { _sbss = .; *(.bss*) . = ALIGN(4); _ebss = .; } > RAM
  .noinit (NOLOAD) : { *(.noinit*) } > RAM
  /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment) }
}
'''


def run_fixture(compiler, headers, work, mcu, words, constructors):
    folder = work / f'{mcu}-{words}-{constructors}'
    folder.mkdir()
    source = SOURCE.replace('@DATA@', (
        f'volatile unsigned initialized[{words}] = {{' + ','.join(hex(0x615A0000 + i) for i in range(words)) + '};\n'
        f'volatile unsigned zeroed[{words}];') if words else '')
    source = source.replace('@CHECK@', (
        f'  for(unsigned i = 0; i < {words}; ++i)\n'
        '    if(initialized[i] != 0x615A0000U + i || zeroed[i] != 0) trace = 0xBAD;') if words else '')
    source = source.replace('@PRE@', 'static callback const pre[] __attribute__((used,section(".preinit_array"))) = {before};' if constructors else '')
    source = source.replace('@INIT@', 'static callback const init[] __attribute__((used,section(".init_array"))) = {construct};' if constructors == 2 else '')
    c = folder / 'probe.c'
    c.write_text(source)
    script = folder / 'probe.ld'
    script.write_text(LINKER.replace('@RAM@', '64K' if mcu == 'f401' else '128K'))
    elf = folder / 'probe.elf'
    chip = 'STM32F401xC' if mcu == 'f401' else 'STM32F411xE'
    command = [str(compiler), '-mcpu=cortex-m4', '-mthumb', '-mfpu=fpv4-sp-d16', '-mfloat-abi=hard',
               '-Os', '-ffreestanding', '-fno-builtin', '-fno-lto', '-ffunction-sections', '-fdata-sections',
               '-nostdlib', '-DMK61_NATIVE_RUNTIME=1', '-D' + chip,
               str(ROOT / 'code/stm32f4_startup.S'), str(c), '-T' + str(script),
               '-Wl,--gc-sections', '-o', str(elf)]
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    image = ElfImage(elf)
    count = check_vectors(image, headers / ('stm32f401xc.h' if mcu == 'f401' else 'stm32f411xe.h'))
    assert image.symbols['RTC_Alarm_IRQHandler'] != image.symbols['Default_Handler']
    machine = Uc(UC_ARCH_ARM, UC_MODE_MCLASS | UC_MODE_THUMB)
    machine.ctl_set_cpu_model(UC_CPU_ARM_CORTEX_M4)
    machine.mem_map(0x08000000, 0x100000)
    machine.mem_map(0x20000000, 0x20000)
    image.load(machine)
    for begin, end in (('_sdata', '_edata'), ('_sbss', '_ebss')):
        start, finish = image.symbols[begin], image.symbols[end]
        assert finish - start == words * 4
        if finish != start:
            machine.mem_write(start, b'\xCC' * (finish - start))
    retained = image.symbols['retained']
    machine.mem_write(retained, b'\xA7' * 16)
    machine.reg_write(UC_ARM_REG_SP, image.symbols['_estack'] - 32)
    machine.reg_write(UC_ARM_REG_XPSR, 0x01000000)
    callbacks = {image.symbols[name] & ~1 for name in ('SystemInit', 'before', 'construct', 'main') if name in image.symbols}
    def check_stack(machine, address, size, user):
        del size, user
        if address in callbacks:
            assert machine.reg_read(UC_ARM_REG_SP) % 8 == 0, 'unaligned callback SP'
    reset_begin = image.symbols['Reset_Handler'] & ~1
    reset_end = reset_begin + image.sizes['Reset_Handler']
    writes = []
    def check_write(machine, access, address, size, value, user):
        del access, user
        pc = machine.reg_read(UC_ARM_REG_PC)
        if not reset_begin <= pc < reset_end:
            return
        if image.symbols['_estack'] - 32 <= address and address + size <= image.symbols['_estack']:
            return
        assert size == 4 and image.symbols['_sdata'] <= address < image.symbols['_ebss'], ('startup write outside data/BSS', hex(address))
        writes.append((address, value))
    machine.hook_add(UC_HOOK_CODE, check_stack)
    machine.hook_add(UC_HOOK_MEM_WRITE, check_write)
    stop = image.symbols['Default_Handler'] & ~1
    machine.emu_start(image.symbols['Reset_Handler'] | 1, stop, count=100000)
    assert len(writes) == 2 * words, ('startup write count', writes, words)
    assert machine.reg_read(UC_ARM_REG_PC) == stop, 'startup did not return from main into the default loop'
    assert machine.reg_read(UC_ARM_REG_SP) == image.symbols['_estack'], 'startup stack imbalance'
    actual = struct.unpack('<I', machine.mem_read(image.symbols['trace'], 4))[0]
    assert actual == (14, 124, 1234)[constructors], (mcu, words, constructors, hex(actual))
    assert bytes(machine.mem_read(retained, 16)) == b'\xA7' * 16
    if words:
        expected = struct.pack('<' + 'I' * words, *(0x615A0000 + i for i in range(words)))
        assert bytes(machine.mem_read(image.symbols['_sdata'], len(expected))) == expected
        assert bytes(machine.mem_read(image.symbols['_sbss'], words * 4)) == bytes(words * 4)
    print(mcu, f'data/BSS={words}words', f'callbacks={constructors}', f'vectors={count}', 'PASS', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler', type=Path, required=True)
    parser.add_argument('--cmsis-headers', type=Path, required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='mk61-owned-startup-') as directory:
        for mcu in ('f401', 'f411'):
            for words in (0, 1, 7):
                for constructors in (0, 1, 2):
                    run_fixture(args.compiler, args.cmsis_headers, Path(directory), mcu, words, constructors)
    print('18 owned ARM startup fixtures: section bounds, preinit/constructors, noinit, SP and IRQ overrides PASS')


if __name__ == '__main__':
    main()
