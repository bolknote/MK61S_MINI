/* Copyright (c) 2020 Raspberry Pi (Trading) Ltd.
 * SPDX-License-Identifier: BSD-3-Clause
 *
 * Unsigned 32-bit EABI divider, adapted from Pico SDK divider_hardware.S
 * and hardware/divider_helper.S for the standalone RP2040 APP build.
 * License: ../../../third_party/rp2040-softfloat/LICENSE.TXT */
.syntax unified
.cpu cortex-m0plus
.thumb

.section .text.__aeabi_uidiv,"ax",%progbits
.align 2
.global __aeabi_uidiv
.global __aeabi_uidivmod
.type __aeabi_uidiv,%function
.type __aeabi_uidivmod,%function
.thumb_func
__aeabi_uidiv:
.thumb_func
__aeabi_uidivmod:
    ldr r2, =0xd0000000
    ldr r3, [r2, #0x78]       /* DIV_CSR.DIRTY */
    lsrs r3, r3, #2
    bcs .Lsave
.Ldivide:
    str r0, [r2, #0x60]       /* unsigned dividend */
    str r1, [r2, #0x64]       /* unsigned divisor; result in eight cycles */
    cmp r1, #0
    beq .Lzero
    b 1f
1:  b 2f
2:  b 3f
3:  ldr r1, [r2, #0x74]       /* remainder must be read before quotient */
    ldr r0, [r2, #0x70]       /* acknowledges DIRTY */
    bx lr
.Lzero:
    push {r2, lr}
    cmp r0, #0
    beq 4f
    movs r0, #0
    mvns r0, r0
4:  bl __aeabi_idiv0
    movs r1, #0
    pop {r2, pc}
.Lsave:
    /* The push and operand reads also allow an in-flight divide to finish. */
    push {r4, r5, r6, r7, lr}
    ldr r4, [r2, #0x60]
    ldr r5, [r2, #0x64]
    ldr r7, [r2, #0x74]
    ldr r6, [r2, #0x70]
    bl .Ldivide
    str r4, [r2, #0x60]
    str r5, [r2, #0x64]
    str r7, [r2, #0x74]
    str r6, [r2, #0x70]
    pop {r4, r5, r6, r7, pc}
.size __aeabi_uidiv, .-__aeabi_uidiv
.size __aeabi_uidivmod, .-__aeabi_uidivmod
