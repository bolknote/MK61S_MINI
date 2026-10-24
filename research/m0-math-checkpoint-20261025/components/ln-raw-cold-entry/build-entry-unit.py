"""Compile the exact naked ln entry with bit-preserving tagged targets."""
from pathlib import Path
import hashlib
import json
import subprocess

W=Path(__file__).resolve().parent
CC=Path('/Users/bolk/Library/Arduino15/packages/STMicroelectronics/tools/xpack-arm-none-eabi-gcc/14.2.1-1.1/bin')
source=(W/'native_eabi_m0_log70.inc').read_text()
a=source.index('__attribute__((naked,noinline,optimize("Os"))) MK61_SOFT_PCS double mk61_m0_ln(double) {')
z=source.index('__attribute__((optimize("Os"),noinline)) MK61_SOFT_PCS double mk61_m0_ln_positive(',a)
fragment=source[a:z].rstrip()
unit='''#include <stdint.h>
#define MK61_SOFT_PCS __attribute__((pcs("aapcs")))
using U=uint64_t;
static U bits(double x) {union {double d;U u;} q={x};return q.u;}
static double real(U x) {union {U u;double d;} q={x};return q.d;}
extern "C" {
MK61_SOFT_PCS double mk61_m0_ln_positive(double x) {return real(bits(x)^UINT64_C(0x13579BDF2468ACE0));}
MK61_SOFT_PCS double mk61_m0_ln_special(double x) {return real(bits(x)^UINT64_C(0xFDB97531ECA86420));}
'''+fragment+'\n}\n'
(W/'entry-unit.cpp').write_text(unit)
(W/'entry-unit.ld').write_text('SECTIONS { . = 0x10000000; .text : { *(.text*) *(.rodata*) } /DISCARD/ : { *(.ARM*) *(.comment) *(.note*) } }\n')
commands=[[str(CC/'arm-none-eabi-g++'),'-mcpu=cortex-m0plus','-mthumb','-mfloat-abi=soft','-Os','-std=gnu++17','-fno-exceptions','-fno-rtti','-fno-unwind-tables','-ffunction-sections','-fno-lto','-c',str(W/'entry-unit.cpp'),'-o',str(W/'entry-unit.o')],
          [str(CC/'arm-none-eabi-ld'),'-T',str(W/'entry-unit.ld'),str(W/'entry-unit.o'),'-o',str(W/'entry-unit.elf')]]
for command in commands:subprocess.run(command,check=True)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
out=dict(status='BUILT_EXACT_NAKED_LN_IEEE_ENTRY_UNIT',source_sha256=sha(W/'native_eabi_m0_log70.inc'),exact_fragment_sha256=hashlib.sha256(fragment.encode()).hexdigest(),unit_ELF_sha256=sha(W/'entry-unit.elf'),commands=commands,firmware_or_ROM_mapped=False,hardware_accessed=False)
(W/'entry-unit-build.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({k:v for k,v in out.items() if k!='commands'},indent=2))
