#if defined(MK61_USE_M0_EABI) && MK61_USE_M0_EABI && defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
.syntax unified
.cpu cortex-m0plus
.thumb
// Full106-bit significand square. All discarded bits reach the RNE test.
// Inputs below exponent485 square to zero; exponents1535..2046 overflow.
// No new tables or floating arithmetic are used.
.section .m0_pow_square_exact_only,"ax",%progbits
.align 2
.global mk61_m0_pow_square_exact
.hidden mk61_m0_pow_square_exact
.type mk61_m0_pow_square_exact,%function
.thumb_func
mk61_m0_pow_square_exact:
 lsls r2,r1,#1
 lsrs r2,#21
 ldr r3,=485
 cmp r2,r3
 bhs .Lsquare_nonzero
 movs r0,#0
 movs r1,#0
 bx lr
.Lsquare_nonzero:
 ldr r3,=1535
 cmp r2,r3
 blo .Lsquare_finite
 b .Lsquare_large
.Lsquare_finite:
 push {r4-r7,lr}
 // H=(1<<20)|fraction_high; B=2*input_exponent-1023.
 lsrs r4,r1,#20
 subs r4,#1
 lsls r4,#20
 subs r1,r4
 lsls r3,r2,#1
 ldr r2,=1023
 subs r3,r3,r2
 push {r0,r1,r3}
 // L^2 into r12:r5 (low word first), using three16x16 products.
 uxth r2,r0
 muls r2,r2
 uxth r3,r0
 lsrs r4,r0,#16
 muls r3,r4
 muls r4,r4
 lsls r5,r3,#17
 lsrs r6,r3,#15
 adds r5,r2
 adcs r6,r4
 mov r12,r5
 mov r5,r6
 // H^2 into r6:r7; H<2^21.
 uxth r2,r1
 muls r2,r2
 uxth r3,r1
 lsrs r4,r1,#16
 muls r3,r4
 muls r4,r4
 lsls r6,r3,#17
 lsrs r7,r3,#15
 adds r6,r2
 adcs r7,r4
 // L*H into r0:r1. Keep the possible carry of the16-bit cross sum.
 uxth r2,r0
 uxth r3,r1
 muls r2,r3
 lsrs r4,r0,#16
 muls r3,r4
 lsrs r1,#16
 muls r4,r1
 uxth r0,r0
 muls r0,r1
 adds r3,r0
 bcc .Lsquare_cross_fits
 movs r0,#1
 lsls r0,#16
 adds r4,r0
.Lsquare_cross_fits:
 lsls r0,r3,#16
 lsrs r1,r3,#16
 adds r0,r2
 adcs r1,r4
 // Add2*(L*H)<<32 to L^2+(H^2<<64).
 lsls r0,#1
 adcs r1,r1
 adds r5,r0
 adcs r6,r1
 movs r0,#0
 adcs r7,r0
 add sp,#8
 pop {r3}
 // Full product is r7:r6:r5:r12. Normalize only the rounding grid.
 lsrs r2,r7,#9
 adds r3,r3,r2
 cmp r3,#0
 ble .Lsquare_subnormal
 movs r4,#52
 adds r4,r4,r2
 subs r3,#1
 lsls r3,#20
 b .Lsquare_choose_word
.Lsquare_subnormal:
 movs r4,#53
 subs r4,r4,r3
 adds r4,r4,r2
 movs r3,#0
.Lsquare_choose_word:
 cmp r4,#64
 bhi .Lsquare_shift_above64
 // Drop s in[52,64]. Remainder word is r5; lower sticky is r12.
 subs r4,#32
 movs r2,#32
 subs r2,r2,r4
 mov r0,r5
 lsrs r0,r4
 mov r1,r6
 lsls r1,r2
 orrs r0,r1
 mov r1,r6
 lsrs r1,r4
 lsls r7,r7,r2
 orrs r1,r7
 lsls r5,r5,r2
 mov r6,r12
 b .Lsquare_round
.Lsquare_shift_above64:
 cmp r4,#96
 bhi .Lsquare_shift_above96
 // Drop s in[65,96]. Remainder word is r6; lower sticky is r5|r12.
 subs r4,#64
 movs r2,#32
 subs r2,r2,r4
 mov r0,r6
 lsrs r0,r4
 mov r1,r7
 lsrs r1,r4
 lsls r7,r7,r2
 orrs r0,r7
 mov r7,r12
 orrs r7,r5
 mov r5,r6
 lsls r5,r2
 mov r6,r7
 b .Lsquare_round
.Lsquare_shift_above96:
 // Drop s in[97,106]. Remainder word is r7; lower96bits are sticky.
 subs r4,#96
 movs r2,#32
 subs r2,r2,r4
 mov r0,r7
 lsrs r0,r4
 movs r1,#0
 orrs r6,r5
 mov r5,r12
 orrs r6,r5
 mov r5,r7
 lsls r5,r2
.Lsquare_round:
 lsls r5,#1
 bcc .Lsquare_pack
 orrs r5,r6
 bne .Lsquare_increment
 movs r2,#1
 tst r0,r2
 beq .Lsquare_pack
.Lsquare_increment:
 adds r0,#1
 movs r2,#0
 adcs r1,r2
.Lsquare_pack:
 adds r1,r3
 pop {r4-r7,pc}
.Lsquare_large:
 ldr r3,=2047
 cmp r2,r3
 bne .Lsquare_infinity
 lsls r2,r1,#12
 orrs r2,r0
 beq .Lsquare_infinity
 ldr r2,=0x00080000
 orrs r1,r2
 bx lr
.Lsquare_infinity:
 movs r0,#0
 ldr r1,=0x7ff00000
 bx lr
.ltorg
.size mk61_m0_pow_square_exact,.-mk61_m0_pow_square_exact
#endif
