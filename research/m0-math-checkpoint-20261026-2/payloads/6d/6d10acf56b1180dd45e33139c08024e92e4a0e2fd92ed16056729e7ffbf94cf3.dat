/* Retain Pico SDK 2.2.0's BootROM memset and EABI calling conventions while
 * memcpy uses the measured project implementation in memory.c.
 * Adapted from pico_mem_ops/mem_ops_aeabi.S:
 * Copyright (c) 2020 Raspberry Pi (Trading) Ltd.
 * License terms: PICO_MEMORY_LICENSE.txt
 * SPDX-License-Identifier: BSD-3-Clause
 */
#include "pico/asm_helper.S"
#include "pico/bootrom.h"
#include "pico/runtime_init.h"
pico_default_asm_setup
PICO_RUNTIME_INIT_FUNC_RUNTIME(__aeabi_mem_init, PICO_RUNTIME_INIT_AEABI_MEM_OPS)

.section .data.aeabi_mem_funcs,"aw",%progbits
.global aeabi_mem_funcs, aeabi_mem_funcs_end
.balign 4
aeabi_mem_funcs:
 .word ROM_FUNC_MEMSET
 .word ROM_FUNC_MEMCPY
 .word ROM_FUNC_MEMSET4
 .word ROM_FUNC_MEMCPY44
aeabi_mem_funcs_end:
.section .text.__aeabi_mem_init,"ax",%progbits
regular_func __aeabi_mem_init
 ldr r0,=aeabi_mem_funcs
 movs r1,#4
 ldr r3,=rom_funcs_lookup
 bx r3
 .ltorg

/* Retain the SDK placement switch for builds which disable XIP temporarily. */
#if PICO_MEM_IN_RAM
.section RAM_SECTION_NAME(mk61_memset),"ax",%progbits
#else
.section SECTION_NAME(mk61_memset),"ax",%progbits
#endif
.balign 4
wrapper_func __aeabi_memset
 eors r2,r1
 eors r1,r2
 eors r2,r1
wrapper_func memset
 ldr r3,=aeabi_mem_funcs
 ldr r3,[r3]
 bx r3
wrapper_func __aeabi_memset4
wrapper_func __aeabi_memset8
 eors r2,r1
 eors r1,r2
 eors r2,r1
 ldr r3,=aeabi_mem_funcs
 ldr r3,[r3,#8]
 bx r3
 .ltorg
