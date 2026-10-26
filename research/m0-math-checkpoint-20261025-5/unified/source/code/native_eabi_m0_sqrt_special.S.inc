/* Internal cold-entry contract: R0:R1 are the original binary64 bits,
 * R3=R1>>20 from the unchanged public guard, and the input is nonzero and outside
 * the positive-normal domain. A direct B preserves the caller LR/SP.
 * The positive subnormal scaling/root path below is byte-for-byte source
 * from V161; normal roots and their coefficient table stay in place. */
.section .m0_sqrt_special,"ax",%progbits
.p2align 2
.hidden mk61_m0_sqrt_special
regular_func mk61_m0_sqrt_special
 cmp r3,#0
 beq .Lsqrt_special_subnormal
 cmp r1,#0
 bmi .Lsqrt_special_negative
 // The only positive nonzero inputs admitted here are Inf and NaN.
 lsls r2,r1,#12
 orrs r2,r0
 beq .Lsqrt_special_return
.Lsqrt_special_quiet:
 ldr r2,=0x00080000
 orrs r1,r2
.Lsqrt_special_return:
 bx lr
.Lsqrt_special_negative:
 ldr r2,=0xfff
 cmp r3,r2
 bhs .Lsqrt_special_quiet
 movs r0,#0
 ldr r1,=0x7ff80000
 bx lr
.Lsqrt_special_subnormal:
 push {r4,lr}
 lsrs r2,r1,#19
 bne .Lsqrt_special_width52
 lsrs r2,r1,#18
 bne .Lsqrt_special_width51
 lsrs r2,r1,#17
 bne .Lsqrt_special_width50
 lsrs r2,r1,#16
 bne .Lsqrt_special_width49
 // N<2^52 is exactly representable. The existing optimized integer
 // converter handles smaller magnitudes; BLX avoids a new SRAM veneer.
 ldr r2,=__aeabi_ul2d
 blx r2
 ldr r2,=0x3fc00000
 subs r1,r2
 b .Lsqrt_special_root
.Lsqrt_special_width52:
 adds r0,r0
 adcs r1,r1
 ldr r2,=(53<<20)
 adds r1,r2
 b .Lsqrt_special_root
.macro sqrt_special_width width
.Lsqrt_special_width\width:
 lsrs r3,r0,#(\width-21)
 lsls r1,#(53-\width)
 orrs r1,r3
 lsls r0,#(53-\width)
 ldr r2,=((\width+1)<<20)
 adds r1,r2
 b .Lsqrt_special_root
.endm
 sqrt_special_width 51
 sqrt_special_width 50
 sqrt_special_width 49
.Lsqrt_special_root:
 bl mk61_m0_sqrt
 ldr r2,=(27<<20)
 subs r1,r2
 pop {r4,pc}
 .ltorg
.size mk61_m0_sqrt_special,.-mk61_m0_sqrt_special
