// ARMv6-M primitives, with the base AAPCS calling convention.
#if defined(MK61_USE_M0_EABI) && MK61_USE_M0_EABI
.syntax unified
.cpu cortex-m0plus
.thumb
.macro function name, group=.text
 .section \group\().\name,"ax",%progbits
 .global \name
 .type \name,%function
 .thumb_func
\name:
.endm
.macro end name
 .size \name, .-\name
.endm

// Every int32/uint32 is exactly representable in binary64. Normalize the
// unsigned magnitude in chunks, then split its 32 bits between R1 and R0.
function __aeabi_i2d
 movs r1,#0
 cmp r0,#0
 beq .Li2d_return
 bpl .Li2d_normalize
 movs r1,#1
 lsls r1,#31
 rsbs r0,r0,#0
 b .Li2d_normalize
.global __aeabi_ui2d
.type __aeabi_ui2d,%function
.thumb_func
__aeabi_ui2d:
 movs r1,#0
 cmp r0,#0
 beq .Li2d_return
.Li2d_normalize:
 ldr r2,=1053
 lsrs r3,r0,#16
 bne 1f
 lsls r0,#16
 subs r2,#16
1:
 lsrs r3,r0,#24
 bne 1f
 // The 19..21-bit band is already close to the binary64 high word.
 // Pack it directly, including after the preceding 16-bit shift.
 lsrs r3,r0,#20
 cmp r3,#1
 beq .Li2d_exact21
 cmp r3,#0
 bne .Li2d_byte
 lsrs r3,r0,#19
 bne .Li2d_exact20
 lsrs r3,r0,#18
 bne .Li2d_exact19
.Li2d_byte:
 lsls r0,#8
 subs r2,#8
1:
 lsrs r3,r0,#28
 bne 1f
 lsls r0,#4
 subs r2,#4
1:
 lsrs r3,r0,#30
 bne 1f
 lsls r0,#2
 subs r2,#2
1:
 cmp r0,#0
 bmi 1f
 lsls r0,#1
 subs r2,#1
1:
 lsrs r3,r0,#11
 orrs r1,r3
 lsls r2,#20
 adds r1,r2
 lsls r0,#21
.Li2d_return:
 bx lr
.size __aeabi_ui2d,.-__aeabi_ui2d
.ltorg
end __aeabi_i2d

.macro i2d_middle width
.Li2d_exact\width:
 .if \width < 21
 lsls r0,#(21-\width)
 .endif
 adds r1,r0
 movs r0,#0
 subs r2,#(32-\width)
 lsls r2,#20
 adds r1,r2
 bx lr
.endm
i2d_middle 21
i2d_middle 20
i2d_middle 19

#include "native_eabi_m0_convert.inc"
#include "native_eabi_m0_product.inc"

// Positive Q62 in [sin(1/64),1], sign in R3. The quotient discards only
// 3..10 bits, so all rounding bits are in R0. Exact nearest-even packing.
function mk61_m0_trig_pack
 push {r4,lr}
 mov r12,r3
 mov r2,r1
 movs r3,#11
 lsrs r4,r2,#24
 bne 1f
 lsls r2,#8
 subs r3,#8
1:
 lsrs r4,r2,#28
 bne 1f
 lsls r2,#4
 subs r3,#4
1:
 lsrs r4,r2,#30
 bne 1f
 lsls r2,#2
 subs r3,#2
1:
 cmp r2,#0
 bmi 1f
 subs r3,#1
1:
 movs r2,#1
 subs r4,r3,#1
 lsls r2,r4
 subs r2,#1
 mov r4,r0
 lsrs r4,r3
 lsls r4,#31
 lsrs r4,#31
 adds r2,r4
 adds r0,r2
 movs r2,#0
 adcs r1,r2
 mov r4,r1
 lsrs r1,r3
 movs r2,#32
 subs r2,r3
 lsls r4,r2
 lsrs r0,r3
 orrs r0,r4
 ldr r2,=1012
 adds r2,r3
 lsls r2,#20
 adds r1,r2
 mov r2,r12
 orrs r1,r2
 pop {r4,pc}
.ltorg
end mk61_m0_trig_pack

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

// Separate these small helpers from the trig argument/literal cache sets.
// Only RP2040 changes placement; every instruction body stays unchanged.
.macro math_shift_function name
#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
 .section .scratch_y.m0_shift_hot,"ax",%progbits
 .align 2
 .global \name
 .type \name,%function
 .thumb_func
\name:
#else
 function \name
#endif
.endm

math_shift_function __aeabi_llsl
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

math_shift_function __aeabi_llsr
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

math_shift_function __aeabi_lasr
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

// Math-only quotient seed. An interrupted caller's pending SIO operation
// takes the ordinary EABI path; never consume or overwrite its result.
function mk61_m0_math_udiv32
#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
 cmp r1,#0
 beq 2f
 ldr r2,=0xd0000078
 ldr r3,[r2]
 lsrs r3,#2
 bcs 2f
 subs r2,#24
 str r0,[r2]
 str r1,[r2,#4]
 // Match Pico SDK's four-branch, eight-cycle hardware divider pause.
 b 1f
1: b 1f
1: b 1f
1: b 1f
1: ldr r0,[r2,#16]
 bx lr
2:
#endif
 b __aeabi_uidiv
end mk61_m0_math_udiv32
#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
#include "native_eabi_m0_log70_ratio.inc"
#endif
.ltorg

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

// Normal binary32 square root. Independent midpoint Taylor coefficients
// estimate sqrt(N)*256 to less than four integer units, for N in [2^30,2^32).
// Only the low square word is needed: the exact residual then fits int32_t.
// Comparing it to +/-root selects nearest-even (an integer radicand cannot
// equal the square of a half-integer). No divider, FPU or 64-bit helper calls.
function mk61_m0_sqrtf
 lsrs r1,r0,#23
 subs r2,r1,#1
 cmp r2,#253
 bhi .Lsqrtf_special             // zero, subnormal, negative, Inf or NaN
.Lsqrtf_normal:
 push {r4-r7,lr}
 lsls r2,r0,#8
 lsrs r7,r2,#25                 // exponent parity and six fraction bits
 movs r3,#1
 lsls r3,#31
 orrs r2,r3
 adds r1,#125
 lsrs r1,#1                     // result exponent minus one; C is input parity
 bcs 1f
 lsrs r2,#1                     // normalized radicand N, in Q30
1:
 lsls r1,#23
 mov r12,r1                     // addend includes the implicit result bit
 lsls r0,#15
 eors r0,r3
 asrs r0,#15                    // exact centered segment coordinate t, Q17
 lsls r7,#4
 adr r4,.Lsqrtf_coefficients
 adds r7,r4
 ldmia r7!,{r3-r5}              // c0, c1, c2
 muls r5,r0
 asrs r5,#17
 adds r4,r5
 // Signed (r4*r0)>>17, using three bounded 16-bit partial products.
 uxth r7,r4
 uxth r5,r0
 muls r5,r7
 lsrs r5,#16
 asrs r6,r0,#16
 muls r6,r7
 adds r5,r6
 lsrs r4,#16
 muls r4,r0
 adds r5,r4
 asrs r5,#1
 adds r0,r3,r5                  // integer root estimate, Q23
 uxth r1,r0
 lsrs r3,r0,#16
 muls r3,r1
 lsls r3,#17
 muls r1,r1
 adds r1,r3                    // root^2 modulo 2^32
 lsls r2,#16
 subs r2,r1                    // exact signed radicand-root^2, |r|<2^28
.Lsqrtf_round:
 // -root < residual <= root is exactly the nearest-integer interval.
 subs r1,r0,r2
 lsls r3,r0,#1
 cmp r1,r3
 blo .Lsqrtf_pack
 bmi .Lsqrtf_below
 adds r2,r0
 subs r0,#1
 adds r2,r0
 b .Lsqrtf_round
.Lsqrtf_below:
 subs r2,r0
 adds r0,#1
 subs r2,r0
 b .Lsqrtf_round
.Lsqrtf_pack:
 mov r1,r12
 adds r0,r1
 pop {r4-r7,pc}
.Lsqrtf_special:
 lsls r2,r0,#1
 beq .Lsqrtf_return              // retain both zero signs
 lsrs r2,#24
 cmp r2,#255
 beq .Lsqrtf_nonfinite
 cmp r1,#0
 beq .Lsqrtf_subnormal           // all other rejected finite inputs are negative
.Lsqrtf_negative:
 ldr r0,=0x7fc00000
 bx lr
.Lsqrtf_nonfinite:
 lsls r2,r0,#9
 bne .Lsqrtf_nan
 cmp r0,#0
 bmi .Lsqrtf_negative
.Lsqrtf_return:
 bx lr
.Lsqrtf_nan:
 movs r1,#1
 lsls r1,#22
 orrs r0,r1                     // quiet NaN, retaining its sign and payload
 bx lr
.Lsqrtf_subnormal:
 movs r1,#1
 lsrs r2,r0,#8
 bne 1f
 lsls r0,#16
 subs r1,#16
1:
 lsrs r2,r0,#16
 bne 1f
 lsls r0,#8
 subs r1,#8
1:
 lsrs r2,r0,#20
 bne 1f
 lsls r0,#4
 subs r1,#4
1:
 lsrs r2,r0,#22
 bne 1f
 lsls r0,#2
 subs r1,#2
1:
 lsrs r2,r0,#23
 bne 1f
 lsls r0,#1
 subs r1,#1
1:
 // R1 is the effective biased exponent, possibly negative. Recreate
 // just its parity in the raw word; the normal kernel needs no other bits.
 lsls r0,#9
 lsrs r0,#9
 lsls r2,r1,#31
 lsrs r2,#8
 orrs r0,r2
 b .Lsqrtf_normal
.ltorg
.align 2
.Lsqrtf_coefficients:
#include "native_eabi_m0_sqrt_table.inc"
end mk61_m0_sqrtf

// Centered Q20 coordinate in R2; c0/c1/c2 in R0/R1/R3. Both signed
// partial products fit 32 bits; their separate floors lose <2 seed units.
.macro sqrt64_polynomial
 asrs r4,r2,#4
 muls r3,r4
 asrs r3,#16
 adds r1,r3
 lsls r3,r1,#20
 lsrs r3,#20
 muls r3,r2
 asrs r3,#20
 asrs r1,#12
 muls r1,r2
 asrs r1,#8
 adds r1,r3
 adds r0,r1
.endm

// Exact 32-bit square: R0 is retained, R4:R3 is the result.
.macro sqrt64_square32 scratch
 uxth r2,r0
 lsrs r3,r0,#16
 mov r4,r2
 muls r4,r2
 muls r2,r3
 muls r3,r3
 lsls \scratch,r2,#17
 lsrs r2,#15
 adds r4,\scratch
 adcs r3,r2
.endm

#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
function mk61_m0_sqrt, .m0_sqrt64_fixed
#else
function mk61_m0_sqrt
#endif
 lsrs r3,r1,#20
 adds r2,r3,#1
 lsrs r2,#11
 bne .Lsqrt64_slow
 cmp r3,#0
 bne .Lsqrt64_normal
.Lsqrt64_slow:
#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
 // Handle signed zero in the same8-byte slow slot. R3 remains the
 // original sign:exponent; the nearby leaf receives only nonzero inputs.
 lsls r2,r1,#1
 orrs r2,r0
 bne mk61_m0_sqrt_special
 bx lr
#else
 push {r4,lr}
 bl mk61_m0_sqrt_slow
 pop {r4,pc}
#endif
.Lsqrt64_normal:
 push {r4-r7,lr}
 // N=m*2^62, 1 <= m < 4. Preserve its low/high words and exponent.
 lsrs r6,r3,#1
 bcc 2f
 // The odd biased exponent already supplies the hidden bit.
 lsls r5,r1,#11
 lsrs r5,#1
 lsrs r4,r0,#22
 orrs r5,r4
 lsls r4,r0,#10
 b 1f
2:
 lsls r5,r1,#11
 movs r4,#1
 lsls r4,#31
 orrs r5,r4
 lsrs r4,r0,#21
 orrs r5,r4
 lsls r4,r0,#11
1:
 ldr r6,=1021
 adds r6,r3
 lsrs r6,#1
 lsls r6,#20
 // LR is available throughout this leaf path; keep N.low there.
 mov lr,r4
 // Both polynomials preserve N.high in R5 and the exponent in R6.
 // Parity + eight leading fraction bits select the midpoint.
 lsls r7,r1,#11
 lsrs r7,#23
 lsls r2,r1,#20
 lsrs r3,r0,#12
 orrs r2,r3
 movs r3,#1
 lsls r3,#31
 eors r2,r3
 asrs r2,#11
 adds r2,#1
 asrs r2,#1
 // Four packed words per row. The larger seed bounds still permit
 // one exact correction after Newton; the table occupies only 8 KiB.
 lsls r7,#4
 adr r4,.Lsqrt64_coefficients
 adds r7,r4
 ldmia r7!,{r0,r1}
 asrs r3,r1,#21
 lsls r3,#3
 lsls r1,#11
 lsrs r1,#9
 sqrt64_polynomial
 // A certified one-unit bias in the last cell keeps R within a word.
 mov r12,r0                   // R ~= sqrt(m)*2^31
 ldmia r7!,{r0,r1}
 lsrs r3,r1,#21
 lsls r3,#3
 lsls r1,#11
 asrs r1,#9
 sqrt64_polynomial
 mov r7,r0                    // V ~= 2^31/sqrt(m)
 mov r0,r12
 sqrt64_square32 r1
 mov r0,lr
 mov r2,r5
 subs r0,r4
 sbcs r2,r3
 // The signed residual fits 37 bits. Dropping six low bits contributes
 // less than 63*(2^31+13)/2^42 to the Q52 root error.
 lsrs r0,#6
 lsls r2,#26
 orrs r0,r2
 // The three partial products undershoot the real high product by <3.
 // Adding nine and shifting four places bounds the error below 5/8.
 asrs r4,r0,#16
 uxth r5,r0
 lsrs r3,r7,#16
 uxth r7,r7
 muls r5,r3
 lsrs r5,#16
 muls r7,r4
 asrs r7,#16
 muls r4,r3
 adds r4,r5
 adds r4,r7
 adds r4,#9
 asrs r2,r4,#4
 mov r0,r12
 lsrs r1,r0,#11
 lsls r0,#21
 asrs r3,r2,#31
 adds r0,r2
 adcs r1,r3
 // Certified polynomial errors (<11 root / <13 inverse Q31 units)
 // bound q's error below one unit. A single exact correction suffices.
 // Its signed 106-bit residual fits 64 bits; only the low square is needed.
 sqrt64_square32 r7
 mov r5,r0
 muls r5,r1
 lsls r5,#1
 adds r3,r5
 mov r7,lr
 lsls r7,#10
 movs r5,#0
 subs r5,r4
 sbcs r7,r3                   // R7:R5 = radicand-q*q
 bmi .Lsqrt64_negative_residual
 cmp r7,r1
 blo .Lsqrt64_pack
 bhi .Lsqrt64_increment
 cmp r5,r0
 bls .Lsqrt64_pack
.Lsqrt64_increment:
 movs r2,#0
 adds r0,#1
 adcs r1,r2
 b .Lsqrt64_pack
.Lsqrt64_negative_residual:
 adds r5,r0
 adcs r7,r1
 bmi .Lsqrt64_decrement
 bne .Lsqrt64_pack
 cmp r5,#0
 bne .Lsqrt64_pack
.Lsqrt64_decrement:
 movs r2,#0
 subs r0,#1
 sbcs r1,r2
.Lsqrt64_pack:
 adds r1,r6
 pop {r4-r7,pc}
.ltorg
.align 5
.Lsqrt64_coefficients:
#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
.global pow_sqrt64_coefficients
.hidden pow_sqrt64_coefficients
pow_sqrt64_coefficients:
#endif
#include "native_eabi_m0_sqrt64_table.inc"
end mk61_m0_sqrt
#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
// Thin exact-power dispatch keeps trivial results out of the large frame.
.section .m0_pow_dispatch_extension,"ax",%progbits
.align 2
 .global mk61_m0_pow_fast
 .type mk61_m0_pow_fast,%function
 .thumb_func
mk61_m0_pow_fast:
 cmp r2,#0
 bne .Lpow_dispatch
 // Handle both signed zero exponents before any algebraic special case.
 lsls r2,r3,#1
 beq .Lpow_zero
 ldr r2,=0x3ff00000
 cmp r3,r2
 beq .Lpow_identity
 ldr r2,=0xbff00000
 cmp r3,r2
 beq .Lpow_reciprocal
 ldr r2,=0x3fe00000
 cmp r3,r2
 beq .Lpow_square_root
 ldr r2,=0x40000000
 cmp r3,r2
 beq .Lpow_square
 ldr r2,=0xbfe00000
 cmp r3,r2
 beq .Lpow_inverse_root
 // Low exponent word is zero and every exact case above has failed.
 ldr r2,=mk61_m0_pow_dispatch_ordinary
 mov r12,r2
 movs r2,#0
 bx r12
.Lpow_restore_low:
 movs r2,#0
.Lpow_dispatch:
 b mk61_m0_pow_dispatch
.Lpow_identity:
 lsls r3,r1,#1
 ldr r2,=0xffe00000
 subs r3,r3,r2
 blo .Lpow_identity_return
 orrs r3,r0
 beq .Lpow_identity_return
.Lpow_identity_quiet:
 ldr r2,=0x00080000
 orrs r1,r2
.Lpow_identity_return:
 bx lr
.Lpow_reciprocal:
 ldr r2,=__aeabi_ddiv
 mov r12,r2
 mov r3,r1
 mov r2,r0
 movs r0,#0
 ldr r1,=0x3ff00000
 bx r12
.Lpow_square:
 ldr r2,=mk61_m0_pow_square_exact
 bx r2
.Lpow_square_root:
 cmp r1,#0
 bmi .Lpow_restore_low
 ldr r2,=mk61_m0_sqrt
 bx r2
.Lpow_inverse_root:
 lsrs r2,r1,#20
 cmp r2,#0
 beq .Lpow_restore_low
 ldr r3,=0x7ff
 cmp r2,r3
 bhs .Lpow_restore_negative_half
 ldr r2,=pow_rsqrt
 bx r2
.Lpow_restore_negative_half:
 ldr r3,=0xbfe00000
 b .Lpow_restore_low
.Lpow_zero:
 // pow(x,+/-0)=1 except that signalling NaN x is quieted.
 lsls r2,r1,#1
 ldr r3,=0xffe00000
 subs r2,r2,r3
 blo .Lpow_zero_one
 orrs r2,r0
 beq .Lpow_zero_one
.Lpow_zero_nan:
 lsls r2,r1,#12
 bmi .Lpow_zero_one
 ldr r2,=0x00080000
 orrs r1,r2
 bx lr
.Lpow_zero_one:
 movs r0,#0
 ldr r1,=0x3ff00000
 bx lr
.ltorg
end mk61_m0_pow_fast
#include "native_eabi_m0_pow_square.inc"
#else
// Thin exact-power dispatch keeps trivial results out of the large frame.
.section .m0_pow_dispatch_extension,"ax",%progbits
.align 2
 .global mk61_m0_pow_fast
 .type mk61_m0_pow_fast,%function
 .thumb_func
mk61_m0_pow_fast:
 cmp r2,#0
 bne .Lpow_dispatch
 ldr r2,=0x3ff00000
 cmp r3,r2
 beq .Lpow_identity
 ldr r2,=0xbff00000
 cmp r3,r2
 beq .Lpow_reciprocal
 ldr r2,=0x40000000
 cmp r3,r2
 beq .Lpow_square
 ldr r2,=0x3fe00000
 cmp r3,r2
 beq .Lpow_square_root
 ldr r2,=0xbfe00000
 cmp r3,r2
 beq .Lpow_inverse_root
.Lpow_restore_low:
 movs r2,#0
.Lpow_dispatch:
 b mk61_m0_pow_dispatch
.Lpow_identity:
 lsls r3,r1,#1
 lsrs r3,#1
 ldr r2,=0x7ff00000
 cmp r3,r2
 blo .Lpow_identity_return
 bhi .Lpow_identity_quiet
 cmp r0,#0
 beq .Lpow_identity_return
.Lpow_identity_quiet:
 ldr r2,=0x00080000
 orrs r1,r2
.Lpow_identity_return:
 bx lr
.Lpow_reciprocal:
 ldr r2,=__aeabi_ddiv
 mov r12,r2
 mov r3,r1
 mov r2,r0
 movs r0,#0
 ldr r1,=0x3ff00000
 bx r12
.Lpow_square:
 lsls r2,r1,#1
 lsrs r2,#21
 ldr r3,=484
 cmp r2,r3
 bls .Lpow_square_zero
 ldr r3,=1535
 cmp r2,r3
 blo .Lpow_square_multiply
 ldr r3,=2047
 cmp r2,r3
 blo .Lpow_square_infinity
.Lpow_square_multiply:
 ldr r2,=__aeabi_dmul
 mov r12,r2
 mov r2,r0
 mov r3,r1
 bx r12
.Lpow_square_zero:
 movs r0,#0
 movs r1,#0
 bx lr
.Lpow_square_infinity:
 movs r0,#0
 ldr r1,=0x7ff00000
 bx lr
.Lpow_square_root:
 cmp r1,#0
 bmi .Lpow_restore_low
 ldr r2,=mk61_m0_sqrt
 bx r2
.Lpow_inverse_root:
 lsrs r2,r1,#20
 cmp r2,#0
 beq .Lpow_restore_low
 ldr r3,=0x7ff
 cmp r2,r3
 bhs .Lpow_restore_negative_half
 ldr r2,=pow_rsqrt
 bx r2
.Lpow_restore_negative_half:
 ldr r3,=0xbfe00000
 b .Lpow_restore_low
.ltorg
end mk61_m0_pow_fast
#endif
.section .note.GNU-stack,"",%progbits
#endif

#if defined(MK61_USE_M0_EABI) && MK61_USE_M0_EABI && defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI && (defined(__arm__) || defined(__thumb__))
.global _ZN12compact_math4sqrtEd
.thumb_set _ZN12compact_math4sqrtEd,mk61_m0_sqrt
.global _ZN12compact_math3powEdd
.thumb_set _ZN12compact_math3powEdd,mk61_m0_pow_fast
#endif

#include "native_eabi_m0_pow_argument.inc"

#include "native_eabi_m0_pow_exp_product.inc"
