// ARMv6-M primitives, with the base AAPCS calling convention.
#if defined(MK61_USE_M0_EABI) && MK61_USE_M0_EABI
.syntax unified
.cpu cortex-m0plus
.thumb
.macro function name, group=.text
 .section \group\().\name,"ax",%progbits
 .global \name
 .type \name,%function
 .thumb_func
\name:
.endm
.macro end name
 .size \name, .-\name
.endm

// Every int32/uint32 is exactly representable in binary64. Normalize the
// unsigned magnitude in chunks, then split its 32 bits between R1 and R0.
function __aeabi_i2d
 movs r1,#0
 cmp r0,#0
 beq .Li2d_return
 bpl .Li2d_normalize
 movs r1,#1
 lsls r1,#31
 rsbs r0,r0,#0
 b .Li2d_normalize
.global __aeabi_ui2d
.type __aeabi_ui2d,%function
.thumb_func
__aeabi_ui2d:
 movs r1,#0
 cmp r0,#0
 beq .Li2d_return
.Li2d_normalize:
 ldr r2,=1053
 lsrs r3,r0,#16
 bne 1f
 lsls r0,#16
 subs r2,#16
1:
 lsrs r3,r0,#24
 bne 1f
 // The 19..21-bit band is already close to the binary64 high word.
 // Pack it directly, including after the preceding 16-bit shift.
 lsrs r3,r0,#20
 cmp r3,#1
 beq .Li2d_exact21
 cmp r3,#0
 bne .Li2d_byte
 lsrs r3,r0,#19
 bne .Li2d_exact20
 lsrs r3,r0,#18
 bne .Li2d_exact19
.Li2d_byte:
 lsls r0,#8
 subs r2,#8
1:
 lsrs r3,r0,#28
 bne 1f
 lsls r0,#4
 subs r2,#4
1:
 lsrs r3,r0,#30
 bne 1f
 lsls r0,#2
 subs r2,#2
1:
 cmp r0,#0
 bmi 1f
 lsls r0,#1
 subs r2,#1
1:
 lsrs r3,r0,#11
 orrs r1,r3
 lsls r2,#20
 adds r1,r2
 lsls r0,#21
.Li2d_return:
 bx lr
.size __aeabi_ui2d,.-__aeabi_ui2d
.ltorg
end __aeabi_i2d

.macro i2d_middle width
.Li2d_exact\width:
 .if \width < 21
 lsls r0,#(21-\width)
 .endif
 adds r1,r0
 movs r0,#0
 subs r2,#(32-\width)
 lsls r2,#20
 adds r1,r2
 bx lr
.endm
i2d_middle 21
i2d_middle 20
i2d_middle 19

// Project-owned Thumb-1 EABI conversions and IEEE comparisons.
// Keep both integer widths in one section: small int64 magnitudes enter
// the existing exact int32 normalizer without an extra call or stack frame.
.section .text.__aeabi_i2d,"ax",%progbits
#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
.global __aeabi_l2d
.type __aeabi_l2d,%function
.thumb_func
__aeabi_l2d:
 // The high word determines the sign. Preserve positive-entry cost and
 // form the negative sign in two instructions instead of four.
 asrs r2,r1,#31
 lsls r2,#31
 bpl .Ll2d_magnitude
 // A complemented high word of zero covers -2^32..-1. Except -2^32,
 // its magnitude fits R0 and is known nonzero: skip high-word ADC and
 // the narrow path's redundant zero test.
 mvns r1,r1
 beq .Ll2d_small_negative
 rsbs r0,r0,#0
 movs r3,#0
 adcs r1,r3
 b .Ll2d_high
.Ll2d_small_negative:
 rsbs r0,r0,#0
 beq .Ll2d_negative_u32_boundary
 mov r1,r2
 b .Li2d_normalize
.Ll2d_negative_u32_boundary:
 movs r1,#1
 b .Ll2d_high
#else
.global __aeabi_l2d
.type __aeabi_l2d,%function
.thumb_func
__aeabi_l2d:
 movs r2,#0
 cmp r1,#0
 bpl .Ll2d_magnitude
 movs r2,#1
 lsls r2,#31
 rsbs r0,r0,#0
 mvns r1,r1
 movs r3,#0
 adcs r1,r3
 bne .Ll2d_high
 b .Ll2d_narrow
#endif
.global __aeabi_ul2d
.type __aeabi_ul2d,%function
.thumb_func
__aeabi_ul2d:
 movs r2,#0
.Ll2d_magnitude:
 cmp r1,#0
 bne .Ll2d_high
.Ll2d_narrow:
 mov r1,r2
 cmp r0,#0
 bne .Li2d_normalize
 bx lr
.Ll2d_high:
 // The input's top bit directly selects the shift into a 53-bit
 // significand. Exact 47..53-bit magnitudes never need rounding.
 lsrs r3,r1,#21
 bne .Ll2d_wide
 lsrs r3,r1,#14
 beq .Ll2d_low_high
 lsrs r3,r1,#20
 bne .Ll2d_exact_53
 lsrs r3,r1,#19
 bne .Ll2d_exact_52
 lsrs r3,r1,#18
 bne .Ll2d_exact_51
 lsrs r3,r1,#17
 bne .Ll2d_exact_50
 lsrs r3,r1,#16
 bne .Ll2d_exact_49
 lsrs r3,r1,#15
 bne .Ll2d_exact_48
 b .Ll2d_exact_47
.Ll2d_low_high:
 // The high word has at most 14 bits: the first 16-bit shift is known.
 mov r12,r2
 ldr r2,=1069
 lsls r1,#16
 lsrs r3,r0,#16
 orrs r1,r3
 lsls r0,#16
.macro l2d_chunk shift
 lsrs r3,r1,#(32-\shift)
 bne 1f
 lsls r1,#\shift
 lsrs r3,r0,#(32-\shift)
 orrs r1,r3
 lsls r0,#\shift
 subs r2,#\shift
1:
.endm
 l2d_chunk 8
 l2d_chunk 4
 l2d_chunk 2
 cmp r1,#0
 bmi .Ll2d_low_pack
 adds r0,r0
 adcs r1,r1
 subs r2,#1
.Ll2d_low_pack:
 // This branch is exact: all discarded bits are zero.
 mov r3,r1
 lsls r3,#21
 lsrs r0,#11
 orrs r0,r3
 lsrs r1,#11
 lsls r2,#20
 adds r1,r2
 mov r2,r12
 orrs r1,r2
 bx lr
.macro l2d_exact width
.Ll2d_exact_\width:
 .if \width == 52
 adds r0,r0
 adcs r1,r1
 .elseif \width < 52
 lsrs r3,r0,#(\width-21)
 lsls r1,#(53-\width)
 orrs r1,r3
 lsls r0,#(53-\width)
 .endif
 ldr r3,=((1021+\width)<<20)
 adds r1,r3
 orrs r1,r2
 bx lr
.endm
 l2d_exact 53
 l2d_exact 52
 l2d_exact 51
 l2d_exact 50
 l2d_exact 49
 l2d_exact 48
 l2d_exact 47
.macro l2d_right shift
.Ll2d_right_\shift:
 lsrs r3,r0,#(\shift+1)
 ldr r3,=((1<<(\shift-1))-1)
 adcs r0,r3
 movs r3,#0
 adcs r1,r3
 .if \shift == 11
 bcs .Ll2d_overflow
 .endif
 mov r3,r1
 lsls r3,#(32-\shift)
 lsrs r0,#\shift
 orrs r0,r3
 lsrs r1,#\shift
 ldr r3,=((1074+\shift)<<20)
 adds r1,r3
 orrs r1,r2
 bx lr
.endm
.Ll2d_wide:
 cmp r1,#0
 bpl .Ll2d_try_10
 l2d_right 11
.Ll2d_overflow:
 movs r0,#0
 ldr r1,=0x43f00000
 orrs r1,r2
 bx lr
.Ll2d_try_10:
 lsrs r3,r1,#30
 beq .Ll2d_try_9
 l2d_right 10
.Ll2d_try_9:
 lsrs r3,r1,#29
 beq .Ll2d_try_8
 l2d_right 9
.Ll2d_try_8:
 lsrs r3,r1,#28
 beq .Ll2d_try_7
 l2d_right 8
.Ll2d_try_7:
 lsrs r3,r1,#27
 beq .Ll2d_try_6
 l2d_right 7
.Ll2d_try_6:
 lsrs r3,r1,#26
 beq .Ll2d_try_5
 l2d_right 6
.Ll2d_try_5:
 lsrs r3,r1,#25
 beq .Ll2d_try_4
 l2d_right 5
.Ll2d_try_4:
 lsrs r3,r1,#24
 beq .Ll2d_try_3
 l2d_right 4
.Ll2d_try_3:
 lsrs r3,r1,#23
 beq .Ll2d_try_2
 l2d_right 3
.Ll2d_try_2:
 lsrs r3,r1,#22
 beq .Ll2d_try_1
 l2d_right 2
.Ll2d_try_1:
 l2d_right 1
.size __aeabi_ul2d,.-__aeabi_ul2d
.size __aeabi_l2d,.-__aeabi_l2d
.ltorg


#endif
