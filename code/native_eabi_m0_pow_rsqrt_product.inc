// Project-owned Thumb-1 evaluation of the existing inverse-root Newton
// expression. All 32x32 products are exact; only the same two low product
// terms as in exp_high_product are omitted. Bit0 tags the enclosure:
// zero means |q-exact|<6, one retains the existing24-unit enclosure.
// Replacing this low bit changes q by at most one unit.
.section .m0_pow_dispatch_extension,"ax",%progbits
.align 2
// The same centered, cubic-corrected Q32 seed as the portable path.
// M is the normalized 53-bit significand; R2 is exponent parity, R3
// points to the existing 512-entry seed table. SIO ownership stays in
// mk61_m0_math_udiv32, including its DIRTY/pending fallback.
regular_func mk61_m0_pow_rsqrt_approx
 push {r4-r7,lr}
 push {r0-r3,r7}              // M, parity, table, padding; align SP for SIO
 lsls r6,r1,#12
 lsrs r6,#24                 // fraction index
 lsls r4,r6,#1
 ldr r3,=513
 adds r4,r3                  // center
 lsls r2,#8
 orrs r6,r2                  // parity*256+index
 lsls r3,r4,#11              // center's high word
 cmp r1,r3
 blo .Lpow_rsqrt_seed_below
 movs r5,#0
 subs r0,#1
 sbcs r1,r3                  // M-center-1
 bcc .Lpow_rsqrt_seed_center // M==center
 b .Lpow_rsqrt_seed_distance
.Lpow_rsqrt_seed_below:
 movs r5,#1
 mvns r0,r0
 subs r1,r3,r1
 subs r1,#1                  // center-M-1
.Lpow_rsqrt_seed_distance:
 lsls r1,#21
 lsrs r0,#11
 orrs r0,r1
 beq .Lpow_rsqrt_seed_center
 mov r1,r4
 bl mk61_m0_math_udiv32
 // T<2^23. Its square and all cubic intermediates fit their stated
 // words; retain the exact high square, including the low-word carry.
 square32_64 r0,r1,r2,r3,r2,r4
 mov r3,r2
 lsls r3,#1
 adds r3,r2
 adds r3,#4
 lsrs r3,#3                  // quadratic
 lsrs r1,r0,#16
 muls r1,r2
 lsrs r1,#16                 // cube
 lsls r2,r1,#2
 adds r2,r1
 adds r2,#8
 lsrs r2,#4                  // cubic
 lsls r2,#1
 adds r0,r2
 lsls r3,#1
 cmp r5,#0
 beq .Lpow_rsqrt_seed_above_delta
 adds r0,r3
 b .Lpow_rsqrt_seed_correct
.Lpow_rsqrt_seed_above_delta:
 subs r0,r3
.Lpow_rsqrt_seed_correct:
 lsls r6,#2
 ldr r1,[sp,#12]
 ldr r6,[r1,r6]
 mov r1,r6
 mul32_32_64 r0,r1,r0,r1,r2,r3,r4,r0,r1
 adds r1,#1
 lsrs r1,#1                  // (base*magnitude+2^32)>>33
 cmp r5,#0
 beq .Lpow_rsqrt_seed_subtract
 adds r0,r6,r1
 bcc .Lpow_rsqrt_seed_return
 movs r0,#0
 mvns r0,r0
 b .Lpow_rsqrt_seed_return
.Lpow_rsqrt_seed_subtract:
 subs r0,r6,r1
 b .Lpow_rsqrt_seed_return
.Lpow_rsqrt_seed_center:
 lsls r6,#2
 ldr r0,[sp,#12]
 ldr r0,[r0,r6]
.Lpow_rsqrt_seed_return:
 mov r7,r0                    // seed
 ldr r0,[sp]
 ldr r1,[sp,#4]
 ldr r2,[sp,#8]
 lsls r1,#10
 lsrs r3,r0,#22
 orrs r1,r3
 lsls r0,#10
 lsrs r2,#1
 bcc .Lpow_rsqrt_argument
 adds r0,r0
 adcs r1,r1                  // argument = M<<(10+parity)
.Lpow_rsqrt_argument:
 add sp,#12                   // replace dead saved arguments by A.low/high
 str r0,[sp]
 str r1,[sp,#4]
 square32_64 r7,r4,r3,r0,r1,r2
 push {r3,r4}                 // square high/low
 // P = AH*SH + high32(AL*SH) + high32(AH*SL).
 ldr r0,[sp,#8]
 mov r1,r3
 mul32_32_64 r0,r1,r5,r6,r2,r3,r4,r5,r6
 push {r6}
 ldr r0,[sp,#16]
 ldr r1,[sp,#8]
 mul32_32_64 r0,r1,r5,r6,r2,r3,r4,r5,r6
 push {r6}
 ldr r0,[sp,#20]
 ldr r1,[sp,#8]
 mul32_32_64 r0,r1,r0,r1,r2,r3,r4,r0,r1
 pop {r5,r6}
 movs r2,#0
 adds r0,r5
 adcs r1,r2
 adds r0,r6
 adcs r1,r2
 mov lr,r1                    // high32(P), for the a-posteriori enclosure
 // F = 3*2^62-P; q = FH*seed + high32(FL*seed).
 rsbs r0,r0,#0
 ldr r2,=0xc0000000
 sbcs r2,r1
 mov r12,r2
 mov r1,r7
 mul32_32_64 r0,r1,r5,r6,r2,r3,r4,r5,r6
 push {r6}
 mov r0,r12
 mov r1,r7
 mul32_32_64 r0,r1,r0,r1,r2,r3,r4,r0,r1
 pop {r2}
 adds r0,r2
 movs r2,#0
 adcs r1,r2
 // The certified seed bounds put high32(P) within5 of2^30. Only
 // 0x3fffffff/0x40000000 satisfy this test, hence |P-2^62|<=2^32.
 // The exact product differs by<3. This gives a six-unit q enclosure
 // including final truncation and replacement of the low tag bit.
 lsrs r0,#1
 mov r2,lr
 adds r2,#1
 lsls r2,#2
 cmp r2,#8
 adcs r0,r0                   // carry0 = tight, carry1 = ordinary enclosure
 add sp,#16
 pop {r4-r7,pc}
.ltorg
.size mk61_m0_pow_rsqrt_approx,.-mk61_m0_pow_rsqrt_approx
