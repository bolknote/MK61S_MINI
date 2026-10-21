@ SPDX-License-Identifier: GPL-2.0-only
@ Derived from Mark Owen's Qfplib-M0-full logarithm (2019-2020).
@ MK61S experiment, 2026-10-21. Unrolled Q62 reductions, compensated at Q82.
@ Positive finite nonzero inputs only. Output: signed96 Q82 and error65536.

.macro lncomp_step number,low,high,delta
 lsrs r5,r1,#\number
 lsls r4,r1,#(32-\number)
 lsrs r6,r0,#\number
 orrs r4,r6
 adcs r4,r0
 adcs r5,r1
 lsrs r6,r5,#30
 bne .Llncomp_next\@
 @ The signed discarded fraction is precisely minus the rounding error.
 lsls r6,r0,#(32-\number)
 asrs r6,#12                   @ -rounding_error, Q20
 movs r0,r4
 movs r1,r5
 lsrs r4,r1,#21
 lsls r4,#1
 ldrh r4,[r7,r4]               @ reciprocal of the updated x, Q10
 muls r6,r4
 asrs r6,#10
 add r8,r6
 adr r4,.Llncomp_row\@
 ldmia r4,{r4,r5,r6}
 subs r2,r4
 sbcs r3,r5
 add r8,r6                    @ restore the discarded logarithm bits
 b .Llncomp_next\@
.align 2
.Llncomp_row\@:
 .word \low,\high,\delta
.Llncomp_next\@:
.if \number == 9
 b .Llncomp_pool\@
 .ltorg
.Llncomp_pool\@:
.endif
.endm

.align 2
.global qfp_ln_comp96
.thumb_func
qfp_ln_comp96:
 push {r4-r7,lr}
 mov r3,r8
 push {r2,r3}                  @ result pointer, saved r8
 lsrs r3,r1,#20
 beq .Llncomp_subnormal
 bl dunpacks
 b .Llncomp_mantissa
.Llncomp_subnormal:
 ldr r2,=-1022
.Llncomp_normalize:
 lsls r0,#1
 adcs r1,r1
 subs r2,#1
 lsrs r3,r1,#20
 beq .Llncomp_normalize
.Llncomp_mantissa:
 push {r2}                     @ unbiased exponent
 lsls r1,#9
 lsrs r2,r0,#23
 orrs r1,r2
 lsls r0,#9
 movs r2,#0
 movs r3,#0
 mov r8,r3
 ldr r7,=.Llncomp_recip-768
 lncomp_steps

 push {r2,r3}                  @ logarithm accumulator, Q62
 movs r4,#1
 lsls r4,#30
 rsbs r0,r0,#0
 sbcs r4,r1                    @ D=1-x, 0<D<2^44
 push {r0,r4}
 @ Exact floor(D^2/2^43), the quadratic term in Q82.
 square32_64 r0,r0,r1,r2,r3,r5
 ldr r0,[sp]
 uxth r2,r0
 muls r2,r4
 lsrs r3,r0,#16
 muls r3,r4
 lsls r5,r3,#17
 lsrs r6,r3,#15
 lsls r2,#1
 adds r5,r2
 movs r2,#0
 adcs r6,r2
 adds r5,r1
 adcs r6,r2
 muls r4,r4
 adds r6,r4
 lsrs r5,#11
 lsls r4,r6,#21
 orrs r5,r4
 lsrs r6,#11
 push {r5,r6}

 @ Cubic at Q82: A=round(D/2^32), floor(A^3/(3*256)).
 ldr r0,[sp,#8]
 ldr r4,[sp,#12]
 lsrs r0,#31
 adds r4,r0
 movs r2,r4
 muls r2,r4
 uxth r3,r2
 muls r3,r4
 lsrs r2,#16
 muls r2,r4
 lsrs r3,#8
 lsls r2,#8
 adds r2,r3                    @ floor(A^3/256), <=2^28
 @ Exact /3 with two narrow MULS: 0xAAAAAAAB low16 = high16+1.
 uxth r3,r2
 lsrs r4,r2,#16
 ldr r5,=0xAAAA
 muls r3,r5
 muls r4,r5
 uxth r6,r2
 adds r6,r3
 lsrs r6,#16
 lsrs r2,#16
 adds r6,r2
 adds r6,r3
 adds r6,r4
 lsrs r6,#16
 adds r6,r4
 lsrs r6,#1
 pop {r4,r5}
 adds r4,r6
 movs r6,#0
 adcs r5,r6                    @ quadratic+cubic, Q82
 ldr r0,[sp]
 ldr r1,[sp,#4]
 ldr r2,[sp,#8]
 ldr r3,[sp,#12]
 subs r2,r0
 sbcs r3,r1                    @ y-D, Q62
 str r4,[sp]
 str r5,[sp,#4]                @ residual polynomial kept for final subtraction

 ldr r7,[sp,#16]
 adds r7,#1
 ldr r5,=lncomp_delta2
 muls r5,r7
 mov r6,r8
 subs r6,r5
 mov r8,r6
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
 @ Convert the exact signed96 linear result Q62->Q82.
 lsrs r2,r0,#12
 lsls r0,#20
 lsrs r3,r1,#12
 lsls r1,#20
 orrs r1,r2
 lsls r4,#20
 orrs r4,r3
 mov r5,r8
 asrs r6,r5,#31
 adds r0,r5
 adcs r1,r6
 adcs r4,r6
 ldr r5,[sp]
 ldr r6,[sp,#4]
 movs r7,#0
 subs r0,r5
 sbcs r1,r6
 sbcs r4,r7
 ldr r6,[sp,#20]
 stmia r6!,{r0,r1,r4}
 movs r0,#1
 lsls r0,#16
 str r0,[r6]
 add sp,#24
 pop {r3}
 mov r8,r3
 pop {r4-r7,pc}
.ltorg
lncomp_reciprocal_data
