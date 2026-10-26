"""Bare wrapper executes the production inline macro with live context guards."""
from pathlib import Path
import hashlib,json,subprocess
W=Path(__file__).resolve().parent
build=json.loads((W/'build.json').read_bytes());tc=Path(build['commands'][0][0]).parent
source='''#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
.syntax unified
.cpu cortex-m0plus
.thumb
#include "inline-seed.inc"
.section .unit,"ax",%progbits
.p2align 2
.global unit_inline_seed
.type unit_inline_seed,%function
.thumb_func
unit_inline_seed:
 push {r4-r7,lr}
 reciprocal_seed_inline
 mov r0,r6
 pop {r4-r7,pc}
.size unit_inline_seed,.-unit_inline_seed
#include "inline-seed-table.inc"
#endif
.section .note.GNU-stack,"",%progbits
'''
(W/'unit.S').write_text(source)
(W/'unit.ld').write_text('PHDRS { code PT_LOAD FLAGS(5); }\nSECTIONS { .unit 0x101e1000 : { KEEP(*(.unit)) } :code\n/DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment) *(.note*) *(.ARM.attributes) } }\n')
commands=[[str(tc/'arm-none-eabi-gcc'),'-mcpu=cortex-m0plus','-mthumb','-DMK61_M0_RP2040_EABI=1','-c',str(W/'unit.S'),'-o',str(W/'unit.o')],
 [str(tc/'arm-none-eabi-ld'),'--gc-sections','-e','unit_inline_seed','-T',str(W/'unit.ld'),str(W/'unit.o'),'-o',str(W/'unit.elf')]]
for c in commands:subprocess.run(c,cwd=W,check=True)
(W/'unit-build.json').write_text(json.dumps(dict(status='BUILT_PRODUCTION_INLINE_MACRO_UNIT_WRAPPER',commands=commands,ELF_sha256=hashlib.sha256((W/'unit.elf').read_bytes()).hexdigest(),hardware_accessed=False),indent=2)+'\n')
