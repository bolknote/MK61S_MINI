// Project-owned pow(x,-1) entry. The numerator is exactly one, so the
// common normal-result bound reduces to1<=E(x)<=2044. Reuse the unchanged
// RNE division kernels after this proof; retain their pending-SIO policy.
.section .m0_pow_dispatch_extension,"ax",%progbits
.align 2
regular_func mk61_m0_pow_reciprocal
 push {r4-r7,lr}
 mov r3,r1
 mov r2,r0
 movs r0,#0
 ldr r1,=0x3ff00000
 lsls r5,r3,#1
 lsrs r5,#21
 ldr r6,=2044
 subs r6,r5
 ldr r7,=2043
 cmp r6,r7
 bhi .Lpow_reciprocal_slow
 cmp r2,#0
 bne .Lpow_reciprocal_general
 lsls r7,r3,#15
 bne .Lpow_reciprocal_general
 lsls r7,r3,#12
 bne .Lpow_reciprocal_small
 ldr r7,=0x3ff00000
 subs r1,r3
 adds r1,r7
 pop {r4-r7,pc}
.Lpow_reciprocal_small:
 ldr r4,=mk61_m0_div_small_kernel
 bx r4
.Lpow_reciprocal_general:
 ldr r7,=0xd0000078
 ldr r7,[r7]
 lsrs r7,#2
 bcs .Lpow_reciprocal_slow
 ldr r4,=mk61_m0_div_general_kernel
 bx r4
.Lpow_reciprocal_slow:
 sub sp,#4
 bl mk61_m0_ddiv_slow
 add sp,#4
 pop {r4-r7,pc}
.ltorg
.size mk61_m0_pow_reciprocal,.-mk61_m0_pow_reciprocal
