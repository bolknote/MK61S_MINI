#if defined(MK61_USE_M0_EABI) && MK61_USE_M0_EABI && defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
.syntax unified
.cpu cortex-m0plus
.thumb
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
.size mk61_m0_pow_fast,.-mk61_m0_pow_fast
#endif
