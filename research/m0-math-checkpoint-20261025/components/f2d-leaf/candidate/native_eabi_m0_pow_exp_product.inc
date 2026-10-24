#if defined(MK61_USE_M0_EABI) && MK61_USE_M0_EABI && defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
// Rounded high64 of a63*b54 after omitting the three lowest16-bit
// products. The omitted integer is<2^49; absolute error<=1/2+2^-15.
// Cache a3/b3 and round column3 before the discarded accumulator is reused.
// The RAM address and Flash-to-RAM transition are unchanged in this fixture.
.syntax unified
.cpu cortex-m0plus
.thumb
.section .scratch_y.m0_pow_hot,"ax",%progbits
.align 2
.global mk61_m0_pow_exp_product
.type mk61_m0_pow_exp_product,%function
.thumb_func
mk61_m0_pow_exp_product:
 push {r4-r7,lr}
 sub sp,#20
 str r0,[sp,#0]
 str r1,[sp,#4]
 str r2,[sp,#8]
 str r3,[sp,#12]
 lsrs r2,r1,#16
 lsrs r7,r3,#16
 mov r3,sp
 movs r6,#0
 // Column2 starts at bit32 of the full product.
 ldrh r0,[r3,#0]
 ldrh r1,[r3,#12]
 muls r0,r1
 mov r4,r0
 movs r5,#0
 ldrh r0,[r3,#2]
 ldrh r1,[r3,#10]
 muls r0,r1
 adds r4,r0
 adcs r5,r6
 ldrh r0,[r3,#4]
 ldrh r1,[r3,#8]
 muls r0,r1
 adds r4,r0
 adcs r5,r6
 // Column3; its upper accumulator stays below2^18.
 ldrh r0,[r3,#0]
 muls r0,r7
 lsrs r1,r0,#16
 lsls r0,#16
 adds r4,r0
 adcs r5,r1
 ldrh r0,[r3,#2]
 ldrh r1,[r3,#12]
 muls r0,r1
 lsrs r1,r0,#16
 lsls r0,#16
 adds r4,r0
 adcs r5,r1
 ldrh r0,[r3,#4]
 ldrh r1,[r3,#10]
 muls r0,r1
 lsrs r1,r0,#16
 lsls r0,#16
 adds r4,r0
 adcs r5,r1
 ldrh r0,[r3,#8]
 muls r0,r2
 lsrs r1,r0,#16
 lsls r0,#16
 adds r4,r0
 adcs r5,r1
 // Bit63 is final after column3. Rounded r5 remains<2^18.
 lsls r4,#1
 adcs r5,r6
 // Column4. First product<2^22, so its sum cannot overflow.
 ldrh r0,[r3,#2]
 muls r0,r7
 adds r5,r0
 movs r4,#0
 ldrh r0,[r3,#4]
 ldrh r1,[r3,#12]
 muls r0,r1
 adds r5,r0
 adcs r6,r4
 ldrh r0,[r3,#10]
 muls r0,r2
 adds r5,r0
 adcs r6,r4
 // Column5; upper accumulator stays below2^16.
 ldrh r0,[r3,#4]
 muls r0,r7
 lsrs r1,r0,#16
 lsls r0,#16
 adds r5,r0
 adcs r6,r1
 ldrh r0,[r3,#12]
 muls r0,r2
 lsrs r1,r0,#16
 lsls r0,#16
 adds r5,r0
 adcs r6,r1
 // Column6; the complete result is<2^53.
 muls r2,r7
 adds r6,r2
 mov r0,r5
 mov r1,r6
 add sp,#20
 pop {r4-r7,pc}
.size mk61_m0_pow_exp_product,.-mk61_m0_pow_exp_product
#endif
