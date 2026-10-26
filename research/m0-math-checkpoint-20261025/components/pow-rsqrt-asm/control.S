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
 // Handle both signed zero exponents before any algebraic special case.
 lsls r2,r3,#1
 beq .Lpow_zero
 ldr r2,=0x3ff00000
 cmp r3,r2
 beq .Lpow_identity
 ldr r2,=0xbff00000
 cmp r3,r2
 beq .Lpow_reciprocal
 ldr r2,=0x3fe00000
 cmp r3,r2
 beq .Lpow_square_root
 ldr r2,=0x40000000
 cmp r3,r2
 beq .Lpow_square
 ldr r2,=0xbfe00000
 cmp r3,r2
 beq .Lpow_inverse_root
 // Low exponent word is zero and every exact case above has failed.
 ldr r2,=mk61_m0_pow_dispatch_ordinary
 mov r12,r2
 movs r2,#0
 bx r12
.Lpow_restore_low:
 movs r2,#0
.Lpow_dispatch:
 b mk61_m0_pow_dispatch
.Lpow_identity:
 lsls r3,r1,#1
 ldr r2,=0xffe00000
 subs r3,r3,r2
 blo .Lpow_identity_return
 orrs r3,r0
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
 ldr r2,=mk61_m0_pow_square_exact
 bx r2
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
.Lpow_zero:
 // pow(x,+/-0)=1 except that signalling NaN x is quieted.
 lsls r2,r1,#1
 ldr r3,=0xffe00000
 subs r2,r2,r3
 blo .Lpow_zero_one
 orrs r2,r0
 beq .Lpow_zero_one
.Lpow_zero_nan:
 lsls r2,r1,#12
 bmi .Lpow_zero_one
 ldr r2,=0x00080000
 orrs r1,r2
 bx lr
.Lpow_zero_one:
 movs r0,#0
 ldr r1,=0x3ff00000
 bx lr
.ltorg
.size mk61_m0_pow_fast,.-mk61_m0_pow_fast
#endif
