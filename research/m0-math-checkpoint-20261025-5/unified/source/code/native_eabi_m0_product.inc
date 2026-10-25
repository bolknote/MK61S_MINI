.macro log_math_function name
#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
 .section .m0_log_product_extension,"ax",%progbits
 .global \name
 .type \name,%function
 .thumb_func
\name:
#else
 function \name
#endif
.endm

// Bounded tangent Q62 product: omit the low32 product and pairs 02/20.
// Their total contribution is <12 Q62 units. Add 6 and the guard bit,
// giving error <=6.5 units whenever the unwrapped result fits 64 bits.
// A zero operand returns 6; tangent's interval enclosures include that.
// Ten 16x16 products stay in registers; no compiler spills or helper calls.
// R8..R11 hold a's limbs; R12/LR/R0/R1 hold b's limbs. R5:R6:R7 are
// product words 1..3, R4 is zero, and R2/R3 are the two scratch registers.
.macro product62_pair a,b
 mov r2,\a
 mov r3,\b
 muls r2,r3
.endm
.macro product62_half1
 mov r3,r2
 lsrs r3,#16
 lsls r2,#16
 adds r5,r2
 adcs r6,r3
.endm
.macro product62_word2
 adds r6,r2
 adcs r7,r4
.endm
.macro product62_half2
 mov r3,r2
 lsrs r3,#16
 lsls r2,#16
 adds r6,r2
 adcs r7,r3
.endm

function mk61_m0_product62
 push {r4-r7,lr}
 mov r4,r8
 mov r5,r9
 mov r6,r10
 mov r7,r11
 push {r4-r7}
 uxth r4,r0
 mov r8,r4
 lsrs r0,#16
 mov r9,r0
 uxth r4,r1
 mov r10,r4
 lsrs r1,#16
 mov r11,r1
 uxth r4,r2
 mov r12,r4
 lsrs r2,#16
 mov lr,r2
 uxth r0,r3
 lsrs r1,r3,#16
 movs r4,#0
 movs r7,#0
 // Pairs 00/01/10/11/02/20 are omitted. Initialize the first retained
 // diagonal directly, instead of accumulating it into zero words.
 product62_pair r8,r1
 lsls r5,r2,#16
 lsrs r6,r2,#16
 product62_pair r9,r0
 product62_half1
 product62_pair r10,lr
 product62_half1
 product62_pair r11,r12
 product62_half1
 // All preceding carries leave word 2 below 2^18, so no carry to word 3
 // was needed. The remaining aligned products must propagate that carry.
 product62_pair r9,r1
 product62_word2
 product62_pair r10,r0
 product62_word2
 product62_pair r11,lr
 product62_word2
 product62_pair r10,r1
 product62_half2
 product62_pair r11,r0
 product62_half2
 product62_pair r11,r1
 adds r7,r2
 lsrs r0,r5,#30
 lsls r2,r6,#2
 orrs r0,r2
 lsrs r1,r6,#30
 lsls r3,r7,#2
 orrs r1,r3
 lsls r2,r5,#3                // carry = the discarded bit 61
 movs r2,#6                  // immediate MOVS preserves carry
 adcs r0,r2
 adcs r1,r4
 pop {r4-r7}
 mov r8,r4
 mov r9,r5
 mov r10,r6
 mov r11,r7
 pop {r4-r7,pc}
end mk61_m0_product62

// For a <= 2^48 only three digits from a are needed. At the endpoint,
// the top digit is 0x10000 and each 32-bit MULS still fits exactly.
// Omit pairs 00/01/10:
// their sum is <2^49+2^32. Nine MULS produce bits 32..127, followed by
// half-up rounding. The Q46 entry adds 4: absolute error <4.5+2^-14.
// The Q54 entry has absolute error <17/32+2^-22. Callers require the
// unwrapped quotient to fit uint64 (a <= 2^41 for Q46).
.macro log_product name,shift,bias
log_math_function \name
 push {r4-r7,lr}
 mov r4,r8
 mov r5,r9
 mov r6,r10
 mov r7,r11
 push {r4-r7}
 uxth r4,r0
 mov r8,r4
 lsrs r0,#16
 mov r9,r0
 mov r10,r1
 uxth r4,r2
 mov r11,r4
 lsrs r2,#16
 mov lr,r2
 uxth r0,r3
 lsrs r1,r3,#16
 movs r4,#0
 movs r6,#0
 movs r7,#0
 product62_pair r8,r0
 mov r5,r2
 product62_pair r9,lr
 adds r5,r2
 adcs r6,r4
 product62_pair r10,r11
 adds r5,r2
 adcs r6,r4
 product62_pair r8,r1
 product62_half1
 product62_pair r9,r0
 product62_half1
 product62_pair r10,lr
 product62_half1
 product62_pair r9,r1
 product62_word2
 product62_pair r10,r0
 product62_word2
 product62_pair r10,r1
 product62_half2
 lsrs r0,r5,#(\shift-32)
 lsls r2,r6,#(64-\shift)
 orrs r0,r2
 lsrs r1,r6,#(\shift-32)
 lsls r3,r7,#(64-\shift)
 orrs r1,r3
 lsls r2,r5,#(65-\shift)
 movs r2,#\bias
 adcs r0,r2
 adcs r1,r4
 pop {r4-r7}
 mov r8,r4
 mov r9,r5
 mov r10,r6
 mov r11,r7
 pop {r4-r7,pc}
end \name
.endm
log_product mk61_m0_log_product46,46,4
log_product mk61_m0_log_product54,54,0

// Shared h*z in Q70, h < 2^64 and z < 2^48. With b3=0 only six retained
// limb pairs are nonzero. Omitted products total <12 Q62 units; direct
// half-up Q70 rounding therefore differs from h*z/2^70 by <35/64.
log_math_function mk61_m0_log_cube70
 push {r4-r7,lr}
 mov r4,r8
 mov r5,r9
 mov r6,r10
 push {r4-r6}
 lsrs r4,r0,#16
 mov r8,r4
 uxth r4,r1
 mov r9,r4
 lsrs r1,#16
 mov r10,r1
 uxth r4,r2
 mov r12,r4
 lsrs r2,#16
 mov lr,r2
 uxth r0,r3
 movs r4,#0
 movs r7,#0
 product62_pair r8,r0
 lsls r5,r2,#16
 lsrs r6,r2,#16
 product62_pair r9,lr
 product62_half1
 product62_pair r10,r12
 product62_half1
 product62_pair r9,r0
 product62_word2
 product62_pair r10,lr
 product62_word2
 product62_pair r10,r0
 product62_half2
 lsrs r0,r6,#6
 lsls r2,r7,#26
 orrs r0,r2
 lsrs r1,r7,#6
 lsls r2,r6,#27
 adcs r0,r4
 adcs r1,r4
 pop {r4-r6}
 mov r8,r4
 mov r9,r5
 mov r10,r6
 pop {r4-r7,pc}
end mk61_m0_log_cube70
