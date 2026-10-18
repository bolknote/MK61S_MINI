// ARMv6-M primitives, with the base AAPCS calling convention.
#if defined(MK61_USE_M0_EABI) && MK61_USE_M0_EABI
.syntax unified
.cpu cortex-m0plus
.thumb
.macro function name
 .section .text.\name,"ax",%progbits
 .global \name
 .type \name,%function
 .thumb_func
\name:
.endm
.macro end name
 .size \name, .-\name
.endm

// Normal finite operands use three exact rounding bits. Exceptional operands
// and the extreme exponents enter the shared, fully IEEE integer fallback
// before either significand is changed. This is independent project code.
#if !defined(MK61_M0_RP2040_EABI) || !MK61_M0_RP2040_EABI
function __aeabi_dsub
 mov r12, r0
 movs r0, #1
 lsls r0, r0, #31
 eors r3, r0
 mov r0, r12
 push {r4,lr}
 bl __aeabi_dadd
 pop {r4,pc}
end __aeabi_dsub

function __aeabi_dadd
 push {r3-r7,lr}
 // Sort by magnitude; sign/exponent bits are removed only after the guard.
 lsls r4, r1, #1
 lsls r5, r3, #1
 cmp r4, r5
 bhi .Ldadd_sorted
 blo .Ldadd_swap
 cmp r0, r2
 bhs .Ldadd_sorted
.Ldadd_swap:
 mov r6, r0
 mov r0, r2
 mov r2, r6
 mov r6, r1
 mov r1, r3
 mov r3, r6
.Ldadd_sorted:
 lsls r4, r1, #1
 lsrs r4, r4, #21
 lsls r5, r3, #1
 lsrs r5, r5, #21
 subs r6, r4, #1
 // eA >= 55 guarantees a nonzero cancellation result stays normal.
 subs r6, #54
 ldr r7, =1990
 cmp r6, r7
 bhi .Ldadd_slow
 cmp r5, #0
 beq .Ldadd_slow
 mov r6, r1
 eors r6, r3
 lsrs r6, r6, #31
 lsrs r7, r1, #31
 lsls r7, r7, #31
 orrs r6, r7
 mov r12, r6             // bit 31 = output sign, bit 0 = subtract magnitudes
 subs r5, r4, r5
 lsls r1, r1, #12
 lsrs r1, r1, #9
 lsrs r6, r0, #29
 orrs r1, r6
 lsls r0, r0, #3
 movs r6, #1
 lsls r6, r6, #23
 orrs r1, r6
 lsls r3, r3, #12
 lsrs r3, r3, #9
 orrs r3, r6
 lsrs r6, r2, #29
 orrs r3, r6
 lsls r2, r2, #3
 cmp r5, #0
 beq .Ldadd_aligned
 cmp r5, #32
 bhs .Ldadd_shift_high
 movs r6, #32
 subs r6, r6, r5
 mov r7, r2
 lsls r7, r7, r6
 push {r7}               // lost low bits; no call while SP is unaligned
 mov r7, r3
 lsls r7, r7, r6
 lsrs r2, r2, r5
 orrs r2, r7
 lsrs r3, r3, r5
 pop {r7}
 b .Ldadd_sticky
.Ldadd_shift_high:
 cmp r5, #56
 bhs .Ldadd_tiny
 mov r7, r2
 movs r6, #64
 subs r6, r6, r5
 mov r2, r3
 lsls r2, r2, r6
 orrs r7, r2
 mov r2, r3
 subs r5, #32
 lsrs r2, r2, r5
 movs r3, #0
.Ldadd_sticky:
 cmp r7, #0
 beq .Ldadd_aligned
 movs r6, #1
 orrs r2, r6
 b .Ldadd_aligned
.Ldadd_tiny:
 movs r2, #1
 movs r3, #0
.Ldadd_aligned:
 mov r6, r12
 lsls r6, r6, #31
 bmi .Ldadd_subtract
 adds r0, r0, r2
 adcs r1, r3
 lsls r6, r1, #7
 bpl .Ldadd_round
 movs r6, #1
 ands r6, r0
 lsrs r0, r0, #1
 lsls r3, r1, #31
 orrs r0, r3
 lsrs r1, r1, #1
 orrs r0, r6
 adds r4, #1
 b .Ldadd_round
.Ldadd_subtract:
 subs r0, r0, r2
 sbcs r1, r3
 mov r6, r0
 orrs r6, r1
 beq .Ldadd_zero
.Ldadd_normalize:
 lsls r6, r1, #8
 bmi .Ldadd_round
 adds r0, r0, r0
 adcs r1, r1
 subs r4, #1
 b .Ldadd_normalize
.Ldadd_round:
 movs r6, #7
 ands r6, r0
 lsrs r0, r0, #3
 lsls r3, r1, #29
 orrs r0, r3
 lsrs r1, r1, #3
 cmp r6, #4
 bhi .Ldadd_increment
 blo .Ldadd_pack
 lsls r6, r0, #31
 bpl .Ldadd_pack
.Ldadd_increment:
 movs r6, #0
 adds r0, #1
 adcs r1, r6
 lsls r6, r1, #10
 bpl .Ldadd_pack
 lsrs r1, r1, #1
 adds r4, #1
.Ldadd_pack:
 lsls r1, r1, #12
 lsrs r1, r1, #12
 lsls r4, r4, #20
 orrs r1, r4
 mov r3, r12
 lsrs r3, r3, #31
 lsls r3, r3, #31
 orrs r1, r3
 pop {r3-r7,pc}
.Ldadd_zero:
 movs r0, #0
 movs r1, #0
 pop {r3-r7,pc}
.Ldadd_slow:
 bl mk61_m0_dadd_slow
 pop {r3-r7,pc}
 .ltorg
end __aeabi_dadd

// Exact R0*R2 -> R2:R0. Four 16-bit limbs, with each cross sum kept below
// 2^32; R1/R3 are untouched and R4-R7 are scratch.
.macro product32
 uxth r4, r0
 lsrs r5, r0, #16
 uxth r6, r2
 lsrs r7, r2, #16
 mov r0, r4
 muls r0, r6
 muls r6, r5
 muls r4, r7
 muls r5, r7
 lsrs r2, r0, #16
 adds r6, r6, r2
 uxth r2, r6
 adds r4, r4, r2
 lsrs r6, r6, #16
 adds r5, r5, r6
 lsrs r2, r4, #16
 adds r2, r2, r5
 lsls r4, r4, #16
 uxth r0, r0
 orrs r0, r4
.endm

function __aeabi_dmul
 push {r4-r7,lr}
 sub sp, #44
 lsls r4, r1, #1
 lsrs r4, r4, #21
 lsls r5, r3, #1
 lsrs r5, r5, #21
 subs r6, r4, #1
 ldr r7, =2045
 cmp r6, r7
 bhi .Ldmul_slow
 subs r6, r5, #1
 cmp r6, r7
 bhi .Ldmul_slow
 adds r4, r4, r5
 ldr r7, =1023
 subs r4, r4, r7
 subs r6, r4, #1
 ldr r7, =2043
 cmp r6, r7
 bhi .Ldmul_slow
 b .Ldmul_normal
.Ldmul_slow:
 bl mk61_m0_dmul_slow
 add sp, #44
 pop {r4-r7,pc}
.Ldmul_normal:
 str r4, [sp,#16]
 mov r6, r1
 eors r6, r3
 lsrs r6, r6, #31
 lsls r6, r6, #31
 str r6, [sp,#20]
 lsls r1, r1, #12
 lsrs r1, r1, #12
 lsls r3, r3, #12
 lsrs r3, r3, #12
 movs r4, #1
 lsls r4, r4, #20
 orrs r1, r4
 orrs r3, r4
 str r0, [sp,#0]
 str r1, [sp,#4]
 str r2, [sp,#8]
 str r3, [sp,#12]
 product32                    // low*low
 mov r12, r0                 // all low 32 product bits become sticky
 str r2, [sp,#28]
 ldr r0, [sp,#0]
 ldr r2, [sp,#12]
 product32                    // low*high
 ldr r4, [sp,#28]
 movs r5, #0
 adds r0, r0, r4
 adcs r2, r5
 str r0, [sp,#28]
 str r2, [sp,#32]
 ldr r0, [sp,#4]
 ldr r2, [sp,#8]
 product32                    // high*low
 ldr r4, [sp,#28]
 movs r5, #0
 adds r0, r0, r4
 adcs r2, r5
 ldr r4, [sp,#32]
 adds r2, r2, r4             // at most 23 bits: no extra word carry
 str r0, [sp,#28]
 str r2, [sp,#32]
 ldr r0, [sp,#4]
 ldr r2, [sp,#12]
 product32                    // high*high
 ldr r4, [sp,#32]
 movs r5, #0
 adds r0, r0, r4
 adcs r2, r5
 ldr r3, [sp,#28]            // upper product words R2:R0:R3
 ldr r4, [sp,#16]
 lsls r5, r2, #22
 bmi .Ldmul_high
 mov r5, r3
 lsls r5, r5, #15
 lsrs r3, r3, #17
 mov r1, r0
 lsls r0, r0, #15
 orrs r0, r3
 lsrs r1, r1, #17
 lsls r2, r2, #15
 orrs r1, r2
 b .Ldmul_jam
.Ldmul_high:
 adds r4, #1
 mov r5, r3
 lsls r5, r5, #14
 lsrs r3, r3, #18
 mov r1, r0
 lsls r0, r0, #14
 orrs r0, r3
 lsrs r1, r1, #18
 lsls r2, r2, #14
 orrs r1, r2
.Ldmul_jam:
 mov r6, r12
 orrs r5, r6
 beq .Ldmul_round
 movs r6, #1
 orrs r0, r6
.Ldmul_round:
 movs r6, #7
 ands r6, r0
 lsrs r0, r0, #3
 lsls r3, r1, #29
 orrs r0, r3
 lsrs r1, r1, #3
 cmp r6, #4
 bhi .Ldmul_increment
 blo .Ldmul_pack
 lsls r6, r0, #31
 bpl .Ldmul_pack
.Ldmul_increment:
 movs r6, #0
 adds r0, #1
 adcs r1, r6
 lsls r6, r1, #10
 bpl .Ldmul_pack
 lsrs r1, r1, #1
 adds r4, #1
.Ldmul_pack:
 lsls r1, r1, #12
 lsrs r1, r1, #12
 lsls r4, r4, #20
 orrs r1, r4
 ldr r3, [sp,#20]
 orrs r1, r3
 add sp, #44
 pop {r4-r7,pc}
 .ltorg
end __aeabi_dmul
#endif

function __aeabi_llsl
 cmp r2, #32
 bhs 1f
 mov r3, r0
 lsls r1, r1, r2
 lsls r0, r0, r2
 rsbs r2, r2, #0
 adds r2, #32
 lsrs r3, r3, r2
 orrs r1, r3
 bx lr
1:
 subs r2, #32
 mov r1, r0
 lsls r1, r1, r2
 movs r0, #0
 bx lr
end __aeabi_llsl

function __aeabi_llsr
 cmp r2, #32
 bhs 1f
 mov r3, r1
 lsrs r0, r0, r2
 lsrs r1, r1, r2
 rsbs r2, r2, #0
 adds r2, #32
 lsls r3, r3, r2
 orrs r0, r3
 bx lr
1:
 subs r2, #32
 mov r0, r1
 lsrs r0, r0, r2
 movs r1, #0
 bx lr
end __aeabi_llsr

function __aeabi_lasr
 cmp r2, #32
 bhs 1f
 mov r3, r1
 lsrs r0, r0, r2
 asrs r1, r1, r2
 rsbs r2, r2, #0
 adds r2, #32
 lsls r3, r3, r2
 orrs r0, r3
 bx lr
1:
 subs r2, #32
 mov r0, r1
 asrs r0, r0, r2
 asrs r1, r1, #31
 bx lr
end __aeabi_lasr

// This result is returned in R0:R1 (quotient), R2:R3 (remainder), not
// the normal AAPCS structure-result convention. Keep the C++ call aligned.
function __aeabi_uldivmod
 push {r4, lr}
 sub sp, #24
 add r4, sp, #8
 str r4, [sp]
 bl mk61_m0_divmod64
 ldmia r4!, {r0,r1,r2,r3}
 add sp, #24
 pop {r4,pc}
end __aeabi_uldivmod

function __aeabi_ldivmod
 push {r4, lr}
 sub sp, #24
 add r4, sp, #8
 str r4, [sp]
 bl mk61_m0_sdivmod64
 ldmia r4!, {r0,r1,r2,r3}
 add sp, #24
 pop {r4,pc}
end __aeabi_ldivmod

function __aeabi_uidiv
 push {r4, lr}
 bl mk61_m0_udiv32
 pop {r4, pc}
end __aeabi_uidiv
.global __aeabi_uidivmod
.thumb_set __aeabi_uidivmod, __aeabi_uidiv
function __aeabi_idiv
 push {r4, lr}
 bl mk61_m0_sdiv32
 pop {r4, pc}
end __aeabi_idiv
.global __aeabi_idivmod
.thumb_set __aeabi_idivmod, __aeabi_idiv

// Pico SDK's interrupt-safe SIO divider supplies the saturated value in R0
// (or R0:R1) on division by zero. The EABI default hook returns it unchanged.
function __aeabi_idiv0
 bx lr
end __aeabi_idiv0
function __aeabi_ldiv0
 bx lr
end __aeabi_ldiv0
.section .note.GNU-stack,"",%progbits
#endif
