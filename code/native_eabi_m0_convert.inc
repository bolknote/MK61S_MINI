// Project-owned Thumb-1 EABI conversions and IEEE comparisons.
// Keep both integer widths in one section: small int64 magnitudes enter
// the existing exact int32 normalizer without an extra call or stack frame.
.section .text.__aeabi_i2d,"ax",%progbits
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
#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
 // A negative input has nonzero magnitude: skip the unsigned zero test.
 mov r1,r2
 b .Li2d_normalize
#else
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

function __aeabi_f2d
 asrs r1,r0,#31
 lsls r1,#31
 lsls r2,r0,#1
 lsrs r3,r2,#24
 subs r3,#1
 cmp r3,#253
 bhi .Lf2d_slow
 lsrs r2,#4
 adds r1,r2
 ldr r2,=0x38000000
 adds r1,r2
 lsls r0,#29
 bx lr
.Lf2d_slow:
 push {r4,lr}
 bl mk61_m0_f2d_slow
 pop {r4,pc}
.ltorg
end __aeabi_f2d

function __aeabi_d2f
 lsls r2,r1,#1
 lsrs r2,#21
 ldr r3,=897
 subs r2,r3
 cmp r2,#253
 bhi .Ld2f_slow
 // Keep discarded guard/sticky bits while packing the retained value.
 // Half of normal inputs skip the rounding arithmetic entirely.
 lsls r3,r0,#4
 lsrs r0,#29
 bcc .Ld2f_pack
 cmp r3,#0
 beq .Ld2f_tie
 adds r0,#1
.Ld2f_pack:
 lsrs r2,r1,#31
 lsls r2,#31
 lsls r1,#4
 lsrs r1,#1
 ldr r3,=0x40000000
 eors r1,r3
 adds r0,r1
 orrs r0,r2
 bx lr
.Ld2f_tie:
 lsrs r3,r0,#1
 movs r3,#0
 adcs r0,r3
 b .Ld2f_pack
.Ld2f_slow:
 push {r4,lr}
 bl mk61_m0_d2f_slow
 pop {r4,pc}
.ltorg
end __aeabi_d2f

function __aeabi_dcmpeq
 eors r0,r2
 eors r1,r3
 cmp r0,#0
 bne .Ldeq_false
 cmp r1,#0
 beq .Ldeq_same
 // Only opposite zero signs can compare equal with different bits.
 lsls r1,#1
 orrs r0,r1
 bne .Ldeq_false
 lsls r3,#1
 orrs r3,r2
 bne .Ldeq_false
 b .Ldeq_true
.Ldeq_same:
 lsls r3,#1
 ldr r1,=0xffe00000
 cmp r3,r1
 blo .Ldeq_true
 bhi .Ldeq_false
 cmp r2,#0
 bne .Ldeq_false
.Ldeq_true:
 movs r0,#1
 bx lr
.Ldeq_false:
 movs r0,#0
 bx lr
.ltorg
end __aeabi_dcmpeq

// Compare magnitudes after rejecting NaNs. Different signs are ordered
// directly (except both zeros); equal negative signs reverse magnitude.
.macro double_compare name,less,equal,greater
function \name
 push {r4,r5,lr}
 mov r12,r2
 lsls r4,r1,#1
 lsls r5,r3,#1
 ldr r2,=0xffe00000
 cmp r4,r2
 bhi .L\name\()_nan
 bne 1f
 cmp r0,#0
 bne .L\name\()_nan
1:
 cmp r5,r2
 bhi .L\name\()_nan
 bne 1f
 mov r2,r12
 cmp r2,#0
 bne .L\name\()_nan
1:
 mov r2,r12
 eors r1,r3
 bmi .L\name\()_mixed
 cmp r4,r5
 bhi .L\name\()_mag_greater
 blo .L\name\()_mag_less
 cmp r0,r2
 bhi .L\name\()_mag_greater
 blo .L\name\()_mag_less
 b .L\name\()_equal
.L\name\()_mag_less:
 cmp r3,#0
 bmi .L\name\()_greater
 b .L\name\()_less
.L\name\()_mag_greater:
 cmp r3,#0
 bmi .L\name\()_less
 b .L\name\()_greater
.L\name\()_mixed:
 orrs r4,r5
 orrs r4,r0
 orrs r4,r2
 beq .L\name\()_equal
 cmp r3,#0
 bpl .L\name\()_less
.L\name\()_greater:
 movs r0,#\greater
 pop {r4,r5,pc}
.L\name\()_less:
 movs r0,#\less
 pop {r4,r5,pc}
.L\name\()_equal:
 movs r0,#\equal
 pop {r4,r5,pc}
.L\name\()_nan:
 movs r0,#0
 pop {r4,r5,pc}
.ltorg
end \name
.endm
double_compare __aeabi_dcmplt,1,0,0
double_compare __aeabi_dcmple,1,1,0
double_compare __aeabi_dcmpge,0,1,1
double_compare __aeabi_dcmpgt,0,0,1

function __aeabi_dcmpun
 push {r4,lr}
 mov r12,r2
 ldr r4,=0xffe00000
 lsls r2,r1,#1
 cmp r2,r4
 bhi .Ldun_true
 bne 1f
 cmp r0,#0
 bne .Ldun_true
1:
 lsls r2,r3,#1
 cmp r2,r4
 bhi .Ldun_true
 bne .Ldun_false
 mov r2,r12
 cmp r2,#0
 bne .Ldun_true
.Ldun_false:
 movs r0,#0
 pop {r4,pc}
.Ldun_true:
 movs r0,#1
 pop {r4,pc}
.ltorg
end __aeabi_dcmpun

function __aeabi_d2iz
 lsls r2,r1,#1
 lsrs r2,#21
 ldr r3,=1023
 subs r2,r3
 bmi .Ld2i_zero
 cmp r2,#30
 bhi .Ld2i_slow
 lsrs r3,r1,#31
 mov r12,r3
 lsls r1,#12
 lsrs r1,#12
 movs r3,#1
 lsls r3,#20
 orrs r1,r3
 cmp r2,#20
 bhi .Ld2i_wide
 movs r3,#20
 subs r3,r2
 lsrs r1,r3
 mov r0,r1
 b .Ld2i_sign
.Ld2i_wide:
 movs r3,#52
 subs r3,r2
 lsrs r0,r3
 subs r2,#20
 lsls r1,r2
 orrs r0,r1
.Ld2i_sign:
 mov r3,r12
 cmp r3,#0
 beq 1f
 rsbs r0,r0,#0
1:
 bx lr
.Ld2i_zero:
 movs r0,#0
 bx lr
.Ld2i_slow:
 push {r4,lr}
 bl mk61_m0_d2iz_slow
 pop {r4,pc}
.ltorg
end __aeabi_d2iz

function __aeabi_d2lz
 lsls r2,r1,#1
 lsrs r2,#21
 ldr r3,=1023
 subs r2,r3
 bmi .Ld2l_zero
 cmp r2,#63
 bhi .Ld2l_slow
 lsrs r3,r1,#31
 mov r12,r3
 lsls r1,#12
 lsrs r1,#12
 movs r3,#1
 lsls r3,#20
 orrs r1,r3
 cmp r2,#52
 bhs .Ld2l_left
 cmp r2,#20
 blo .Ld2l_high_only
 movs r3,#52
 subs r3,r2
 lsrs r0,r3
 subs r2,#20
 mov r3,r1
 lsls r3,r2
 orrs r0,r3
 movs r3,#32
 subs r3,r2
 lsrs r1,r3
 b .Ld2l_sign
.Ld2l_high_only:
 movs r3,#20
 subs r3,r2
 lsrs r1,r3
 mov r0,r1
 movs r1,#0
 b .Ld2l_sign
.Ld2l_left:
 subs r2,#52
 mov r3,r0
 lsls r1,r2
 lsls r0,r2
 rsbs r2,r2,#0
 adds r2,#32
 lsrs r3,r2
 orrs r1,r3
 b .Ld2l_sign
.Ld2l_zero:
 movs r0,#0
 movs r1,#0
 bx lr
.Ld2l_slow:
 push {r4,lr}
 bl mk61_m0_d2lz_slow
 pop {r4,pc}
.Ld2l_sign:
 mov r3,r12
 cmp r3,#0
 beq 1f
 rsbs r0,r0,#0
 mvns r1,r1
 movs r3,#0
 adcs r1,r3
1:
 bx lr
.ltorg
end __aeabi_d2lz

function __aeabi_d2ulz
 cmp r1,#0
 bmi .Ld2ul_zero
 lsrs r2,r1,#20
 ldr r3,=1023
 subs r2,r3
 bmi .Ld2ul_zero
 cmp r2,#63
 bhi .Ld2ul_slow
 lsls r1,#12
 lsrs r1,#12
 movs r3,#1
 lsls r3,#20
 orrs r1,r3
 cmp r2,#52
 bhs .Ld2ul_left
 cmp r2,#20
 blo .Ld2ul_high_only
 movs r3,#52
 subs r3,r2
 lsrs r0,r3
 subs r2,#20
 mov r3,r1
 lsls r3,r2
 orrs r0,r3
 movs r3,#32
 subs r3,r2
 lsrs r1,r3
 bx lr
.Ld2ul_high_only:
 movs r3,#20
 subs r3,r2
 lsrs r1,r3
 mov r0,r1
 movs r1,#0
 bx lr
.Ld2ul_left:
 subs r2,#52
 mov r3,r0
 lsls r1,r2
 lsls r0,r2
 rsbs r2,r2,#0
 adds r2,#32
 lsrs r3,r2
 orrs r1,r3
 bx lr
.Ld2ul_zero:
 movs r0,#0
 movs r1,#0
 bx lr
.Ld2ul_slow:
 push {r4,lr}
 bl mk61_m0_d2ulz_slow
 pop {r4,pc}
.ltorg
end __aeabi_d2ulz
