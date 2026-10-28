.syntax unified
.cpu cortex-m0plus
.thumb
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


.section .m0_sqrt64_fixed.root64,"ax",%progbits
.align 2
.global pow_sqrt64_raw
.type pow_sqrt64_raw,%function
.thumb_func
// A in R1:R0 is normalized Q63; parity in R2 is 0 or1.
// Return sqrt(A/2^63 * 2^parity)*2^63 modulo2^64, error<3.
// Input/return overflow is handled by the interval wrapper.
pow_sqrt64_raw:
 push {r4-r7,lr}
 lsrs r7,r1,#23
 cmp r2,#0
 beq .Lroot64_even
 movs r3,#1
 lsls r3,#8
 eors r7,r3
 mov r4,r0
 mov r5,r1
 b .Lroot64_coordinate
.Lroot64_even:
 lsrs r4,r0,#1
 lsls r5,r1,#31
 orrs r4,r5
 lsrs r5,r1,#1
.Lroot64_coordinate:
 mov lr,r4
 lsrs r2,r0,#23
 lsls r3,r1,#9
 orrs r2,r3
 movs r3,#1
 lsls r3,#31
 eors r2,r3
 asrs r2,#11
 adds r2,#1
 asrs r2,#1
 lsls r7,#4
 ldr r4,=pow_sqrt64_coefficients
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
 mov r6,r0                    // Retain inverse seed through the Q52 step.
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

 // R7:R5 is exact signed residual; R1:R0 is the unrounded Q52 root.
 // Signed floor correction: floor(floor(S/2^38)*floor(V/2^16)/2^19).
 // The product fits signed32, and the same conservative Q63 radius3 applies.
 lsls r1,#11
 lsrs r2,r0,#21
 orrs r1,r2
 lsls r0,#11
 asrs r7,#6
 lsrs r6,#16
 muls r7,r6
 asrs r7,#19
 asrs r2,r7,#31
 adds r0,r7
 adcs r1,r2
 pop {r4-r7,pc}
.ltorg
.size pow_sqrt64_raw,.-pow_sqrt64_raw
