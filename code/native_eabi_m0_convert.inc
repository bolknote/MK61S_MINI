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
 b .Ll2d_magnitude
.global __aeabi_ul2d
.type __aeabi_ul2d,%function
.thumb_func
__aeabi_ul2d:
 movs r2,#0
.Ll2d_magnitude:
 cmp r1,#0
 bne .Ll2d_high
 mov r1,r2
 cmp r0,#0
 bne .Li2d_normalize
 bx lr
.Ll2d_high:
 mov r12,r2
 ldr r2,=1085
 cmp r1,#0
 bmi .Ll2d_round
 adds r0,r0
 adcs r1,r1
 subs r2,#1
 cmp r1,#0
 bmi .Ll2d_round
 adds r0,r0
 adcs r1,r1
 subs r2,#1
 cmp r1,#0
 bmi .Ll2d_round
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
 l2d_chunk 16
 l2d_chunk 8
 l2d_chunk 4
 l2d_chunk 2
 cmp r1,#0
 bmi .Ll2d_round
 adds r0,r0
 adcs r1,r1
 subs r2,#1
.Ll2d_round:
 // C is the retained quotient's parity. LDR preserves it; adding
 // half-1+C implements nearest-even, including a carry across 64 bits.
 lsrs r3,r0,#12
 ldr r3,=1023
 adcs r0,r3
 movs r3,#0
 adcs r1,r3
 bcc 1f
 movs r1,#1
 lsls r1,#31
 adds r2,#1
1:
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
 // Normal binary32 results discard 29 bits; preserve ties and carry.
 lsrs r3,r0,#30
 ldr r3,=0x0fffffff
 adcs r0,r3
 movs r3,#0
 adcs r1,r3
 lsrs r2,r1,#31
 lsls r2,#31
 lsls r1,#4
 lsrs r1,#1
 ldr r3,=0x40000000
 eors r1,r3
 lsrs r0,#29
 orrs r0,r1
 orrs r0,r2
 bx lr
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
