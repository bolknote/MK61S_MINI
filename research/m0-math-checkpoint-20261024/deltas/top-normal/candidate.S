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
 // Each subtrahend is sign:(exponent-1):0. Their sum minus 1021
 // exponent units packs both the result sign and the exponent addend
 // for a product in [2,4), without separately extracting either sign.
 lsrs r4,r1,#20
 subs r4,#1
 lsls r4,#20
 subs r1,r4
 lsrs r5,r3,#20
 subs r5,#1
 lsls r5,#20
 subs r3,r5
 adds r6,r4,r5
 ldr r7,=0x3fd00000
 subs r6,r7
.endm
.section .text.m0_top_trial,"ax",%progbits

.macro da_top_same_y_finish
 adds r0,r2
 adcs r1,r3
 lsrs r5,r1,#21
 bne .Lda_top_same_shift
 lsls r4,#1
 bcc .Lda_top_same_pack
 b .Lda_top_same_increment
.endm

.Lda_top_guard:
 // BHS retained the preceding CMP flags. Equality means exponent2046;
 // every larger unsigned value remains a fallback input.
 bne .Lda_slow
 mov r6,r1
 eors r6,r3
 bmi 1f
 b .Lda_top_same_start
1:
 b .Lda_mixed_sign
.Lda_slow:
 // Save the volatile R3 in the previously reserved alignment word.
 // A six-register pop restores the identical24-byte frame in one step.
 push {r3}
 bl mk61_m0_dadd_slow
 pop {r3-r7,pc}

regular_func top_candidate_dsub
 push {r4-r7,r14}
 movs r4,#1
 lsls r4,#31
 eors r3,r4                    @ flip sign on second argument
 b da_entry                    @ continue in dadd

.align 2
.section .text.m0_top_trial,"ax",%progbits
regular_func top_candidate_dadd
 push {r4-r7,r14}
da_entry:
 lsrs r4, r1, #20
 lsrs r5, r3, #20
 // Normal inputs and max exponent 55..2045 guarantee that every nonzero
 // result is normal, including cancellation across a power-of-two boundary.
 // The top guard separately accepts exponent2046 with normal inputs.
 // Inf/NaN are rejected before the significands change.
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
 ldr r7, =1991
 cmp r6, r7
 bhs .Lda_top_guard
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
 // The existing guard established normal operands and a normal nonzero
 // result. Gaps 0/1 use the unchanged exact cancellation path above.
 adds r7,#53
 cmp r7,#108
 bhi .Lda_far_return
 // Unpack unsigned magnitudes, retaining each packed sign:exponent-1.
 subs r7,r4,#1
 lsls r7,#20
 subs r1,r7
 subs r5,#1
 lsls r5,#20
 subs r3,r5
 cmp r6,#0
 bmi .Lda_unsigned_y
 mov r12,r7
 cmp r6,#32
 bhs .Lda_unsigned_x_far
 movs r7,#32
 subs r7,r7,r6
 movs r4,r2
 lsls r4,r7
 movs r5,r3
 lsls r5,r7
 lsrs r2,r6
 lsrs r3,r6
 orrs r2,r5
.Lda_unsigned_x_subtract:
 // NEG supplies the borrow for subtracting the discarded fractional limb.
 negs r4,r4
 sbcs r0,r2
 sbcs r1,r3
 b .Lda_unsigned_normalize
.Lda_unsigned_x_far:
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
 b .Lda_unsigned_x_subtract
.Lda_unsigned_y:
 mov r12,r5
 negs r6,r6
 cmp r6,#32
 bhs .Lda_unsigned_y_far
 movs r7,#32
 subs r7,r7,r6
 movs r4,r0
 lsls r4,r7
 movs r5,r1
 lsls r5,r7
 lsrs r0,r6
 lsrs r1,r6
 orrs r0,r5
.Lda_unsigned_y_subtract:
 negs r4,r4
 sbcs r2,r0
 sbcs r3,r1
 movs r0,r2
 movs r1,r3
 b .Lda_unsigned_normalize
.Lda_unsigned_y_far:
 movs r7,#64
 subs r7,r7,r6
 movs r4,r0
 lsls r4,r7
 beq 1f
 movs r4,#1
1:
 subs r6,#32
 lsrs r0,r6
 orrs r4,r0
 movs r0,r1
 lsls r1,r7
 orrs r4,r1
 lsrs r0,r6
 movs r1,#0
 b .Lda_unsigned_y_subtract
.Lda_unsigned_normalize:
 mov r2,r12
 // For gap>=2 the magnitude is greater than half of the larger binade.
 // Its unsigned integer representation therefore needs at most one shift.
 lsrs r5,r1,#20
 bne .Lda_unsigned_round
 adds r4,r4
 adcs r0,r0
 adcs r1,r1
 movs r5,#1
 lsls r5,#20
 subs r2,r5
.Lda_unsigned_round:
 lsls r4,#1
 bcc .Lda_unsigned_pack
 adds r0,#1
 bcc 1f
 adds r1,#1
1:
 cmp r4,#0
 bne .Lda_unsigned_pack
 lsrs r0,#1
 lsls r0,#1
.Lda_unsigned_pack:
 adds r1,r2
 pop {r4-r7,pc}

.ltorg
.Lda_top_same_start:
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
 bmi .Lda_top_same_y
 beq .Lda_top_same_add
 cmp r6,#32
 bhs .Lda_top_same_x_far
 movs r7,#32
 subs r7,r7,r6
 movs r4,r2
 lsls r4,r7
 movs r5,r3
 lsls r5,r7
 lsrs r2,r6
 lsrs r3,r6
 orrs r2,r5
.Lda_top_same_add:
 adds r0,r2
 adcs r1,r3
 lsrs r5,r1,#21
 bne .Lda_top_same_shift
 lsls r4,#1
 bcc .Lda_top_same_pack
.Lda_top_same_increment:
 adds r0,#1
 bcc 1f
 adds r1,#1
1:
 cmp r4,#0
 bne .Lda_top_same_pack
 lsrs r0,#1                    @ an exact midpoint rounds to even
 lsls r0,#1
.Lda_top_same_pack:
 // This also detects a carry caused only by the final RNE increment.
 lsrs r5,r1,#21
 bne .Lda_top_same_shift
 mov r2,r12
 adds r1,r2
 pop {r4-r7,pc}
.Lda_top_same_shift:
 // R5=1 from the leading-bit test. R12 is sign:(2045):0.
 lsls r5,#21
 mov r1,r12
 orrs r1,r5
 movs r0,#0
 pop {r4-r7,pc}

.Lda_top_same_y:
 mov r12,r5
 negs r6,r6
 cmp r6,#32
 bhs .Lda_top_same_y_far
 movs r7,#32
 subs r7,r7,r6
 movs r4,r0
 lsls r4,r7
 movs r5,r1
 lsls r5,r7
 lsrs r0,r6
 lsrs r1,r6
 orrs r0,r5
 da_top_same_y_finish

.Lda_top_same_x_far:
 cmp r6,#54
 bhs .Lda_top_same_pack            @ less than half an ULP: larger input is exact
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
 b .Lda_top_same_add
.Lda_top_same_y_far:
 cmp r6,#54
 blo 1f
 movs r0,r2
 movs r1,r3
 b .Lda_top_same_pack
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
 da_top_same_y_finish


.align 2

.ltorg

#endif
