/*
 * Copyright (c) 2020 Raspberry Pi (Trading) Ltd.
 * SPDX-License-Identifier: BSD-3-Clause
 *
 * Adapted normal-number kernels from Pico SDK 2.2.0, commit
 * a1438dff1d38bd9c65dbd693f0e5db4b9ae91779:
 * src/rp2_common/pico_double/double_v1_rom_shim_rp2040.S
 * Original SHA-256: 3c85c8175bdd01d04ef319e75445418228b21ee2b2264cf31ef159aff0fd2c60
 * License: ../third_party/rp2040-softfloat/LICENSE.TXT
 *
 * Project changes: full IEEE C++ fallback guards, normal-only unpacking,
 * unsigned equal-sign addition, chunked cancellation normalization,
 * short-mantissa products, bounded quotient correction, exact exponent
 * scaling, rational reciprocal seeds, and
 * an exact software seed continuation while SIO's divider is dirty.
 * No Qfplib GPL-2.0 source is linked or copied into this firmware.
 */
.syntax unified
.cpu cortex-m0plus
.thumb
.macro mul32_32_64 rx,ry,rzl,rzh,rt0,rt1,rt2,rt3,rt4,cross_fit=0
                               @   t0   t1   t2   t3   t4
                               @                  (x)  (y)
 uxth \rt0,\rx                 @   xl
 uxth \rt1,\ry                 @        yl
 muls \rt0,\rt1                @  xlyl=L
 lsrs \rt2,\rx,#16             @             xh
 muls \rt1,\rt2                @       xhyl=M0
 lsrs \rt4,\ry,#16             @                       yh
 muls \rt2,\rt4                @           xhyh=H
 uxth \rt3,\rx                 @                   xl
 muls \rt3,\rt4                @                  xlyh=M1
 adds \rt1,\rt3                @      M0+M1=M
.if !\cross_fit
 bcc l\@_1                     @ addition of the two cross terms can overflow, so add carry into H
 movs \rt3,#1                  @                   1
 lsls \rt3,#16                 @                0x10000
 adds \rt2,\rt3                @             H'
l\@_1:
.endif
                               @   t0   t1   t2   t3   t4
                               @                 (zl) (zh)
 lsls \rzl,\rt1,#16            @                  ML
 lsrs \rzh,\rt1,#16            @                       MH
 adds \rzl,\rt0                @                  ZL
 adcs \rzh,\rt2                @                       ZH
.endm
#include "remainder-certificate.inc"
.section .unit,"ax",%progbits
.p2align 2
.global unit_remainder_sign
.type unit_remainder_sign,%function
.thumb_func
unit_remainder_sign:
 push {r4-r7,lr}
 mov r4,r0
 mov r0,r2
 mov r2,r1
.global unit_certificate_begin
unit_certificate_begin:
 remainder_certificate .Lfull,.Lnegative
 movs r0,#1
 pop {r4-r7,pc}
.Lfull:
 adds r4,r5
 mul32_32_64 r2,r0, r2,r3, r5,r6,r7,r2,r3
 negs r2,r2
 sbcs r4,r3
 cmp r4,#0
 beq .Lzero
 bmi .Lnegative
 movs r0,#1
 pop {r4-r7,pc}
.Lnegative:
 movs r0,#0
 subs r0,#1
 pop {r4-r7,pc}
.Lzero:
 movs r0,#0
 pop {r4-r7,pc}
.size unit_remainder_sign,.-unit_remainder_sign
.section .note.GNU-stack,"",%progbits
