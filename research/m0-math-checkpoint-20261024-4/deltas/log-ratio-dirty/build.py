"""Compile ln public components against a pinned, read-only resident image."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys

sys.dont_write_bytecode = True
W = Path(__file__).resolve().parent
ROOT = W.parents[1]
P = ROOT / '.build/m0-asin-scaled-bound-v164-20261023'
CC = Path('/Users/bolk/Library/Arduino15/packages/STMicroelectronics/tools/xpack-arm-none-eabi-gcc/14.2.1-1.1/bin')
sys.path.insert(0, str(ROOT / 'tests'))
from check_stm32_vectors import ElfImage


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


resident_path = P / 'firmware/mk61s-picocalc-pico-h.elf'
assert sha(resident_path) == '3b92d7dc30cc860c0b1f17943f1cd626f94112a98adaf165ec4f9cd300364db1'
resident = ElfImage(resident_path)
for label, directory in [('control', P / 'source/code'), ('candidate', W)]:
    commands = [[str(CC / 'arm-none-eabi-g++'), '-mcpu=cortex-m0plus', '-mthumb', '-mfloat-abi=soft',
                 '-Os', '-std=gnu++17', '-fno-exceptions', '-fno-rtti', '-fno-unwind-tables', '-fno-use-cxa-atexit',
                 '-ffunction-sections', '-fdata-sections', '-fno-lto', '-DMK61_USE_M0_EABI=1', '-DMK61_M0_RP2040_EABI=1',
                 '-I', str(P / 'source/code'), '-c', str(directory / 'native_eabi_m0.cpp'), '-o', str(W / (label + '-full.o'))]]
    subprocess.run(commands[0], check=True)
    asm_command = [str(CC / 'arm-none-eabi-gcc'), '-mcpu=cortex-m0plus', '-mthumb',
                   '-mfloat-abi=soft', '-DMK61_USE_M0_EABI=1', '-DMK61_M0_RP2040_EABI=1',
                   '-I', str(P / 'source/code'), '-c', str(W / ('ratio.S' if label=='candidate' else 'control-asm/ratio.S')), '-o', str(W / (label + '-ratio.o'))]
    commands.append(asm_command)
    subprocess.run(asm_command, check=True)

    names = [line.split()[-1] for line in subprocess.check_output(
        [str(CC / 'arm-none-eabi-nm'), '-u', str(W / (label + '-full.o'))], text=True).splitlines()]
    bindings = {n: resident.symbols[n] for n in names if n in resident.symbols and n != 'mk61_m0_log_ratio70'}
    for name in ('memset', 'memcpy'):
        if name in names and name not in bindings:
            bindings[name] = resident.symbols['__wrap_' + name]
    script = '\n'.join(n + ' = ' + hex(v) + ';' for n, v in sorted(bindings.items())) + '\n'
    script += '''SECTIONS {
 . = 0x101a0000;
 .text : { *(.text*) *(.m0*) }
 .rodata : { *(.rodata*) }
 /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment) *(.ARM.attributes) *(.note*) }
}
'''
    ld = W / (label + '.ld')
    ld.write_text(script)
    command = [str(CC / 'arm-none-eabi-ld'), '--gc-sections', '-e', 'mk61_m0_ln', '-T', str(ld),
               str(W / (label + '-full.o')), str(W / (label + '-ratio.o')), '-o', str(W / (label + '.elf'))]
    commands.append(command)
    subprocess.run(command, check=True)
    image = ElfImage(W / (label + '.elf'))
    ranges = [(s[3], s[3] + s[5]) for s in image.named_sections.values() if s[2] & 2 and s[5]]
    assert all(0x101a0000 <= lo < hi <= 0x10200000 for lo, hi in ranges)
    assert all(not any(lo <= (v & ~1) < hi for lo, hi in ranges) for v in bindings.values())
    with (W / (label + '.dis')).open('w') as f:
        subprocess.run([str(CC / 'arm-none-eabi-objdump'), '-dr', str(W / (label + '.elf'))], check=True, stdout=f)
    r = dict(status='BUILT_PRIVATE_PUBLIC_LN_COMPONENT_NOT_FIRMWARE', label=label,
             source_include_sha256=sha(directory / 'native_eabi_m0_log70_center.inc'),
             full_object_sha256=sha(W / (label + '-full.o')), ELF_sha256=sha(W / (label + '.elf')),
             resident_bindings=bindings, resident_ELF_sha256=sha(resident_path),
             all_bindings_outside_overlay=True, allocated_ranges=ranges, commands=commands,
             hardware_accessed=False, canonical_or_frozen_changed=False)
    (W / (label + '-build.json')).write_text(json.dumps(r, indent=2) + '\n')
    print(json.dumps({k: v for k, v in r.items() if k not in ('commands', 'resident_bindings')}))
