// Extracted seed-only control from native_eabi_m0.S, preserving its exact
// midpoint coordinate, packed coefficients and polynomial instruction body.
.syntax unified
.cpu cortex-m0plus
.thumb
.macro polynomial
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
.section .text.current_sqrt_seeds,"ax",%progbits
.global current_sqrt_seeds
.type current_sqrt_seeds,%function
.thumb_func
current_sqrt_seeds:
 push {r4-r7,lr}
 lsrs r7,r1,#12
 lsls r2,#8
 eors r7,r2
 lsls r2,r1,#20
 lsrs r3,r0,#12
 orrs r2,r3
 movs r3,#1
 lsls r3,#31
 eors r2,r3
 asrs r2,#11
 adds r2,#1
 asrs r2,#1
 lsls r7,#4
 adr r4,.Lcoefficients
 adds r7,r4
 ldmia r7!,{r0,r1}
 asrs r3,r1,#21
 lsls r3,#3
 lsls r1,#11
 lsrs r1,#9
 polynomial
 mov r12,r0
 ldmia r7!,{r0,r1}
 lsrs r3,r1,#21
 lsls r3,#3
 lsls r1,#11
 asrs r1,#9
 polynomial
 mov r1,r0
 mov r0,r12
 pop {r4-r7,pc}
.size current_sqrt_seeds,.-current_sqrt_seeds
.align 2
.Lcoefficients:
#include "baseline_sqrt_table.inc"
