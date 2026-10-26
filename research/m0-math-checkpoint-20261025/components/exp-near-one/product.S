#if defined(MK61_USE_M0_EABI) && MK61_USE_M0_EABI && defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
// Rounded high64 of a63*b54 after omitting the three lowest16-bit
// products. The omitted integer is<2^49; absolute error<=1/2+2^-15.
// Cache a3/b3 and round column3 before the discarded accumulator is reused.
// The RAM address and Flash-to-RAM transition are unchanged in this fixture.
.syntax unified
.cpu cortex-m0plus
.thumb
.section .scratch_y.m0_exp_product_only,"ax",%progbits
.align 2
.global mk61_m0_pow_exp_product
.type mk61_m0_pow_exp_product,%function
.thumb_func
mk61_m0_pow_exp_product:
 // Save arguments and callee-saved registers in one instruction.
 push {r0-r7,lr}
 lsrs r2,r1,#16
 lsrs r7,r3,#16
 mov r3,sp
 movs r1,#0
 // Column2 starts at bit32 of the full product.
 ldrh r4,[r3,#0]
 ldrh r6,[r3,#12]
 muls r4,r6
 movs r0,#0
 ldrh r5,[r3,#2]
 ldrh r6,[r3,#10]
 muls r5,r6
 adds r4,r5
 adcs r0,r1
 ldrh r5,[r3,#4]
 ldrh r6,[r3,#8]
 muls r5,r6
 adds r4,r5
 adcs r0,r1
 // Column3; its upper accumulator stays below2^18.
 ldrh r5,[r3,#0]
 muls r5,r7
 lsrs r6,r5,#16
 lsls r5,#16
 adds r4,r5
 adcs r0,r6
 ldrh r5,[r3,#2]
 ldrh r6,[r3,#12]
 muls r5,r6
 lsrs r6,r5,#16
 lsls r5,#16
 adds r4,r5
 adcs r0,r6
 ldrh r5,[r3,#4]
 ldrh r6,[r3,#10]
 muls r5,r6
 lsrs r6,r5,#16
 lsls r5,#16
 adds r4,r5
 adcs r0,r6
 ldrh r5,[r3,#8]
 muls r5,r2
 lsrs r6,r5,#16
 lsls r5,#16
 adds r4,r5
 adcs r0,r6
 // Bit63 is final after column3. Rounded r0 remains<2^18.
 mov r12,r4
 lsls r4,#1
 adcs r0,r1
 // Column4. First product<2^22, so its sum cannot overflow.
 ldrh r5,[r3,#2]
 muls r5,r7
 adds r0,r5
 movs r4,#0
 ldrh r5,[r3,#4]
 ldrh r6,[r3,#12]
 muls r5,r6
 adds r0,r5
 adcs r1,r4
 ldrh r5,[r3,#10]
 muls r5,r2
 adds r0,r5
 adcs r1,r4
 // Column5; upper accumulator stays below2^16.
 ldrh r5,[r3,#4]
 muls r5,r7
 lsrs r6,r5,#16
 lsls r5,#16
 adds r0,r5
 adcs r1,r6
 ldrh r5,[r3,#12]
 muls r5,r2
 lsrs r6,r5,#16
 lsls r5,#16
 adds r0,r5
 adcs r1,r6
 // Column6; the complete result is<2^53.
 muls r2,r7
 adds r1,r2
 add sp,#16
 pop {r4-r7,pc}
.size mk61_m0_pow_exp_product,.-mk61_m0_pow_exp_product
 // Preserve the established168-byte RAM slot and all following symbols.
 // These fourteen padding bytes are outside the function and never executed.
 .hword 0xbf00,0xbf00,0xbf00,0xbf00,0xbf00,0xbf00,0xbf00
#endif
