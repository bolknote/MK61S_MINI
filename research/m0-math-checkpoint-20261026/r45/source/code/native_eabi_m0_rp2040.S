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
.section .text.mk61_rp2040_arithmetic,"ax",%progbits

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
 // Equality means exponent2046; the remaining cases retain CMP's N flag.
 bne .Lda_cold_other
 mov r6,r1
 eors r6,r3
 bmi 1f
 b .Lda_top_same_start
1:
 b .Lda_mixed_sign
.Lda_cold_other:
 // Negative residual means normal max exponent1..54. The only positive
 // residual here is exponent2047; zero was handled by the top path.
 bpl .Lda_nonfinite_start
 b .Lda_low_start
.Lda_nonfinite_start:
 // At least one exponent is2047. Preserve the existing first-NaN policy.
 lsls r6,r4,#21
 asrs r6,#21
 adds r6,#1
 bne .Lda_nonfinite_b
 lsls r6,r1,#12
 orrs r6,r0
 bne .Lda_nonfinite_quiet_a
 // A is infinity. A finite B returns A; a NaN B takes precedence.
 lsls r6,r5,#21
 asrs r6,#21
 adds r6,#1
 bne .Lda_nonfinite_return_a
 lsls r6,r3,#12
 orrs r6,r2
 bne .Lda_nonfinite_quiet_b
 movs r6,r1
 eors r6,r3
 bmi .Lda_nonfinite_invalid
.Lda_nonfinite_return_a:
 pop {r4-r7,pc}
.Lda_nonfinite_invalid:
 // Both inputs are infinities, so R0 is already zero.
 ldr r1,=0x7ff80000
 pop {r4-r7,pc}
.Lda_nonfinite_quiet_a:
 ldr r6,=0x00080000
 orrs r1,r6
 pop {r4-r7,pc}
.Lda_nonfinite_b:
 lsls r6,r3,#12
 orrs r6,r2
 beq .Lda_nonfinite_return_b
.Lda_nonfinite_quiet_b:
 ldr r6,=0x00080000
 orrs r3,r6
.Lda_nonfinite_return_b:
 movs r0,r2
 movs r1,r3
 pop {r4-r7,pc}
.ltorg

.Lda_zero_a_stub:
 b .Lda_zero_a
.Lda_zero_b_stub:
 b .Lda_zero_b

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
 // The top guard separately accepts exponent2046 with normal inputs.
 // Inf/NaN are rejected before the significands change.
 lsls r6, r4, #21
 beq .Lda_zero_a_stub
 lsls r7, r5, #21
 beq .Lda_zero_b_stub
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
.Lda_same_sign_start:
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
.Lda_mixed_unsigned_core:
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


.Lda_low_start:
 mov r6,r1
 eors r6,r3
 bmi .Lda_low_mixed_sign
 b .Lda_same_sign_start
.Lda_low_mixed_sign:
 // Align the encoded signs before subtracting exponents. For gaps 0/1,
 // the exact magnitude difference needs at most 54 bits, not a sticky limb.
 movs r6,#1
 lsls r6,#11
 eors r6,r5
 subs r6,r4,r6
 adds r7,r6,#1
 cmp r7,#2
 bls .Lda_low_near_input
 b .Lda_mixed_unsigned_core
.Lda_low_near_input:
 subs r7,r4,#1
 lsls r7,#20
 subs r1,r7
 subs r7,r5,#1
 lsls r7,#20
 subs r3,r7
 cmp r6,#0
 bmi .Lda_low_near_y
 bne .Lda_low_near_x
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
 beq .Lda_low_near_return
 b .Lda_low_near_normalize
.Lda_low_near_y:
 adds r2,r2
 adcs r3,r3
 subs r2,r2,r0
 sbcs r3,r1
 movs r0,r2
 movs r1,r3
 movs r4,r5
 b 1f
.Lda_low_near_x:
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
 bne .Lda_low_near_round
.Lda_low_near_normalize:
 lsrs r5,r1,#20
 bne .Lda_low_near_pack
 // R7 is the number of exact left shifts available before exponent1.
 lsls r7,r4,#21
 lsrs r7,#21
 cmp r7,#1
 beq .Lda_low_near_pack
 subs r7,#1
 lsrs r5,r1,#16
 bne .Lda_low_norm_one
.Lda_low_norm_sixteen:
 cmp r1,#16
 bhs .Lda_low_norm_eight
 cmp r7,#16
 blo .Lda_low_norm_short
 lsls r1,#16
 lsrs r5,r0,#16
 orrs r1,r5
 lsls r0,#16
 subs r4,#16
 subs r7,#16
 b .Lda_low_norm_sixteen
.Lda_low_norm_eight:
 lsrs r5,r1,#12
 bne .Lda_low_norm_four
 cmp r7,#8
 blo .Lda_low_norm_short
 lsls r1,#8
 lsrs r5,r0,#24
 orrs r1,r5
 lsls r0,#8
 subs r4,#8
 subs r7,#8
.Lda_low_norm_four:
 lsrs r5,r1,#16
 bne .Lda_low_norm_one
 cmp r7,#4
 blo .Lda_low_norm_short
 lsls r1,#4
 lsrs r5,r0,#28
 orrs r1,r5
 lsls r0,#4
 subs r4,#4
 subs r7,#4
.Lda_low_norm_one:
 cmp r7,#0
 beq .Lda_low_near_pack
 adds r0,r0
 adcs r1,r1
 subs r4,#1
 subs r7,#1
 lsrs r5,r1,#20
 beq .Lda_low_norm_one
 b .Lda_low_near_pack
.Lda_low_norm_short:
 // Needed normalization exceeds the remaining budget. Shift exactly to
 // exponent1 and pack the raw subnormal coefficient without discarding bits.
 cmp r7,#0
 beq .Lda_low_near_pack
 movs r5,#32
 subs r5,r5,r7
 movs r6,r0
 lsrs r6,r5
 lsls r1,r7
 orrs r1,r6
 lsls r0,r7
 subs r4,r4,r7
 b .Lda_low_near_pack

.Lda_low_near_pack:
 subs r4,#1
 lsls r4,#20
 adds r1,r4
.Lda_low_near_return:
 pop {r4-r7,pc}
.Lda_low_near_round:
 movs r5,#3
 ands r5,r0
 lsrs r0,#1
 lsls r6,r1,#31
 orrs r0,r6
 lsrs r1,#1
 adds r4,#1
 cmp r5,#3                    @ exact half ULP with an odd retained LSB
 bne .Lda_low_near_pack
 adds r0,#1
 bcc .Lda_low_near_pack
 adds r1,#1
 b .Lda_low_near_pack


.macro da_zero_cell sublo,subhi,otherlo,otherhi,ret,virtual
 // R6=other exponent+1. The usual half-ULP is2^(E-2) minimum subnormals.
 // Opposite signs at an exact power of two use the smaller lower cell.
 subs r6,#3
 movs r7,r1
 eors r7,r3
 bpl 1f
 lsls r4,\otherhi,#12
 orrs r4,\otherlo
 bne 1f
 subs r6,#1
 bmi \virtual
1:
 cmp r6,#32
 blo 3f
 subs r6,#31
 movs r4,#1
 lsls r4,r6
 lsls r7,\subhi,#1
 cmp r7,r4
 blo \ret
 bhi \virtual
 cmp \sublo,#0
 bne \virtual
 b 4f
3:
 lsls r7,\subhi,#1
 bne \virtual
 movs r4,#1
 lsls r4,r6
 cmp \sublo,r4
 blo \ret
 bhi \virtual
4:
 // Equality is a midpoint: retain the normal value only when its LSB is even.
 lsls r7,\otherlo,#31
 bmi \virtual
 b \ret
.endm

.Lda_zero_small:
 // Exponents0/1 encode integer coefficients at the minimum-subnormal
 // quantum directly after clearing the sign. At least one field is0.
 mov r6,r1
 eors r6,r3
 bmi .Lda_zero_small_opposite
 orrs r4,r5
 lsls r1,#1
 lsrs r1,#1
 lsls r3,#1
 lsrs r3,#1
 adds r0,r2
 adcs r1,r3
 lsrs r5,r1,#21
 beq .Lda_zero_small_sign
 // A54-bit sum implies that the larger input had field1. The existing
 // one-bit exact tie-even round therefore packs the result at field2.
 b .Lda_low_near_round
.Lda_zero_small_opposite:
 lsls r1,#1
 lsrs r1,#1
 lsls r3,#1
 lsrs r3,#1
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
 beq .Lda_zero_small_return
.Lda_zero_small_sign:
 lsrs r4,#11
 lsls r4,#31
 orrs r1,r4
.Lda_zero_small_return:
 pop {r4-r7,pc}

.Lda_zero_a:
 // A has field0; R4/R5 still contain the original sign:exponents.
 lsls r6,r5,#21
 lsrs r6,#21
 cmp r6,#1
 bls .Lda_zero_small
 adds r6,#1
 lsrs r7,r6,#11
 beq 1f
 b .Lda_nonfinite_start
1:
 // At exponent>=55 every subnormal is strictly inside the rounding cell.
 cmp r6,#56
 bhs .Lda_zero_return_b
 lsls r7,r1,#1
 orrs r7,r0
 beq .Lda_zero_return_b
 da_zero_cell r0,r1,r2,r3,.Lda_zero_return_b,.Lda_zero_virtual_a
.Lda_zero_b:
 lsls r6,r4,#21
 lsrs r6,#21
 cmp r6,#1
 bls .Lda_zero_small
 adds r6,#1
 lsrs r7,r6,#11
 beq 1f
 b .Lda_nonfinite_start
1:
 cmp r6,#56
 bhs .Lda_zero_return_a
 lsls r7,r3,#1
 orrs r7,r2
 beq .Lda_zero_return_a
 da_zero_cell r2,r3,r0,r1,.Lda_zero_return_a,.Lda_zero_virtual_b
.Lda_zero_virtual_a:
 // Cell comparison used the metadata as scratch; restore the real fields.
 lsrs r4,r1,#20
 lsrs r5,r3,#20
 // A's exact coefficient has no implicit bit. Virtual field1 makes the
 // common unpack remove only its sign, preserving that coefficient.
 adds r4,#1
 b .Lda_zero_virtual
.Lda_zero_virtual_b:
 lsrs r4,r1,#20
 lsrs r5,r3,#20
 adds r5,#1
.Lda_zero_virtual:
 // The other normal has exponent2..54, so every nonzero difference stays
 // normal. For gap1 its exact coefficient is already at least2^52+1.
 mov r6,r1
 eors r6,r3
 bpl 1f
 b .Lda_mixed_sign
1:
 b .Lda_same_sign_start
.Lda_zero_return_b:
 movs r0,r2
 movs r1,r3
.Lda_zero_return_a:
 pop {r4-r7,pc}

.align 2

.ltorg
mk61_m0_dadd_end:

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
@ Also exact for negative int32 x with0<=y<=2^30, or nonnegative x,y
@ with x+y<2^31. The software-divider certificate proves these ranges.
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
.Lrp_mul_short_b:
 lsls r7,r3,#12
 beq .Lrp_mul_scale
 mov r2,r0
 movs r0,#0
 mov r7,r1
 mov r1,r3
 mov r3,r7
 b .Lrp_mul_short
.Lrp_mul_short_a:
 lsls r7,r1,#12
 beq 1f
 b .Lrp_mul_short
1:
 mov r0,r2
.Lrp_mul_scale:
 // One high word is a signed power of two. Adding both packed high
 // words and subtracting the bias preserves the other fraction and
 // XORs the signs modulo 2^32. The guard proves a normal result.
 ldr r7,=0x3ff00000
 adds r1,r3
 subs r1,r7
 pop {r4-r7,pc}
.Lrp_mul_slow:
 sub sp,#4
 bl mk61_m0_dmul_slow
 add sp,#4
 pop {r4-r7,pc}

 regular_func __aeabi_dmul
 push {r4-r7,r14}
 lsls r4, r1, #1
 lsrs r4, r4, #21
 lsls r5, r3, #1
 lsrs r5, r5, #21
 subs r6, r4, #1
 ldr r7, =2045
 cmp r6, r7
 bhi .Lrp_mul_slow
 subs r6, r5, #1
 cmp r6, r7
 bhi .Lrp_mul_slow
 adds r6, r4, r5
 // Reuse the input bound 2045 instead of loading two more constants.
 lsrs r4,r7,#1
 adds r4,#2                    @ 1024
 subs r6,r4
 subs r7,#2                    @ 2043
 cmp r6, r7
 bhi .Lrp_mul_slow
 cmp r2,#0
 beq .Lrp_mul_short_b
 cmp r0,#0
 beq .Lrp_mul_short_a
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
 // Removing the implicit bit here is equivalent to subtracting one
 // exponent unit from R3, including a later rounding carry into R1.
 lsls r1,#12
 lsrs r1,#12
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
 b .Lrp_mul_pack


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
@ Normal division uses a32-byte table generated by an exact rational formula.
@ For h=floor(bMant/2^32), g=round(16384/(2*floor(h/32768)+1)).
@ t=s32((h<<8)*g)>>14; z=t>>11;
@ U0=(g<<7)-floor((floor((t-z*z)*g/2^14)+1)/2).
@ All1048576 h values and every signed intermediate are checked exactly.
@ Constant-U0 runs partition every normalized divisor; rational intervals
@ cover every remaining32-bit tail and every53-bit numerator.
@ The unchanged reciprocal/quotient refinements give a Q62 approximation A
@ with-256<A-T<128. The existing biased pack plus exact midpoint product
@ comparison is therefore RNE. Public R12 retains the parent's packed
@ exponent/sign representation. Cold IEEE and extreme paths are unchanged.

.section .text.mk61_rp2040_arithmetic,"ax",%progbits
.Lrp2040_small_divisor:
 // R7 is index<<29; R6 is the guarded biased exponent addend.
 lsls r6,#20
 mov r12,r6
 mov r6,r1
 eors r6,r3
 lsrs r6,#31
 lsls r6,#31
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

// Entry only from the second exponent rejection: numerator normal;
// CMP(Eb-1),2045 has N=1 for Eb0 and N=0 for Eb2047.
.global mk61_m0_ddiv_denominator_guard_begin
.hidden mk61_m0_ddiv_denominator_guard_begin
mk61_m0_ddiv_denominator_guard_begin:
.Lrp2040_div_den_slow:
 bpl .Lrp2040_div_slow
 // A normal finite numerator divided by signed zero is signed infinity.
 lsls r5,r3,#12
 orrs r5,r2
 beq .Lrp2040_div_den_overflow
 ldr r6,=1025
 subs r7,r6,r4             // k=1025-Ea
 ble .Lrp2040_div_den_overflow
 cmp r7,#53
 bhs .Lrp2040_div_slow
 // 1<=k<=52. Let M be the exact53-bit numerator significand;
 // denominator N is a subnormal coefficient. N<=M>>k implies
 // |a/b|>=2^1024. Retain all argument registers on every decline.
 lsls r5,r1,#12
 lsrs r5,r5,#12
 movs r6,#1
 lsls r6,r6,#20
 orrs r5,r6
 cmp r7,#32
 bhs .Lrp2040_div_den_shift_high
 mov r6,r0
 lsrs r6,r7
 mov r4,r5
 lsrs r5,r7
 negs r7,r7
 adds r7,#32
 lsls r4,r7
 orrs r6,r4
 b .Lrp2040_div_den_compare
.Lrp2040_div_den_shift_high:
 subs r7,#32
 mov r6,r5
 lsrs r6,r7
 movs r5,#0
.Lrp2040_div_den_compare:
 lsls r4,r3,#12
 lsrs r4,r4,#12
 cmp r4,r5
 bhi .Lrp2040_div_slow
 blo .Lrp2040_div_den_overflow
 cmp r2,r6
 bhi .Lrp2040_div_slow
.Lrp2040_div_den_overflow:
 eors r1,r3
 lsrs r1,r1,#31
 lsls r1,r1,#31
 ldr r0,=0x7ff00000
 orrs r1,r0
 movs r0,#0
 pop {r4-r7,pc}
.global mk61_m0_ddiv_denominator_guard_end
.hidden mk61_m0_ddiv_denominator_guard_end
mk61_m0_ddiv_denominator_guard_end:
 .ltorg

.Lrp2040_div_slow:
 sub sp,#4
 bl mk61_m0_ddiv_slow
 add sp,#4
 pop {r4-r7,pc}


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
 bhi .Lrp2040_div_slow
 subs r6, r5, #1
 cmp r6, r7
.global mk61_m0_ddiv_denominator_guard_call
.hidden mk61_m0_ddiv_denominator_guard_call
mk61_m0_ddiv_denominator_guard_call:
 bhi .Lrp2040_div_den_slow
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
 // General normal division never touches SIO. The reciprocal error and
 // exact final rounding are proved over all normalized mantissas.
.Lrp2040_general_divisor:
 lsls r6,#20
 mov r12,r6
 mov r7,r1
 eors r7,r3
 lsrs r7,#31                  @ result sign
 lsls r7,#31
 add r12,r7                   @ guarded biased exponent and sign
 ldr r4,=0x00100000
 lsls r3,#12
 lsrs r3,#12
 orrs r3,r4                   @ normal divisor significand

 lsrs r5,r3,#4
.global mk61_m0_public_ddiv_seed_begin
.hidden mk61_m0_public_ddiv_seed_begin
mk61_m0_public_ddiv_seed_begin:
 // h is the complete normalized21-bit high significand word.
 // g=round(16384/(2*floor(h/32768)+1)), generated from exact integers.
 lsrs r6,r3,#15
 ldr r7,=mk61_m0_public_div_seed8_table-32
 ldrb r6,[r7,r6]
 lsls r5,r3,#8
 muls r5,r6
 asrs r5,#14
 asrs r7,r5,#11
 muls r7,r7
 subs r5,r7
 muls r5,r6
 lsls r6,#7
 asrs r5,#14
 adds r5,#1
 asrs r5,#1
 subs r6,r5
.global mk61_m0_public_ddiv_seed_estimate
.hidden mk61_m0_public_ddiv_seed_estimate
mk61_m0_public_ddiv_seed_estimate:
.global mk61_m0_public_ddiv_seed_done
.hidden mk61_m0_public_ddiv_seed_done
mk61_m0_public_ddiv_seed_done:
 // Certified polynomial half-seed; general numerator words preserved.
 lsls r1,#12
 lsrs r1,#12
 orrs r1,r4
 lsls r4,r3,#10
 lsrs r5,r2,#22
 orrs r5,r4
 lsls r4,r1,#11
 lsrs r7,r0,#21
 orrs r4,r7

.global mk61_m0_public_ddiv_seed_join
.hidden mk61_m0_public_ddiv_seed_join
mk61_m0_public_ddiv_seed_join:

@ here
@ r0:r1 y mantissa
@ r2:r3 x mantissa
@ r6    u0, first approximation to 1/x Q15
@ r12: exponent addend in bits20..30, result sign in bit31

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

 movs r2,#1
 lsls r2,#20
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
 adds r1,r2                    @ prepacked guarded exponent and sign
 pop {r4-r7,r15}



.align 2
// Nearest-even values of 2^33/(8+i), generated from exact integers.
.Lrp2040_small_reciprocals:
 .word 0x40000000,0x38e38e39,0x33333333,0x2e8ba2e9,0x2aaaaaab,0x27627627,0x24924925,0x22222222

.ltorg
#include "native_eabi_m0_pow_kernels.inc"
#include "native_eabi_m0_pow_root64.inc"
#include "native_eabi_m0_pow_root_prefix.inc"
// Exact boundary helper is linked to the real compare function in this TU.
.global mk61_m0_boundary128_compare
.thumb_set mk61_m0_boundary128_compare,_ZL15root128_compareRK13PowInteger128S1_


/* Exact endpoints and a checked interval route for small finite y.
 * Only this cold helper changes; rejected arguments retain the old ABI. */
.section .m0_pow_tiny_cold,"ax",%progbits
.p2align 2
.hidden mk61_m0_pow_tiny_or_cr
regular_func mk61_m0_pow_tiny_or_cr
 push {r4,r5,r6,lr}
 lsls r4,r3,#1
 lsrs r4,r4,#1
 movs r5,r0
 orrs r5,r1
 beq .Lpow_magnitude_positive_zero
 ldr r5,=0x7ff00000
 cmp r1,r5
 bhs .Lpow_magnitude_fallback
 ldr r5,=0x3bf00000
 cmp r4,r5
 blo .Lpow_magnitude_one
 bhi .Lpow_magnitude_large
 cmp r2,#0
 beq .Lpow_magnitude_one
.Lpow_magnitude_large:
 ldr r5,=0x43e00000
 cmp r4,r5
 blo .Lpow_magnitude_small_y
 ldr r5,=0x7ff00000
 cmp r4,r5
 bhs .Lpow_magnitude_fallback
 ldr r5,=0x3ff00000
 cmp r1,r5
 blo .Lpow_magnitude_below_one
 bhi .Lpow_magnitude_above_one
 cmp r0,#0
 beq .Lpow_magnitude_one
.Lpow_magnitude_above_one:
 cmp r3,#0
 bmi .Lpow_magnitude_zero
 b .Lpow_magnitude_infinity
.Lpow_magnitude_below_one:
 cmp r3,#0
 bmi .Lpow_magnitude_infinity
.Lpow_magnitude_zero:
 movs r0,#0
 movs r1,#0
 pop {r4,r5,r6,pc}
.Lpow_magnitude_infinity:
 movs r0,#0
 ldr r1,=0x7ff00000
 pop {r4,r5,r6,pc}
.Lpow_magnitude_one:
 movs r0,#0
 ldr r1,=0x3ff00000
 pop {r4,r5,r6,pc}
.Lpow_magnitude_small_y:
 ldr r5,=0x3f300000
 cmp r4,r5
 bhs .Lpow_subnormal_endpoints
 ldr r5,=0x00100000
 cmp r1,r5
 blo .Lpow_magnitude_fallback
 bl mk61_m0_pow_small_y
 pop {r4,r5,r6,pc}
.Lpow_magnitude_fallback:
 bl mk61_m0_cr_pow
 pop {r4,r5,r6,pc}
.Lpow_magnitude_positive_zero:
 // R0|R1==0 proves +0. Keep zero/nonfinite y on the original IEEE path.
 ldr r5,=0x7ff00000
 cmp r4,r5
 bhs .Lpow_magnitude_fallback
 movs r5,r4
 orrs r5,r2
 beq .Lpow_magnitude_fallback
 cmp r3,#0
 bmi .Lpow_magnitude_infinity
 b .Lpow_magnitude_zero
.Lpow_subnormal_endpoints:
 // Existing prefix: positive nonzero finite x, 2^-12<=abs(y)<2^63.
 // R4 holds abs(y)high; all four argument registers remain original.
.global mk61_m0_pow_subnormal_gate_begin
.hidden mk61_m0_pow_subnormal_gate_begin
mk61_m0_pow_subnormal_gate_begin:
 lsrs r5,r1,#20
 bne .Lpow_magnitude_fallback
 ldr r5,=0x3ff10000
 cmp r4,r5
 bhs .Lpow_subnormal_uniform_endpoint
 cmp r3,#0
 bpl .Lpow_magnitude_fallback
 lsrs r5,r1,#17
 bne .Lpow_magnitude_fallback
 ldr r5,=0x3feffc00
 cmp r4,r5
 blo .Lpow_magnitude_fallback
 b .Lpow_magnitude_infinity
.Lpow_subnormal_uniform_endpoint:
 cmp r3,#0
 bmi .Lpow_magnitude_infinity
 b .Lpow_magnitude_zero
.global mk61_m0_pow_subnormal_gate_end
.hidden mk61_m0_pow_subnormal_gate_end
mk61_m0_pow_subnormal_gate_end:
 .ltorg
.size mk61_m0_pow_tiny_or_cr,.-mk61_m0_pow_tiny_or_cr

/* A private Flash thunk avoids adding an automatic ld veneer request.
 * The original SRAM kernel and every existing veneer remain unchanged. */
.section .m0_pow_small_y_cold,"ax",%progbits
.p2align 2
.hidden mk61_m0_pow_exp_product_flash
regular_func mk61_m0_pow_exp_product_flash
 push {r0}
 ldr r0,=mk61_m0_pow_exp_product
 mov ip,r0
 pop {r0}
 bx ip
 nop
 .ltorg
.size mk61_m0_pow_exp_product_flash,.-mk61_m0_pow_exp_product_flash
#include "native_eabi_m0_trig_large.S.inc"
#include "native_eabi_m0_sqrt_special.S.inc"
#include "native_eabi_m0_pow_argument_select.inc"
#include "native_eabi_m0_pow_log_select.inc"
.section .rodata.mk61_m0_public_div_seed8,"a",%progbits
.p2align 2
.global mk61_m0_public_div_seed8_table
.hidden mk61_m0_public_div_seed8_table
.type mk61_m0_public_div_seed8_table,%object
mk61_m0_public_div_seed8_table:
#include "public-div-polynomial-table.inc"
.size mk61_m0_public_div_seed8_table,.-mk61_m0_public_div_seed8_table

// Exact floor(n/d), arbitrary uint32 n and32768<=d<=65535.
// E approximates2^31/d; the initial quotient differs by[-2,+4].
// Exact signed residual corrections restore floor division. No SIO, BL,
// R12 clobber, new table, or changes to the public EABI division entries.
.section .text.mk61_m0_math_udiv16_sw,"ax",%progbits
.p2align 2
.global mk61_m0_math_udiv16_sw
.hidden mk61_m0_math_udiv16_sw
.type mk61_m0_math_udiv16_sw,%function
.thumb_func
mk61_m0_math_udiv16_sw:
 cmp r0,r1
 blo .Lmath_udiv16_zero
 push {r4-r7,lr}
 lsls r5,r1,#1
 lsrs r6,r5,#9
 subs r6,#128
 lsls r6,#1
 ldr r7,=mk61_m0_div_seed_table
 ldrh r6,[r7,r6]
 muls r5,r6
 asrs r5,#16
 muls r5,r6
 asrs r5,#16
 subs r6,r5
 // n*E fits48bits. The middle partial-product sum fits uint32.
 uxth r4,r0
 lsrs r5,r0,#16
 muls r4,r6
 muls r5,r6
 lsrs r4,#16
 adds r5,r4
 lsrs r5,#15
 movs r2,r5
 muls r2,r1
 subs r0,r0,r2
 bpl .Lmath_udiv16_under
.Lmath_udiv16_over:
 subs r5,#1
 adds r0,r1
 bmi .Lmath_udiv16_over
 b .Lmath_udiv16_done
.Lmath_udiv16_under:
 cmp r0,r1
 blo .Lmath_udiv16_done
 subs r0,r1
 adds r5,#1
 b .Lmath_udiv16_under
.Lmath_udiv16_done:
 movs r0,r5
 pop {r4-r7,pc}
.Lmath_udiv16_zero:
 movs r0,#0
 bx lr
.size mk61_m0_math_udiv16_sw,.-mk61_m0_math_udiv16_sw
.ltorg

#endif
.section .note.GNU-stack,"",%progbits
