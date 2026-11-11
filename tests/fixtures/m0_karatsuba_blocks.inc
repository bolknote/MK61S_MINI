// Test-only replacements for the normal binary64 mantissa product.
// Inputs on the44-byte frame: a0,a1,b0,b1 at0,4,8,12. a1,b1<2^21.
// Outputs match production: r12=w0, r3=w1, r0=w2, r2=w3.
// The exponent/sign words at16/20 and the existing rounding code are intact.
.macro kara_difference
 product32
 mov r12,r0
 str r2,[sp,#28]
 ldr r0,[sp,#4]
 ldr r2,[sp,#12]
 product32
 str r0,[sp,#32]
 str r2,[sp,#36]
 movs r1,#0
 ldr r0,[sp,#0]
 ldr r4,[sp,#4]
 subs r0,r0,r4
 bcs .Ldifference_a_\@
 rsbs r0,r0,#0
 movs r1,#1
.Ldifference_a_\@:
 ldr r2,[sp,#8]
 ldr r4,[sp,#12]
 subs r2,r2,r4
 bcs .Ldifference_b_\@
 rsbs r2,r2,#0
 movs r4,#1
 eors r1,r4
.Ldifference_b_\@:
 str r1,[sp,#40]
 product32
 str r0,[sp,#0]
 str r2,[sp,#4]
 mov r0,r12
 ldr r2,[sp,#28]
 ldr r4,[sp,#32]
 ldr r5,[sp,#36]
 adds r0,r0,r4
 adcs r2,r5
 ldr r4,[sp,#0]
 ldr r5,[sp,#4]
 ldr r6,[sp,#40]
 cmp r6,#0
 bne .Ldifference_add_\@
 subs r0,r0,r4
 sbcs r2,r5
 b .Ldifference_join_\@
.Ldifference_add_\@:
 adds r0,r0,r4
 adcs r2,r5
.Ldifference_join_\@:
 // Cross term is <2^54. Its modular64-bit reconstruction is exact even
 // when z0+z2 above wraps; no65th cross bit is required for53-bit inputs.
 ldr r4,[sp,#28]
 movs r5,#0
 adds r3,r0,r4
 adcs r2,r5
 ldr r0,[sp,#32]
 ldr r4,[sp,#36]
 adds r0,r0,r2
 adcs r4,r5
 mov r2,r4
.endm

.macro kara_sum_guarded
 // A low32-bit limb plus its high21-bit limb normally fits32 bits. If
 // either addition carries, use the unchanged production product block.
 adds r0,r0,r1
 bcs .Lsum_full_\@
 adds r2,r2,r3
 bcs .Lsum_full_\@
 product32
 str r0,[sp,#36]
 str r2,[sp,#40]
 ldr r0,[sp,#0]
 ldr r2,[sp,#8]
 product32
 mov r12,r0
 str r2,[sp,#28]
 ldr r0,[sp,#4]
 ldr r2,[sp,#12]
 product32
 str r0,[sp,#32]
 str r2,[sp,#24]
 ldr r0,[sp,#36]
 ldr r2,[sp,#40]
 mov r4,r12
 ldr r5,[sp,#28]
 subs r0,r0,r4
 sbcs r2,r5
 ldr r4,[sp,#32]
 ldr r5,[sp,#24]
 subs r0,r0,r4
 sbcs r2,r5
 ldr r4,[sp,#28]
 movs r5,#0
 adds r3,r0,r4
 adcs r2,r5
 ldr r0,[sp,#32]
 ldr r4,[sp,#24]
 adds r0,r0,r2
 adcs r4,r5
 mov r2,r4
 b .Lsum_join_\@
.Lsum_full_\@:
 ldr r0,[sp,#0]
 ldr r1,[sp,#4]
 ldr r2,[sp,#8]
 ldr r3,[sp,#12]
 baseline_product53
.Lsum_join_\@:
.endm
