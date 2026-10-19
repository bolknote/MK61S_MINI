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
 * fallback while SIO's divider is dirty.
 * No Qfplib GPL-2.0 source is linked or copied into this firmware.
 */
#if defined(MK61_USE_M0_EABI) && MK61_USE_M0_EABI && defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
.syntax unified
.cpu cortex-m0plus
.thumb
.equ use_hw_div,1
.equ IOPORT,0xd0000000
.equ DIV_UDIVIDEND,0x60
.equ DIV_UDIVISOR,0x64
.equ DIV_QUOTIENT,0x70
.macro regular_func name
 .global \name
 .type \name,%function
 .thumb_func
\name:
.endm
.macro mdunpack ra,rb,re,rs,rt
 lsrs \re,\rb,#20
 subs \rs,\re,#1
 lsls \rs,#20
 subs \rb,\rs
 lsrs \rs,\re,#11
 lsls \re,#21
 lsrs \re,#21
.endm
.macro mdunpacks_normal ra,rb,re,rt0
 // re already contains sign:exponent from the common IEEE guard.
 subs \rt0,\re,#1
 lsls \rt0,#20
 subs \rb,\rt0
 lsls \re,#21
 bcc 1f
 mvns \rb,\rb
 negs \ra,\ra
 bcc 1f
 adds \rb,#1
1:
 lsrs \re,#21
.endm
.macro mul_unpack_normal
 // R6 is the guarded exponent sum minus 1024. Save its packed addend
 // for a product in [2,4); normalization subtracts one exponent unit.
 mov r7,r1
 eors r7,r3
 lsrs r7,#31
 lsls r7,#31
 adds r6,#1
 lsls r6,#20
 orrs r6,r7
 movs r7,#1
 lsls r7,#20
 lsls r1,#12
 lsrs r1,#12
 orrs r1,r7
 lsls r3,#12
 lsrs r3,#12
 orrs r3,r7
.endm
.section .text.mk61_rp2040_arithmetic,"ax",%progbits

.Lda_slow:
 sub sp, #4
 bl mk61_m0_dadd_slow
 add sp, #4
 pop {r4-r7,pc}

regular_func __aeabi_dsub
 push {r4-r7,r14}
 movs r4,#1
 lsls r4,#31
 eors r3,r4                    @ flip sign on second argument
 b da_entry                    @ continue in dadd

.align 2
.section .text.mk61_rp2040_arithmetic,"ax",%progbits
regular_func __aeabi_dadd
 push {r4-r7,r14}
da_entry:
 lsrs r4, r1, #20
 lsrs r5, r3, #20
 // Normal inputs and max exponent 55..2045 guarantee that every nonzero
 // result is normal, including cancellation across a power-of-two boundary.
 // This also rejects Inf/NaN before the significands change.
 lsls r6, r4, #21
 beq .Lda_slow
 lsls r7, r5, #21
 beq .Lda_slow
 cmp r6, r7
 bhs 89f
 mov r6, r7
89:
 lsrs r6, #21
 subs r6, #55
 ldr r7, =1990
 cmp r6, r7
 bhi .Lda_slow
 mov r6,r1
 eors r6,r3
 bmi .Lda_mixed_sign
 // With equal signs there is no cancellation or signed normalization.
 // Keep the larger operand's packed exponent/sign as the final addend;
 // only the fraction and implicit leading bit enter the unsigned sum.
 subs r6,r4,r5
 subs r4,#1
 lsls r4,#20
 subs r1,r4
 subs r5,#1
 lsls r5,#20
 subs r3,r5
 mov r12,r4
 movs r4,#0
 cmp r6,#0
 bmi .Lda_same_y
 beq .Lda_same_add
 cmp r6,#32
 bhs .Lda_same_x_far
 movs r7,#32
 subs r7,r7,r6
 movs r4,r2
 lsls r4,r7
 movs r5,r3
 lsls r5,r7
 lsrs r2,r6
 lsrs r3,r6
 orrs r2,r5
.Lda_same_add:
 adds r0,r2
 adcs r1,r3
 lsrs r5,r1,#21
 bne .Lda_same_shift
 lsls r4,#1
 bcc .Lda_same_pack
.Lda_same_increment:
 adds r0,#1
 bcc 1f
 adds r1,#1
1:
 cmp r4,#0
 bne .Lda_same_pack
 lsrs r0,#1                    @ an exact midpoint rounds to even
 lsls r0,#1
.Lda_same_pack:
 mov r2,r12
 adds r1,r2
 pop {r4-r7,pc}
.Lda_same_shift:
 // The sum has one extra leading bit. Its discarded low bit is the
 // guard; the entire alignment tail remains available as sticky bits.
 lsls r6,r0,#31
 lsrs r0,#1
 lsls r5,r1,#31
 orrs r0,r5
 lsrs r1,#1
 movs r2,#1
 lsls r2,#20
 add r12,r2
 cmp r6,#0
 beq .Lda_same_pack
 b .Lda_same_increment

.Lda_same_y:
 mov r12,r5
 negs r6,r6
 cmp r6,#32
 bhs .Lda_same_y_far
 movs r7,#32
 subs r7,r7,r6
 movs r4,r0
 lsls r4,r7
 movs r5,r1
 lsls r5,r7
 lsrs r0,r6
 lsrs r1,r6
 orrs r0,r5
 b .Lda_same_add

.Lda_same_x_far:
 cmp r6,#54
 bhs .Lda_same_pack            @ less than half an ULP: larger input is exact
 movs r7,#64
 subs r7,r7,r6
 movs r4,r2
 lsls r4,r7
 beq 1f
 movs r4,#1
1:
 subs r6,#32
 lsrs r2,r6
 orrs r4,r2
 movs r2,r3
 lsls r3,r7
 orrs r4,r3
 lsrs r2,r6
 movs r3,#0
 b .Lda_same_add
.Lda_same_y_far:
 cmp r6,#54
 blo 1f
 movs r0,r2
 movs r1,r3
 b .Lda_same_pack
1:
 movs r7,#64
 subs r7,r7,r6
 movs r4,r0
 lsls r4,r7
 beq 2f
 movs r4,#1
2:
 subs r6,#32
 lsrs r0,r6
 orrs r4,r0
 movs r0,r1
 lsls r1,r7
 orrs r4,r1
 lsrs r0,r6
 movs r1,#0
 b .Lda_same_add

.Lda_mixed_sign:
 // Align the encoded signs before subtracting exponents. For gaps 0/1,
 // the exact magnitude difference needs at most 54 bits, not a sticky limb.
 movs r6,#1
 lsls r6,#11
 eors r6,r5
 subs r6,r4,r6
 adds r7,r6,#1
 cmp r7,#2
 bhi .Lda_mixed_general
 subs r7,r4,#1
 lsls r7,#20
 subs r1,r7
 subs r7,r5,#1
 lsls r7,#20
 subs r3,r7
 cmp r6,#0
 bmi .Lda_near_y
 bne .Lda_near_x
 // Equal exponents: the difference is exact. Only its magnitude and sign
 // are needed; a zero difference returns +0 before an exponent is packed.
 subs r0,r0,r2
 sbcs r1,r3
 bcs 1f
 movs r4,r5
 mvns r1,r1
 negs r0,r0
 bcc 1f
 adds r1,#1
1:
 movs r6,r0
 orrs r6,r1
 beq .Lda_near_return
 b .Lda_near_normalize
.Lda_near_y:
 adds r2,r2
 adcs r3,r3
 subs r2,r2,r0
 sbcs r3,r1
 movs r0,r2
 movs r1,r3
 movs r4,r5
 b 1f
.Lda_near_x:
 adds r0,r0
 adcs r1,r1
 subs r0,r0,r2
 sbcs r1,r3
1:
 // Use the smaller exponent with an exact integer difference. A result
 // with 54 significant bits needs one nearest-even rounding step; every
 // smaller result can be normalized and packed without losing any bit.
 subs r4,#1
 lsrs r5,r1,#21
 bne .Lda_near_round
.Lda_near_normalize:
 lsrs r5,r1,#20
 bne .Lda_near_pack
 lsrs r5,r1,#16
 bne .Lda_near_one
.Lda_near_sixteen:
 cmp r1,#16
 bhs .Lda_near_eight
 lsls r1,#16
 lsrs r5,r0,#16
 orrs r1,r5
 lsls r0,#16
 subs r4,#16
 b .Lda_near_sixteen
.Lda_near_eight:
 lsrs r5,r1,#12
 bne .Lda_near_four
 lsls r1,#8
 lsrs r5,r0,#24
 orrs r1,r5
 lsls r0,#8
 subs r4,#8
.Lda_near_four:
 lsrs r5,r1,#16
 bne .Lda_near_one
 lsls r1,#4
 lsrs r5,r0,#28
 orrs r1,r5
 lsls r0,#4
 subs r4,#4
.Lda_near_one:
 adds r0,r0
 adcs r1,r1
 subs r4,#1
 lsrs r5,r1,#20
 beq .Lda_near_one
.Lda_near_pack:
 subs r4,#1
 lsls r4,#20
 adds r1,r4
.Lda_near_return:
 pop {r4-r7,pc}
.Lda_near_round:
 movs r5,#3
 ands r5,r0
 lsrs r0,#1
 lsls r6,r1,#31
 orrs r0,r6
 lsrs r1,#1
 adds r4,#1
 cmp r5,#3                    @ exact half ULP with an odd retained LSB
 bne .Lda_near_pack
 adds r0,#1
 bcc .Lda_near_pack
 adds r1,#1
 b .Lda_near_pack

.Lda_far_return:
 cmp r6,#0
 bpl .Lda_near_return
 movs r0,r2
 movs r1,r3
 pop {r4-r7,pc}
.Lda_mixed_general:
 // Reuse the decoded gap: with at least 55 exponent steps the smaller
 // magnitude cannot change nearest-even, even below a power of two.
 adds r7,#53                  @ delta + 54, using the earlier delta + 1
 cmp r7,#108
 bhi .Lda_far_return
 mdunpacks_normal r0,r1,r4,r6
 mdunpacks_normal r2,r3,r5,r6
 subs r7,r5,r4                 @ ye-xe
 subs r6,r4,r5                 @ xe-ye
 bmi da_ygtx
@ here xe>=ye: need to shift y down r6 places
 mov r12,r4                    @ save exponent
 cmp r6,#32
 bge da_xrgty                  @ xe rather greater than ye?
 adds r7,#32
 movs r4,r2
 lsls r4,r4,r7                 @ rounding bit + sticky bits
da_xgty0:
 movs r5,r3
 lsls r5,r5,r7
 lsrs r2,r6
 asrs r3,r6
 orrs r2,r5
da_add:
 adds r0,r2
 adcs r1,r3
da_pack:
@ here unnormalised signed result (possibly 0) is in r0:r1 with exponent r12, rounding + sticky bits in r4
@ Note that if a large normalisation shift is required then the arguments were close in magnitude and so we
@ cannot have not gone via the xrgty/yrgtx paths. There will therefore always be enough high bits in r4
@ to provide a correct continuation of the exact result.
@ now pack result back up
 lsrs r3,r1,#31                @ get sign bit
 beq 1f                        @ skip on positive
 mvns r1,r1                    @ negate mantissa
 mvns r0,r0
 movs r2,#0
 negs r4,r4
 adcs r0,r2
 adcs r1,r2
1:
 mov r2,r12                    @ get exponent
 // Opposite signs reduce magnitude, so a carry normalization is impossible.
 lsrs r5,r1,#20
 bne da_1                      @ normalised?
 cmp r0,#0
 beq da_5                      @ could mantissa be zero?
da_2:
 // Large cancellation shifts are common in argument reduction. Move 16,
 // 8, and 4 bits at a time through the 96-bit significand/rounding state.
 cmp r1,#16
 bhs .Lrp_normalize_eight
 lsls r1,#16
 lsrs r5,r0,#16
 orrs r1,r5
 lsls r0,#16
 lsrs r5,r4,#16
 orrs r0,r5
 lsls r4,#16
 subs r2,#16
 b da_2
.Lrp_normalize_eight:
 lsrs r5,r1,#12
 bne .Lrp_normalize_four
 lsls r1,#8
 lsrs r5,r0,#24
 orrs r1,r5
 lsls r0,#8
 lsrs r5,r4,#24
 orrs r0,r5
 lsls r4,#8
 subs r2,#8
.Lrp_normalize_four:
 lsrs r5,r1,#16
 bne .Lrp_normalize_one
 lsls r1,#4
 lsrs r5,r0,#28
 orrs r1,r5
 lsls r0,#4
 lsrs r5,r4,#28
 orrs r0,r5
 lsls r4,#4
 subs r2,#4
.Lrp_normalize_one:
 adds r4,r4
 adcs r0,r0
 adcs r1,r1
 subs r2,#1                    @ adjust exponent
 lsrs r5,r1,#20
 beq .Lrp_normalize_one
da_1:
 lsls r4,#1                    @ check rounding bit
 bcc da_3
da_4:
 adds r0,#1                    @ round up
 bcc 2f
 adds r1,#1
2:
 cmp r4,#0                     @ sticky bits zero?
 bne da_3
 lsrs r0,#1                    @ round to even
 lsls r0,#1
da_3:
 // The entry guard already excludes underflow and overflow. Do not repeat
 // those checks after the exact signed sum and nearest-even rounding.
 subs r2,#1
 lsls r2,#20                   @ pack exponent and sign
 add r1,r2
 lsls r3,#31
 add r1,r3
 pop {r4-r7,r15}

da_5:
@ here mantissa could be zero
 cmp r1,#0
 bne da_2
 cmp r4,#0
 bne da_2
@ inputs must have been of identical magnitude and opposite sign, so return +0
 pop {r4-r7,r15}

da_xrgty:                      @ xe>ye and shift>=32 places
 cmp r6,#60
 bge da_xmgty                  @ xe much greater than ye?
 subs r6,#32
 adds r7,#64

 movs r4,r2
 lsls r4,r4,r7                 @ these would be shifted off the bottom of the sticky bits
 beq 1f
 movs r4,#1
1:
 lsrs r2,r2,r6
 orrs r4,r2
 movs r2,r3
 lsls r3,r3,r7
 orrs r4,r3
 asrs r3,r2,#31                @ propagate sign bit
 b da_xgty0

da_ygtx:
@ here ye>xe: need to shift x down r7 places
 mov r12,r5                    @ save exponent
 cmp r7,#32
 bge da_yrgtx                  @ ye rather greater than xe?
 adds r6,#32
 movs r4,r0
 lsls r4,r4,r6                 @ rounding bit + sticky bits
da_ygtx0:
 movs r5,r1
 lsls r5,r5,r6
 lsrs r0,r7
 asrs r1,r7
 orrs r0,r5
 b da_add

da_yrgtx:
 cmp r7,#60
 bge da_ymgtx                  @ ye much greater than xe?
 subs r7,#32
 adds r6,#64

 movs r4,r0
 lsls r4,r4,r6                 @ these would be shifted off the bottom of the sticky bits
 beq 1f
 movs r4,#1
1:
 lsrs r0,r0,r7
 orrs r4,r0
 movs r0,r1
 lsls r1,r1,r6
 orrs r4,r1
 asrs r1,r0,#31                @ propagate sign bit
 b da_ygtx0

da_ymgtx:                      @ result is just y
 movs r0,r2
 movs r1,r3
da_xmgty:                      @ result is just x
 movs r4,#0                    @ clear sticky bits
 b da_pack

.ltorg

@ equivalent of UMULL
@ needs five temporary registers
@ can have rt3==rx, in which case rx trashed
@ can have rt4==ry, in which case ry trashed
@ can have rzl==rx
@ can have rzh==ry
@ can have rzl,rzh==rt3,rt4
@ cross_fit=1 requires xh*yl+xl*yh < 2^32; two 21-bit inputs
@ satisfy this because their high halves are at most 31.
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

@ SUMULL for |x|<2^30 and 0<=y<=2^30, as in quotient correction.
@ The signed sum xh*yl+xl*yh fits in int32_t: its maximum is
@ 32767*65535 < 2^31. Its arithmetic high half includes the sign extension,
@ so no separate signed-cross-term carry correction is needed.
@ in table below ¯ means signed variable
@ needs five temporary registers
@ can have rt3==rx, in which case rx trashed
@ can have rt4==ry, in which case ry trashed
@ can have rzl==rx
@ can have rzh==ry
@ can have rzl,rzh==rt3,rt4
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

@ SSMULL: x signed, y signed
@ in table below ¯ means signed variable
@ needs five temporary registers
@ can have rt3==rx, in which case rx trashed
@ can have rt4==ry, in which case ry trashed
@ can have rzl==rx
@ can have rzh==ry
@ can have rzl,rzh==rt3,rt4
.macro muls32_s32_64 rx,ry,rzl,rzh,rt0,rt1,rt2,rt3,rt4
                               @   t0   t1   t2   t3   t4
                               @                 ¯(x)  (y)
 uxth \rt0,\rx                 @   xl
 uxth \rt1,\ry                 @        yl
 muls \rt0,\rt1                @  xlyl=L
 asrs \rt2,\rx,#16             @            ¯xh
 muls \rt1,\rt2                @      ¯xhyl=M0
 asrs \rt4,\ry,#16             @                      ¯yh
 muls \rt2,\rt4                @          ¯xhyh=H
 uxth \rt3,\rx                 @                   xl
 muls \rt3,\rt4                @                ¯xlyh=M1
 adds \rt1,\rt3                @     ¯M0+M1=M
 asrs \rt3,\rt1,#31            @                  Msx
 bvc l\@_1                     @
 mvns \rt3,\rt3                @                 ¯Msx        flip sign extension bits if overflow
l\@_1:
 lsls \rt3,#16                 @                    ¯Msx<<16
 adds \rt2,\rt3                @             H'

                               @   t0   t1   t2   t3   t4
                               @                 (zl) (zh)
 lsls \rzl,\rt1,#16            @                  M~
 lsrs \rzh,\rt1,#16            @                       M~
 adds \rzl,\rt0                @                  ZL
 adcs \rzh,\rt2                @                      ¯ZH
.endm

@ can have rt2==rx, in which case rx trashed
@ can have rzl==rx
@ can have rzh==rt1
.macro square32_64 rx,rzl,rzh,rt0,rt1,rt2
                               @   t0   t1   t2   zl   zh
 uxth \rt0,\rx                 @   xl
 muls \rt0,\rt0                @ xlxl=L
 uxth \rt1,\rx                 @        xl
 lsrs \rt2,\rx,#16             @             xh
 muls \rt1,\rt2                @      xlxh=M
 muls \rt2,\rt2                @           xhxh=H
 lsls \rzl,\rt1,#17            @                  ML
 lsrs \rzh,\rt1,#15            @                       MH
 adds \rzl,\rt0                @                  ZL
 adcs \rzh,\rt2                @                       ZH
.endm

.section .text.mk61_rp2040_arithmetic,"ax",%progbits
 regular_func __aeabi_dmul
 push {r4-r7,r14}
 lsls r4, r1, #1
 lsrs r4, r4, #21
 lsls r5, r3, #1
 lsrs r5, r5, #21
 subs r6, r4, #1
 ldr r7, =2045
 cmp r6, r7
 bhi 90f
 subs r6, r5, #1
 cmp r6, r7
 bhi 90f
 adds r6, r4, r5
 ldr r7, =1024
 subs r6, r6, r7
 ldr r7, =2043
 cmp r6, r7
 bhi 90f
 b 91f
90:
 sub sp, #4
 bl mk61_m0_dmul_slow
 add sp, #4
 pop {r4-r7,pc}
91:
 // Multiplication by a signed power of two is exact exponent scaling.
 cmp r2,#0
 bne 87f
 lsls r7,r3,#12
 beq .Lrp_mul_scale_a
 // Multiplication is commutative. The short product always has XL=0.
 mov r2,r0
 movs r0,#0
 mov r7,r1
 mov r1,r3
 mov r3,r7
 b .Lrp_mul_short
87:
 cmp r0,#0
 bne .Lrp_mul_general
 lsls r7,r1,#12
 bne .Lrp_mul_short
 mov r0,r2
 mov r7,r1
 mov r1,r3
 mov r3,r7
.Lrp_mul_scale_a:
 mov r7,r1
 eors r7,r3
 lsrs r7,r7,#31
 lsls r7,r7,#31
 lsls r1,r1,#12
 lsrs r1,r1,#12
 adds r6,#1
 lsls r6,r6,#20
 orrs r1,r6
 orrs r1,r7
 pop {r4-r7,pc}
.Lrp_mul_general:
 mul_unpack_normal
 push {r0-r2,r6}

@ accumulate full product in r12:r5:r6:r7
 mul32_32_64 r0,r2, r0,r5, r4,r6,r7,r0,r5    @ XL*YL
 mov r12,r0                    @ save LL bits

 mul32_32_64 r1,r3, r6,r7, r0,r2,r4,r6,r7,1  @ XH*YH, both at most 21 bits

 pop {r0}                      @ XL
 mul32_32_64 r0,r3, r0,r3, r1,r2,r4,r0,r3    @ XL*YH
 adds r5,r0
 adcs r6,r3
 movs r0,#0
 adcs r7,r0

 pop {r1,r2}                   @ XH,YL
 mul32_32_64 r1,r2, r1,r2, r0,r3,r4, r1,r2   @ XH*YL
 adds r5,r1
 adcs r6,r2
 movs r0,#0
 adcs r7,r0

@ here r5:r6:r7 holds the product [1..4) in Q(104-32)=Q72, with extra LSBs in r12
 pop {r3}                      @ guarded packed exponent and sign
 b .Lrp_mul_pack

.Lrp_mul_short:
 // If either low word is zero, two 32x32 products suffice instead of four.
 // This includes ordinary integers and short dyadic fractions, without
 // restricting the other operand or sacrificing any rounding/sticky bits.
 mul_unpack_normal
 push {r3,r6}
 cmp r2,#0
 bne 1f
 movs r5,#0
 movs r6,#0
 b 2f
1:
 mul32_32_64 r1,r2, r5,r6, r0,r3,r4,r5,r6    @ XH*YL; XH remains in R1
2:
 push {r5,r6}
 ldr r3,[sp,#8]
 mul32_32_64 r1,r3, r6,r7, r0,r2,r4,r6,r7,1  @ XH*YH
 pop {r0,r1}
 movs r5,r0
 adds r6,r1
 movs r0,#0
 adcs r7,r0
 mov r12,r0                    @ the bottom 32 product bits are exactly zero
 add sp,#4
 pop {r3}
.Lrp_mul_pack:
 lsls r1,r7,#11
 lsrs r2,r6,#21
 orrs r1,r2
 lsls r0,r6,#11
 lsrs r2,r5,#21
 orrs r0,r2
 lsls r5,#11                   @ now r5:r0:r1 Q83=Q(51+32), extra LSBs in r12
 lsrs r2,r1,#20
 bne 1f                        @ skip if in range [2..4)
 adds r5,r5                    @ shift up so always [2..4) Q83, i.e. [1..2) Q84=Q(52+32)
 adcs r0,r0
 adcs r1,r1
 movs r6,#1
 lsls r6,#20
 subs r3,r6                    @ correct the already packed exponent
1:
 // The entry guard proves that either normalization and any rounding
 // carry produce a finite normal result; retain the full IEEE slow path
 // for all other inputs instead of checking the same bounds twice.
 lsls r5,#1                    @ rounding bit to carry
 bcc 1f                        @ result is correctly rounded
 adds r0,#1
 movs r6,#0
 adcs r1,r6                    @ round up
 mov r6,r12                    @ remaining sticky bits
 orrs r5,r6
 bne 1f                        @ some sticky bits set?
 lsrs r0,#1
 lsls r0,#1                    @ round to even
1:
 adds r1,r3
 pop {r4-r7,r15}

.ltorg

@ Approach to division y/x is as follows.
@
@ First generate u1, an approximation to 1/x to about 29 bits. Multiply this by the top
@ 32 bits of y to generate a0, a first approximation to the result (good to 28 bits or so).
@ Calculate the exact remainder r0=y-a0*x, which will be about 0. Calculate a correction
@ d0=r0*u1, and then write a1=a0+d0. If near a rounding boundary, compute the exact
@ remainder r1=y-a1*x (which can be done using r0 as a basis) to determine whether to
@ round up or down.
@
@ The calculation of 1/x is as given in dreciptest.c. That code verifies exhaustively
@ that | u1*x-1 | < 10*2^-32.
@
@ More precisely:
@
@ x0=(q16)x;
@ x1=(q30)x;
@ y0=(q31)y;
@ u0=(q15~)"(0xffffffffU/(unsigned int)roundq(x/x_ulp))/powq(2,16)"(x0); // q15 approximation to 1/x; "~" denotes rounding rather than truncation
@ v=(q30)(u0*x1-1);
@ u1=(q30)u0-(q30~)(u0*v);
@
@ a0=(q30)(u1*y0);
@ r0=(q82)y-a0*x;
@ r0x=(q57)r0;
@ d0=r0x*u1;
@ a1=d0+a0;
@
@ Error analysis
@
@ Use Greek letters to represent the errors introduced by rounding and truncation.
@
@               r₀ = y - a₀x
@                  = y - [ u₁ ( y - α ) - β ] x    where 0 ≤ α < 2^-31, 0 ≤ β < 2^-30
@                  = y ( 1 - u₁x ) + ( u₁α + β ) x
@
@     Hence
@
@       | r₀ / x | < 2 * 10*2^-32 + 2^-31 + 2^-30
@                  = 26*2^-32
@
@               r₁ = y - a₁x
@                  = y - a₀x - d₀x
@                  = r₀ - d₀x
@                  = r₀ - u₁ ( r₀ - γ ) x    where 0 ≤ γ < 2^-57
@                  = r₀ ( 1 - u₁x ) + u₁γx
@
@     Hence
@
@       | r₁ / x | < 26*2^-32 * 10*2^-32 + 2^-57
@                  = (260+128)*2^-64
@                  < 2^-55
@
@ Empirically it seems to be nearly twice as good as this.
@
@ To determine correctly whether the exact remainder calculation can be skipped we need a result
@ accurate to < 0.25ulp. In the case where x>y the quotient will be shifted up one place for normalisation
@ and so 1ulp is 2^-53 and so the calculation above suffices.

.section .text.mk61_rp2040_arithmetic,"ax",%progbits
 regular_func __aeabi_ddiv
 push {r4-r7,r14}
ddiv0:                         @ entry point from dtan
 lsls r4, r1, #1
 lsrs r4, r4, #21
 lsls r5, r3, #1
 lsrs r5, r5, #21
 subs r6, r4, #1
 ldr r7, =2045
 cmp r6, r7
 bhi 90f
 subs r6, r5, #1
 cmp r6, r7
 bhi 90f
 subs r6, r4, r5
 ldr r7, =1021
 adds r6, r6, r7
 ldr r7, =2043
 cmp r6, r7
 bhi 90f
 // Dyadic mantissas with at most three fraction bits use an exact
 // rational reciprocal seed. Powers of two reduce to exponent scaling.
 cmp r2, #0
 bne 88f
 lsls r7, r3, #15
 bne 88f
 lsls r7, r3, #12
 bne .Lrp2040_small_divisor
 mov r7, r1
 eors r7, r3
 lsrs r7, r7, #31
 lsls r7, r7, #31
 lsls r1, r1, #12
 lsrs r1, r1, #12
 adds r6, #2
 lsls r6, r6, #20
 orrs r1, r6
 orrs r1, r7
 pop {r4-r7,pc}
88:
 // Respect an in-flight divider operation, including an interrupted caller.
 ldr r7, =0xd0000078
 ldr r7, [r7]
 lsrs r7, r7, #2
 bcs 90f
 b 91f
90:
 sub sp, #4
 bl mk61_m0_ddiv_slow
 add sp, #4
 pop {r4-r7,pc}
91:
 b .Lrp2040_general_divisor
.Lrp2040_small_divisor:
 // R4/R5 still hold the original biased exponents, R7 is index<<29.
 lsrs r7, r7, #27
 // R6 already holds the guarded exponent addend, including its bias.
 lsls r6, r6, #2
 mov r12, r6
 mov r6, r1
 eors r6, r3
 lsrs r6, r6, #31
 add r12, r12, r6
 lsls r1, r1, #12
 lsrs r1, r1, #12
 lsls r3, r3, #12
 lsrs r3, r3, #12
 movs r6, #1
 lsls r6, r6, #20
 orrs r1, r6
 orrs r3, r6
 ldr r6, =.Lrp2040_small_reciprocals
 ldr r6, [r6, r7]
 b .Lrp2040_quotient_refine
.Lrp2040_general_divisor:
 mov r7,r1
 eors r7,r3
 lsrs r7,#31                  @ result sign
 mov r12,r6                   @ retain the guarded biased exponent
 movs r4,#1
 lsls r4,#20
 lsls r3,#12
 lsrs r3,#12
 orrs r3,r4                   @ normal divisor significand

.if use_hw_div

 movs r5,#IOPORT>>24
 lsls r5,#24
 movs r6,#0
 mvns r6,r6
 str r6,[r5,#DIV_UDIVIDEND]
 lsrs r6,r3,#4                 @ x0=(q16)x
 str r6,[r5,#DIV_UDIVISOR]
@ if there are not enough cycles from now to the read of the quotient for
@ the divider to do its stuff we need a busy-wait here

.endif

@ Pack the exponent and unpack the dividend while the divider is working.
 mov r6,r12
 lsls r6,#2
 adds r6,r7
 mov r12,r6                    @ biased exponent in [31:2], sign in bit 0
 lsls r1,#12
 lsrs r1,#12
 orrs r1,r4                    @ normal dividend significand
 // Keep at least eight independent ALU instructions between starting the
 // SIO divide and reading its result, which is undefined while busy.
 lsls r4,r3,#10
 lsrs r7,r2,#22

.if use_hw_div

 ldr r6,[r5,#DIV_QUOTIENT]
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

 movs r5,r7
 orrs r5,r4                    @ x1=(q30)x
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

.Lrp2040_quotient_refine:
 push {r2,r3}
 lsls r4,r1,#11
 lsrs r5,r0,#21
 orrs r4,r5                    @ y0=(q31)y
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

.align 2
// Nearest-even values of 2^33/(8+i), generated from exact integers.
.Lrp2040_small_reciprocals:
 .word 0x40000000,0x38e38e39,0x33333333,0x2e8ba2e9,0x2aaaaaab,0x27627627,0x24924925,0x22222222

.ltorg
#endif
.section .note.GNU-stack,"",%progbits
