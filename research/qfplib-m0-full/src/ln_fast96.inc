@ SPDX-License-Identifier: GPL-2.0-only
@ Derived from Mark Owen's Qfplib-M0-full qfp_dln (2019-2020).
@ MK61S experiment, 2026-10-21: 20 greedy steps, bounded quadratic tail,
@ exact signed 96-bit Q62 result and an absolute error bound. Positive finite
@ nonzero inputs only. This is a research entry, not a firmware replacement.

.global qfp_ln_fast96
.thumb_func
qfp_ln_fast96:
 push {r4-r7,lr}
 push {r2}                      @ output[4]
 lsrs r3,r1,#20
 beq .Lln96_subnormal
 bl dunpacks
 b .Lln96_mantissa
.Lln96_subnormal:
 ldr r2,=-1022
.Lln96_normalize:
 lsls r0,#1
 adcs r1,r1
 subs r2,#1
 lsrs r3,r1,#20
 beq .Lln96_normalize
.Lln96_mantissa:
 push {r2}
 lsls r1,#9
 lsrs r2,r0,#23
 orrs r1,r2
 lsls r0,#9
 movs r7,#1
 ldr r6,=dtab_exp
 mov r12,r6
 movs r2,#0
 movs r3,#0
.Lln96_loop:
 rsbs r6,r7,#0
 adds r6,#32
 movs r5,r1
 asrs r5,r7
 movs r4,r1
 lsls r4,r6
 movs r6,r0
 lsrs r6,r7
 orrs r4,r6
 adcs r4,r0
 adcs r5,r1
 lsrs r6,r5,#30
 bne .Lln96_reject
 movs r0,r4
 movs r1,r5
 mov r6,r12
 ldmia r6!,{r4,r5}
 subs r2,r4
 sbcs r3,r5
.Lln96_reject:
 movs r4,#8
 add r12,r4
 adds r7,#1
 cmp r7,#21
 bne .Lln96_loop

 @ D=1-x in Q62, 0<D<2^42. A=ceil(D/2^23) fits 20 bits.
 @ K=high16(A)^2*2^15 + high16(A)*low16(A)
 @   + floor(low16(A)^2/2^17) + 1 approximates D^2/2^63
 @ from above, by <9 Q62 units. The cubic tail is <1.334 Q62.
 lsls r4,r1,#9
 lsrs r5,r0,#23
 orrs r4,r5
 rsbs r4,r4,#0
 lsls r5,r4,#16
 lsrs r5,#16
 lsrs r6,r4,#16
 movs r7,r6
 muls r7,r6
 lsls r7,#15
 muls r6,r5
 adds r7,r6
 muls r5,r5
 lsrs r5,#17
 adds r7,r5
 adds r7,#1
 movs r4,#0
 subs r0,r7
 sbcs r1,r4
 lsls r1,#2
 asrs r1,#2
 adds r2,r0
 adcs r3,r1

 pop {r7}                      @ unbiased exponent
 adds r7,#1
 movs r5,r7
 asrs r6,r5,#31
 eors r5,r6
 subs r5,r6
 adds r5,#1
 lsrs r5,#1
 adds r5,#64                   @ error64 + ceil(|e+1|/2), Q62
 ldr r6,[sp]
 str r5,[r6,#12]
 ldr r4,=dreddata1+4
 ldmia r4,{r0,r1,r4}
 muls r0,r7
 muls r1,r7
 muls r4,r7
 lsls r7,r1,#21
 asrs r1,#11
 asrs r5,r1,#31
 adds r0,r7
 adcs r1,r5
 lsls r7,r4,#10
 asrs r4,#22
 asrs r5,r1,#31
 adds r1,r7
 adcs r4,r5
 asrs r5,r3,#31
 adds r0,r2
 adcs r1,r3
 adcs r4,r5
 pop {r6}
 str r0,[r6,#0]
 str r1,[r6,#4]
 str r4,[r6,#8]
 pop {r4-r7,pc}
.ltorg
