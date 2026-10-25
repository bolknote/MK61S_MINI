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
#if defined(MK61_USE_M0_EABI) && MK61_USE_M0_EABI && defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
.syntax unified
.cpu cortex-m0plus
.thumb
.equ IOPORT,0xd0000000
.equ DIV_UDIVIDEND,0x60
.equ DIV_UDIVISOR,0x64
.equ DIV_QUOTIENT,0x70
.equ use_hw_div,1
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
.macro muls32_32_64 rx,ry,rzl,rzh,rt0,rt1,rt2,rt3,rt4
                               @   t0   t1   t2   t3   t4
                               @                 ¯(x)  (y)
 uxth \rt0,\rx                 @   xl
 uxth \rt1,\ry                 @        yl
 muls \rt0,\rt1                @  xlyl=L
 asrs \rt2,\rx,#16             @            ¯xh
 muls \rt1,\rt2                @      ¯xhyl=M0
 lsrs \rt4,\ry,#16             @                       yh
 muls \rt2,\rt4                @          ¯xhyh=H
 uxth \rt3,\rx                 @                   xl
 muls \rt3,\rt4                @                 xlyh=M1
 adds \rt1,\rt3                @      M0+M1=M

                               @   t0   t1   t2   t3   t4
                               @                 (zl) (zh)
 lsls \rzl,\rt1,#16            @                  M~
 asrs \rzh,\rt1,#16            @                      ¯M~
 adds \rzl,\rt0                @                  ZL
 adcs \rzh,\rt2                @                      ¯ZH
.endm
.section .m0_ddiv_hint_hw,"ax",%progbits
.p2align 2
.Lrp2040_small_divisor:
 // R7 is index<<29; R6 is the guarded biased exponent addend.
 lsls r6,#2
 mov r12,r6
 mov r6,r1
 eors r6,r3
 lsrs r6,#31
 add r12,r6
 lsls r1,#12
 lsrs r1,#12
 // The three-bit dyadic index is the entire divisor fraction.
 lsrs r3,r7,#12
 lsrs r7,#27
 movs r6,#1
 lsls r6,#20
 orrs r1,r6
 orrs r3,r6
 adr r6,.Lrp2040_small_reciprocals
 ldr r6,[r6,r7]
 push {r2,r3}
 lsls r4,r1,#11
 lsrs r5,r0,#21
 orrs r4,r5
 b .Lrp2040_quotient_refine

.Lrp2040_div_dirty_bridge:
 ldr r7,.Lrp2040_sw_target
 bx r7
.p2align 2
.Lrp2040_sw_target: .word mk61_m0_ddiv_sw_from_guard
.fill (12-(.-.Lrp2040_div_dirty_bridge))/2,2,0xbf00

.Lrp2040_div_slow:
 sub sp,#4
 bl mk61_m0_ddiv_slow
 add sp,#4
 pop {r4-r7,pc}

 .global mk61_m0_hint_ddiv
.hidden mk61_m0_hint_ddiv
.type mk61_m0_hint_ddiv,%function
.thumb_func
mk61_m0_hint_ddiv:
 push {r4-r7,r14}
ddiv0:                         @ entry point from dtan
 lsls r4, r1, #1
 lsrs r4, r4, #21
 lsls r5, r3, #1
 lsrs r5, r5, #21
 subs r6, r4, #1
 ldr r7, =2045
 cmp r6, r7
 bhi .Lrp2040_div_slow
 subs r6, r5, #1
 cmp r6, r7
 bhi .Lrp2040_div_slow
 subs r6, r4, r5
 lsrs r5,r7,#1
 subs r5,#1                    @ 1021
 adds r6,r5
 subs r7,#2                    @ 2043
 cmp r6, r7
 bhi .Lrp2040_div_slow
 // Dyadic mantissas with at most three fraction bits use an exact
 // rational reciprocal seed. Powers of two reduce to exponent scaling.
 cmp r2, #0
 bne 88f
 lsls r7, r3, #15
 bne 88f
 lsls r7, r3, #12
 bne .Lrp2040_small_divisor
 // Subtract the packed power-of-two divisor and restore the bias;
 // its sign bit subtracts exactly like XOR, with no rounding needed.
 ldr r7,=0x3ff00000
 subs r1,r3
 adds r1,r7
 pop {r4-r7,pc}
88:
 // Respect an in-flight divider operation, including an interrupted caller.
 ldr r7, =0xd0000078
 ldr r7, [r7]
 lsrs r7, r7, #2
 bcs .Lrp2040_div_dirty_bridge
.Lrp2040_general_divisor:
 lsls r6,#2
 mov r12,r6
 mov r7,r1
 eors r7,r3
 lsrs r7,#31                  @ result sign
 add r12,r7                   @ guarded biased exponent and sign
 movs r4,#1
 lsls r4,#20
 lsls r3,#12
 lsrs r3,#12
 orrs r3,r4                   @ normal divisor significand

.if use_hw_div

 movs r7,#IOPORT>>24
 lsls r7,#24
 movs r6,#0
 mvns r6,r6
 str r6,[r7,#DIV_UDIVIDEND]
 lsrs r6,r3,#4                 @ x0=(q16)x
 str r6,[r7,#DIV_UDIVISOR]
@ if there are not enough cycles from now to the read of the quotient for
@ the divider to do its stuff we need a busy-wait here

.endif

@ Unpack the dividend and prepare both leading products during the divide.
 lsls r1,#12
 lsrs r1,#12
 orrs r1,r4                    @ normal dividend significand
 // Keep at least eight independent ALU instructions between starting the
 // SIO divide and reading its result, which is undefined while busy.
 lsls r4,r3,#10
 lsrs r5,r2,#22
 orrs r5,r4                    @ x1=(q30)x
 lsls r4,r1,#11
 lsrs r6,r0,#21
 orrs r4,r6                    @ y0=(q31)y; nine ALU instructions since STR

.if use_hw_div

 ldr r6,[r7,#DIV_QUOTIENT]
 adds r6,#1
 lsrs r6,#1

.else

@ this is not beautiful; could be replaced by better code that uses knowledge of divisor range
 push {r0-r3}
 movs r0,#0
 mvns r0,r0
 lsrs r1,r3,#4                 @ x0=(q16)x
 bl __aeabi_uidiv              @ !!! this could (but apparently does not) trash R12
 adds r6,r0,#1
 lsrs r6,#1
 pop {r0-r3}

.endif

@ here
@ r0:r1 y mantissa
@ r2:r3 x mantissa
@ r6    u0, first approximation to 1/x Q15
@ r12: result sign, biased exponent addend

.global mk61_m0_hint_join
mk61_m0_hint_join:
 muls r5,r6                    @ u0*x1 Q45
 asrs r5,#15                   @ v=u0*x1-1 Q30
 muls r5,r6                    @ u0*v Q45
 asrs r5,#14
 adds r5,#1
 asrs r5,#1                    @ round u0*v to Q30
 lsls r6,#15
 subs r6,r5                    @ u1 Q30

@ here
@ r0:r1 y mantissa
@ r2:r3 x mantissa
@ r6    u1, second approximation to 1/x Q30
@ r12: result sign, exponent

 push {r2,r3}
.Lrp2040_quotient_refine:
.global mk61_m0_hint_first_product
mk61_m0_hint_first_product:
 mul32_32_64 r4,r6, r4,r5, r2,r3,r7,r4,r5  @ y0*u1 Q61
 adds r4,r4
 adcs r5,r5                    @ a0=(q30)(y0*u1)

@ here
@ r0:r1 y mantissa
@ r5    a0, first approximation to y/x Q30
@ r6    u1, second approximation to 1/x Q30
@ r12   result sign, exponent

 ldr r2,[r13,#0]               @ xL
 mul32_32_64 r2,r5, r2,r3, r1,r4,r7,r2,r3  @ xL*a0
.global mk61_m0_hint_after_second_product
mk61_m0_hint_after_second_product:
 ldr r4,[r13,#4]               @ xH
 muls r4,r5                    @ xH*a0
 adds r3,r4                    @ r2:r3 now x*a0 Q82
 lsrs r2,#25
 lsls r1,r3,#7
 orrs r2,r1                    @ r2 now x*a0 Q57; r7:r2 is x*a0 Q89
 lsls r4,r0,#5                 @ y Q57
 subs r0,r4,r2                 @ r0x=y-x*a0 Q57 (signed)

@ here
@ r0  r0x Q57
@ r5  a0, first approximation to y/x Q30
@ r4  yL  Q57
@ r6  u1 Q30
@ r12 result sign, exponent

 muls32_32_64 r0,r6, r7,r6, r1,r2,r3, r7,r6   @ r7:r6 r0x*u1 Q87
 asrs r3,r6,#25
 adds r5,r3
 lsls r3,r6,#7                 @ r3:r5 a1 Q62 (but bottom 7 bits are zero so 55 bits of precision after binary point)
@ here we could recover another 7 bits of precision (but not accuracy) from the top of r7
@ but these bits are thrown away in the rounding and conversion to Q52 below

@ here
@ r3:r5  a1 Q62 candidate quotient [0.5,2) or so
@ r4     yL Q57
@ r12    result sign, exponent

 movs r6,#0
 adds r3,#128                  @ for initial rounding to Q53
 adcs r5,r5,r6
 lsrs  r1,r5,#30
 bne dd_0
@ here candidate quotient a1 is in range [0.5,1)
@ so 30 significant bits in r5

 lsls r4,#1                    @ y now Q58
 lsrs r1,r5,#9                 @ to Q52
 lsls r0,r5,#23
 lsrs r3,#9                    @ 0.5ulp-significance bit in carry: if this is 1 we may need to correct result
 orrs r0,r3
 bcs dd_1
 b dd_2
dd_0:
@ here candidate quotient a1 is in range [1,2)
@ so 31 significant bits in r5

 movs r2,#4
 add r12,r12,r2                @ fix exponent; r3:r5 now effectively Q61
 adds r3,#128                  @ complete rounding to Q53
 adcs r5,r5,r6
 lsrs r1,r5,#10
 lsls r0,r5,#22
 lsrs r3,#10                   @ 0.5ulp-significance bit in carry: if this is 1 we may need to correct result
 orrs r0,r3
 bcc dd_2
dd_1:

@ here
@ r0:r1  rounded result Q53 [0.5,1) or Q52 [1,2), but may not be correctly rounded-to-nearest
@ r4     yL Q58 or Q57
@ r12    result sign, exponent
@ carry set

 adcs r0,r0,r0
 adcs r1,r1,r1                 @ z Q53 with 1 in LSB
 lsls r4,#16                   @ Q105-32=Q73
 ldr r2,[r13,#0]               @ xL Q52
 ldr r3,[r13,#4]               @ xH Q20

 movs r5,r1                    @ zH Q21
 muls r5,r2                    @ zH*xL Q73
 subs r4,r5
 muls r3,r0                    @ zL*xH Q73
 subs r4,r3
 mul32_32_64 r2,r0, r2,r3, r5,r6,r7,r2,r3  @ xL*zL
 negs r2,r2                    @ borrow from low half?
 sbcs r4,r3                    @ y-xz Q73 (remainder bits 52..73)

 cmp r4,#0

 bmi 1f
 movs r2,#0                    @ round up
 adds r0,#1
 adcs r1,r2
1:
 lsrs r0,#1                    @ shift back down to Q52
 lsls r2,r1,#31
 orrs r0,r2
 lsrs r1,#1
dd_2:
 add r13,#8
 mov r2,r12
 lsls r7,r2,#31                @ result sign
 lsrs r2,#2                    @ guarded biased exponent addend
 lsls r2,#20
 adds r1,r2                    @ pack exponent
 adds r1,r7                    @ pack sign
 pop {r4-r7,r15}

.size mk61_m0_hint_ddiv,.-mk61_m0_hint_ddiv

.align 2
// Nearest-even values of 2^33/(8+i), generated from exact integers.
.Lrp2040_small_reciprocals:
 .word 0x40000000,0x38e38e39,0x33333333,0x2e8ba2e9,0x2aaaaaab,0x27627627,0x24924925,0x22222222

.ltorg

#endif
