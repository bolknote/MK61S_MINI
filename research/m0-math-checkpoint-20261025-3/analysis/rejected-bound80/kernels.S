#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
.syntax unified
.cpu cortex-m0plus
.thumb
.section .m0_pow_bound80_wide32,"ax",%progbits
.p2align 1
.global mk61_m0_bound80_wide32
.type mk61_m0_bound80_wide32,%function
.thumb_func
mk61_m0_bound80_wide32:
 push {r4-r6,lr}
 uxth r4,r0
 lsrs r6,r0,#16
 uxth r2,r1
 lsrs r5,r1,#16
 mov r0,r4
 muls r0,r2
 muls r2,r6
 lsrs r3,r0,#16
 adds r2,r3
 muls r4,r5
 uxth r3,r2
 adds r4,r3
 muls r5,r6
 lsrs r2,#16
 adds r5,r2
 lsrs r1,r4,#16
 adds r1,r5
 lsls r4,#16
 uxth r0,r0
 orrs r0,r4
 pop {r4-r6,pc}
.size mk61_m0_bound80_wide32,.-mk61_m0_bound80_wide32

// B80: H.low32@0,H.high32@4,L.low16@8,exponent32@12,radius32@16.
// T <= A*A/2^80 < T+8; +16 also encloses propagated input radius.
.section .m0_pow_bound80_square,"ax",%progbits
.p2align 1
.global mk61_m0_bound80_square
.type mk61_m0_bound80_square,%function
.thumb_func
mk61_m0_bound80_square:
 push {r4-r7,lr}
 sub sp,#12
 mov r7,r0
 ldr r0,[r7,#4]
 // Exact U^2; each partial fits32 bits.
 uxth r2,r0
 lsrs r3,r0,#16
 mov r4,r2
 muls r4,r2
 muls r2,r3
 muls r3,r3
 lsls r1,r2,#17
 lsrs r2,#15
 adds r4,r1
 adcs r3,r2
 // T80 = U^2<<16.
 lsrs r2,r3,#16
 lsls r3,#16
 lsrs r1,r4,#16
 orrs r3,r1
 lsls r4,#16
 str r4,[sp,#0]
 str r3,[sp,#4]
 str r2,[sp,#8]
 // Exact U*V in R1:R0.
 ldr r6,[r7,#0]
 ldr r5,[r7,#4]
 uxth r4,r6
 lsrs r6,#16
 uxth r2,r5
 lsrs r5,#16
 mov r0,r4
 muls r0,r2
 muls r2,r6
 lsrs r3,r0,#16
 adds r2,r3
 muls r4,r5
 uxth r3,r2
 adds r4,r3
 muls r5,r6
 lsrs r2,#16
 adds r5,r2
 lsrs r1,r4,#16
 adds r1,r5
 lsls r4,#16
 uxth r0,r0
 orrs r0,r4
 // Add floor(U*V/2^15).
 lsls r2,r1,#17
 lsrs r0,#15
 orrs r0,r2
 lsrs r1,#15
 ldr r2,[sp,#0]
 ldr r3,[sp,#4]
 ldr r4,[sp,#8]
 movs r5,#0
 adds r2,r0
 adcs r3,r1
 adcs r4,r5
 // Add floor((V>>16)^2/2^16).
 ldrh r0,[r7,#2]
 muls r0,r0
 lsrs r0,#16
 adds r2,r0
 adcs r3,r5
 adcs r4,r5
 // Add 2*floor((H>>48)*L/2^16).
 ldrh r0,[r7,#6]
 ldrh r1,[r7,#8]
 muls r0,r1
 lsrs r0,#16
 lsls r0,#1
 adds r2,r0
 adcs r3,r5
 adcs r4,r5
 ldr r1,[r7,#16]
 lsls r1,#1
 adds r1,#16
 ldr r0,[r7,#12]
 lsls r0,#1
 lsls r5,r4,#16
 bmi .Lb80_square_upper
 lsls r2,#1
 adcs r3,r3
 adcs r4,r4
 lsls r1,#1
 b .Lb80_square_store
.Lb80_square_upper:
 adds r0,#1
.Lb80_square_store:
 str r0,[r7,#12]
 str r1,[r7,#16]
 uxth r5,r2
 str r5,[r7,#8]
 lsls r4,#16
 lsrs r5,r3,#16
 orrs r4,r5
 str r4,[r7,#4]
 lsls r3,#16
 lsrs r2,#16
 orrs r3,r2
 str r3,[r7,#0]
 add sp,#12
 pop {r4-r7,pc}
.size mk61_m0_bound80_square,.-mk61_m0_bound80_square
#endif
